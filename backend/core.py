import os
import uuid
import logging
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
log = logging.getLogger("wallet")

ASSETS = {
    "TON": {"network": "ton", "decimals": 9, "title": "TON"},
    "USDT_TON": {"network": "ton", "decimals": 6, "title": "USDT (TON)"},
    "USDT_TRC20": {"network": "tron", "decimals": 6, "title": "USDT (TRC20)"},
}
NETWORKS = ["ton", "tron"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:20]


def code(n: int = 12) -> str:
    return secrets.token_urlsafe(n)[:n]


def iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


def bad(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def check_asset(asset: str) -> dict:
    if asset not in ASSETS:
        bad("Неизвестный актив")
    return ASSETS[asset]


def to_units(asset: str, value) -> int:
    dec = check_asset(asset)["decimals"]
    try:
        d = Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        bad("Некорректная сумма")
    units = d * (Decimal(10) ** dec)
    if units != units.to_integral_value() or units <= 0:
        bad("Некорректная сумма")
    return int(units)


def fmt(asset: str, units: int) -> str:
    dec = ASSETS[asset]["decimals"]
    d = Decimal(int(units)) / (Decimal(10) ** dec)
    s = format(d.quantize(Decimal(1) / (Decimal(10) ** dec)), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


DEFAULT_SETTINGS = {
    "networks": {
        "ton": {"enabled": True, "confirmations": 3},
        "tron": {"enabled": True, "confirmations": 20},
    },
    "assets": {
        "TON": {"deposit_enabled": True, "withdraw_enabled": True, "withdraw_fee": "0.05", "withdraw_min": "0.5", "deposit_fee": "0",
                "per_op_limit": "100", "daily_limit": "300", "auto_approve_limit": "20", "sweep_threshold": "2",
                "hot_alert": "50"},
        "USDT_TON": {"deposit_enabled": True, "withdraw_enabled": True, "withdraw_fee": "0.3", "withdraw_min": "2", "deposit_fee": "0",
                     "per_op_limit": "500", "daily_limit": "1000", "auto_approve_limit": "50", "sweep_threshold": "10",
                     "hot_alert": "200"},
        "USDT_TRC20": {"deposit_enabled": True, "withdraw_enabled": True, "withdraw_fee": "2.5", "withdraw_min": "10", "deposit_fee": "1",
                       "per_op_limit": "500", "daily_limit": "1000", "auto_approve_limit": "50", "sweep_threshold": "50",
                       "hot_alert": "200"},
    },
    "features": {"transfers": True, "checks": True, "invoices": True, "merchant": True, "referral": True, "swap": True},
    "swap": {"fee_pct": "1.0", "min_usd": "1", "max_usd": "1000"},
    "cold": {"ton": "", "tron": "", "auto": False, "max_pct": "15", "target_pct": "8"},
    "security": {"withdrawals_paused": False, "outflow_alert_usd": "2000"},
    "merchant_fee_pct": "1.0",
    "referral_pct": "20",
    "aml": {"enabled": True, "risk_threshold": "0.5"},
    "check_claims_per_minute": 5,
    "gas": {"ton_jetton_sweep": "0.1", "tron_trx_topup": "30"},
    "fees": {"dynamic": True, "gas_margin_pct": "15", "profit_usdt": "0.3", "ton_jetton_gas": "0.05",
             "tron_energy_existing": 65000, "tron_energy_new": 131000, "hot_trx_alert": "100"},
}


def _merge(base: dict, over: dict) -> dict:
    out = deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


async def get_settings() -> dict:
    doc = await db.settings.find_one({"_id": "global"}) or {}
    doc.pop("_id", None)
    return _merge(DEFAULT_SETTINGS, doc)


async def require_feature(name: str):
    s = await get_settings()
    if not s["features"].get(name):
        bad("Функция временно отключена", 503)
