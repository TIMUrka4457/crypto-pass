import asyncio
import hashlib
import hmac
import json
import os

import httpx

_cache: dict = {}


async def _call(path: str, payload: dict) -> dict:
    url = os.environ.get("SIGNER_URL")
    if not url:
        import signer
        fn = signer.address if path == "address" else signer.sign
        if path == "address":
            return {"address": await asyncio.to_thread(fn, payload["network"], payload["index"])}
        return await asyncio.to_thread(fn, payload)
    body = json.dumps(payload).encode()
    sig = hmac.new(os.environ["SIGNER_HMAC_SECRET"].encode(), body, hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{url}/{path}", content=body, headers={"X-Signature": sig, "Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()


async def address(network: str, index: int) -> str:
    k = (network, index)
    if k not in _cache:
        _cache[k] = (await _call("address", {"network": network, "index": index}))["address"]
    return _cache[k]


async def hot_address(network: str) -> str:
    return await address(network, 0)


async def sign(req: dict) -> dict:
    return await _call("sign", req)
