"""Background jobs. Each loop holds a Mongo lease so only one backend instance runs it."""
import asyncio
import time
import uuid
from datetime import timedelta
from decimal import Decimal

import httpx
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import aml
import chains
import signer_client
from chains import ProviderDown
from core import db, now, new_id, log, ASSETS, NETWORKS, get_settings, fmt
from services import (complete_withdrawal, refund_withdrawal, credit_deposit, notify, units0, sign_webhook)
from ledger import txn, reconcile

INSTANCE = uuid.uuid4().hex


async def lease(name: str, seconds: int) -> bool:
    try:
        r = await db.locks.find_one_and_update(
            {"_id": name, "$or": [{"owner": INSTANCE}, {"until": {"$lt": now()}}]},
            {"$set": {"owner": INSTANCE, "until": now() + timedelta(seconds=seconds)}}, upsert=True,
            return_document=ReturnDocument.AFTER)
        return r["owner"] == INSTANCE
    except DuplicateKeyError:
        return False


async def _status(network: str, tx_hash: str) -> str:
    return await (chains.ton_status(tx_hash) if network == "ton" else chains.tron_status(tx_hash))


async def _broadcast(network: str, payload: str):
    await (chains.ton_broadcast(payload) if network == "ton" else chains.tron_broadcast(payload))


async def _sign_outbound(network: str, asset: str, from_index: int, from_addr: str, to: str, amount: int,
                         sweep_all: bool = False) -> dict:
    if network == "ton":
        seqno = await chains.ton_seqno(from_addr)
        req = {"network": "ton", "from_index": from_index, "to": to, "amount": amount, "seqno": seqno}
        if asset == "USDT_TON":
            req["jetton_wallet"] = await chains.ton_jetton_wallet_of(from_addr)
            req["gas"] = 50_000_000
        elif sweep_all:
            req["sweep_all"] = True
        return await signer_client.sign(req)
    if asset == "USDT_TRC20":
        tx = await chains.tron_build_trc20(from_addr, to, amount)
    else:
        tx = await chains.tron_build_trx(from_addr, to, amount)
    return await signer_client.sign({"network": "tron", "from_index": from_index, "to": to, "unsigned_tx": tx})


async def _ton_hot_busy() -> bool:
    busy = {"$in": ["broadcasting", "sent", "unknown", "signing"]}
    return bool(await db.withdrawals.find_one({"network": "ton", "status": busy}) or
                await db.sweeps.find_one({"network": "ton", "from_index": 0, "status": busy}))


# ---------------- deposits ----------------
async def scan_deposits():
    s = await get_settings()
    cursor = db.deposit_addresses.find({}).sort("last_scan", 1).limit(60)
    async for a in cursor:
        net = a["network"]
        if not s["networks"][net]["enabled"]:
            continue
        try:
            txs = await (chains.ton_incoming(a["address"]) if net == "ton" else chains.tron_incoming(a["address"]))
        except ProviderDown as e:
            log.info("scan %s down: %s", net, e)
            continue
        for t in txs:
            dep_id = f"{net}:{t['tx_hash']}"
            await db.deposits.update_one({"_id": dep_id}, {"$setOnInsert": {
                "network": net, "asset": t["asset"], "amount": t["amount"], "tx_hash": t["tx_hash"],
                "from": t["from"], "address": a["address"], "address_id": a["_id"], "owner_type": a["owner_type"],
                "owner_id": a["owner_id"], "chain_ts": t["ts"], "status": "confirming", "aml": None,
                "created_at": now()}, "$set": {"pending": t["pending"]}}, upsert=True)
        await db.deposit_addresses.update_one({"_id": a["_id"]}, {"$set": {"last_scan": now()}})


async def process_deposits():
    s = await get_settings()
    async for d in db.deposits.find({"status": "confirming"}).limit(100):
        conf = int(s["networks"][d["network"]]["confirmations"])
        block_time = 5 if d["network"] == "ton" else 3
        if d.get("pending") or time.time() - d["chain_ts"] < conf * block_time:
            continue
        claimed = await db.deposits.find_one_and_update({"_id": d["_id"], "status": "confirming"},
                                                        {"$set": {"status": "checking"}})
        if not claimed:
            continue
        result = {"risk": 0.0, "source": "disabled", "error": None}
        if s["aml"]["enabled"]:
            result = await aml.check_address(d["from"], d["network"])
        dirty = result["risk"] is None or result["risk"] >= float(s["aml"]["risk_threshold"])
        if dirty:
            await _hold_deposit(d, result)
        else:
            await db.deposits.update_one({"_id": d["_id"]}, {"$set": {"aml": result}})
            await credit_deposit({**d, "status": "checking"}, "checking")


