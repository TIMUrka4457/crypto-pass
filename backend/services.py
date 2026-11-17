"""Money operations shared by the Mini App, the merchant API and workers."""
import asyncio
import hashlib
import json
import os
import secrets
from datetime import timedelta
from decimal import Decimal

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import chains
import signer_client
from core import db, now, new_id, code, bad, to_units, fmt, ASSETS, get_settings, check_asset, log
from ledger import post, txn, acct, hold, Insufficient, Duplicate


def units0(asset, v) -> int:
    return 0 if Decimal(str(v)) == 0 else to_units(asset, v)


def notify(uid: str, text: str):
    try:
        import bot
        asyncio.get_event_loop().create_task(bot.send(uid, text))
    except Exception as e:
        log.warning("notify failed: %s", e)


async def next_index() -> int:
    c = await db.counters.find_one_and_update({"_id": "addr_index"}, {"$inc": {"seq": 1}}, upsert=True,
                                              return_document=ReturnDocument.AFTER)
    return int(c["seq"])


async def deposit_address(owner_type: str, owner_id: str, network: str) -> dict:
    d = await db.deposit_addresses.find_one({"owner_type": owner_type, "owner_id": owner_id, "network": network})
    if d:
        return d
    idx = await next_index()
    addr = await signer_client.address(network, idx)
    doc = {"_id": f"{network}:{idx}", "network": network, "index": idx, "address": addr, "owner_type": owner_type,
           "owner_id": owner_id, "created_at": now(), "last_scan": None, "sweep_blocked": False, "unswept": {}}
    try:
        await db.deposit_addresses.insert_one(doc)
    except DuplicateKeyError:
        return await db.deposit_addresses.find_one({"owner_type": owner_type, "owner_id": owner_id, "network": network})
    return doc


async def find_user_by_username(name: str) -> dict:
    u = await db.users.find_one({"username": name.strip().lstrip("@").lower(), "deleted": {"$ne": True}})
    if not u:
        bad("Пользователь не найден. Он должен хотя бы раз запустить бота")
    return u


async def recreate_addresses(uid: str) -> int:
    """Retire current deposit addresses (still watched and credited) so new ones are issued on next request."""
    stamp = now().strftime("%Y%m%d%H%M%S")
    r = await db.deposit_addresses.update_many({"owner_type": "user", "owner_id": uid}, {"$set": {"owner_type": f"user_old_{stamp}"}})
    return r.modified_count


async def delete_account(user: dict) -> dict:
    """Irreversible: remaining balances are forfeited to sys:forfeit (recorded in the journal), profile anonymised."""
    from ledger import user_balances
    bals = await user_balances(user["_id"])
    if any(v["hold"] for v in bals.values()):
        bad("Есть выводы в обработке — дождитесь их завершения")
    lines = []
    for a, v in bals.items():
        if v["available"]:
            lines += [(acct(user["_id"]), a, -v["available"]), ("sys:forfeit", a, v["available"])]

    async def fn(s):
        if lines:
            await post(s, "account_delete", lines, idem=f"del:{user['_id']}", ref=user["_id"])
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"deleted": True, "frozen": True, "username": None,
                                                                   "first_name": "", "deleted_at": now()}}, session=s)
        await db.checks.update_many({"creator_id": user["_id"], "status": "active"}, {"$set": {"status": "cancelled"}}, session=s)
        await db.invoices.update_many({"creator_id": user["_id"], "status": "active"}, {"$set": {"status": "cancelled"}}, session=s)
    await txn(fn)
    return {"status": "deleted", "forfeited": {a: fmt(a, v["available"]) for a, v in bals.items() if v["available"]}}


def fee_split(fee: int, referrer: str | None, pct: str) -> list:
    """Ledger lines crediting system fees and the referrer's share."""
    if fee <= 0:
        return []
    ref_part = int(Decimal(fee) * Decimal(pct) / 100) if referrer else 0
    lines = [("sys:fees", None, fee - ref_part)]
    if ref_part:
        lines.append((acct(referrer), None, ref_part))
    return lines


def _with_asset(lines, asset):
    return [(a, asset, v) for a, _, v in lines]


