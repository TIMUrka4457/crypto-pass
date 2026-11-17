import hmac
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

import bot
from auth import login_step1, login_step2, current_admin, perm, audit, hash_pw, ROLE_PERMS
from checks import close_check
from core import db, ASSETS, fmt, to_units, get_settings, bad, now, new_id, DEFAULT_SETTINGS, _merge
from ledger import txn, post, user_balances, acct, hold, reconcile, Insufficient
from routes_user import history_rows
from services import credit_deposit, refund_withdrawal, public_wd, cancel_invoice, units0
import workers

def _panel_ok(key: str | None) -> bool:
    return bool(key) and hmac.compare_digest(key, os.environ["ADMIN_PANEL_PATH"])


async def panel_gate(x_panel_key: str = Header(None)):
    if not _panel_ok(x_panel_key):
        raise HTTPException(404, "Not Found")


gate_router = APIRouter(prefix="/api")
router = APIRouter(prefix="/api/admin", dependencies=[Depends(panel_gate)])


@gate_router.get("/p/{key}")
async def panel_check(key: str):
    if not _panel_ok(key):
        raise HTTPException(404, "Not Found")
    return {"ok": True}


def ser(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k in ("password_hash", "hash"):
            continue
        out["id" if k == "_id" else k] = v.isoformat() if isinstance(v, datetime) else v
    return out


def amt(d: dict, *fields) -> dict:
    for f in fields:
        if f in d and isinstance(d[f], int):
            d[f] = fmt(d["asset"], d[f])
    return d


class Login(BaseModel):
    email: str
    password: str


class Verify(BaseModel):
    challenge_id: str
    code: str


@router.post("/auth/login")
async def login(body: Login, request: Request):
    return await login_step1(body.email, body.password, request.client.host if request.client else "")


@router.post("/auth/verify")
async def verify(body: Verify, request: Request):
    return await login_step2(body.challenge_id, body.code, request.client.host if request.client else "")


@router.get("/me")
async def me(a=Depends(current_admin)):
    perms = ROLE_PERMS[a["role"]]
    return {"email": a["email"], "role": a["role"], "perms": sorted(perms)}


# ---------------- stats ----------------
@router.get("/stats")
async def stats(a=Depends(perm("view")), days: int = 14):
    since = now() - timedelta(days=days)
    turnover, fees = {x: 0 for x in ASSETS}, {x: 0 for x in ASSETS}
    async for r in db.journal.aggregate([
        {"$match": {"created_at": {"$gte": since}, "kind": {"$in": ["deposit", "withdraw", "transfer", "invoice_payment", "check_claim"]}}},
        {"$unwind": "$entries"}, {"$match": {"entries.amount": {"$gt": 0}, "entries.account": {"$not": {"$regex": "^sys:"}}}},
        {"$group": {"_id": "$entries.asset", "s": {"$sum": "$entries.amount"}}}]):
        turnover[r["_id"]] = int(r["s"])
    async for r in db.journal.aggregate([
        {"$match": {"created_at": {"$gte": since}}}, {"$unwind": "$entries"},
        {"$match": {"entries.account": "sys:fees"}}, {"$group": {"_id": "$entries.asset", "s": {"$sum": "$entries.amount"}}}]):
        fees[r["_id"]] = int(r["s"])
    dau = {r["_id"]: r["n"] async for r in db.activity.aggregate([
        {"$match": {"day": {"$gte": since.date().isoformat()}}}, {"$group": {"_id": "$day", "n": {"$sum": 1}}}])}
    series = [{"day": (since + timedelta(days=i + 1)).date().isoformat(),
               "dau": dau.get((since + timedelta(days=i + 1)).date().isoformat(), 0)} for i in range(days)]
    snap = await db.hot_wallet.find_one({"_id": "snapshot"}) or {}
    rec = await db.hot_wallet.find_one({"_id": "reconcile"}) or {}
    return {"users": await db.users.count_documents({}), "dau_today": series[-1]["dau"], "dau_series": series,
            "turnover": {k: fmt(k, v) for k, v in turnover.items()}, "fees": {k: fmt(k, v) for k, v in fees.items()},
            "pending_withdrawals": await db.withdrawals.count_documents({"status": "pending_approval"}),
            "processing_withdrawals": await db.withdrawals.count_documents({"status": {"$in": ["queued", "signing", "broadcasting", "sent", "unknown"]}}),
            "unknown_withdrawals": await db.withdrawals.count_documents({"status": "unknown"}),
            "aml_holds": await db.deposits.count_documents({"status": "aml_hold"}),
            "pending_merchants": await db.merchants.count_documents({"status": "pending"}),
            "hot_alerts": snap.get("alerts", []), "reconcile_ok": rec.get("ok"),
            "reconcile_at": rec["at"].isoformat() if rec.get("at") else None}


@router.get("/finance")
async def finance(a=Depends(perm("view")), days: int = 30):
    return await finance_report(days)


async def finance_report(days: int = 30) -> dict:
    import fees
    from decimal import Decimal
    s = await get_settings()
    r = await fees.rates() or {"TON": Decimal(0), "TRX": Decimal(0)}
    price = lambda x: Decimal(1) if x.startswith("USDT") else r["TON"]  # noqa: E731
    since = now() - timedelta(days=days)
    rows: dict = {}

    def row(day):
        return rows.setdefault(day, {"day": day, "income": {x: 0 for x in ASSETS}, "income_usd": Decimal(0),
                                     "cost_usd": Decimal(0), "withdrawals": 0, "sweeps": 0})
    async for x in db.journal.aggregate([
        {"$match": {"created_at": {"$gte": since}}}, {"$unwind": "$entries"}, {"$match": {"entries.account": "sys:fees"}},
        {"$group": {"_id": {"d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "a": "$entries.asset"},
                    "s": {"$sum": "$entries.amount"}}}]):
        rr, asset = row(x["_id"]["d"]), x["_id"]["a"]
        rr["income"][asset] += int(x["s"])
        rr["income_usd"] += Decimal(int(x["s"])) / Decimal(10 ** ASSETS[asset]["decimals"]) * price(asset)
    unit = {x: await fees.op_cost_usd(x, "withdraw", s) for x in ASSETS}
    sweep_unit = {x: await fees.op_cost_usd(x, "sweep", s) for x in ASSETS}
    async for x in db.withdrawals.aggregate([
        {"$match": {"status": "completed", "completed_at": {"$gte": since}}},
        {"$group": {"_id": {"d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$completed_at"}}, "a": "$asset"}, "n": {"$sum": 1}}}]):
        rr = row(x["_id"]["d"])
        rr["withdrawals"] += x["n"]
        rr["cost_usd"] += unit[x["_id"]["a"]] * x["n"]
    async for x in db.sweeps.aggregate([
        {"$match": {"status": "done", "kind": "sweep", "created_at": {"$gte": since}}},
        {"$group": {"_id": {"d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "a": "$asset"}, "n": {"$sum": 1}}}]):
        rr = row(x["_id"]["d"])
        rr["sweeps"] += x["n"]
        rr["cost_usd"] += sweep_unit.get(x["_id"]["a"], Decimal(0)) * x["n"]
    out = []
    for d in sorted(rows, reverse=True):
        v = rows[d]
        out.append({**v, "income": {k: fmt(k, n) for k, n in v["income"].items()}, "income_usd": f"{v['income_usd']:.2f}",
                    "cost_usd": f"{v['cost_usd']:.2f}", "profit_usd": f"{v['income_usd'] - v['cost_usd']:.2f}"})
    tot_in = sum((rows[d]["income_usd"] for d in rows), Decimal(0))
    tot_cost = sum((rows[d]["cost_usd"] for d in rows), Decimal(0))
    return {"days": days, "rows": out, "total": {"income_usd": f"{tot_in:.2f}", "cost_usd": f"{tot_cost:.2f}",
                                                 "profit_usd": f"{tot_in - tot_cost:.2f}"},
            "prices": {"TON": str(r["TON"]), "TRX": str(r["TRX"])},
            "unit_cost_usd": {k: f"{v:.2f}" for k, v in unit.items()}}


@router.get("/ledger/reconcile")
async def do_reconcile(a=Depends(perm("view"))):
    r = await reconcile()
    await db.hot_wallet.update_one({"_id": "reconcile"}, {"$set": {**r, "at": now()}}, upsert=True)
    return r


# ---------------- users ----------------
@router.get("/users")
async def users(a=Depends(perm("view")), q: str = "", skip: int = 0):
    flt = {}
    if q:
        q = q.strip().lstrip("@")
        flt = {"$or": [{"username": {"$regex": "^" + re.escape(q.lower())}}, {"_id": q}, {"first_name": {"$regex": re.escape(q), "$options": "i"}}]}
    docs = await db.users.find(flt).sort("created_at", -1).skip(skip).limit(50).to_list(50)
    return {"total": await db.users.count_documents(flt), "items": [ser(d) for d in docs]}


@router.get("/users/{uid}")
async def user_detail(uid: str, a=Depends(perm("view"))):
    u = await db.users.find_one({"_id": uid})
    if not u:
        bad("Не найдено", 404)
    bals = await user_balances(uid)
    accts = {acct(uid), hold(uid)}
    docs = await db.journal.find({"entries.account": {"$in": list(accts)}}).sort("created_at", -1).limit(100).to_list(100)
    deps = await db.deposits.find({"owner_id": uid}).sort("created_at", -1).limit(30).to_list(30)
    wds = await db.withdrawals.find({"user_id": uid}).sort("created_at", -1).limit(30).to_list(30)
    addrs = await db.deposit_addresses.find({"owner_type": "user", "owner_id": uid}).to_list(5)
    return {"user": ser(u), "balances": {k: {"available": fmt(k, v["available"]), "hold": fmt(k, v["hold"])} for k, v in bals.items()},
            "history": history_rows(docs, accts), "deposits": [amt(ser(d), "amount") for d in deps],
            "withdrawals": [public_wd(w) for w in wds], "addresses": [{"network": x["network"], "address": x["address"]} for x in addrs],
            "referrals": await db.users.count_documents({"ref_by": uid})}


class Comment(BaseModel):
    comment: str = Field(min_length=3, max_length=500)


class FreezeIn(Comment):
    frozen: bool


@router.post("/users/{uid}/freeze")
async def freeze(uid: str, body: FreezeIn, a=Depends(perm("freeze"))):
    r = await db.users.update_one({"_id": uid}, {"$set": {"frozen": body.frozen}})
    if not r.matched_count:
        bad("Не найдено", 404)
    await audit(a, "user_freeze" if body.frozen else "user_unfreeze", uid, {}, body.comment)
    return {"status": "ok"}


class AdjustIn(Comment):
    asset: str
    amount: str
    direction: str


@router.post("/users/{uid}/adjust")
async def adjust(uid: str, body: AdjustIn, a=Depends(perm("adjust"))):
    if not await db.users.find_one({"_id": uid}):
        bad("Не найдено", 404)
    units = to_units(body.asset, body.amount) * (1 if body.direction == "credit" else -1)
    aid = new_id("adj_")

    async def fn(s):
        await post(s, "adjust", [("sys:adjust", body.asset, -units), (acct(uid), body.asset, units)], idem=aid, ref=aid,
                   meta={"admin": a["email"], "comment": body.comment})
        await audit(a, "balance_adjust", uid, {"asset": body.asset, "amount": fmt(body.asset, abs(units)),
                                                "direction": body.direction}, body.comment, session=s)
    try:
        await txn(fn)
    except Insufficient:
        bad("Списание больше доступного баланса")
    return {"status": "ok"}


# ---------------- deposits ----------------
@router.get("/deposits")
async def deposits(a=Depends(perm("view")), status: str = ""):
    flt = {"status": status} if status else {}
    docs = await db.deposits.find(flt).sort("created_at", -1).limit(100).to_list(100)
    return [amt(ser(d), "amount") for d in docs]


class CreditIn(Comment):
    unblock_sweep: bool = False


@router.post("/deposits/{dep_id}/credit")
async def deposit_credit(dep_id: str, body: CreditIn, a=Depends(perm("deposits"))):
    d = await db.deposits.find_one({"_id": dep_id, "status": "aml_hold"})
    if not d:
        bad("Депозит не на AML-проверке", 409)
    await credit_deposit(d, "aml_hold", manual_admin=a, comment=body.comment)
    if body.unblock_sweep:
        await db.deposit_addresses.update_one({"_id": d["address_id"]}, {"$set": {"sweep_blocked": False}})
    return {"status": "credited"}


@router.post("/deposits/{dep_id}/reject")
async def deposit_reject(dep_id: str, body: Comment, a=Depends(perm("deposits"))):
    async def fn(s):
        r = await db.deposits.update_one({"_id": dep_id, "status": "aml_hold"},
                                         {"$set": {"status": "rejected", "comment": body.comment}}, session=s)
        if not r.modified_count:
            bad("Депозит не на AML-проверке", 409)
        await audit(a, "deposit_reject", dep_id, {}, body.comment, session=s)
    await txn(fn)
    return {"status": "rejected"}


class BlockIn(BaseModel):
    address: str
    note: str = ""


@router.get("/aml/blocklist")
async def blocklist(a=Depends(perm("view"))):
    return [ser(d) for d in await db.aml_blocklist.find({}).sort("created_at", -1).to_list(500)]


@router.post("/aml/blocklist")
async def blocklist_add(body: BlockIn, a=Depends(perm("aml"))):
    await db.aml_blocklist.update_one({"address": body.address.strip()}, {"$setOnInsert": {
        "_id": new_id("bl_"), "note": body.note, "created_at": now(), "admin": a["email"]}}, upsert=True)
    await audit(a, "aml_block_add", body.address, {}, body.note)
    return {"status": "ok"}


@router.delete("/aml/blocklist/{bid}")
async def blocklist_del(bid: str, a=Depends(perm("aml"))):
    await db.aml_blocklist.delete_one({"_id": bid})
    await audit(a, "aml_block_remove", bid, {}, "")
    return {"status": "ok"}


# ---------------- withdrawals ----------------
@router.get("/withdrawals")
async def withdrawals(a=Depends(perm("view")), status: str = ""):
    flt = {"status": {"$in": status.split(",")}} if status else {}
    docs = await db.withdrawals.find(flt).sort("created_at", -1).limit(100).to_list(100)
    out = []
    for w in docs:
        p = public_wd(w)
        p.update({"user_id": w["user_id"], "last_error": w.get("last_error"), "attempts": w.get("attempts", 0),
                  "source": w.get("source"), "raw_status": w["status"]})
        out.append(p)
    return out


@router.post("/withdrawals/{wid}/approve")
async def wd_approve(wid: str, body: Comment, a=Depends(perm("withdrawals"))):
    async def fn(s):
        r = await db.withdrawals.update_one({"_id": wid, "status": "pending_approval"},
                                            {"$set": {"status": "queued", "approved_by": a["email"], "next_try_at": now()}}, session=s)
        if not r.modified_count:
            bad("Вывод не ожидает одобрения", 409)
        await audit(a, "withdrawal_approve", wid, {}, body.comment, session=s)
    await txn(fn)
    return {"status": "queued"}


@router.post("/withdrawals/{wid}/reject")
async def wd_reject(wid: str, body: Comment, a=Depends(perm("withdrawals"))):
    w = await db.withdrawals.find_one({"_id": wid})
    if not w or w["status"] not in ("pending_approval", "queued"):
        bad("Отклонить можно только ещё не отправленный вывод", 409)

    async def fn(s):
        await refund_withdrawal(w, "rejected", body.comment, s)
        await audit(a, "withdrawal_reject", wid, {}, body.comment, session=s)
    await txn(fn)
    from services import notify
    notify(w["user_id"], "Вывод отклонён, средства возвращены на баланс.")
    return {"status": "rejected"}


@router.post("/withdrawals/{wid}/mark-failed")
async def wd_mark_failed(wid: str, body: Comment, a=Depends(perm("withdrawals"))):
    """For 'unknown' status only, after the admin verified on the explorer that the tx never landed."""
    w = await db.withdrawals.find_one({"_id": wid, "status": "unknown"})
    if not w:
        bad("Доступно только для статуса unknown", 409)

    async def fn(s):
        await refund_withdrawal(w, "failed", "admin: " + body.comment, s)
        await audit(a, "withdrawal_mark_failed", wid, {"tx_hash": w.get("tx_hash")}, body.comment, session=s)
    await txn(fn)
    return {"status": "failed"}


# ---------------- settings ----------------
@router.get("/settings")
async def settings_get(a=Depends(perm("view"))):
    return await get_settings()


@router.put("/settings")
async def settings_put(body: dict, a=Depends(perm("settings"))):
    old = await get_settings()
    new = _merge(DEFAULT_SETTINGS, {k: v for k, v in body.items() if k in DEFAULT_SETTINGS})
    for asset, cfg in new["assets"].items():
        for f in ("withdraw_fee", "withdraw_min", "per_op_limit", "daily_limit", "auto_approve_limit", "sweep_threshold", "hot_alert", "deposit_fee"):
            units0(asset, cfg[f])
    await db.settings.update_one({"_id": "global"}, {"$set": new}, upsert=True)
    changed = {k: new[k] for k in new if new[k] != old.get(k)}
    await audit(a, "settings_update", "settings", changed, "")
    return new


# ---------------- hot wallet ----------------
@router.get("/hot-wallet")
async def hot_wallet(a=Depends(perm("view")), refresh: bool = False):
    snap = await workers.hot_wallet_snapshot() if refresh else await db.hot_wallet.find_one({"_id": "snapshot"})
    if not snap:
        snap = await workers.hot_wallet_snapshot()
    snap = {k: v for k, v in snap.items() if k != "_id"}
    snap["at"] = snap["at"].isoformat() if isinstance(snap.get("at"), datetime) else snap.get("at")
    snap["sweeps"] = [ser(x) for x in await db.sweeps.find({}).sort("created_at", -1).limit(30).to_list(30)]
    return snap


# ---------------- merchants ----------------
@router.get("/merchants")
async def merchants(a=Depends(perm("view"))):
    out = []
    for m in await db.merchants.find({}).sort("created_at", -1).to_list(500):
        d = ser(m)
        d.pop("webhook_secret", None)
        d["active_keys"] = await db.api_keys.count_documents({"merchant_id": m["_id"], "revoked": False})
        out.append(d)
    return out


class MerchantUpd(Comment):
    status: Optional[str] = None
    fee_pct: Optional[str] = None


@router.post("/merchants/{mid}")
async def merchant_update(mid: str, body: MerchantUpd, a=Depends(perm("merchants"))):
    upd = {}
    if body.status:
        if body.status not in ("approved", "rejected", "suspended"):
            bad("Неверный статус")
        upd["status"] = body.status
    if body.fee_pct is not None:
        if not 0 <= float(body.fee_pct) <= 20:
            bad("Комиссия от 0 до 20%")
        upd["fee_pct"] = body.fee_pct
    r = await db.merchants.update_one({"_id": mid}, {"$set": upd})
    if not r.matched_count:
        bad("Не найдено", 404)
    await audit(a, "merchant_update", mid, upd, body.comment)
    return {"status": "ok"}


@router.post("/merchants/{mid}/revoke-keys")
async def merchant_revoke(mid: str, body: Comment, a=Depends(perm("merchants"))):
    r = await db.api_keys.update_many({"merchant_id": mid, "revoked": False}, {"$set": {"revoked": True}})
    await audit(a, "merchant_revoke_keys", mid, {"count": r.modified_count}, body.comment)
    return {"revoked": r.modified_count}


# ---------------- checks & invoices ----------------
@router.get("/checks")
async def checks(a=Depends(perm("view")), status: str = ""):
    flt = {"status": status} if status else {}
    docs = await db.checks.find(flt, {"activated_by": 0}).sort("created_at", -1).limit(100).to_list(100)
    return [amt(ser(d), "amount_per") for d in docs]


@router.post("/checks/{cid}/cancel")
async def check_cancel(cid: str, body: Comment, a=Depends(perm("cancel"))):
    return await close_check(cid, "cancelled", admin=a, comment=body.comment)


@router.get("/invoices")
async def invoices(a=Depends(perm("view")), status: str = ""):
    flt = {"status": status} if status else {}
    docs = await db.invoices.find(flt, {"paid_by": 0}).sort("created_at", -1).limit(100).to_list(100)
    return [amt(ser(d), "amount", "received") for d in docs]


@router.post("/invoices/{iid}/cancel")
async def invoice_cancel(iid: str, body: Comment, a=Depends(perm("cancel"))):
    await cancel_invoice(iid)
    await audit(a, "invoice_force_cancel", iid, {}, body.comment)
    return {"status": "cancelled"}


# ---------------- broadcasts ----------------
class BroadcastIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("/broadcasts")
async def broadcasts(a=Depends(perm("view"))):
    return [ser(d) for d in await db.broadcasts.find({}).sort("created_at", -1).limit(30).to_list(30)]


@router.post("/broadcasts")
async def broadcast_new(body: BroadcastIn, a=Depends(perm("broadcast"))):
    if not bot.enabled():
        bad("Бот не настроен", 503)
    doc = await bot.queue_broadcast(body.text, a)
    await audit(a, "broadcast", doc["_id"], {"chars": len(body.text)}, "")
    return ser(doc)


# ---------------- audit & admins ----------------
@router.get("/audit")
async def audit_log(a=Depends(perm("view")), skip: int = 0):
    docs = await db.audit_log.find({}).sort("at", -1).skip(skip).limit(100).to_list(100)
    return [ser(d) for d in docs]


@router.get("/admins")
async def admins(a=Depends(perm("view"))):
    return [ser(d) for d in await db.admins.find({}).to_list(100)]


class AdminIn(BaseModel):
    email: str
    password: str = Field(min_length=10)
    role: str


@router.post("/admins")
async def admin_create(body: AdminIn, a=Depends(perm("manage_admins"))):
    if body.role not in ("admin", "support"):
        bad("Роль: admin или support")
    email = body.email.strip().lower()
    if await db.admins.find_one({"email": email}):
        bad("Такой админ уже есть")
    await db.admins.insert_one({"_id": new_id("adm_"), "email": email, "password_hash": hash_pw(body.password),
                                "role": body.role, "active": True, "created_at": now()})
    await audit(a, "admin_create", email, {"role": body.role}, "")
    return {"status": "ok"}


class AdminActive(BaseModel):
    active: bool


@router.post("/admins/{aid}/active")
async def admin_active(aid: str, body: AdminActive, a=Depends(perm("manage_admins"))):
    if aid == a["_id"]:
        bad("Нельзя отключить себя")
    await db.admins.update_one({"_id": aid, "role": {"$ne": "owner"}}, {"$set": {"active": body.active}})
    await audit(a, "admin_active", aid, {"active": body.active}, "")
    return {"status": "ok"}
