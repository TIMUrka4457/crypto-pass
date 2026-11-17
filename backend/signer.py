"""Isolated signing service. The ONLY module that reads SIGNER_MASTER_SEED.

Run standalone on a separate host: `uvicorn signer:signer_app --port 9100` with SIGNER_MASTER_SEED and
SIGNER_HMAC_SECRET set; then set SIGNER_URL in the main API and remove the seed from the API host.
Policy: index 0 = hot wallet; deposit addresses (index > 0) may only send to the hot wallet.
"""
import base64
import hashlib
import hmac
import json
import os

from fastapi import FastAPI, Header, HTTPException, Request
from nacl.bindings import crypto_sign_seed_keypair


def _seed() -> bytes:
    return bytes.fromhex(os.environ["SIGNER_MASTER_SEED"])


def _derive(network: str, index: int) -> bytes:
    return hmac.new(_seed(), f"{network}:{index}".encode(), hashlib.sha256).digest()


def _ton_wallet(index: int):
    from tonsdk.contract.wallet import WalletV4ContractR2
    pk, sk = crypto_sign_seed_keypair(_derive("ton", index))
    return WalletV4ContractR2(public_key=pk, private_key=sk, wc=0)


def _tron_key(index: int):
    from tronpy.keys import PrivateKey
    return PrivateKey(_derive("tron", index))


def address(network: str, index: int) -> str:
    if network == "ton":
        return _ton_wallet(index).address.to_string(True, True, False)
    return _tron_key(index).public_key.to_base58check_address()


def sign(req: dict) -> dict:
    """req: {network, from_index, to, ...}. Returns {tx_hash, payload}. Never broadcasts."""
    network, idx, to = req["network"], int(req["from_index"]), req["to"]
    if idx != 0 and to != address(network, 0):
        raise ValueError("Deposit addresses may only send to the hot wallet")
    if network == "ton":
        from tonsdk.utils import Address
        w = _ton_wallet(idx)
        if req.get("jetton_wallet"):
            from tonsdk.contract.token.ft import JettonWallet
            body = JettonWallet().create_transfer_body(
                to_address=Address(to), jetton_amount=int(req["amount"]), forward_amount=1,
                response_address=Address(address("ton", 0)), query_id=int(req.get("query_id", 0)))
            msg = w.create_transfer_message(req["jetton_wallet"], int(req.get("gas", 50_000_000)),
                                            int(req["seqno"]), payload=body)
        elif req.get("sweep_all"):
            msg = w.create_transfer_message(to, 0, int(req["seqno"]), send_mode=128)
        else:
            msg = w.create_transfer_message(to, int(req["amount"]), int(req["seqno"]),
                                            payload=req.get("comment") or None)
        cell = msg["message"]
        return {"tx_hash": cell.bytes_hash().hex(), "payload": base64.b64encode(cell.to_boc(False)).decode()}
    tx = req["unsigned_tx"]
    key = _tron_key(idx)
    if tx.get("raw_data", {}).get("contract", [{}])[0].get("parameter", {}).get("value", {}).get("owner_address") not in (
            key.public_key.to_base58check_address(), key.public_key.to_hex_address()):
        raise ValueError("Owner mismatch")
    raw = bytes.fromhex(tx["raw_data_hex"])
    txid = hashlib.sha256(raw).hexdigest()
    if txid != tx["txID"]:
        raise ValueError("txID mismatch")
    sig = key.sign_msg_hash(bytes.fromhex(txid)).hex()
    return {"tx_hash": txid, "payload": json.dumps({**tx, "signature": [sig]})}


# ---------- standalone HTTP mode ----------
signer_app = FastAPI()


def _verify(body: bytes, sig: str):
    good = hmac.new(os.environ["SIGNER_HMAC_SECRET"].encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig or ""):
        raise HTTPException(401, "bad signature")


@signer_app.post("/address")
async def _http_address(request: Request, x_signature: str = Header(None)):
    body = await request.body()
    _verify(body, x_signature)
    d = json.loads(body)
    return {"address": address(d["network"], int(d["index"]))}


@signer_app.post("/sign")
async def _http_sign(request: Request, x_signature: str = Header(None)):
    body = await request.body()
    _verify(body, x_signature)
    try:
        return sign(json.loads(body))
    except ValueError as e:
        raise HTTPException(400, str(e))
