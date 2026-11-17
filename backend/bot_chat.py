"""Wallet features inside the Telegram chat (no Mini App needed)."""
import io
import uuid

import qrcode
from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo)
from fastapi import HTTPException

import bot
from auth import upsert_tg_user, not_frozen
from checks import create_check, claim_check, public_check
from core import db, ASSETS, NETWORKS, fmt, to_units, get_settings, require_feature
from ledger import user_balances, acct
from services import (transfer, create_withdrawal, public_wd, deposit_address, find_user_by_username,
                      create_invoice, pay_invoice, public_invoice)

router = Router()

B_BAL, B_HIST, B_DEP, B_WD = "Баланс", "История", "Пополнить", "Вывести"
B_TR, B_CHK, B_INV, B_APP = "Перевести", "Чек", "Счёт", "Открыть кошелёк"
MENU = ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True, keyboard=[
    [KeyboardButton(text=B_BAL), KeyboardButton(text=B_HIST)],
    [KeyboardButton(text=B_DEP), KeyboardButton(text=B_WD)],
    [KeyboardButton(text=B_TR), KeyboardButton(text=B_CHK)],
    [KeyboardButton(text=B_INV), KeyboardButton(text=B_APP)]])
CANCEL_KB = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="x")]])
FLOW_TITLE = {"tr": "перевода", "wd": "вывода", "ck": "чека", "iv": "счёта"}


class Tr(StatesGroup):
    username = State()
    amount = State()
    comment = State()
    confirm = State()


class Wd(StatesGroup):
    address = State()
    amount = State()
    confirm = State()


class Ck(StatesGroup):
    amount = State()
    confirm = State()


class Iv(StatesGroup):
    amount = State()
    desc = State()


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in r] for r in rows])


def app_kb(text: str, param: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=bot.miniapp_url(param)))]])


CONFIRM_KB = kb([("Подтвердить", "ok"), ("Отмена", "x")])


async def me(ev) -> dict:
    return await upsert_tg_user(ev.from_user.model_dump())


def err(e: HTTPException) -> str:
    return f"Не получилось: {e.detail}"


def asset_kb(flow: str) -> InlineKeyboardMarkup:
    return kb([(ASSETS[a]["title"], f"as:{flow}:{a}") for a in ASSETS], [("Отмена", "x")])


