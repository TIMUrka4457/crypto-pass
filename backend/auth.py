import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qsl

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request

from core import db, now, new_id, log, bad

JWT_ALG = "HS256"
ROLE_PERMS = {
    "owner": {"*"},
    "admin": {"view", "freeze", "adjust", "deposits", "withdrawals", "settings", "merchants", "cancel", "broadcast", "aml"},
    "support": {"view", "freeze", "cancel"},
}


def _secret():
    return os.environ["JWT_SECRET"]


def make_token(payload: dict, hours: int) -> str:
    return jwt.encode({**payload, "exp": int(time.time()) + hours * 3600}, _secret(), algorithm=JWT_ALG)


def read_token(token: str, typ: str) -> dict:
    try:
        d = jwt.decode(token, _secret(), algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Сессия истекла")
    if d.get("typ") != typ:
        raise HTTPException(401, "Неверный токен")
    return d


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Требуется вход")
    return authorization[7:]


# ---------------- Telegram ----------------
def verify_init_data(init_data: str) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        bad("Бот не настроен", 503)
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        bad("Неверная подпись Telegram", 401)
    if time.time() - int(pairs.get("auth_date", 0)) > 86400:
        bad("Данные Telegram устарели, откройте приложение заново", 401)
    user = json.loads(pairs.get("user", "{}"))
    if not user.get("id"):
        bad("Нет пользователя", 401)
    return {"user": user, "start_param": pairs.get("start_param")}


async def upsert_tg_user(tg: dict, ref: str | None = None) -> dict:
    uid = str(tg["id"])
    username = (tg.get("username") or "").lower() or None
    upd = {"$set": {"username": username, "first_name": tg.get("first_name", ""), "last_seen": now()},
           "$setOnInsert": {"tg_id": int(tg["id"]), "created_at": now(), "frozen": False}}
    existing = await db.users.find_one({"_id": uid}, {"_id": 1})
    if not existing and ref and ref != uid and await db.users.find_one({"_id": ref}, {"_id": 1}):
        upd["$setOnInsert"]["ref_by"] = ref
    await db.users.update_one({"_id": uid}, upd, upsert=True)
    await db.activity.update_one({"_id": f"{uid}:{now().date().isoformat()}"},
                                 {"$setOnInsert": {"uid": uid, "day": now().date().isoformat()}}, upsert=True)
    return await db.users.find_one({"_id": uid})


async def current_user(authorization: str = Header(None)) -> dict:
    d = read_token(_bearer(authorization), "user")
    u = await db.users.find_one({"_id": d["uid"]})
    if not u:
        raise HTTPException(401, "Пользователь не найден")
    day = now().date().isoformat()
    await db.activity.update_one({"_id": f"{u['_id']}:{day}"}, {"$setOnInsert": {"uid": u["_id"], "day": day}}, upsert=True)
    return u


def not_frozen(u: dict):
    if u.get("frozen"):
        bad("Аккаунт заморожен. Обратитесь в поддержку", 403)


# ---------------- Admin ----------------
def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


async def seed_owner():
    email = os.environ["ADMIN_EMAIL"].strip().lower()
    pw = os.environ["ADMIN_PASSWORD"]
    a = await db.admins.find_one({"email": email})
    if not a:
        await db.admins.insert_one({"_id": new_id("adm_"), "email": email, "password_hash": hash_pw(pw),
                                    "role": "owner", "active": True, "created_at": now()})
    elif not check_pw(pw, a["password_hash"]):
        await db.admins.update_one({"_id": a["_id"]}, {"$set": {"password_hash": hash_pw(pw)}})


async def login_step1(email: str, password: str, ip: str) -> dict:
    email = email.strip().lower()
    key = f"{email}|{ip}"
    lock = await db.login_attempts.find_one({"_id": key})
    if lock and lock.get("locked_until") and lock["locked_until"] > now():
        bad("Слишком много попыток. Попробуйте через 15 минут", 429)
    a = await db.admins.find_one({"email": email, "active": True})
    if not a or not check_pw(password, a["password_hash"]):
        n = (lock or {}).get("count", 0) + 1
        upd = {"count": n, "at": now()}
        if n >= 5:
            upd = {"count": 0, "locked_until": now() + timedelta(minutes=15), "at": now()}
        await db.login_attempts.update_one({"_id": key}, {"$set": upd}, upsert=True)
        bad("Неверный email или пароль", 401)
    await db.login_attempts.delete_one({"_id": key})
    otp = f"{secrets.randbelow(10**6):06d}"
    cid = new_id("otp_")
    await db.otp.insert_one({"_id": cid, "admin_id": a["_id"], "hash": hashlib.sha256(otp.encode()).hexdigest(),
                             "tries": 0, "expires_at": now() + timedelta(minutes=10)})
    if os.environ.get("OTP_DEBUG_LOG") == "true":
        log.warning("ADMIN OTP for %s: %s (OTP_DEBUG_LOG enabled — disable before production)", email, otp)
    from emailer import send_otp
    await send_otp(email, otp)
    return {"challenge_id": cid}


async def login_step2(cid: str, code: str, ip: str) -> dict:
    c = await db.otp.find_one_and_update({"_id": cid, "tries": {"$lt": 5}}, {"$inc": {"tries": 1}})
    if not c or c["expires_at"].replace(tzinfo=now().tzinfo) < now():
        bad("Код недействителен, войдите заново", 401)
    if not hmac.compare_digest(c["hash"], hashlib.sha256(code.strip().encode()).hexdigest()):
        bad("Неверный код", 401)
    await db.otp.delete_one({"_id": cid})
    a = await db.admins.find_one({"_id": c["admin_id"]})
    await audit(a, "login", a["email"], {}, "", ip)
    return {"token": make_token({"typ": "admin", "aid": a["_id"]}, 8), "role": a["role"], "email": a["email"]}


async def current_admin(request: Request, authorization: str = Header(None)) -> dict:
    d = read_token(_bearer(authorization), "admin")
    a = await db.admins.find_one({"_id": d["aid"], "active": True})
    if not a:
        raise HTTPException(401, "Нет доступа")
    a["ip"] = request.client.host if request.client else ""
    return a


def perm(p: str):
    async def dep(a: dict = Depends(current_admin)) -> dict:
        perms = ROLE_PERMS.get(a["role"], set())
        if "*" not in perms and p not in perms:
            raise HTTPException(403, "Недостаточно прав для этого действия")
        return a
    return dep


async def audit(admin: dict, action: str, target: str, details: dict, comment: str, ip: str = "", session=None):
    await db.audit_log.insert_one({"_id": new_id("aud_"), "admin_id": admin["_id"], "admin_email": admin["email"],
                                   "action": action, "target": target, "details": details, "comment": comment,
                                   "ip": ip or admin.get("ip", ""), "at": now()}, session=session)


# ---------------- Merchant API key ----------------
def hash_key(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


async def current_merchant(x_api_key: str = Header(None)) -> dict:
    if not x_api_key:
        raise HTTPException(401, "Нужен заголовок X-API-Key")
    k = await db.api_keys.find_one({"hash": hash_key(x_api_key), "revoked": False})
    if not k:
        raise HTTPException(401, "Неверный или отозванный API-ключ")
    m = await db.merchants.find_one({"_id": k["merchant_id"], "status": "approved"})
    if not m:
        raise HTTPException(403, "Мерчант не одобрен")
    u = await db.users.find_one({"_id": m["user_id"]})
    not_frozen(u)
    await db.api_keys.update_one({"_id": k["_id"]}, {"$set": {"last_used": now()}})
    return {"merchant": m, "user": u}
