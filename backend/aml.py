import hashlib
import os

import httpx

from core import db, log

AMLBOT_URL = "https://extrnlapiendpoint.silencatech.com/"


async def check_address(address: str, network: str) -> dict:
    """Returns {"risk": float|None, "source": str, "error": str|None}."""
    if await db.aml_blocklist.find_one({"address": address}):
        return {"risk": 1.0, "source": "blocklist", "error": None}
    aid, akey = os.environ.get("AMLBOT_ACCESS_ID"), os.environ.get("AMLBOT_ACCESS_KEY")
    if not aid or not akey:
        return {"risk": None, "source": "amlbot", "error": "not_configured"}
    token = hashlib.md5(f"{address}:{akey}:{aid}".encode()).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(AMLBOT_URL, data={"address": address, "asset": "TON" if network == "ton" else "TRX",
                                               "token": token, "accessId": aid, "locale": "en_US", "flow": "fast"})
        j = r.json()
        data = j.get("data") or {}
        if not j.get("result") or data.get("riskscore") is None:
            return {"risk": None, "source": "amlbot", "error": str(j.get("description") or j)[:200]}
        return {"risk": float(data["riskscore"]), "source": "amlbot", "error": None}
    except Exception as e:
        log.warning("AML check failed: %s", e)
        return {"risk": None, "source": "amlbot", "error": str(e)[:200]}