# ---------------- transfers ----------------
async def transfer(sender: dict, to_user: dict, asset: str, amount_str, idem: str, comment: str = "", via: str = "app"):
    check_asset(asset)
    amount = to_units(asset, amount_str)
    if to_user["_id"] == sender["_id"]:
        bad("Нельзя перевести самому себе")
    if to_user.get("frozen"):
        bad("Получатель недоступен")
    tid = new_id("tr_")

    async def fn(s):
        await post(s, "transfer", [(acct(sender["_id"]), asset, -amount), (acct(to_user["_id"]), asset, amount)],
                   idem=f"tr:{sender['_id']}:{idem}", ref=tid,
                   meta={"from": sender["_id"], "to": to_user["_id"], "comment": comment[:200], "via": via})
    try:
        await txn(fn)
    except Insufficient:
        bad("Недостаточно средств")
    except Duplicate:
        return {"status": "duplicate", "idempotency_key": idem}
    notify(to_user["_id"], f"Вам перевели {fmt(asset, amount)} {ASSETS[asset]['title']} от @{sender.get('username') or sender['_id']}"
           + (f"\nКомментарий: {comment[:200]}" if comment else ""))
    return {"status": "completed", "id": tid, "amount": fmt(asset, amount), "asset": asset}


# ---------------- withdrawals ----------------
async def create_withdrawal(user: dict, asset: str, address: str, amount_str, idem: str, source: str = "app") -> dict:
    meta = check_asset(asset)
    net = meta["network"]
    s = await get_settings()
    cfg = s["assets"][asset]
    if not s["networks"][net]["enabled"] or not cfg["withdraw_enabled"]:
        bad("Вывод в этой сети временно отключён", 503)
    if user.get("frozen"):
        bad("Аккаунт заморожен", 403)
    address = address.strip()
    if not chains.valid_address(net, address):
        bad("Некорректный адрес")
    if await db.deposit_addresses.find_one({"address": address}):
        bad("Это адрес нашего кошелька — используйте внутренний перевод")
    amount = to_units(asset, amount_str)
    import fees
    fee = await fees.withdraw_fee(asset, address, s)
    if amount < units0(asset, cfg["withdraw_min"]):
        bad(f"Минимальная сумма вывода {cfg['withdraw_min']}")
    if amount > units0(asset, cfg["per_op_limit"]):
        bad(f"Лимит на одну операцию {cfg['per_op_limit']}")
    status = "pending_approval" if amount > units0(asset, cfg["auto_approve_limit"]) else "queued"
    wid = new_id("wd_")
    doc = {"_id": wid, "user_id": user["_id"], "asset": asset, "network": net, "address": address, "amount": amount,
           "fee": fee, "status": status, "idem": f"{user['_id']}:{idem}", "source": source, "tx_hash": None,
           "old_hashes": [], "attempts": 0, "next_try_at": now(), "created_at": now(), "updated_at": now(),
           "last_error": None}

    async def fn(sess):
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"wd_lock": now()}}, session=sess)
        since = now() - timedelta(hours=24)
        agg = await db.withdrawals.aggregate([
            {"$match": {"user_id": user["_id"], "asset": asset, "created_at": {"$gte": since},
                        "status": {"$nin": ["rejected", "failed"]}}},
            {"$group": {"_id": None, "s": {"$sum": "$amount"}}}], session=sess).to_list(1)
        if (agg[0]["s"] if agg else 0) + amount > units0(asset, cfg["daily_limit"]):
            bad(f"Превышен суточный лимит {cfg['daily_limit']}")
        await db.withdrawals.insert_one(doc, session=sess)
        await post(sess, "withdraw_hold", [(acct(user["_id"]), asset, -(amount + fee)), (hold(user["_id"]), asset, amount + fee)],
                   idem=f"wdhold:{wid}", ref=wid)
    try:
        await txn(fn)
    except Insufficient:
        bad("Недостаточно средств с учётом комиссии")
    except DuplicateKeyError:
        ex = await db.withdrawals.find_one({"idem": doc["idem"]})
        return public_wd(ex)
    return public_wd(doc)


