"""Double-entry immutable journal. Balances are a cache maintained only by post()."""
from collections import defaultdict

from pymongo.errors import DuplicateKeyError

from core import db, client, new_id, now, bad

SYSTEM_PREFIXES = ("ext:", "sys:")


class Insufficient(Exception):
    pass


class Duplicate(Exception):
    pass


def acct(uid: str) -> str:
    return f"u:{uid}"


def hold(uid: str) -> str:
    return f"u:{uid}:hold"


async def txn(fn):
    """Run fn(session) inside a MongoDB multi-document transaction (requires replica set)."""
    async with await client.start_session() as s:
        return await s.with_transaction(fn)


async def post(session, kind: str, entries: list, idem: str, ref: str = None, meta: dict = None) -> str:
    sums = defaultdict(int)
    clean = []
    for account, asset, amount in entries:
        amount = int(amount)
        if amount == 0:
            continue
        sums[asset] += amount
        clean.append({"account": account, "asset": asset, "amount": amount})
    if any(v != 0 for v in sums.values()) or not clean:
        raise ValueError("Unbalanced journal entry")
    jid = new_id("jr_")
    try:
        await db.journal.insert_one({"_id": jid, "idem": idem, "kind": kind, "ref": ref, "entries": clean,
                                     "meta": meta or {}, "created_at": now()}, session=session)
    except DuplicateKeyError:
        raise Duplicate(idem)
    for e in clean:
        key = f"{e['account']}|{e['asset']}"
        system = e["account"].startswith(SYSTEM_PREFIXES)
        if e["amount"] < 0 and not system:
            r = await db.balances.update_one({"_id": key, "amount": {"$gte": -e["amount"]}},
                                             {"$inc": {"amount": e["amount"]}}, session=session)
            if r.matched_count == 0:
                raise Insufficient(e["account"])
        else:
            await db.balances.update_one({"_id": key}, {"$inc": {"amount": e["amount"]},
                                                        "$setOnInsert": {"account": e["account"], "asset": e["asset"]}},
                                         upsert=True, session=session)
    return jid


async def post_now(kind, entries, idem, ref=None, meta=None):
    async def fn(s):
        return await post(s, kind, entries, idem, ref, meta)
    try:
        return await txn(fn)
    except Insufficient:
        bad("Недостаточно средств")


async def balance(account: str, asset: str, session=None) -> int:
    d = await db.balances.find_one({"_id": f"{account}|{asset}"}, session=session)
    return int(d["amount"]) if d else 0


async def user_balances(uid: str) -> dict:
    from core import ASSETS
    out = {a: {"available": 0, "hold": 0} for a in ASSETS}
    async for d in db.balances.find({"account": {"$in": [acct(uid), hold(uid)]}}):
        out[d["asset"]]["hold" if d["account"].endswith(":hold") else "available"] = int(d["amount"])
    return out


async def reconcile() -> dict:
    pipeline = [{"$unwind": "$entries"},
                {"$group": {"_id": {"a": "$entries.account", "s": "$entries.asset"}, "sum": {"$sum": "$entries.amount"}}}]
    sums = {f"{r['_id']['a']}|{r['_id']['s']}": int(r["sum"]) async for r in db.journal.aggregate(pipeline)}
    cache = {d["_id"]: int(d["amount"]) async for d in db.balances.find({})}
    mism = [{"key": k, "journal": sums.get(k, 0), "cache": cache.get(k, 0)}
            for k in set(sums) | set(cache) if sums.get(k, 0) != cache.get(k, 0)]
    neg = [k for k, v in cache.items() if v < 0 and not k.startswith(SYSTEM_PREFIXES)]
    return {"ok": not mism and not neg, "mismatches": mism[:50], "negative_user_balances": neg[:50],
            "accounts": len(cache)}
