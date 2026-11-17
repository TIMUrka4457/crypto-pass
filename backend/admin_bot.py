"""Separate Telegram bot for staff: login with email+password+OTP once, then manage from Telegram."""
import asyncio
import os
from datetime import timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)
from fastapi import HTTPException

from auth import ROLE_PERMS, login_step1, login_step2, audit
from core import db, ASSETS, fmt, log, now, get_settings
from services import units0
import routes_admin as ra

_bot: Bot | None = None
router = Router()
SOURCE = "admin-bot"

B_STATS, B_WD, B_USERS, B_HOT, B_BC, B_OUT = "Статистика", "Выводы", "Пользователи", "Горячий кошелёк", "Рассылка", "Выйти"
MENU = ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True, keyboard=[
    [KeyboardButton(text=B_STATS), KeyboardButton(text=B_HOT)],
    [KeyboardButton(text=B_WD), KeyboardButton(text=B_USERS)],
    [KeyboardButton(text=B_BC), KeyboardButton(text=B_OUT)]])
CANCEL = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="x")]])


class Login(StatesGroup):
    email = State()
    password = State()
    code = State()


class Act(StatesGroup):
    reason = State()
    query = State()
    broadcast = State()
    broadcast_confirm = State()


def enabled() -> bool:
    return bool(os.environ.get("ADMIN_BOT_TOKEN"))


def get_bot() -> Bot | None:
    global _bot
    if _bot is None and enabled():
        _bot = Bot(os.environ["ADMIN_BOT_TOKEN"])
    return _bot


def can(a: dict, p: str) -> bool:
    perms = ROLE_PERMS.get(a["role"], set())
    return "*" in perms or p in perms


async def staff(tg_id: int) -> dict | None:
    a = await db.admins.find_one({"tg_id": tg_id, "active": True})
    if a:
        a["ip"] = SOURCE
    return a


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in r] for r in rows])


async def guard(ev, p: str = "view") -> dict | None:
    a = await staff(ev.from_user.id)
    reply = ev.message.answer if isinstance(ev, CallbackQuery) else ev.answer
    if not a:
        await reply("Нужен вход. Нажмите /start.", reply_markup=ReplyKeyboardRemove())
        return None
    if not can(a, p):
        await reply("Недостаточно прав для этого действия.")
        return None
    return a


# ---------------- login ----------------
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    a = await staff(msg.from_user.id)
    if a:
        return await msg.answer(f"Вы вошли как {a['email']} ({a['role']}).", reply_markup=MENU)
    await state.set_state(Login.email)
    await msg.answer("Панель управления EasyCrypto. Вход только для сотрудников.\n\nВведите рабочий email:",
                     reply_markup=ReplyKeyboardRemove())


@router.message(Login.email)
async def login_email(msg: Message, state: FSMContext):
    await state.update_data(email=(msg.text or "").strip().lower())
    await state.set_state(Login.password)
    await msg.answer("Введите пароль. Сообщение с паролем будет сразу удалено.")


@router.message(Login.password)
async def login_password(msg: Message, state: FSMContext):
    pw = msg.text or ""
    try:
        await msg.delete()
    except Exception:
        pass
    d = await state.get_data()
    try:
        r = await login_step1(d["email"], pw, f"{SOURCE}:{msg.from_user.id}")
    except HTTPException as e:
        await state.clear()
        return await msg.answer(f"{e.detail}. Начните заново: /start")
    await state.update_data(cid=r["challenge_id"])
    await state.set_state(Login.code)
    await msg.answer("Отправили 6-значный код на почту. Введите его:")


@router.message(Login.code)
async def login_code(msg: Message, state: FSMContext):
    d = await state.get_data()
    try:
        r = await login_step2(d["cid"], (msg.text or "").strip(), f"{SOURCE}:{msg.from_user.id}")
    except HTTPException as e:
        if e.detail == "Неверный код":
            return await msg.answer("Неверный код, попробуйте ещё раз:")
        await state.clear()
        return await msg.answer(f"{e.detail}. Начните заново: /start")
    await state.clear()
    await db.admins.update_many({"tg_id": msg.from_user.id}, {"$unset": {"tg_id": ""}})
    await db.admins.update_one({"email": r["email"]}, {"$set": {"tg_id": msg.from_user.id}})
    a = await staff(msg.from_user.id)
    await audit(a, "admin_bot_link", a["email"], {"tg_id": msg.from_user.id}, "", SOURCE)
    await msg.answer(f"Готово, вы вошли как {r['email']} ({r['role']}). Сюда же будут приходить уведомления.",
                     reply_markup=MENU)