async def _hold_deposit(d, result):
    from ledger import post

    async def fn(sess):
        await db.deposits.update_one({"_id": d["_id"], "status": "checking"},
                                     {"$set": {"status": "aml_hold", "aml": result}}, session=sess)
        await post(sess, "deposit_aml_hold", [(f"ext:{d['network']}", d["asset"], -d["amount"]),
                                              ("sys:aml_hold", d["asset"], d["amount"])],
                   idem=f"amlhold:{d['_id']}", ref=d["_id"])
        await db.deposit_addresses.update_one({"_id": d["address_id"]}, {"$set": {"sweep_blocked": True}}, session=sess)
    await txn(fn)
    owner = d["owner_id"]
    if d["owner_type"] == "invoice":
        inv = await db.invoices.find_one({"_id": owner})
        owner = inv["creator_id"]
    notify(owner, f"Депозит {fmt(d['asset'], d['amount'])} {ASSETS[d['asset']]['title']} получен и проходит "
                  f"дополнительную проверку. Статус: в обработке.")


# ---------------- withdrawals ----------------
async def send_withdrawals():
    if (await get_settings())["security"]["withdrawals_paused"]:
        return
    for net in NETWORKS:
        if net == "ton" and await _ton_hot_busy():
            continue
        w = await db.withdrawals.find_one_and_update(
            {"network": net, "status": "queued", "next_try_at": {"$lte": now()}},
            {"$set": {"status": "signing", "updated_at": now()}, "$inc": {"attempts": 1}},
            sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
        if not w:
            continue
        try:
            hot = await signer_client.hot_address(net)
            signed = await _sign_outbound(net, w["asset"], 0, hot, w["address"], w["amount"])
        except ProviderDown as e:
            await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {
                "status": "queued", "last_error": f"provider: {e}"[:300], "next_try_at": now() + timedelta(seconds=60)}})
            continue
        except Exception as e:
            log.exception("sign failed")
            await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {
                "status": "queued", "last_error": f"sign: {e}"[:300], "next_try_at": now() + timedelta(seconds=120)}})
            continue
        # Persist the hash BEFORE broadcasting: from here on the tx is never re-signed until proven expired.
        await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {
            "status": "broadcasting", "tx_hash": signed["tx_hash"], "signed_at": time.time()},
            "$push": {"old_hashes": signed["tx_hash"]}})
        try:
            await _broadcast(net, signed["payload"])
            await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {"status": "sent", "updated_at": now()}})
        except Exception as e:
            await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {"status": "unknown", "last_error": str(e)[:300]}})


async def confirm_withdrawals():
    await db.withdrawals.update_many({"status": "signing", "tx_hash": None, "updated_at": {"$lt": now() - timedelta(minutes=5)}},
                                     {"$set": {"status": "queued", "next_try_at": now()}})
    async for w in db.withdrawals.find({"status": {"$in": ["sent", "unknown", "broadcasting"]}}).limit(50):
        try:
            st = await _status(w["network"], w["tx_hash"])
        except ProviderDown:
            continue
        if st == "ok":
            await complete_withdrawal(w)
        elif st == "failed":
            await txn(lambda s: refund_withdrawal(w, "failed", "on-chain failure", s))
            notify(w["user_id"], "Вывод не прошёл в сети, средства возвращены на баланс.")
        elif chains.tx_expired(w.get("signed_at", 0), w["network"]):
            await db.withdrawals.update_one({"_id": w["_id"], "status": w["status"]}, {"$set": {
                "status": "queued", "tx_hash": None, "next_try_at": now(), "last_error": "expired, not landed"}})


