from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import bot
import chains
from auth import verify_init_data, upsert_tg_user, make_token, current_user, not_frozen
from checks import create_check, claim_check, close_check, public_check, captcha_for
from core import db, ASSETS, NETWORKS, fmt, get_settings, require_feature, bad, now, new_id
from ledger import user_balances, acct
from services import (transfer, create_withdrawal, public_wd, deposit_address, find_user_by_username, create_invoice,
                      pay_invoice, cancel_invoice, public_invoice, new_api_key)
from auth import hash_key

router = APIRouter(prefix="/api")


class TgAuth(BaseModel):
    init_data: str


@router.post("/auth/telegram")
async def auth_telegram(body: TgAuth):
    d = verify_init_data(body.init_data)
    sp = d.get("start_param") or ""
    u = await upsert_tg_user(d["user"], sp[2:] if sp.startswith("r_") else None)
    return {"token": make_token({"typ": "user", "uid": u["_id"]}, 12), "start_param": sp}


@router.get("/config")
async def public_config():
    s = await get_settings()
    return {"assets": {k: {**v, **s["assets"][k]} for k, v in ASSETS.items()}, "networks": s["networks"],
            "features": s["features"], "merchant_fee_pct": s["merchant_fee_pct"], "referral_pct": s["referral_pct"],
            "bot_username": await bot.username()}


def _user_out(u):
    return {"id": u["_id"], "tg_id": u["tg_id"], "username": u.get("username"), "first_name": u.get("first_name"),
            "frozen": u.get("frozen", False)}


@router.get("/me")
async def me(u=Depends(current_user)):
    bals = await user_balances(u["_id"])
    return {"user": _user_out(u), "balances": {a: {"available": fmt(a, b["available"]), "hold": fmt(a, b["hold"])}
                                                for a, b in bals.items()}}


KIND_TEXT = {"deposit": "Пополнение", "withdraw_hold": "Вывод (блокировка)", "withdraw_refund": "Возврат вывода",
             "withdraw": "Вывод", "transfer": "Перевод", "check_create": "Создание чека", "check_claim": "Чек",
             "check_refund": "Возврат чека", "invoice_payment": "Счёт", "adjust": "Корректировка",
             "deposit_aml_release": "Пополнение (после проверки)"}


def history_rows(docs, accounts):
    rows = []
    for j in docs:
        for e in j["entries"]:
            if e["account"] in accounts:
                rows.append({"id": j["_id"], "kind": j["kind"], "kind_text": KIND_TEXT.get(j["kind"], j["kind"]),
                             "asset": e["asset"], "amount": fmt(e["asset"], abs(e["amount"])),
                             "sign": "+" if e["amount"] > 0 else "-", "hold": e["account"].endswith(":hold"),
                             "meta": {k: v for k, v in (j.get("meta") or {}).items() if k in ("comment", "tx_hash", "address")},
                             "created_at": j["created_at"].isoformat()})
    return rows


@router.get("/history")
async def history(u=Depends(current_user), limit: int = 50):
    a = acct(u["_id"])
    docs = await db.journal.find({"entries.account": a}).sort("created_at", -1).limit(min(limit, 200)).to_list(200)
    return [r for r in history_rows(docs, {a})]


@router.get("/deposit/{network}")
async def get_deposit(network: str, u=Depends(current_user)):
    if network not in NETWORKS:
        bad("Неизвестная сеть")
    not_frozen(u)
    s = await get_settings()
    if not s["networks"][network]["enabled"]:
        bad("Сеть временно отключена", 503)
    d = await deposit_address("user", u["_id"], network)
    deps = await db.deposits.find({"owner_type": "user", "owner_id": u["_id"], "network": network}).sort(
        "created_at", -1).limit(10).to_list(10)
    return {"address": d["address"], "network": network, "confirmations": s["networks"][network]["confirmations"],
            "assets": [a for a, m in ASSETS.items() if m["network"] == network],
            "recent": [{"asset": x["asset"], "amount": fmt(x["asset"], x["amount"]), "status": x["status"],
                        "tx_hash": x["tx_hash"], "created_at": x["created_at"].isoformat()} for x in deps]}


class WithdrawIn(BaseModel):
    asset: str
    address: str
    amount: str
    idempotency_key: str = Field(min_length=8, max_length=64)


@router.post("/withdrawals")
async def withdraw(body: WithdrawIn, u=Depends(current_user)):
    return await create_withdrawal(u, body.asset, body.address, body.amount, body.idempotency_key)


@router.get("/withdrawals/quote")
async def withdraw_quote(asset: str, address: str = "", u=Depends(current_user)):
    import fees
    if asset not in ASSETS:
        bad("Неизвестный актив")
    s = await get_settings()
    return {"asset": asset, "fee": fmt(asset, await fees.withdraw_fee(asset, address.strip() or None, s)),
            "dynamic": bool(s["fees"]["dynamic"]) and asset != "TON"}