@router.message(F.text == B_OUT)
@router.message(Command("logout"))
async def logout(msg: Message, state: FSMContext):
    await state.clear()
    a = await staff(msg.from_user.id)
    if a:
        await db.admins.update_one({"_id": a["_id"]}, {"$unset": {"tg_id": ""}})
        await audit(a, "admin_bot_unlink", a["email"], {}, "", SOURCE)
    await msg.answer("Вы вышли. Уведомления больше не приходят. Войти снова: /start", reply_markup=ReplyKeyboardRemove())


@router.callback_query(F.data == "x")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text("Отменено.")


# ---------------- stats & hot wallet ----------------
@router.message(F.text == B_STATS)
async def stats(msg: Message, state: FSMContext):
    await state.clear()
    a = await guard(msg)
    if not a:
        return
    s = await ra.stats(a=a, days=14)
    turnover = "\n".join(f"  {ASSETS[k]['title']}: {v}" for k, v in s["turnover"].items())
    fees = "\n".join(f"  {ASSETS[k]['title']}: {v}" for k, v in s["fees"].items())
    alerts = "\n".join(f"• {x}" for x in s["hot_alerts"]) or "нет"
    await msg.answer(f"Статистика\n\nПользователей: {s['users']}\nАктивны сегодня: {s['dau_today']}\n"
                     f"Выводы ждут одобрения: {s['pending_withdrawals']}\nВыводы в обработке: {s['processing_withdrawals']}\n"
                     f"Статус неизвестен: {s['unknown_withdrawals']}\nМерчанты на одобрении: {s['pending_merchants']}\n"
                     f"Сверка журнала: {'OK' if s['reconcile_ok'] else ('—' if s['reconcile_ok'] is None else 'ОШИБКА')}\n\n"
                     f"Оборот за 14 дней:\n{turnover}\n\nКомиссии за 14 дней:\n{fees}\n\nАлерты:\n{alerts}", reply_markup=MENU)


@router.message(F.text == B_HOT)
async def hot(msg: Message, state: FSMContext):
    await state.clear()
    a = await guard(msg)
    if not a:
        return
    await msg.answer("Обновляю балансы…")
    s = await ra.hot_wallet(a=a, refresh=True)
    rows = [f"{ASSETS[k]['title']}: {v['balance'] if v['balance'] is not None else 'нет данных'} "
            f"(обязательства {v['liabilities']}, порог {v['alert_threshold']})\n<code>{v['address']}</code>"
            for k, v in s["assets"].items()]
    trx = f"\nTRX на газ: {s['trx_balance']}" if s.get("trx_balance") else ""
    alerts = "\n".join(f"• {x}" for x in s["alerts"]) or "нет"
    await msg.answer("Горячий кошелёк\n\n" + "\n\n".join(rows) + trx + f"\n\nАлерты:\n{alerts}", parse_mode="HTML",
                     reply_markup=MENU)


# ---------------- withdrawals ----------------
def wd_text(w: dict) -> str:
    return (f"Вывод {w['amount']} {ASSETS[w['asset']]['title']}\nПользователь: {w['user_id']}\n"
            f"Адрес: <code>{w['address']}</code>\nСтатус: {w['status_text']}\nСоздан: {w['created_at'][:16].replace('T', ' ')} UTC")


def wd_kb(wid: str) -> InlineKeyboardMarkup:
    return kb([("Одобрить", f"wa:{wid}"), ("Отклонить", f"wr:{wid}")])


@router.message(F.text == B_WD)
async def wds(msg: Message, state: FSMContext):
    await state.clear()
    a = await guard(msg)
    if not a:
        return
    items = (await ra.withdrawals(a=a, status="pending_approval"))[:10]
    if not items:
        return await msg.answer("Нет выводов, ожидающих одобрения.", reply_markup=MENU)
    for w in items:
        await msg.answer(wd_text(w), parse_mode="HTML", reply_markup=wd_kb(w["id"]) if can(a, "withdrawals") else None)