# ---------------- sweeps ----------------
async def run_sweeps():
    s = await get_settings()
    async for sw in db.sweeps.find({"status": {"$in": ["sent", "unknown", "broadcasting"]}}):
        try:
            st = await _status(sw["network"], sw["tx_hash"])
        except ProviderDown:
            continue
        if st == "ok":
            await db.sweeps.update_one({"_id": sw["_id"]}, {"$set": {"status": "done", "done_at": now()}})
            if sw["kind"] == "sweep":
                await db.deposit_addresses.update_one({"_id": sw["address_id"]}, {"$set": {f"unswept.{sw['asset']}": 0}})
        elif st == "failed" or chains.tx_expired(sw.get("signed_at", 0), sw["network"]):
            await db.sweeps.update_one({"_id": sw["_id"]}, {"$set": {"status": "failed", "result": st}})
    async for a in db.deposit_addresses.find({"sweep_blocked": False, "unswept": {"$ne": {}}}).limit(30):
        if await db.sweeps.find_one({"address_id": a["_id"], "status": {"$in": ["signing", "broadcasting", "sent", "unknown"]}}):
            continue
        for asset, amt in (a.get("unswept") or {}).items():
            if amt and amt >= units0(asset, s["assets"][asset]["sweep_threshold"]):
                try:
                    await _sweep_one(a, asset, s)
                except ProviderDown as e:
                    log.info("sweep provider down: %s", e)
                except Exception:
                    log.exception("sweep failed")
                break


async def _sweep_one(a, asset, s):
    net, hot = a["network"], await signer_client.hot_address(a["network"])
    if net == "ton":
        if asset == "TON" and a["unswept"].get("USDT_TON"):
            return  # sweep jettons first, TON on the address pays their gas
        if asset == "USDT_TON":
            bal = await chains.ton_balance(a["address"])
            if bal < 60_000_000:
                if await _ton_hot_busy():
                    return
                return await _outbound(a, "TON", 0, hot, a["address"], units0("TON", s["gas"]["ton_jetton_sweep"]), "gas")
            jb = (await chains.ton_jetton(a["address"]))["balance"]
            return await _outbound(a, asset, a["index"], a["address"], hot, jb, "sweep") if jb else None
        return await _outbound(a, "TON", a["index"], a["address"], hot, 0, "sweep", sweep_all=True)
    b = await chains.tron_balances(a["address"])
    if b["trx"] < 15_000_000:
        return await _outbound(a, "TRX", 0, hot, a["address"], int(Decimal(s["gas"]["tron_trx_topup"]) * 10**6), "gas")
    if b["usdt"]:
        await _outbound(a, asset, a["index"], a["address"], hot, b["usdt"], "sweep")


async def _outbound(a, asset, from_index, from_addr, to, amount, kind, sweep_all=False):
    sid = new_id("sw_")
    await db.sweeps.insert_one({"_id": sid, "address_id": a["_id"], "network": a["network"], "asset": asset,
                                "from_index": from_index, "to": to, "amount": amount, "kind": kind,
                                "status": "signing", "created_at": now()})
    signed = await _sign_outbound(a["network"], asset, from_index, from_addr, to, amount, sweep_all)
    await db.sweeps.update_one({"_id": sid}, {"$set": {"status": "broadcasting", "tx_hash": signed["tx_hash"],
                                                       "signed_at": time.time()}})
    try:
        await _broadcast(a["network"], signed["payload"])
        await db.sweeps.update_one({"_id": sid}, {"$set": {"status": "sent"}})
    except Exception as e:
        await db.sweeps.update_one({"_id": sid}, {"$set": {"status": "unknown", "error": str(e)[:300]}})


# ---------------- expiry ----------------
async def expire_items():
    from checks import close_check
    async for c in db.checks.find({"status": "active", "expires_at": {"$ne": None, "$lt": now()}}).limit(100):
        try:
            await close_check(c["_id"], "expired")
        except Exception as e:
            log.info("expire check %s: %s", c["_id"], e)
    await db.invoices.update_many({"status": "active", "expires_at": {"$ne": None, "$lt": now()}},
                                  {"$set": {"status": "expired"}})