def public_wd(w: dict) -> dict:
    return {"id": w["_id"], "asset": w["asset"], "network": w["network"], "address": w["address"],
            "amount": fmt(w["asset"], w["amount"]), "fee": fmt(w["asset"], w["fee"]), "status": w["status"],
            "status_text": WD_STATUS_TEXT.get(w["status"], w["status"]), "tx_hash": w.get("tx_hash"),
            "explorer": chains.explorer(w["network"], w.get("tx_hash")) if w["status"] == "completed" else "",
            "created_at": w["created_at"].isoformat()}


WD_STATUS_TEXT = {"pending_approval": "На проверке", "queued": "В обработке", "signing": "В обработке",
                  "broadcasting": "В обработке", "sent": "Отправлено, ждём подтверждения", "unknown": "В обработке",
                  "completed": "Выполнено", "rejected": "Отклонено, средства возвращены",
                  "failed": "Не удалось, средства возвращены"}


async def refund_withdrawal(w: dict, new_status: str, reason: str, session):
    r = await db.withdrawals.update_one({"_id": w["_id"], "status": w["status"]},
                                        {"$set": {"status": new_status, "last_error": reason, "updated_at": now()}},
                                        session=session)
    if r.modified_count == 0:
        bad("Статус вывода уже изменился", 409)
    total = w["amount"] + w["fee"]
    await post(session, "withdraw_refund", [(hold(w["user_id"]), w["asset"], -total), (acct(w["user_id"]), w["asset"], total)],
               idem=f"wdref:{w['_id']}", ref=w["_id"], meta={"reason": reason})


async def complete_withdrawal(w: dict):
    s = await get_settings()
    u = await db.users.find_one({"_id": w["user_id"]})

    async def fn(sess):
        r = await db.withdrawals.update_one({"_id": w["_id"], "status": w["status"]},
                                            {"$set": {"status": "completed", "completed_at": now(), "updated_at": now()}},
                                            session=sess)
        if r.modified_count == 0:
            return
        lines = [(hold(w["user_id"]), w["asset"], -(w["amount"] + w["fee"])), (f"ext:{w['network']}", w["asset"], w["amount"])]
        lines += _with_asset(fee_split(w["fee"], u.get("ref_by") if s["features"]["referral"] else None,
                                       s["referral_pct"]), w["asset"])
        await post(sess, "withdraw", lines, idem=f"wd:{w['_id']}", ref=w["_id"],
                   meta={"tx_hash": w["tx_hash"], "address": w["address"], "fee": w["fee"], "user": w["user_id"],
                         "referrer": u.get("ref_by")})
    await txn(fn)
    notify(w["user_id"], f"Вывод {fmt(w['asset'], w['amount'])} {ASSETS[w['asset']]['title']} выполнен.\n"
                         f"Хеш: {w['tx_hash']}\n{chains.explorer(w['network'], w['tx_hash'])}")


