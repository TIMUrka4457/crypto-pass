"""Read/broadcast adapters for TonAPI and TronGrid. No keys here."""
import os
import time

import httpx

TONAPI = "https://tonapi.io"
TRONGRID = "https://api.trongrid.io"


class ProviderDown(Exception):
    pass


def usdt_ton_master() -> str:
    return os.environ["USDT_TON_MASTER"]


def usdt_trc20() -> str:
    return os.environ["USDT_TRC20_CONTRACT"]


def ton_raw(addr: str) -> str:
    from tonsdk.utils import Address
    return Address(addr).to_string(False).lower()


def valid_address(network: str, addr: str) -> bool:
    try:
        if network == "ton":
            ton_raw(addr)
            return len(addr) >= 48
        from tronpy.keys import is_base58check_address
        return is_base58check_address(addr)
    except Exception:
        return False


async def _req(method, url, headers, **kw):
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.request(method, url, headers=headers, **kw)
    except httpx.HTTPError as e:
        raise ProviderDown(str(e))
    if r.status_code >= 500 or r.status_code == 429:
        raise ProviderDown(f"{r.status_code}")
    return r


def _ton_h():
    k = os.environ.get("TONAPI_KEY")
    return {"Authorization": f"Bearer {k}"} if k else {}


def _tron_h():
    k = os.environ.get("TRONGRID_API_KEY")
    return {"TRON-PRO-API-KEY": k} if k else {}


# ---------------- TON ----------------
async def ton_incoming(addr: str) -> list:
    r = await _req("GET", f"{TONAPI}/v2/accounts/{addr}/events", _ton_h(), params={"limit": 50})
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        raise ProviderDown(r.text[:200])
    me, master, out = ton_raw(addr), ton_raw(usdt_ton_master()), []
    for ev in r.json().get("events", []):
        for i, a in enumerate(ev.get("actions", [])):
            if a.get("status") != "ok":
                continue
            t = a.get("type")
            if t == "TonTransfer":
                d = a["TonTransfer"]
                if d["recipient"]["address"].lower() != me:
                    continue
                asset, amount = "TON", int(d["amount"])
            elif t == "JettonTransfer":
                d = a["JettonTransfer"]
                if (d.get("recipient") or {}).get("address", "").lower() != me:
                    continue
                if d["jetton"]["address"].lower() != master:
                    continue  # fake jetton: wrong master contract
                asset, amount = "USDT_TON", int(d["amount"])
            else:
                continue
            out.append({"tx_hash": f"{ev['event_id']}:{i}", "asset": asset, "amount": amount,
                        "from": (d.get("sender") or {}).get("address", ""), "ts": int(ev["timestamp"]),
                        "pending": bool(ev.get("in_progress"))})
    return out


async def ton_seqno(addr: str) -> int:
    r = await _req("GET", f"{TONAPI}/v2/wallet/{addr}/seqno", _ton_h())
    if r.status_code != 200:
        acc = await _req("GET", f"{TONAPI}/v2/accounts/{addr}", _ton_h())
        if acc.status_code == 200 and acc.json().get("status") == "active":
            raise ProviderDown("seqno unavailable")
        return 0
    return int(r.json()["seqno"])


async def ton_balance(addr: str) -> int:
    r = await _req("GET", f"{TONAPI}/v2/accounts/{addr}", _ton_h())
    return int(r.json().get("balance", 0)) if r.status_code == 200 else 0


async def ton_jetton(addr: str) -> dict:
    r = await _req("GET", f"{TONAPI}/v2/accounts/{addr}/jettons/{usdt_ton_master()}", _ton_h())
    if r.status_code != 200:
        return {"balance": 0, "wallet": None}
    j = r.json()
    return {"balance": int(j.get("balance", 0)), "wallet": j["wallet_address"]["address"]}


async def ton_jetton_wallet_of(addr: str) -> str:
    r = await _req("GET", f"{TONAPI}/v2/blockchain/accounts/{usdt_ton_master()}/methods/get_wallet_address",
                   _ton_h(), params={"args": addr})
    if r.status_code != 200:
        raise ProviderDown(r.text[:200])
    return r.json()["decoded"]["jetton_wallet_address"]