# ---------------- webhooks ----------------
async def deliver_webhooks():
    async for j in db.webhook_jobs.find({"status": "pending", "next_at": {"$lte": now()}}).limit(20):
        m = await db.merchants.find_one({"_id": j["merchant_id"]})
        ts = str(int(time.time()))
        sig = sign_webhook(m["webhook_secret"], ts, j["body"])
        ok, err = False, ""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(j["url"], content=j["body"], headers={
                    "Content-Type": "application/json", "X-Signature": sig, "X-Timestamp": ts, "X-Event-Id": j["_id"]})
            ok, err = 200 <= r.status_code < 300, f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)[:200]
        n = j["attempts"] + 1
        if ok:
            upd = {"status": "delivered", "delivered_at": now()}
        elif n >= 8:
            upd = {"status": "failed"}
        else:
            upd = {"next_at": now() + timedelta(seconds=30 * 2 ** n)}
        await db.webhook_jobs.update_one({"_id": j["_id"]}, {"$set": {**upd, "attempts": n, "last_error": "" if ok else err}})


# ---------------- hot wallet ----------------
async def hot_wallet_snapshot() -> dict:
    s = await get_settings()
    snap = {"at": now(), "assets": {}, "alerts": []}
    liab = {}
    async for r in db.balances.aggregate([{"$match": {"account": {"$not": {"$regex": "^(ext|sys):"}}}},
                                          {"$group": {"_id": "$asset", "s": {"$sum": "$amount"}}}]):
        liab[r["_id"]] = int(r["s"])
    ton_hot, tron_hot = await signer_client.hot_address("ton"), await signer_client.hot_address("tron")
    onchain = {}
    try:
        onchain["TON"] = await chains.ton_balance(ton_hot)
        onchain["USDT_TON"] = (await chains.ton_jetton(ton_hot))["balance"]
    except ProviderDown:
        pass
    try:
        tb = await chains.tron_balances(tron_hot)
        onchain["USDT_TRC20"], snap["trx_balance"] = tb["usdt"], fmt("TON", tb["trx"] * 1000)
        if tb["trx"] < int(Decimal(str(s["fees"]["hot_trx_alert"])) * 10**6):
            snap["alerts"].append(f"TRX на газ в горячем кошельке: {snap['trx_balance']} — пополните, иначе выводы и свипы USDT TRC20 встанут")
    except ProviderDown:
        pass
    for asset in ASSETS:
        bal = onchain.get(asset)
        li = liab.get(asset, 0)
        entry = {"address": ton_hot if ASSETS[asset]["network"] == "ton" else tron_hot,
                 "balance": fmt(asset, bal) if bal is not None else None, "liabilities": fmt(asset, li),
                 "share_pct": round(bal / li * 100, 2) if bal is not None and li else None,
                 "alert_threshold": s["assets"][asset]["hot_alert"]}
        if bal is not None and bal < units0(asset, s["assets"][asset]["hot_alert"]):
            snap["alerts"].append(f"{ASSETS[asset]['title']}: баланс горячего кошелька ниже порога — пополните из холодного")
        if entry["share_pct"] and entry["share_pct"] > 10:
            snap["alerts"].append(f"{ASSETS[asset]['title']}: в горячем кошельке {entry['share_pct']}% средств — "
                                  f"переведите излишек в холодный (рекомендуется 5–10%)")
        snap["assets"][asset] = entry
    await db.hot_wallet.update_one({"_id": "snapshot"}, {"$set": snap}, upsert=True)
    return snap


# ---------------- cold wallet ----------------
COLD_RESERVE = {"TON": 2_000_000_000, "USDT_TON": 0, "USDT_TRC20": 0}