# ---------------- deposits ----------------
async def credit_deposit(dep: dict, from_status: str, manual_admin: dict = None, comment: str = ""):
    """Credit a confirmed deposit to the owner of the address (user or invoice)."""
    addr = await db.deposit_addresses.find_one({"_id": dep["address_id"]})
    asset, amount = dep["asset"], dep["amount"]
    src = "sys:aml_hold" if from_status == "aml_hold" else f"ext:{dep['network']}"
    s = await get_settings()
    inv = None
    if addr["owner_type"] == "invoice":
        inv = await db.invoices.find_one({"_id": addr["owner_id"]})
    owner = inv["creator_id"] if inv else addr["owner_id"]

    async def fn(sess):
        r = await db.deposits.update_one({"_id": dep["_id"], "status": from_status},
                                         {"$set": {"status": "credited", "credited_at": now(),
                                                   "manual": bool(manual_admin), "comment": comment}}, session=sess)
        if r.modified_count == 0:
            bad("Статус депозита уже изменился", 409)
        fee, referrer = 0, None
        if inv and inv.get("merchant_id"):
            fee = int(Decimal(amount) * Decimal(str(inv.get("fee_pct", "0"))) / 100)
        elif addr["owner_type"] == "user":
            import fees
            fee = fees.deposit_fee(asset, amount, s)
        lines = [(src, asset, -amount), (acct(owner), asset, amount - fee)]
        if fee:
            ou = await db.users.find_one({"_id": owner}, session=sess)
            referrer = ou.get("ref_by")
            lines += _with_asset(fee_split(fee, ou.get("ref_by") if s["features"]["referral"] else None,
                                           s["referral_pct"]), asset)
        await post(sess, "deposit", lines, idem=f"dep:{dep['_id']}", ref=dep["_id"],
                   meta={"tx_hash": dep["tx_hash"], "user": owner, "invoice": inv["_id"] if inv else None, "fee": fee,
                         "referrer": referrer})
        if not addr.get("sweep_blocked"):
            await db.deposit_addresses.update_one({"_id": addr["_id"]}, {"$inc": {f"unswept.{asset}": amount}}, session=sess)
        if manual_admin:
            from auth import audit
            await audit(manual_admin, "deposit_credit", dep["_id"], {"amount": fmt(asset, amount)}, comment, session=sess)
        if inv:
            await record_invoice_payment(sess, inv, None, amount, "external", dep["_id"])
        return amount - fee
    credited = await txn(fn)
    notify(owner, f"Зачислено {fmt(asset, credited)} {ASSETS[asset]['title']}" + (f" по счёту #{inv['code']}" if inv else "")
           + (f" (комиссия {fmt(asset, amount - credited)})" if credited != amount and not inv else ""))


# ---------------- invoices ----------------
async def create_invoice(creator: dict, asset: str, amount_str, description: str = "", kind: str = "single",
                         max_payments: int | None = None, expires_in: int | None = None, merchant: dict | None = None,
                         payload: str = "") -> dict:
    check_asset(asset)
    s = await get_settings()
    amount = to_units(asset, amount_str)
    if kind not in ("single", "multi"):
        bad("Тип счёта: single или multi")
    inv = {"_id": new_id("inv_"), "code": code(10), "creator_id": creator["_id"], "asset": asset, "amount": amount,
           "kind": kind, "max_payments": (max_payments if kind == "multi" else 1), "paid_count": 0, "received": 0,
           "description": description[:500], "payload": payload[:1000], "status": "active", "created_at": now(),
           "expires_at": now() + timedelta(seconds=expires_in) if expires_in else None,
           "merchant_id": merchant["_id"] if merchant else None,
           "fee_pct": (merchant.get("fee_pct") or s["merchant_fee_pct"]) if merchant else "0"}
    await db.invoices.insert_one(inv)
    return inv


async def record_invoice_payment(sess, inv, payer_id, amount, method, ref):
    await db.invoice_payments.insert_one({"_id": new_id("ip_"), "invoice_id": inv["_id"], "payer_id": payer_id,
                                          "amount": amount, "method": method, "ref": ref, "at": now()}, session=sess)
    if method == "external":
        upd = await db.invoices.find_one_and_update({"_id": inv["_id"]}, {"$inc": {"received": amount}},
                                                    return_document=ReturnDocument.AFTER, session=sess)
        if upd["status"] == "active" and upd["received"] >= upd["amount"]:
            await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"status": "paid", "paid_count": 1, "paid_at": now()}},
                                         session=sess)
            await queue_webhook(sess, inv, "invoice.paid", {"payer_id": None, "method": "external", "amount_received": upd["received"]})
    else:
        await queue_webhook(sess, inv, "invoice.paid", {"payer_id": payer_id, "method": "balance"})


