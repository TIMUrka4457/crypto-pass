import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt

from core import db, now, new_id, code, bad, to_units, fmt, ASSETS, get_settings, check_asset
from auth import make_token, read_token
from ledger import post, txn, acct, Insufficient
from services import notify

# Telegram does not expose registration date; estimate it from the monotonically growing user id.
_ID_DATES = [(0, 2013.6), (1e8, 2015.2), (3e8, 2017.0), (5e8, 2018.0), (1e9, 2019.8), (1.5e9, 2020.95),
             (2e9, 2021.45), (5e9, 2021.95), (6e9, 2023.2), (7e9, 2024.2), (8e9, 2025.1), (9e9, 2026.0)]


def account_age_days(tg_id: int) -> int:
    pts = _ID_DATES
    y = pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if tg_id <= x1:
            y = y0 + (y1 - y0) * (tg_id - x0) / (x1 - x0)
            break
    year = int(y)
    est = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=(y - year) * 365)
    return max(0, (now() - est).days)


async def create_check(user: dict, body: dict) -> dict:
    asset = body["asset"]
    check_asset(asset)
    kind = body.get("kind", "personal")
    per = to_units(asset, body["amount"])
    n = 1 if kind == "personal" else int(body.get("activations") or 0)
    if n < 1 or n > 10000:
        bad("Количество активаций от 1 до 10000")
    total = per * n
    channels = [c.strip() if c.strip().startswith("@") else "@" + c.strip()
                for c in (body.get("channels") or []) if c.strip()]
    pw = (body.get("password") or "").strip()
    exp_h = body.get("expires_in_hours")
    doc = {"_id": new_id("chk_"), "code": code(14), "creator_id": user["_id"], "asset": asset, "kind": kind,
           "amount_per": per, "activations": n, "remaining": n, "activated_by": [],
           "bind_username": ((body.get("bind_username") or "").strip().lstrip("@").lower() or None) if kind == "personal" else None,
           "password_hash": bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode() if pw else None,
           "captcha": bool(body.get("captcha")) if kind == "multi" else False,
           "channels": channels[:5] if kind == "multi" else [],
           "min_account_age_days": int(body.get("min_account_age_days") or 0) if kind == "multi" else 0,
           "description": (body.get("description") or "")[:300], "status": "active", "created_at": now(),
           "expires_at": now() + timedelta(hours=float(exp_h)) if exp_h else None}

    async def fn(s):
        await db.checks.insert_one(doc, session=s)
        await post(s, "check_create", [(acct(user["_id"]), asset, -total), (f"chk:{doc['_id']}", asset, total)],
                   idem=f"chkc:{doc['_id']}", ref=doc["_id"])
    try:
        await txn(fn)
    except Insufficient:
        bad("Недостаточно средств")
    return doc


def public_check(c: dict, bot_username: str | None, owner: bool) -> dict:
    out = {"id": c["_id"], "code": c["code"], "asset": c["asset"], "kind": c["kind"],
           "amount": fmt(c["asset"], c["amount_per"]), "activations": c["activations"], "remaining": c["remaining"],
           "status": c["status"], "description": c["description"], "has_password": bool(c.get("password_hash")),
           "captcha": c.get("captcha", False), "channels": c.get("channels", []),
           "min_account_age_days": c.get("min_account_age_days", 0), "bind_username": c.get("bind_username"),
           "expires_at": c["expires_at"].isoformat() if c.get("expires_at") else None,
           "created_at": c["created_at"].isoformat(),
           "link": f"https://t.me/{bot_username}?start=c_{c['code']}" if bot_username else None}
    if not owner:
        out.pop("bind_username")
    return out


def captcha_for(check_code: str) -> dict:
    import secrets
    a, b = secrets.randbelow(9) + 1, secrets.randbelow(9) + 1
    h = hashlib.sha256(f"{a + b}:{check_code}".encode()).hexdigest()
    return {"question": f"{a} + {b} = ?", "token": make_token({"typ": "captcha", "h": h, "c": check_code}, 1)}


async def _rate_limit(uid: str):
    s = await get_settings()
    minute = now().strftime("%Y%m%d%H%M")
    r = await db.rate.find_one_and_update({"_id": f"claim:{uid}:{minute}"},
                                          {"$inc": {"n": 1}, "$setOnInsert": {"at": now()}}, upsert=True,
                                          return_document=True)
    if r["n"] > int(s["check_claims_per_minute"]):
        bad("Слишком много попыток, подождите минуту", 429)