async def cold_transfer(asset: str, amount: int, source: str = "manual") -> dict:
    """Signs and broadcasts hot (index 0) -> configured cold address. Destination is never taken from the caller."""
    from core import bad
    s = await get_settings()
    net = ASSETS[asset]["network"]
    to = (s["cold"].get(net) or "").strip()
    if not to or not chains.valid_address(net, to):
        bad("Холодный адрес для этой сети не задан")
    if amount <= 0:
        bad("Некорректная сумма")
    if net == "ton" and await _ton_hot_busy():
        bad("Горячий TON-кошелёк сейчас отправляет другую транзакцию, повторите через минуту", 409)
    hot = await signer_client.hot_address(net)
    bal = await (chains.ton_balance(hot) if asset == "TON" else
                 (chains.ton_jetton(hot)) if asset == "USDT_TON" else chains.tron_balances(hot))
    onchain = bal if asset == "TON" else bal["balance"] if asset == "USDT_TON" else bal["usdt"]
    if amount > onchain - COLD_RESERVE[asset]:
        bad(f"Недостаточно на горячем кошельке (доступно {fmt(asset, max(0, onchain - COLD_RESERVE[asset]))})")
    sid = new_id("cold_")
    await db.sweeps.insert_one({"_id": sid, "address_id": None, "network": net, "asset": asset, "from_index": 0, "to": to,
                                "amount": amount, "kind": "cold", "source": source, "status": "signing", "created_at": now()})
    signed = await _sign_outbound(net, asset, 0, hot, to, amount)
    await db.sweeps.update_one({"_id": sid}, {"$set": {"status": "broadcasting", "tx_hash": signed["tx_hash"], "signed_at": time.time()}})
    try:
        await _broadcast(net, signed["payload"])
        await db.sweeps.update_one({"_id": sid}, {"$set": {"status": "sent"}})
    except Exception as e:
        await db.sweeps.update_one({"_id": sid}, {"$set": {"status": "unknown", "error": str(e)[:300]}})
    return {"id": sid, "tx_hash": signed["tx_hash"], "to": to, "amount": fmt(asset, amount)}


async def cold_auto():
    """If the hot wallet holds more than max_pct of user funds, move the excess down to target_pct."""
    s = await get_settings()
    if not s["cold"]["auto"]:
        return
    snap = await hot_wallet_snapshot()
    for asset, e in snap["assets"].items():
        if e["balance"] is None or not e["share_pct"] or e["share_pct"] <= float(s["cold"]["max_pct"]):
            continue
        if not s["cold"].get(ASSETS[asset]["network"]):
            continue
        bal, li = units0(asset, e["balance"]), units0(asset, e["liabilities"])
        excess = bal - int(Decimal(li) * Decimal(str(s["cold"]["target_pct"])) / 100)
        try:
            r = await cold_transfer(asset, excess, "auto")
            notify_admins = __import__("admin_bot")._notify
            await notify_admins(f"Автоперевод в холодный кошелёк: {r['amount']} {ASSETS[asset]['title']}\nTx: <code>{r['tx_hash']}</code>")
        except Exception as ex:
            log.info("cold auto %s skipped: %s", asset, ex)


async def reconcile_job():
    r = await reconcile()
    await db.hot_wallet.update_one({"_id": "reconcile"}, {"$set": {**r, "at": now()}}, upsert=True)
    if not r["ok"]:
        log.error("LEDGER RECONCILE MISMATCH: %s", r)


# ---------------- runner ----------------
JOBS = [("scan_deposits", scan_deposits, 30), ("process_deposits", process_deposits, 10),
        ("send_withdrawals", send_withdrawals, 8), ("confirm_withdrawals", confirm_withdrawals, 15),
        ("sweeps", run_sweeps, 60), ("expire", expire_items, 30), ("webhooks", deliver_webhooks, 5),
        ("hot_wallet", hot_wallet_snapshot, 300), ("reconcile", reconcile_job, 600), ("cold_auto", cold_auto, 900)]


async def _security_watch():
    import security
    await security.watch()


JOBS.append(("security", _security_watch, 60))


async def _loop(name, fn, every, stop: asyncio.Event):
    while not stop.is_set():
        try:
            if await lease(f"job:{name}", every * 3 + 30):
                await fn()
        except Exception:
            log.exception("job %s failed", name)
        try:
            await asyncio.wait_for(stop.wait(), timeout=every)
        except asyncio.TimeoutError:
            pass


def start_all(stop: asyncio.Event) -> list:
    import bot
    import admin_bot
    tasks = [asyncio.create_task(_loop(n, f, e, stop)) for n, f, e in JOBS]
    tasks.append(asyncio.create_task(_loop("broadcast", bot.broadcast_worker, 5, stop)))
    tasks.append(asyncio.create_task(_loop("admin_notify", admin_bot.notify_job, 20, stop)))
    tasks.append(asyncio.create_task(bot.run_polling(stop)))
    tasks.append(asyncio.create_task(admin_bot.run_polling(stop)))
    return tasks