@router.get("/withdrawals")
async def my_withdrawals(u=Depends(current_user)):
    docs = await db.withdrawals.find({"user_id": u["_id"]}).sort("created_at", -1).limit(30).to_list(30)
    return [public_wd(w) for w in docs]


class TransferIn(BaseModel):
    to_username: str
    asset: str
    amount: str
    comment: str = ""
    idempotency_key: str = Field(min_length=8, max_length=64)


@router.post("/transfer")
async def do_transfer(body: TransferIn, u=Depends(current_user)):
    await require_feature("transfers")
    not_frozen(u)
    to = await find_user_by_username(body.to_username)
    return await transfer(u, to, body.asset, body.amount, body.idempotency_key, body.comment)


# ---------------- checks ----------------
class CheckIn(BaseModel):
    asset: str
    amount: str
    kind: str = "personal"
    activations: int = 1
    bind_username: Optional[str] = None
    password: Optional[str] = None
    captcha: bool = False
    channels: List[str] = []
    min_account_age_days: int = 0
    expires_in_hours: Optional[float] = None
    description: str = ""


@router.post("/checks")
async def new_check(body: CheckIn, u=Depends(current_user)):
    await require_feature("checks")
    not_frozen(u)
    if body.kind not in ("personal", "multi"):
        bad("Тип чека: personal или multi")
    c = await create_check(u, body.model_dump())
    return public_check(c, await bot.username(), True)


@router.get("/checks")
async def my_checks(u=Depends(current_user)):
    docs = await db.checks.find({"creator_id": u["_id"]}).sort("created_at", -1).limit(50).to_list(50)
    return [public_check(c, await bot.username(), True) for c in docs]


@router.get("/checks/view/{check_code}")
async def view_check(check_code: str, u=Depends(current_user)):
    c = await db.checks.find_one({"code": check_code})
    if not c:
        bad("Чек не найден", 404)
    out = public_check(c, None, c["creator_id"] == u["_id"])
    out["already_claimed"] = u["_id"] in c.get("activated_by", [])
    out["captcha_challenge"] = captcha_for(check_code) if c.get("captcha") else None
    return out


class ClaimIn(BaseModel):
    password: Optional[str] = None
    captcha_token: Optional[str] = None
    captcha_answer: Optional[str] = None


@router.post("/checks/claim/{check_code}")
async def do_claim(check_code: str, body: ClaimIn, u=Depends(current_user)):
    await require_feature("checks")
    not_frozen(u)
    return await claim_check(u, check_code, body.model_dump())


@router.post("/checks/{check_id}/cancel")
async def cancel_check(check_id: str, u=Depends(current_user)):
    return await close_check(check_id, "cancelled", by_creator=u["_id"])


# ---------------- invoices ----------------
class InvoiceIn(BaseModel):
    asset: str
    amount: str
    description: str = ""
    kind: str = "single"
    max_payments: Optional[int] = None
    expires_in: Optional[int] = None


@router.post("/invoices")
async def new_invoice(body: InvoiceIn, u=Depends(current_user)):
    await require_feature("invoices")
    not_frozen(u)
    inv = await create_invoice(u, body.asset, body.amount, body.description, body.kind, body.max_payments, body.expires_in)
    return public_invoice(inv, await bot.username())


@router.get("/invoices")
async def my_invoices(u=Depends(current_user)):
    docs = await db.invoices.find({"creator_id": u["_id"]}).sort("created_at", -1).limit(50).to_list(50)
    return [public_invoice(i, await bot.username()) for i in docs]


@router.get("/invoices/view/{inv_code}")
async def view_invoice(inv_code: str, u=Depends(current_user)):
    inv = await db.invoices.find_one({"code": inv_code})
    if not inv:
        bad("Счёт не найден", 404)
    out = public_invoice(inv, await bot.username())
    out["already_paid"] = u["_id"] in inv.get("paid_by", [])
    creator = await db.users.find_one({"_id": inv["creator_id"]})
    m = await db.merchants.find_one({"_id": inv["merchant_id"]}) if inv.get("merchant_id") else None
    out["recipient"] = m["name"] if m else ("@" + creator["username"] if creator.get("username") else creator.get("first_name"))
    out["external_address"] = None
    if inv["kind"] == "single" and inv["status"] == "active":
        net = ASSETS[inv["asset"]]["network"]
        out["external_address"] = (await deposit_address("invoice", inv["_id"], net))["address"]
    return out


@router.post("/invoices/pay/{inv_code}")
async def do_pay(inv_code: str, u=Depends(current_user)):
    await require_feature("invoices")
    not_frozen(u)
    return await pay_invoice(u, inv_code)


