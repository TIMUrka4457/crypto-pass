import asyncio
import logging
import os
from contextlib import suppress

from fastapi import FastAPI
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

from core import db, client, log

import routes_user
import routes_merchant
import routes_admin
import workers
from auth import seed_owner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

INDEXES: dict[str, list[IndexModel]] = {
    "journal": [IndexModel([("idem", ASCENDING)], name="idem", unique=True),
                IndexModel([("entries.account", ASCENDING), ("created_at", DESCENDING)], name="acct_time"),
                IndexModel([("created_at", DESCENDING)], name="time"),
                IndexModel([("meta.referrer", ASCENDING)], name="referrer", sparse=True)],
    "balances": [IndexModel([("account", ASCENDING)], name="account")],
    "users": [IndexModel([("username", ASCENDING)], name="username"), IndexModel([("ref_by", ASCENDING)], name="ref_by"),
              IndexModel([("tg_id", ASCENDING)], name="tg_id", unique=True), IndexModel([("created_at", DESCENDING)], name="created")],
    "withdrawals": [IndexModel([("idem", ASCENDING)], name="idem", unique=True),
                    IndexModel([("status", ASCENDING), ("network", ASCENDING), ("created_at", ASCENDING)], name="status"),
                    IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user")],
    "deposits": [IndexModel([("status", ASCENDING)], name="status"), IndexModel([("owner_id", ASCENDING)], name="owner"),
                 IndexModel([("created_at", DESCENDING)], name="created")],
    "deposit_addresses": [IndexModel([("owner_type", ASCENDING), ("owner_id", ASCENDING), ("network", ASCENDING)], name="owner", unique=True),
                          IndexModel([("address", ASCENDING)], name="address"), IndexModel([("last_scan", ASCENDING)], name="scan")],
    "checks": [IndexModel([("code", ASCENDING)], name="code", unique=True), IndexModel([("creator_id", ASCENDING)], name="creator"),
               IndexModel([("status", ASCENDING), ("expires_at", ASCENDING)], name="status_exp")],
    "invoices": [IndexModel([("code", ASCENDING)], name="code", unique=True), IndexModel([("creator_id", ASCENDING)], name="creator"),
                 IndexModel([("status", ASCENDING), ("expires_at", ASCENDING)], name="status_exp"),
                 IndexModel([("merchant_id", ASCENDING)], name="merchant")],
    "invoice_payments": [IndexModel([("invoice_id", ASCENDING)], name="invoice")],
    "merchants": [IndexModel([("user_id", ASCENDING)], name="user", unique=True)],
    "api_keys": [IndexModel([("hash", ASCENDING)], name="hash", unique=True), IndexModel([("merchant_id", ASCENDING)], name="merchant")],
    "webhook_jobs": [IndexModel([("status", ASCENDING), ("next_at", ASCENDING)], name="due"),
                     IndexModel([("merchant_id", ASCENDING), ("created_at", DESCENDING)], name="merchant")],
    "sweeps": [IndexModel([("address_id", ASCENDING), ("status", ASCENDING)], name="addr_status"),
               IndexModel([("status", ASCENDING)], name="status")],
    "admins": [IndexModel([("email", ASCENDING)], name="email", unique=True),
               IndexModel([("tg_id", ASCENDING)], name="tg_id", sparse=True)],
    "audit_log": [IndexModel([("at", DESCENDING)], name="at")],
    "activity": [IndexModel([("day", ASCENDING)], name="day")],
    "rate": [IndexModel([("at", ASCENDING)], name="ttl", expireAfterSeconds=180)],
    "otp": [IndexModel([("expires_at", ASCENDING)], name="ttl", expireAfterSeconds=0)],
    "aml_blocklist": [IndexModel([("address", ASCENDING)], name="address", unique=True)],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                log.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)


app = FastAPI(title="NeonWallet API")
app.include_router(routes_user.router)
app.include_router(routes_merchant.router)
app.include_router(routes_admin.router)
app.include_router(routes_admin.gate_router)


@app.get("/api/health")
async def health():
    hello = await db.command("hello")
    return {"ok": True, "replica_set": hello.get("setName"), "transactions": bool(hello.get("setName"))}


app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    hello = await db.command("hello")
    if not hello.get("setName"):
        log.error("MongoDB is NOT a replica set: money operations will fail (transactions required)")
    await seed_owner()
    app.state.stop = asyncio.Event()
    app.state.tasks = workers.start_all(app.state.stop) if os.environ.get("DISABLE_WORKERS") != "true" else []


@app.on_event("shutdown")
async def shutdown():
    app.state.stop.set()
    for t in app.state.tasks:
        t.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await t
    client.close()