async def claim_check(user: dict, check_code: str, body: dict) -> dict:
    await _rate_limit(user["_id"])
    c = await db.checks.find_one({"code": check_code})
    if not c or c["status"] != "active":
        bad("Чек не найден или уже не активен", 404)
    if c["creator_id"] == user["_id"]:
        bad("Нельзя активировать свой чек")
    if c.get("expires_at") and c["expires_at"].replace(tzinfo=timezone.utc) < now():
        bad("Срок действия чека истёк", 409)
    if c.get("bind_username") and (user.get("username") or "") != c["bind_username"]:
        bad("Этот чек предназначен другому пользователю", 403)
    if c.get("password_hash"):
        pw = (body.get("password") or "").encode()
        if not bcrypt.checkpw(pw, c["password_hash"].encode()):
            bad("Неверный пароль", 403)
    if c.get("captcha"):
        try:
            d = read_token(body.get("captcha_token") or "", "captcha")
        except Exception:
            bad("Пройдите капчу заново", 403)
        if d.get("c") != check_code or d["h"] != hashlib.sha256(f"{str(body.get('captcha_answer', '')).strip()}:{check_code}".encode()).hexdigest():
            bad("Неверный ответ капчи", 403)
    if c.get("min_account_age_days") and account_age_days(user["tg_id"]) < c["min_account_age_days"]:
        bad("Аккаунт слишком новый для этого чека", 403)
    if c.get("channels"):
        import bot
        for ch in c["channels"]:
            if not await bot.is_member(ch, user["tg_id"]):
                bad(f"Подпишитесь на {ch} и попробуйте снова", 403)

    async def fn(s):
        upd = await db.checks.find_one_and_update(
            {"_id": c["_id"], "status": "active", "remaining": {"$gt": 0}, "activated_by": {"$ne": user["_id"]}},
            {"$inc": {"remaining": -1}, "$push": {"activated_by": user["_id"]}}, return_document=True, session=s)
        if not upd:
            bad("Чек уже активирован или закончился", 409)
        if upd["remaining"] == 0:
            await db.checks.update_one({"_id": c["_id"]}, {"$set": {"status": "done"}}, session=s)
        await post(s, "check_claim", [(f"chk:{c['_id']}", c["asset"], -c["amount_per"]),
                                      (acct(user["_id"]), c["asset"], c["amount_per"])],
                   idem=f"chkx:{c['_id']}:{user['_id']}", ref=c["_id"], meta={"claimer": user["_id"]})
    await txn(fn)
    notify(c["creator_id"], f"Ваш чек активировал @{user.get('username') or user['_id']}")
    return {"status": "claimed", "amount": fmt(c["asset"], c["amount_per"]), "asset": c["asset"]}


async def close_check(check_id: str, new_status: str, by_creator: str | None = None, admin: dict = None, comment: str = ""):
    """Cancel/expire: returns the locked remainder to the creator atomically."""
    flt = {"_id": check_id, "status": "active"}
    if by_creator:
        flt["creator_id"] = by_creator

    async def fn(s):
        c = await db.checks.find_one_and_update(flt, {"$set": {"status": new_status, "closed_at": now()}}, session=s)
        if not c:
            bad("Чек не найден или уже закрыт", 404)
        left = c["remaining"] * c["amount_per"]
        if left:
            await post(s, "check_refund", [(f"chk:{c['_id']}", c["asset"], -left), (acct(c["creator_id"]), c["asset"], left)],
                       idem=f"chkr:{c['_id']}", ref=c["_id"], meta={"reason": new_status})
        if admin:
            from auth import audit
            await audit(admin, "check_force_cancel", c["_id"], {"refund": fmt(c["asset"], left)}, comment, session=s)
        return c, left
    c, left = await txn(fn)
    if left:
        notify(c["creator_id"], f"Чек {'истёк' if new_status == 'expired' else 'отменён'}: возвращено "
                                f"{fmt(c['asset'], left)} {ASSETS[c['asset']]['title']}")
    return {"status": new_status, "refunded": fmt(c["asset"], left)}