async def ton_broadcast(boc_b64: str):
    r = await _req("POST", f"{TONAPI}/v2/blockchain/message", _ton_h(), json={"boc": boc_b64})
    if r.status_code != 200:
        raise ProviderDown(r.text[:200])


async def ton_status(msg_hash: str) -> str:
    """'ok' | 'failed' | 'not_found'"""
    r = await _req("GET", f"{TONAPI}/v2/blockchain/messages/{msg_hash}/transaction", _ton_h())
    if r.status_code == 404:
        return "not_found"
    if r.status_code != 200:
        raise ProviderDown(r.text[:200])
    return "ok" if r.json().get("success") else "failed"


# ---------------- TRON ----------------
async def tron_incoming(addr: str) -> list:
    r = await _req("GET", f"{TRONGRID}/v1/accounts/{addr}/transactions/trc20", _tron_h(),
                   params={"only_to": "true", "only_confirmed": "true", "limit": 50, "contract_address": usdt_trc20()})
    if r.status_code != 200:
        raise ProviderDown(r.text[:200])
    out = []
    for t in r.json().get("data", []):
        if t.get("to") != addr or (t.get("token_info") or {}).get("address") != usdt_trc20():
            continue
        out.append({"tx_hash": t["transaction_id"], "asset": "USDT_TRC20", "amount": int(t["value"]),
                    "from": t.get("from", ""), "ts": int(t["block_timestamp"]) // 1000, "pending": False})
    return out


async def tron_balances(addr: str) -> dict:
    r = await _req("GET", f"{TRONGRID}/v1/accounts/{addr}", _tron_h())
    data = (r.json().get("data") or [{}]) if r.status_code == 200 else [{}]
    d = data[0] if data else {}
    usdt = 0
    for item in d.get("trc20", []) or []:
        if usdt_trc20() in item:
            usdt = int(item[usdt_trc20()])
    return {"trx": int(d.get("balance", 0)), "usdt": usdt}


async def tron_build_trc20(owner: str, to: str, amount: int) -> dict:
    from tronpy.keys import to_hex_address
    param = to_hex_address(to)[2:].rjust(64, "0") + hex(amount)[2:].rjust(64, "0")
    r = await _req("POST", f"{TRONGRID}/wallet/triggersmartcontract", _tron_h(), json={
        "owner_address": owner, "contract_address": usdt_trc20(), "function_selector": "transfer(address,uint256)",
        "parameter": param, "fee_limit": 40_000_000, "call_value": 0, "visible": True})
    tx = r.json().get("transaction")
    if not tx:
        raise ProviderDown(r.text[:200])
    return tx


async def tron_build_trx(owner: str, to: str, amount_sun: int) -> dict:
    r = await _req("POST", f"{TRONGRID}/wallet/createtransaction", _tron_h(),
                   json={"owner_address": owner, "to_address": to, "amount": amount_sun, "visible": True})
    tx = r.json()
    if "txID" not in tx:
        raise ProviderDown(r.text[:200])
    return tx


async def tron_broadcast(signed_json: str):
    r = await _req("POST", f"{TRONGRID}/wallet/broadcasttransaction", _tron_h(), content=signed_json,
                   headers={**_tron_h(), "Content-Type": "application/json"})
    if not r.json().get("result"):
        raise ProviderDown(r.text[:200])


async def tron_status(txid: str) -> str:
    r = await _req("POST", f"{TRONGRID}/walletsolidity/gettransactioninfobyid", _tron_h(), json={"value": txid})
    info = r.json() if r.status_code == 200 else {}
    if not info:
        return "not_found"
    res = (info.get("receipt") or {}).get("result")
    if res in (None, "SUCCESS") and info.get("result") != "FAILED":
        return "ok"
    return "failed"


def tx_expired(created_ts: float, network: str) -> bool:
    # TON external message valid 60s, TRON tx expiration 60s; add margin before declaring "never landed".
    return time.time() - created_ts > 300


def explorer(network: str, tx_hash: str) -> str:
    if not tx_hash:
        return ""
    return f"https://tonviewer.com/transaction/{tx_hash}" if network == "ton" else f"https://tronscan.org/#/transaction/{tx_hash}"
