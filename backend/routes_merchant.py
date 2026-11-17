"""Public merchant API, authenticated by X-API-Key."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import bot
from auth import current_merchant
from core import db, fmt, bad, ASSETS, require_feature
from ledger import user_balances
from services import (create_invoice, public_invoice, deposit_address, transfer, create_withdrawal, public_wd)

router = APIRouter(prefix="/api/v1", tags=["merchant-api"])


@router.get("/balance")
async def balance(ctx=Depends(current_merchant)):
    b = await user_balances(ctx["user"]["_id"])
    return {a: {"available": fmt(a, v["available"]), "hold": fmt(a, v["hold"])} for a, v in b.items()}


class InvoiceIn(BaseModel):
    asset: str
    amount: str
    description: str = ""
    payload: str = ""
    kind: str = "single"
    max_payments: Optional[int] = None
    expires_in: Optional[int] = Field(None, ge=60, le=30 * 86400)


async def _inv_out(inv):
    out = public_invoice(inv, await bot.username())
    if inv["kind"] == "single":
        out["external_address"] = (await deposit_address("invoice", inv["_id"], ASSETS[inv["asset"]]["network"]))["address"]
    return out


@router.post("/invoices")
async def create(body: InvoiceIn, ctx=Depends(current_merchant)):
    await require_feature("merchant")
    inv = await create_invoice(ctx["user"], body.asset, body.amount, body.description, body.kind, body.max_payments,
                               body.expires_in, merchant=ctx["merchant"], payload=body.payload)
    return await _inv_out(inv)


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, ctx=Depends(current_merchant)):
    inv = await db.invoices.find_one({"_id": invoice_id, "merchant_id": ctx["merchant"]["_id"]})
    if not inv:
        bad("Счёт не найден", 404)
    return await _inv_out(inv)


class TransferIn(BaseModel):
    to_username: Optional[str] = None
    to_tg_id: Optional[int] = None
    asset: str
    amount: str
    comment: str = ""
    idempotency_key: str = Field(min_length=8, max_length=64)


@router.post("/transfers")
async def api_transfer(body: TransferIn, ctx=Depends(current_merchant)):
    q = {"tg_id": body.to_tg_id} if body.to_tg_id else {"username": (body.to_username or "").lstrip("@").lower()}
    to = await db.users.find_one(q)
    if not to:
        bad("Получатель не найден", 404)
    return await transfer(ctx["user"], to, body.asset, body.amount, body.idempotency_key, body.comment, via="api")


class PayoutIn(BaseModel):
    asset: str
    address: str
    amount: str
    idempotency_key: str = Field(min_length=8, max_length=64)


@router.post("/payouts")
async def api_payout(body: PayoutIn, ctx=Depends(current_merchant)):
    return await create_withdrawal(ctx["user"], body.asset, body.address, body.amount, "api:" + body.idempotency_key, "api")


@router.get("/payouts/{payout_id}")
async def get_payout(payout_id: str, ctx=Depends(current_merchant)):
    w = await db.withdrawals.find_one({"_id": payout_id, "user_id": ctx["user"]["_id"]})
    if not w:
        bad("Не найдено", 404)
    return public_wd(w)