async def pay_invoice(payer: dict, inv_code: str) -> dict:
    inv = await db.invoices.find_one({"code": inv_code})
    if not inv:
        bad("Счёт не найден", 404)
    if inv["creator_id"] == payer["_id"]:
        bad("Нельзя оплатить свой счёт")
    s = await get_settings()
    asset, amount = inv["asset"], inv["amount"]
    fee = int(Decimal(amount) * Decimal(str(inv.get("fee_pct", "0"))) / 100) if inv.get("merchant_id") else 0
    creator = await db.users.find_one({"_id": inv["creator_id"]})

    async def fn(sess):
        flt = {"_id": inv["_id"], "status": "active", "paid_by": {"$ne": payer["_id"]},
               "$expr": {"$lt": ["$paid_count", {"$ifNull": ["$max_payments", 10**12]}]}}
        upd = await db.invoices.find_one_and_update(flt, {"$inc": {"paid_count": 1}, "$push": {"paid_by": payer["_id"]}},
                                                    return_document=ReturnDocument.AFTER, session=sess)
        if not upd:
            bad("Счёт уже оплачен, отменён или недоступен", 409)
        if upd.get("expires_at") and upd["expires_at"].replace(tzinfo=now().tzinfo) < now():
            bad("Срок счёта истёк", 409)
        if upd["max_payments"] and upd["paid_count"] >= upd["max_payments"]:
            await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"status": "paid", "paid_at": now()}}, session=sess)
        lines = [(acct(payer["_id"]), asset, -amount), (acct(inv["creator_id"]), asset, amount - fee)]
        lines += _with_asset(fee_split(fee, creator.get("ref_by") if s["features"]["referral"] else None,
                                       s["referral_pct"]), asset)
        await post(sess, "invoice_payment", lines, idem=f"invpay:{inv['_id']}:{payer['_id']}", ref=inv["_id"],
                   meta={"payer": payer["_id"], "creator": inv["creator_id"], "fee": fee,
                         "referrer": creator.get("ref_by") if fee else None})
        await record_invoice_payment(sess, inv, payer["_id"], amount, "balance", inv["_id"])
    try:
        await txn(fn)
    except Insufficient:
        bad("Недостаточно средств")
    except Duplicate:
        bad("Вы уже оплатили этот счёт", 409)
    notify(inv["creator_id"], f"Счёт #{inv['code']} оплачен: {fmt(asset, amount - fee)} {ASSETS[asset]['title']}")
    return {"status": "paid"}


async def cancel_invoice(inv_id: str, by_user: str | None = None):
    flt = {"_id": inv_id, "status": "active"}
    if by_user:
        flt["creator_id"] = by_user
    r = await db.invoices.update_one(flt, {"$set": {"status": "cancelled", "cancelled_at": now()}})
    if r.modified_count == 0:
        bad("Счёт не найден или уже закрыт", 404)


def public_invoice(inv: dict, bot_username: str | None = None) -> dict:
    return {"id": inv["_id"], "code": inv["code"], "asset": inv["asset"], "amount": fmt(inv["asset"], inv["amount"]),
            "kind": inv["kind"], "max_payments": inv.get("max_payments"), "paid_count": inv["paid_count"],
            "received": fmt(inv["asset"], inv.get("received", 0)), "description": inv["description"],
            "payload": inv.get("payload", ""), "status": inv["status"], "created_at": inv["created_at"].isoformat(),
            "expires_at": inv["expires_at"].isoformat() if inv.get("expires_at") else None,
            "pay_url": f"https://t.me/{bot_username}?start=i_{inv['code']}" if bot_username else None}


# ---------------- webhooks ----------------
async def queue_webhook(sess, inv, event, extra):
    if not inv.get("merchant_id"):
        return
    m = await db.merchants.find_one({"_id": inv["merchant_id"]}, session=sess)
    if not m or not m.get("webhook_url"):
        return
    body = {"event": event, "invoice_id": inv["_id"], "code": inv["code"], "asset": inv["asset"],
            "amount": fmt(inv["asset"], inv["amount"]), "payload": inv.get("payload", ""), **extra,
            "event_id": new_id("evt_"), "created_at": now().isoformat()}
    await db.webhook_jobs.insert_one({"_id": body["event_id"], "merchant_id": m["_id"], "url": m["webhook_url"],
                                      "body": json.dumps(body, ensure_ascii=False), "attempts": 0, "status": "pending",
                                      "next_at": now(), "created_at": now()}, session=sess)


def sign_webhook(secret: str, ts: str, body: str) -> str:
    import hmac
    return hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()


def new_api_key() -> str:
    return "mk_live_" + secrets.token_urlsafe(32)