# ---------------- start & menu ----------------
@router.message(CommandStart())
async def start(msg: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    arg = command.args or ""
    u = await upsert_tg_user(msg.from_user.model_dump(), arg[2:] if arg.startswith("r_") else None)
    if arg.startswith("c_"):
        return await show_check(msg, u, arg[2:])
    if arg.startswith("i_"):
        return await show_invoice(msg, u, arg[2:])
    await msg.answer("Кошелёк готов. Храните TON и USDT, переводите друзьям по @username, создавайте чеки и счета — "
                     "прямо здесь, кнопками ниже, или в приложении.", reply_markup=MENU)
    await msg.answer("Полная версия кошелька:", reply_markup=app_kb("Открыть кошелёк"))


@router.message(Command("cancel"))
@router.callback_query(F.data == "x")
async def cancel(ev, state: FSMContext):
    await state.clear()
    if isinstance(ev, CallbackQuery):
        await ev.answer()
        return await ev.message.edit_text("Отменено.")
    await ev.answer("Отменено.", reply_markup=MENU)


@router.message(F.text == B_APP)
async def open_app(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Откройте полную версию кошелька:", reply_markup=app_kb("Открыть кошелёк"))


@router.message(F.text == B_BAL)
async def balance(msg: Message, state: FSMContext):
    await state.clear()
    u = await me(msg)
    b = await user_balances(u["_id"])
    lines = [f"{ASSETS[a]['title']}: {fmt(a, v['available'])}" + (f"  (в обработке {fmt(a, v['hold'])})" if v["hold"] else "")
             for a, v in b.items()]
    await msg.answer("Ваш баланс\n\n" + "\n".join(lines) + ("\n\nАккаунт заморожен." if u.get("frozen") else ""),
                     reply_markup=MENU)


@router.message(F.text == B_HIST)
async def history(msg: Message, state: FSMContext):
    await state.clear()
    from routes_user import history_rows
    u = await me(msg)
    a = acct(u["_id"])
    docs = await db.journal.find({"entries.account": a}).sort("created_at", -1).limit(10).to_list(10)
    rows = history_rows(docs, {a})
    if not rows:
        return await msg.answer("Операций пока нет.", reply_markup=MENU)
    text = "\n".join(f"{r['created_at'][:16].replace('T', ' ')}  {r['kind_text']}  {r['sign']}{r['amount']} "
                     f"{ASSETS[r['asset']]['title']}" for r in rows)
    await msg.answer("Последние операции (UTC)\n\n" + text, reply_markup=MENU)


# ---------------- deposit ----------------
@router.message(F.text == B_DEP)
async def deposit(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Выберите сеть для пополнения:", reply_markup=kb(
        [("TON · USDT TON", "dep:ton"), ("TRON · USDT TRC20", "dep:tron")]))


@router.callback_query(F.data.startswith("dep:"))
async def deposit_net(cb: CallbackQuery):
    net = cb.data[4:]
    await cb.answer()
    if net not in NETWORKS:
        return
    u = await me(cb)
    try:
        not_frozen(u)
        s = await get_settings()
        if not s["networks"][net]["enabled"]:
            return await cb.message.answer("Сеть временно отключена.")
        d = await deposit_address("user", u["_id"], net)
    except HTTPException as e:
        return await cb.message.answer(err(e))
    buf = io.BytesIO()
    qrcode.make(d["address"]).save(buf, format="PNG")
    assets = ", ".join(ASSETS[a]["title"] for a, m in ASSETS.items() if m["network"] == net)
    await cb.message.answer_photo(BufferedInputFile(buf.getvalue(), "address.png"), caption=(
        f"Адрес для пополнения ({assets}):\n\n<code>{d['address']}</code>\n\n"
        f"Отправляйте только {assets} в сети {'TON' if net == 'ton' else 'TRON'}. "
        f"Зачисление после {s['networks'][net]['confirmations']} подтверждений."), parse_mode="HTML")


# ---------------- choose asset (shared) ----------------
async def begin(msg: Message, state: FSMContext, flow: str, feature: str | None):
    await state.clear()
    try:
        if feature:
            await require_feature(feature)
        not_frozen(await me(msg))
    except HTTPException as e:
        return await msg.answer(err(e))
    await msg.answer(f"Выберите актив для {FLOW_TITLE[flow]}:", reply_markup=asset_kb(flow))


@router.message(F.text == B_TR)
async def tr_begin(msg: Message, state: FSMContext):
    await begin(msg, state, "tr", "transfers")


@router.message(F.text == B_WD)
async def wd_begin(msg: Message, state: FSMContext):
    await begin(msg, state, "wd", None)


@router.message(F.text == B_CHK)
async def ck_begin(msg: Message, state: FSMContext):
    await begin(msg, state, "ck", "checks")


@router.message(F.text == B_INV)
async def iv_begin(msg: Message, state: FSMContext):
    await begin(msg, state, "iv", "invoices")


@router.callback_query(F.data.startswith("as:"))
async def asset_chosen(cb: CallbackQuery, state: FSMContext):
    _, flow, asset = cb.data.split(":")
    await cb.answer()
    if asset not in ASSETS:
        return
    await state.set_data({"asset": asset, "idem": uuid.uuid4().hex})
    t = ASSETS[asset]["title"]
    if flow == "tr":
        await state.set_state(Tr.username)
        await cb.message.edit_text(f"Перевод {t}. Введите @username получателя:", reply_markup=CANCEL_KB)
    elif flow == "wd":
        await state.set_state(Wd.address)
        net = "TON" if ASSETS[asset]["network"] == "ton" else "TRON"
        await cb.message.edit_text(f"Вывод {t}. Введите адрес кошелька в сети {net}:", reply_markup=CANCEL_KB)
    elif flow == "ck":
        await state.set_state(Ck.amount)
        await cb.message.edit_text(f"Чек в {t}. Введите сумму чека:", reply_markup=CANCEL_KB)
    elif flow == "iv":
        await state.set_state(Iv.amount)
        await cb.message.edit_text(f"Счёт в {t}. Введите сумму к оплате:", reply_markup=CANCEL_KB)


async def read_amount(msg: Message, asset: str) -> str | None:
    v = (msg.text or "").strip().replace(",", ".")
    try:
        to_units(asset, v)
        return v
    except HTTPException as e:
        await msg.answer(f"{e.detail}. Введите сумму числом, например 1.5", reply_markup=CANCEL_KB)
        return None


# ---------------- transfer ----------------
@router.message(Tr.username)
async def tr_username(msg: Message, state: FSMContext):
    try:
        to = await find_user_by_username(msg.text or "")
    except HTTPException as e:
        return await msg.answer(e.detail + ". Введите другой @username:", reply_markup=CANCEL_KB)
    await state.update_data(to=to["_id"], to_name=to.get("username"))
    await state.set_state(Tr.amount)
    await msg.answer("Введите сумму перевода:", reply_markup=CANCEL_KB)


@router.message(Tr.amount)
async def tr_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if v:
        await state.update_data(amount=v)
        await state.set_state(Tr.comment)
        await msg.answer("Комментарий к переводу (или «-» без комментария):", reply_markup=CANCEL_KB)


@router.message(Tr.comment)
async def tr_comment(msg: Message, state: FSMContext):
    c = (msg.text or "").strip()
    await state.update_data(comment="" if c == "-" else c[:200])
    await state.set_state(Tr.confirm)
    d = await state.get_data()
    await msg.answer(f"Перевести {d['amount']} {ASSETS[d['asset']]['title']} пользователю @{d['to_name']}?\n"
                     f"Комиссия: 0", reply_markup=CONFIRM_KB)


@router.callback_query(Tr.confirm, F.data == "ok")
async def tr_ok(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    await cb.answer()
    u = await me(cb)
    to = await db.users.find_one({"_id": d["to"]})
    try:
        not_frozen(u)
        r = await transfer(u, to, d["asset"], d["amount"], d["idem"], d.get("comment", ""), via="bot")
    except HTTPException as e:
        return await cb.message.edit_text(err(e))
    await cb.message.edit_text(f"Готово: {r.get('amount', d['amount'])} {ASSETS[d['asset']]['title']} отправлено @{d['to_name']}.")


# ---------------- withdraw ----------------
@router.message(Wd.address)
async def wd_address(msg: Message, state: FSMContext):
    import chains
    d = await state.get_data()
    addr = (msg.text or "").strip()
    if not chains.valid_address(ASSETS[d["asset"]]["network"], addr):
        return await msg.answer("Некорректный адрес. Проверьте и введите ещё раз:", reply_markup=CANCEL_KB)
    await state.update_data(address=addr)
    cfg = (await get_settings())["assets"][d["asset"]]
    await state.set_state(Wd.amount)
    await msg.answer(f"Введите сумму вывода.\nМинимум {cfg['withdraw_min']}, комиссия сети {cfg['withdraw_fee']} "
                     f"{ASSETS[d['asset']]['title']}.", reply_markup=CANCEL_KB)


@router.message(Wd.amount)
async def wd_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if not v:
        return
    await state.update_data(amount=v)
    await state.set_state(Wd.confirm)
    cfg = (await get_settings())["assets"][d["asset"]]
    t = ASSETS[d["asset"]]["title"]
    await msg.answer(f"Вывести {v} {t}\nна адрес <code>{d['address']}</code>?\n\nКомиссия {cfg['withdraw_fee']} {t} "
                     f"спишется дополнительно. Перевод в блокчейне необратим — проверьте адрес.",
                     reply_markup=CONFIRM_KB, parse_mode="HTML")


@router.callback_query(Wd.confirm, F.data == "ok")
async def wd_ok(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    await cb.answer()
    try:
        w = public_wd_safe(await create_withdrawal(await me(cb), d["asset"], d["address"], d["amount"], d["idem"], source="bot"))
    except HTTPException as e:
        return await cb.message.edit_text(err(e))
    await cb.message.edit_text(f"Заявка на вывод создана: {w['amount']} {ASSETS[w['asset']]['title']}.\n"
                               f"Статус: {w['status_text']}. Пришлём уведомление, когда средства уйдут.")


def public_wd_safe(w: dict) -> dict:
    return w if "status_text" in w else public_wd(w)


# ---------------- checks ----------------
@router.message(Ck.amount)
async def ck_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if v:
        await state.update_data(amount=v)
        await state.set_state(Ck.confirm)
        await msg.answer(f"Создать чек на {v} {ASSETS[d['asset']]['title']}? Сумма спишется с баланса и вернётся, "
                         f"если чек отменить.", reply_markup=CONFIRM_KB)


@router.callback_query(Ck.confirm, F.data == "ok")
async def ck_ok(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    await cb.answer()
    try:
        u = await me(cb)
        not_frozen(u)
        c = await create_check(u, {"asset": d["asset"], "amount": d["amount"], "kind": "personal"})
    except HTTPException as e:
        return await cb.message.edit_text(err(e))
    link = public_check(c, await bot.username(), True)["link"]
    await cb.message.edit_text(f"Чек на {d['amount']} {ASSETS[d['asset']]['title']} создан.\n"
                               f"Отправьте ссылку получателю:\n{link}\n\nЧеки с условиями — в приложении.")


async def show_check(msg: Message, u: dict, check_code: str):
    c = await db.checks.find_one({"code": check_code})
    if not c or c["status"] != "active":
        return await msg.answer("Чек не найден или уже использован.", reply_markup=MENU)
    t = f"Чек на {fmt(c['asset'], c['amount_per'])} {ASSETS[c['asset']]['title']}" + (f"\n{c['description']}" if c.get("description") else "")
    if c.get("password_hash") or c.get("captcha"):
        return await msg.answer(t + "\n\nДля этого чека нужно пройти проверку в приложении.",
                                reply_markup=app_kb("Забрать чек", f"c_{check_code}"))
    await msg.answer(t, reply_markup=kb([("Забрать чек", f"claim:{check_code}")]))


@router.callback_query(F.data.startswith("claim:"))
async def claim(cb: CallbackQuery):
    await cb.answer()
    try:
        u = await me(cb)
        not_frozen(u)
        await require_feature("checks")
        r = await claim_check(u, cb.data[6:], {})
    except HTTPException as e:
        return await cb.message.edit_text(err(e))
    await cb.message.edit_text(f"Зачислено {r['amount']} {ASSETS[r['asset']]['title']}.")


# ---------------- invoices ----------------
@router.message(Iv.amount)
async def iv_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if v:
        await state.update_data(amount=v)
        await state.set_state(Iv.desc)
        await msg.answer("За что счёт? Короткое описание (или «-»):", reply_markup=CANCEL_KB)


@router.message(Iv.desc)
async def iv_desc(msg: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    desc = (msg.text or "").strip()
    try:
        u = await me(msg)
        not_frozen(u)
        inv = await create_invoice(u, d["asset"], d["amount"], "" if desc == "-" else desc)
    except HTTPException as e:
        return await msg.answer(err(e), reply_markup=MENU)
    url = public_invoice(inv, await bot.username())["pay_url"]
    await msg.answer(f"Счёт на {d['amount']} {ASSETS[d['asset']]['title']} создан.\nСсылка для оплаты:\n{url}",
                     reply_markup=MENU)


async def show_invoice(msg: Message, u: dict, inv_code: str):
    inv = await db.invoices.find_one({"code": inv_code})
    if not inv or inv["status"] != "active":
        return await msg.answer("Счёт не найден или уже закрыт.", reply_markup=MENU)
    t = ASSETS[inv["asset"]]["title"]
    amount = fmt(inv["asset"], inv["amount"])
    await msg.answer(f"Счёт #{inv['code']}: {amount} {t}" + (f"\n{inv['description']}" if inv.get("description") else ""),
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                         [InlineKeyboardButton(text=f"Оплатить {amount} {t} с баланса", callback_data=f"pay:{inv_code}")],
                         [InlineKeyboardButton(text="Другие способы оплаты", web_app=WebAppInfo(url=bot.miniapp_url(f"i_{inv_code}")))]]))


@router.callback_query(F.data.startswith("pay:"))
async def pay(cb: CallbackQuery):
    await cb.answer()
    try:
        u = await me(cb)
        not_frozen(u)
        await require_feature("invoices")
        await pay_invoice(u, cb.data[4:])
    except HTTPException as e:
        return await cb.message.edit_text(err(e))
    await cb.message.edit_text("Счёт оплачен.")


@router.callback_query(F.data == "ok")
async def stale_confirm(cb: CallbackQuery):
    await cb.answer("Операция устарела, начните заново", show_alert=True)


@router.message(F.text)
async def other(msg: Message):
    await msg.answer("Выберите действие кнопками ниже.", reply_markup=MENU)
