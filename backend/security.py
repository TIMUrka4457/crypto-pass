"""Request hardening (rate limits, headers) and anomaly watch (ledger mismatch, brute force, outflow spikes)."""
import time
from datetime import timedelta
from decimal import Decimal

from fastapi import Request
from fastapi.responses import JSONResponse

from core import db, now, log, get_settings, ASSETS

LIMITS = [("/api/admin/auth", 10), ("/api/p/", 10), ("/api/auth/telegram", 30), ("/api/v1/", 300), ("/api/", 180)]


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "")


async def guard_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path != "/api/health":
        limit = next(n for p, n in LIMITS if path.startswith(p))
        bucket = next(p for p, n in LIMITS if path.startswith(p))
        key = f"ip:{client_ip(request)}:{bucket}:{int(time.time() // 60)}"
        r = await db.rate.find_one_and_update({"_id": key}, {"$inc": {"n": 1}, "$setOnInsert": {"at": now()}},
                                              upsert=True, return_document=True)
        if r["n"] > limit:
            if r["n"] == limit + 1:
                await db.security_events.insert_one({"kind": "rate_limit", "ip": client_ip(request), "path": bucket, "at": now()})
            return JSONResponse({"detail": "Слишком много запросов, подождите минуту"}, status_code=429)
        if int(request.headers.get("content-length") or 0) > 256_000:
            return JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


async def _alert(key: str, text: str):
    """Send once per key (dedupe in db)."""
    if await db.security_events.find_one({"_id": key}):
        return
    await db.security_events.insert_one({"_id": key, "kind": "alert", "text": text, "at": now()})
    log.warning("SECURITY: %s", text)
    try:
        import admin_bot
        await admin_bot._notify("Безопасность: " + text)
    except Exception as e:
        log.info("security notify failed: %s", e)


async def watch():
    s = await get_settings()
    hour = now().strftime("%Y%m%d%H")
    rec = await db.hot_wallet.find_one({"_id": "reconcile"}) or {}
    if rec and rec.get("ok") is False and not s["security"]["withdrawals_paused"]:
        await db.settings.update_one({"_id": "global"}, {"$set": {"security.withdrawals_paused": True}}, upsert=True)
        await _alert(f"recon:{hour}", "сверка журнала не сошлась — выводы автоматически поставлены на паузу. "
                                      "Проверьте «Журнал» и снимите паузу в настройках.")
    locks = await db.login_attempts.count_documents({"locked_until": {"$gt": now()}})
    if locks:
        await _alert(f"brute:{hour}", f"заблокировано попыток входа в админку: {locks} (перебор пароля).")
    floods = await db.security_events.count_documents({"kind": "rate_limit", "at": {"$gt": now() - timedelta(minutes=10)}})
    if floods >= 5:
        await _alert(f"flood:{hour}", f"{floods} IP превысили лимит запросов за 10 минут — возможна атака.")
    import fees
    r = await fees.rates()
    if r:
        usd = Decimal(0)
        async for w in db.withdrawals.find({"created_at": {"$gt": now() - timedelta(hours=1)}, "status": {"$nin": ["rejected", "failed"]}}):
            p = Decimal(1) if w["asset"].startswith("USDT") else r["TON"]
            usd += Decimal(w["amount"]) / Decimal(10 ** ASSETS[w["asset"]]["decimals"]) * p
        if usd > Decimal(str(s["security"]["outflow_alert_usd"])):
            await _alert(f"outflow:{hour}", f"выводы за последний час: ${usd:.0f} — выше порога ${s['security']['outflow_alert_usd']}.")
    async for u in db.withdrawals.aggregate([{"$match": {"created_at": {"$gt": now() - timedelta(minutes=10)}}},
                                             {"$group": {"_id": "$user_id", "n": {"$sum": 1}}}, {"$match": {"n": {"$gte": 5}}}]):
        await _alert(f"velo:{u['_id']}:{hour}", f"пользователь {u['_id']} создал {u['n']} выводов за 10 минут.")
