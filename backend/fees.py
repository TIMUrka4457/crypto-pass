"""Network-cost-aware fees: withdrawal fee covers real gas/energy plus a small margin, never below the admin minimum."""
import time
from decimal import Decimal, ROUND_UP

import httpx

import chains
from chains import ProviderDown
from core import db, log, to_units

_rates: dict = {"at": 0.0, "v": None}
_energy: dict = {"at": 0.0, "v": 100}


def _u(asset: str, v) -> int:
    return 0 if Decimal(str(v)) == 0 else to_units(asset, v)


async def rates() -> dict | None:
    """USD prices of TON and TRX (cached 10 min; falls back to the last saved value)."""
    if _rates["v"] and time.time() - _rates["at"] < 600:
        return _rates["v"]
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.coingecko.com/api/v3/simple/price",
                            params={"ids": "tron,the-open-network", "vs_currencies": "usd"})
        j = r.json()
        v = {"TRX": Decimal(str(j["tron"]["usd"])), "TON": Decimal(str(j["the-open-network"]["usd"]))}
        _rates.update(at=time.time(), v=v)
        await db.hot_wallet.update_one({"_id": "rates"}, {"$set": {"TRX": str(v["TRX"]), "TON": str(v["TON"])}}, upsert=True)
    except Exception as e:
        log.warning("price feed failed: %s", e)
        if not _rates["v"]:
            d = await db.hot_wallet.find_one({"_id": "rates"})
            if d:
                _rates["v"] = {"TRX": Decimal(d["TRX"]), "TON": Decimal(d["TON"])}
    return _rates["v"]


async def energy_fee_sun() -> int:
    if time.time() - _energy["at"] < 3600:
        return _energy["v"]
    try:
        r = await chains._req("POST", f"{chains.TRONGRID}/wallet/getchainparameters", chains._tron_h())
        for p in r.json().get("chainParameter", []):
            if p["key"] == "getEnergyFee":
                _energy.update(at=time.time(), v=int(p["value"]))
    except Exception as e:
        log.warning("energy fee fetch failed: %s", e)
    return _energy["v"]


async def withdraw_fee(asset: str, address: str | None, s: dict) -> int:
    """Fee in asset units. TON is flat; USDT fees follow the real network cost converted at market price."""
    minimum = _u(asset, s["assets"][asset]["withdraw_fee"])
    f = s["fees"]
    if asset == "TON" or not f["dynamic"]:
        return minimum
    r = await rates()
    if not r:
        return minimum
    if asset == "USDT_TON":
        cost = Decimal(str(f["ton_jetton_gas"])) * r["TON"]
    else:
        new = True
        if address and chains.valid_address("tron", address):
            try:
                new = (await chains.tron_balances(address))["usdt"] == 0
            except ProviderDown:
                pass
        energy = int(f["tron_energy_new"] if new else f["tron_energy_existing"])
        trx = Decimal(energy * await energy_fee_sun()) / Decimal(10 ** 6) + Decimal("0.35")
        cost = trx * r["TRX"]
    usd = (cost * (1 + Decimal(str(f["gas_margin_pct"])) / 100) + Decimal(str(f["profit_usdt"])))
    return max(minimum, to_units(asset, usd.quantize(Decimal("0.1"), rounding=ROUND_UP)))


def deposit_fee(asset: str, amount: int, s: dict) -> int:
    """Flat deposit fee (covers the sweep), never more than 10% of the deposit."""
    return min(_u(asset, s["assets"][asset].get("deposit_fee", "0")), amount // 10)


async def op_cost_usd(asset: str, op: str, s: dict) -> Decimal:
    """Estimated network cost of one completed withdrawal or sweep, at current prices."""
    r = await rates()
    if not r:
        return Decimal(0)
    if asset == "TON":
        return Decimal("0.006") * r["TON"]
    if asset == "USDT_TON":
        gas = s["fees"]["ton_jetton_gas"] if op == "withdraw" else s["gas"]["ton_jetton_sweep"]
        return Decimal(str(gas)) * r["TON"]
    trx = Decimal(int(s["fees"]["tron_energy_existing"]) * await energy_fee_sun()) / Decimal(10 ** 6) + Decimal("0.35")
    return (trx + (Decimal("0.3") if op == "sweep" else 0)) * r["TRX"]