@router.post("/invoices/{inv_id}/cancel")
async def do_cancel_invoice(inv_id: str, u=Depends(current_user)):
    await cancel_invoice(inv_id, by_user=u["_id"])
    return {"status": "cancelled"}


# ---------------- referral ----------------
@router.get("/referral")
async def referral(u=Depends(current_user)):
    s = await get_settings()
    invited = await db.users.count_documents({"ref_by": u["_id"]})
    earned = {a: 0 for a in ASSETS}
    pipeline = [{"$match": {"meta.referrer": u["_id"]}}, {"$unwind": "$entries"},
                {"$match": {"entries.account": acct(u["_id"])}},
                {"$group": {"_id": "$entries.asset", "s": {"$sum": "$entries.amount"}}}]
    async for r in db.journal.aggregate(pipeline):
        earned[r["_id"]] = int(r["s"])
    name = await bot.username()
    return {"link": f"https://t.me/{name}?start=r_{u['_id']}" if name else None, "invited": invited,
            "percent": s["referral_pct"], "earned": {a: fmt(a, v) for a, v in earned.items()}}


# ---------------- merchant cabinet ----------------
class MerchantApply(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    website: str = ""
    description: str = ""


async def _merchant(u):
    return await db.merchants.find_one({"user_id": u["_id"]})


def _merchant_out(m, keys, hooks):
    return {"id": m["_id"], "name": m["name"], "website": m.get("website", ""), "status": m["status"],
            "fee_pct": m.get("fee_pct"), "webhook_url": m.get("webhook_url"), "webhook_secret": m.get("webhook_secret"),
            "keys": [{"id": k["_id"], "prefix": k["prefix"], "label": k.get("label", ""), "revoked": k["revoked"],
                      "created_at": k["created_at"].isoformat(),
                      "last_used": k["last_used"].isoformat() if k.get("last_used") else None} for k in keys],
            "webhooks": [{"id": h["_id"], "status": h["status"], "attempts": h["attempts"], "last_error": h.get("last_error"),
                          "created_at": h["created_at"].isoformat()} for h in hooks]}


@router.get("/merchant")
async def merchant_get(u=Depends(current_user)):
    m = await _merchant(u)
    if not m:
        return {"merchant": None}
    keys = await db.api_keys.find({"merchant_id": m["_id"]}).sort("created_at", -1).to_list(50)
    hooks = await db.webhook_jobs.find({"merchant_id": m["_id"]}).sort("created_at", -1).limit(20).to_list(20)
    return {"merchant": _merchant_out(m, keys, hooks)}


@router.post("/merchant/apply")
async def merchant_apply(body: MerchantApply, u=Depends(current_user)):
    await require_feature("merchant")
    not_frozen(u)
    if await _merchant(u):
        bad("Заявка уже подана")
    import secrets
    await db.merchants.insert_one({"_id": new_id("mer_"), "user_id": u["_id"], "name": body.name, "website": body.website,
                                   "description": body.description[:500], "status": "pending", "fee_pct": None,
                                   "webhook_url": None, "webhook_secret": "whsec_" + secrets.token_urlsafe(24),
                                   "created_at": now()})
    return {"status": "pending"}


class WebhookIn(BaseModel):
    url: str


@router.put("/merchant/webhook")
async def merchant_webhook(body: WebhookIn, u=Depends(current_user)):
    m = await _merchant(u)
    if not m:
        bad("Сначала подайте заявку", 404)
    if body.url and not body.url.startswith("https://"):
        bad("Адрес вебхука должен начинаться с https://")
    await db.merchants.update_one({"_id": m["_id"]}, {"$set": {"webhook_url": body.url or None}})
    return {"status": "saved"}


class KeyIn(BaseModel):
    label: str = ""


@router.post("/merchant/keys")
async def merchant_new_key(body: KeyIn, u=Depends(current_user)):
    m = await _merchant(u)
    if not m or m["status"] != "approved":
        bad("Мерчант ещё не одобрен", 403)
    if await db.api_keys.count_documents({"merchant_id": m["_id"], "revoked": False}) >= 5:
        bad("Не больше 5 активных ключей")
    key = new_api_key()
    await db.api_keys.insert_one({"_id": new_id("key_"), "merchant_id": m["_id"], "hash": hash_key(key),
                                  "prefix": key[:14] + "…", "label": body.label[:40], "revoked": False, "created_at": now()})
    return {"api_key": key}


@router.delete("/merchant/keys/{key_id}")
async def merchant_revoke_key(key_id: str, u=Depends(current_user)):
    m = await _merchant(u)
    if not m:
        bad("Не найдено", 404)
    r = await db.api_keys.update_one({"_id": key_id, "merchant_id": m["_id"]}, {"$set": {"revoked": True}})
    if not r.matched_count:
        bad("Не найдено", 404)
    return {"status": "revoked"}