@router.callback_query(F.data.startswith("wa:"))
async def wd_approve(cb: CallbackQuery):
    await cb.answer()
    a = await guard(cb, "withdrawals")
    if not a:
        return
    try:
        await ra.wd_approve(cb.data[3:], ra.Comment(comment=f"Одобрено в админ-боте ({a['email']})"), a=a)
    except HTTPException as e:
        return await cb.message.edit_text(f"{cb.message.html_text}\n\n{e.detail}", parse_mode="HTML")
    await cb.message.edit_text(f"{cb.message.html_text}\n\nОДОБРЕНО: {a['email']}", parse_mode="HTML")


@router.callback_query(F.data.startswith(("wr:", "uf:", "uu:")))
async def ask_reason(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    a = await guard(cb, "withdrawals" if cb.data.startswith("wr:") else "freeze")
    if not a:
        return
    await state.set_state(Act.reason)
    await state.update_data(act=cb.data[:2], target=cb.data[3:])
    what = {"wr": "отклонения вывода", "uf": "заморозки", "uu": "разморозки"}[cb.data[:2]]
    await cb.message.answer(f"Укажите причину {what} (попадёт в журнал):", reply_markup=CANCEL)


@router.message(Act.reason)
async def do_reason(msg: Message, state: FSMContext):
    d = await state.get_data()
    reason = (msg.text or "").strip()
    if len(reason) < 3:
        return await msg.answer("Причина — минимум 3 символа:", reply_markup=CANCEL)
    await state.clear()
    a = await guard(msg, "withdrawals" if d["act"] == "wr" else "freeze")
    if not a:
        return
    try:
        if d["act"] == "wr":
            await ra.wd_reject(d["target"], ra.Comment(comment=reason), a=a)
            text = "Вывод отклонён, средства возвращены пользователю."
        else:
            await ra.freeze(d["target"], ra.FreezeIn(comment=reason, frozen=d["act"] == "uf"), a=a)
            text = "Пользователь заморожен." if d["act"] == "uf" else "Пользователь разморожен."
    except HTTPException as e:
        text = f"Не получилось: {e.detail}"
    await msg.answer(text, reply_markup=MENU)


# ---------------- users ----------------
@router.message(F.text == B_USERS)
async def users_begin(msg: Message, state: FSMContext):
    await state.clear()
    if not await guard(msg):
        return
    await state.set_state(Act.query)
    await msg.answer("Введите @username, Telegram ID или имя пользователя:", reply_markup=CANCEL)


@router.message(Act.query)
async def users_find(msg: Message, state: FSMContext):
    await state.clear()
    a = await guard(msg)
    if not a:
        return
    r = await ra.users(a=a, q=(msg.text or "").strip(), skip=0)
    if not r["items"]:
        return await msg.answer("Никого не нашли.", reply_markup=MENU)
    rows = [[(f"{'@' + u['username'] if u.get('username') else u.get('first_name') or u['id']} · {u['id']}"
              + (" · заморожен" if u.get("frozen") else ""), f"u:{u['id']}")] for u in r["items"][:8]]
    await msg.answer(f"Найдено: {r['total']}", reply_markup=kb(*rows))


@router.callback_query(F.data.startswith("u:"))
async def user_card(cb: CallbackQuery):
    await cb.answer()
    a = await guard(cb)
    if not a:
        return
    try:
        d = await ra.user_detail(cb.data[2:], a=a)
    except HTTPException as e:
        return await cb.message.answer(e.detail)
    u = d["user"]
    bals = "\n".join(f"  {ASSETS[k]['title']}: {v['available']}" + (f" (в обработке {v['hold']})" if v["hold"] != "0" else "")
                     for k, v in d["balances"].items())
    wds = "\n".join(f"  {w['amount']} {ASSETS[w['asset']]['title']} — {w['status_text']}" for w in d["withdrawals"][:5]) or "  нет"
    text = (f"{'@' + u['username'] if u.get('username') else u.get('first_name', '')}\nID: {u['id']}\n"
            f"Статус: {'ЗАМОРОЖЕН' if u.get('frozen') else 'активен'}\nРефералов: {d['referrals']}\n\n"
            f"Баланс:\n{bals}\n\nПоследние выводы:\n{wds}")
    btn = None
    if can(a, "freeze"):
        btn = kb([("Разморозить", f"uu:{u['id']}")] if u.get("frozen") else [("Заморозить", f"uf:{u['id']}")])
    await cb.message.answer(text, reply_markup=btn)


# ---------------- broadcasts ----------------
@router.message(F.text == B_BC)
async def bc_begin(msg: Message, state: FSMContext):
    await state.clear()
    if not await guard(msg, "broadcast"):
        return
    await state.set_state(Act.broadcast)
    await msg.answer("Пришлите текст рассылки для всех пользователей кошелька:", reply_markup=CANCEL)


@router.message(Act.broadcast)
async def bc_text(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if not text:
        return await msg.answer("Нужен текст:", reply_markup=CANCEL)
    await state.update_data(text=text[:4000])
    await state.set_state(Act.broadcast_confirm)
    n = await db.users.count_documents({})
    await msg.answer(f"Предпросмотр:\n\n{text[:4000]}\n\nОтправить {n} пользователям?",
                     reply_markup=kb([("Отправить", "bc_ok"), ("Отмена", "x")]))


@router.callback_query(Act.broadcast_confirm, F.data == "bc_ok")
async def bc_ok(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    await cb.answer()
    a = await guard(cb, "broadcast")
    if not a:
        return
    try:
        await ra.broadcast_new(ra.BroadcastIn(text=d["text"]), a=a)
    except HTTPException as e:
        return await cb.message.edit_text(f"Не получилось: {e.detail}")
    await cb.message.edit_text("Рассылка поставлена в очередь. Итог можно посмотреть в веб-панели.")


@router.message()
async def other(msg: Message):
    a = await staff(msg.from_user.id)
    await msg.answer("Выберите действие в меню." if a else "Нужен вход: /start", reply_markup=MENU if a else None)


# ---------------- notifications ----------------
async def _notify(text: str, perm: str = "view", markup=None):
    b = get_bot()
    if not b:
        return
    async for a in db.admins.find({"active": True, "tg_id": {"$exists": True}}):
        if not can(a, perm):
            continue
        try:
            await b.send_message(a["tg_id"], text, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            log.info("admin notify %s failed: %s", a["email"], e)


async def notify_job():
    if not enabled():
        return
    from services import public_wd
    recent = now() - timedelta(hours=1)
    flt = {"status": "pending_approval", "admin_notified": {"$ne": True}, "created_at": {"$gte": recent}}
    async for w in db.withdrawals.find(flt).limit(20):
        await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {"admin_notified": True}})
        p = {**public_wd(w), "user_id": w["user_id"]}
        await _notify("Новый вывод ждёт одобрения\n\n" + wd_text(p), "withdrawals", wd_kb(w["_id"]))
    async for w in db.withdrawals.find({"status": "unknown", "unknown_notified": {"$ne": True}}).limit(20):
        await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {"unknown_notified": True}})
        await _notify(f"Внимание: статус вывода {w['_id']} неизвестен — проверьте транзакцию в обозревателе "
                      f"и в веб-панели.", "withdrawals")
    s = await get_settings()
    async for d in db.deposits.find({"status": "credited", "admin_notified": {"$ne": True}, "created_at": {"$gte": recent}}).limit(50):
        await db.deposits.update_one({"_id": d["_id"]}, {"$set": {"admin_notified": True}})
        if d["amount"] >= units0(d["asset"], s["assets"][d["asset"]]["auto_approve_limit"]):
            await _notify(f"Крупный депозит: {fmt(d['asset'], d['amount'])} {ASSETS[d['asset']]['title']}\n"
                          f"Владелец: {d['owner_type']} {d['owner_id']}\nTx: <code>{d['tx_hash']}</code>")
    snap = await db.hot_wallet.find_one({"_id": "snapshot"}) or {}
    alerts = snap.get("alerts") or []
    sent = await db.hot_wallet.find_one({"_id": "alerts_notified"}) or {}
    if alerts and alerts != sent.get("alerts"):
        await _notify("Алерты горячего кошелька:\n" + "\n".join(f"• {x}" for x in alerts))
    if alerts != sent.get("alerts"):
        await db.hot_wallet.update_one({"_id": "alerts_notified"}, {"$set": {"alerts": alerts}}, upsert=True)


async def run_polling(stop: asyncio.Event):
    if not enabled():
        log.warning("ADMIN_BOT_TOKEN not set — admin bot disabled")
        return
    from workers import lease
    dp = Dispatcher()
    dp.include_router(router)
    b = get_bot()
    while not stop.is_set():
        if not await lease("admin_bot", 60):
            await asyncio.sleep(20)
            continue
        task = asyncio.create_task(dp.start_polling(b, handle_signals=False))
        while not stop.is_set() and not task.done():
            await asyncio.sleep(20)
            if not await lease("admin_bot", 60):
                break
        await dp.stop_polling() if not task.done() else None
        task.cancel()
