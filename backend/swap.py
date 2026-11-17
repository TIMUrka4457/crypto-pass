"""Internal swap TON <-> USDT at market price minus a small spread."""
from decimal import Decimal, ROUND_DOWN

import fees
from core import ASSETS, fmt, to_units, bad, get_settings, require_feature, new_id
from ledger import post, txn, acct, Insufficient, Duplicate
from services import fee_split, _with_asset


def _price(asset: str, r: dict) -> Decimal:
    return Decimal(1) if asset.startswith("USDT") else r["TON"]


async def quote(from_a: str, to_a: str, amount_str) -> dict:
    if from_a not in ASSETS or to_a not in ASSETS or from_a == to_a:
        bad("Выберите два разных актива")
    cfg = (await get_settings())["swap"]
    r = await fees.rates()
    if not r:
        bad("Курс временно недоступен, попробуйте позже", 503)
    amt = to_units(from_a, amount_str)
    d_from, d_to = ASSETS[from_a]["decimals"], ASSETS[to_a]["decimals"]
    usd = Decimal(amt) / Decimal(10 ** d_from) * _price(from_a, r)
    if usd < Decimal(str(cfg["min_usd"])):
        bad(f"Минимальная сумма обмена — ${cfg['min_usd']}")
    if usd > Decimal(str(cfg["max_usd"])):
        bad(f"Максимальная сумма обмена — ${cfg['max_usd']}")
    gross = int((usd / _price(to_a, r) * Decimal(10 ** d_to)).to_integral_value(ROUND_DOWN))
    fee = int(Decimal(gross) * Decimal(str(cfg["fee_pct"])) / 100)
    rate = (_price(from_a, r) / _price(to_a, r)).quantize(Decimal("0.000001"))
    return {"from": from_a, "to": to_a, "amount": amt, "gross": gross, "fee": fee, "receive": gross - fee, "rate": rate,
            "out": {"amount": fmt(from_a, amt), "receive": fmt(to_a, gross - fee), "fee": fmt(to_a, fee),
                    "rate": format(rate.normalize(), "f"), "fee_pct": cfg["fee_pct"]}}


async def execute(user: dict, from_a: str, to_a: str, amount_str, idem: str, min_receive: str | None = None) -> dict:
    await require_feature("swap")
    if user.get("frozen"):
        bad("Аккаунт заморожен", 403)
    q = await quote(from_a, to_a, amount_str)
    if min_receive and q["receive"] < to_units(to_a, min_receive):
        bad("Курс изменился — обновите расчёт", 409)
    s = await get_settings()
    ref = user.get("ref_by") if s["features"]["referral"] else None
    sid = new_id("swp_")
    lines = [(acct(user["_id"]), from_a, -q["amount"]), ("sys:swap", from_a, q["amount"]),
             ("sys:swap", to_a, -q["gross"]), (acct(user["_id"]), to_a, q["receive"])]
    lines += _with_asset(fee_split(q["fee"], ref, s["referral_pct"]), to_a)

    async def fn(sess):
        await post(sess, "swap", lines, idem=f"swap:{user['_id']}:{idem}", ref=sid,
                   meta={"from": from_a, "to": to_a, "rate": str(q["rate"]), "fee": q["fee"], "referrer": ref if q["fee"] else None})
    try:
        await txn(fn)
    except Insufficient:
        bad("Недостаточно средств")
    except Duplicate:
        return {"status": "duplicate"}
    return {"status": "completed", "id": sid, **q["out"]}
