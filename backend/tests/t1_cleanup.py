# T1 cleanup: removes TEST users 900000001/900000002/900000099 and all their data; reverses journal effects on balances.
import asyncio
import os
import re

from motor.motor_asyncio import AsyncIOMotorClient

UIDS = ["900000001", "900000002", "900000099"]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    chk_ids = [c["_id"] async for c in db.checks.find({"creator_id": {"$in": UIDS}}, {"_id": 1})]
    inv_ids = [i["_id"] async for i in db.invoices.find({"creator_id": {"$in": UIDS}}, {"_id": 1})]
    accts = [f"u:{u}" for u in UIDS] + [f"u:{u}:hold" for u in UIDS] + [f"chk:{c}" for c in chk_ids]
    jdocs = await db.journal.find({"entries.account": {"$in": accts}}).to_list(1000)
    rev = {}
    for j in jdocs:
        for e in j["entries"]:
            k = f"{e['account']}|{e['asset']}"
            rev[k] = rev.get(k, 0) + e["amount"]
    print("journal docs:", len(jdocs), [j["kind"] for j in jdocs])
    for k, v in rev.items():
        if v:
            await db.balances.update_one({"_id": k}, {"$inc": {"amount": -v}})
    print("reversed balance keys:", {k: v for k, v in rev.items() if v})
    r = await db.journal.delete_many({"_id": {"$in": [j["_id"] for j in jdocs]}})
    print("journal deleted", r.deleted_count)
    print("balances deleted", (await db.balances.delete_many({"account": {"$in": accts}})).deleted_count)
    print("checks deleted", (await db.checks.delete_many({"_id": {"$in": chk_ids}})).deleted_count)
    print("invoices deleted", (await db.invoices.delete_many({"_id": {"$in": inv_ids}})).deleted_count)
    print("invoice_payments deleted", (await db.invoice_payments.delete_many({"invoice_id": {"$in": inv_ids}})).deleted_count)
    print("inline_checks deleted", (await db.inline_checks.delete_many({"creator_id": {"$in": UIDS}})).deleted_count)
    print("deposit_addresses deleted", (await db.deposit_addresses.delete_many(
        {"$or": [{"owner_id": {"$in": UIDS}}, {"owner_id": {"$in": inv_ids}}]})).deleted_count)
    print("activity deleted", (await db.activity.delete_many({"uid": {"$in": UIDS}})).deleted_count)
    print("transfers deleted", (await db.transfers.delete_many({"$or": [{"from_id": {"$in": UIDS}}, {"to_id": {"$in": UIDS}}]})).deleted_count)
    print("users deleted", (await db.users.delete_many({"_id": {"$in": UIDS}})).deleted_count)
    left = await db.balances.find({"_id": {"$regex": "^u:9000000"}}).to_list(10)
    print("leftover user balances:", left)


asyncio.run(main())
