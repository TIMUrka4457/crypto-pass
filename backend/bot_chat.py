"""Full wallet inside the Telegram chat: one inline 'wallet card' message, navigation by buttons (xRocket-style)."""
import io
import re
import uuid

import qrcode
from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery,
                           InlineQueryResultArticle, InlineQueryResultsButton, InputTextMessageContent,
                           KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo)
from fastapi import HTTPException

import bot
import fees
from auth import upsert_tg_user, not_frozen
from checks import create_check, claim_check, public_check, close_check
from core import db, ASSETS, NETWORKS, fmt, to_units, get_settings, require_feature, new_id, now
from ledger import user_balances, acct
from services import (transfer, create_withdrawal, deposit_address, find_user_by_username,
                      create_invoice, pay_invoice, public_invoice, cancel_invoice)

router = Router()
H = "HTML"
B_WALLET = "Кошелёк"
MENU = ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True, keyboard=[[KeyboardButton(text=B_WALLET)]])
FLOW_TITLE = {"tr": "перевода", "wd": "вывода", "ck": "чека", "iv": "счёта", "sw": "обмена (отдаёте)"}


class Sw(StatesGroup):
    amount = State()
    confirm = State()


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


def app_btn(text: str, param: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=bot.miniapp_url(param)))


BACK = [("« В кошелёк", "home")]
BACK_KB = kb(BACK)
CANCEL_KB = kb([("Отмена", "x")])
CONFIRM_KB = kb([("Подтвердить", "ok"), ("Отмена", "x")])


async def me(ev) -> dict:
    return await upsert_tg_user(ev.from_user.model_dump())


def t(asset: str) -> str:
    return ASSETS[asset]["title"]


async def show(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    """Edit the current card in place; photos (QR) can't become text, so send a new card then."""
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode=H, disable_web_page_preview=True)
    except Exception:
        await cb.message.answer(text, reply_markup=markup, parse_mode=H, disable_web_page_preview=True)


# ---------------- wallet card ----------------
async def card(u: dict) -> tuple[str, InlineKeyboardMarkup]:
    b = await user_balances(u["_id"])
    lines = [f"{t(a)}: <b>{fmt(a, v['available'])}</b>" + (f"  <i>(в обработке {fmt(a, v['hold'])})</i>" if v["hold"] else "")
             for a, v in b.items()]
    head = f"<b>EasyCrypto · Кошелёк</b>\n{'@' + u['username'] if u.get('username') else u.get('first_name', '')}\n\n"
    warn = "\n\n<b>Аккаунт заморожен.</b> Обратитесь в поддержку." if u.get("frozen") else ""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пополнить", callback_data="m:dep"), InlineKeyboardButton(text="Вывести", callback_data="m:wd")],
        [InlineKeyboardButton(text="Перевести", callback_data="m:tr"), InlineKeyboardButton(text="Получить", callback_data="m:recv")],
        [InlineKeyboardButton(text="Обмен", callback_data="m:sw"), InlineKeyboardButton(text="Чеки", callback_data="m:ck")],
        [InlineKeyboardButton(text="Счета", callback_data="m:iv"), InlineKeyboardButton(text="История", callback_data="m:hist")],
        [InlineKeyboardButton(text="Рефералы", callback_data="m:ref"), InlineKeyboardButton(text="Комиссии", callback_data="m:fees")],
        [InlineKeyboardButton(text="Обновить", callback_data="home")],
        [app_btn("Открыть приложение")]])
    return head + "\n".join(lines) + warn, markup


async def send_card(msg: Message, u: dict):
    text, markup = await card(u)
    await msg.answer(text, reply_markup=markup, parse_mode=H)


WELCOME = ("<b>Добро пожаловать в EasyCrypto!</b>\n\n"
           "Криптокошелёк прямо в Telegram — без регистрации, телефона и почты.\n\n"
           "• Храните <b>TON</b>, <b>USDT (TON)</b> и <b>USDT (TRC20)</b>\n"
           "• Переводите друзьям по @username — <b>бесплатно и мгновенно</b>\n"
           "• Меняйте TON ↔ USDT по рыночному курсу\n"
           "• Отправляйте крипту ссылкой-чеком — или прямо в любом чате: напишите <code>@{bot} 5 usdt</code>\n"
           "• Выставляйте счета и принимайте оплату\n"
           "• Получайте {ref}% от комиссий приглашённых друзей\n\n"
           "Всё работает прямо здесь, в чате, кнопками. Кнопка «Кошелёк» внизу всегда вернёт к балансу.")


@router.message(CommandStart())
async def start(msg: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    arg = command.args or ""
    u = await upsert_tg_user(msg.from_user.model_dump(), arg[2:] if arg.startswith("r_") else None)
    if arg.startswith("c_"):
        return await show_check(msg, arg[2:])
    if arg.startswith("i_"):
        return await show_invoice(msg, arg[2:])
    s = await get_settings()
    await msg.answer(WELCOME.format(ref=s["referral_pct"], bot=await bot.username()), reply_markup=MENU, parse_mode=H)
    await send_card(msg, u)


@router.message(F.text == B_WALLET)
@router.message(Command("wallet"))
async def wallet_msg(msg: Message, state: FSMContext):
    await state.clear()
    await send_card(msg, await me(msg))


@router.callback_query(F.data == "home")
async def home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    text, markup = await card(await me(cb))
    await show(cb, text, markup)


@router.message(Command("cancel"))
async def cancel_cmd(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено.", reply_markup=MENU)
    await send_card(msg, await me(msg))


@router.callback_query(F.data == "x")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await home(cb, state)


# ---------------- simple screens ----------------
@router.callback_query(F.data == "m:hist")
async def history(cb: CallbackQuery):
    await cb.answer()
    from routes_user import history_rows
    u = await me(cb)
    a = acct(u["_id"])
    rows = history_rows(await db.journal.find({"entries.account": a}).sort("created_at", -1).limit(12).to_list(12), {a})
    text = "\n".join(f"<code>{r['created_at'][5:16].replace('T', ' ')}</code> {r['kind_text']}: <b>{r['sign']}{r['amount']}</b> {t(r['asset'])}"
                     for r in rows) or "Операций пока нет."
    await show(cb, "<b>История</b> (время UTC)\n\n" + text, BACK_KB)


@router.callback_query(F.data == "m:recv")
async def receive(cb: CallbackQuery):
    await cb.answer()
    u = await me(cb)
    name = f"@{u['username']}" if u.get("username") else "— задайте username в настройках Telegram, чтобы получать переводы"
    await show(cb, "<b>Получить</b>\n\n"
                   f"Внутри EasyCrypto — по вашему username: <b>{name}</b>\nБесплатно и мгновенно.\n\n"
                   "Из другого кошелька или биржи — на ваш адрес пополнения.\n\n"
                   "Или выставьте счёт и отправьте ссылку плательщику.",
               kb([("Адрес пополнения", "m:dep"), ("Выставить счёт", "as:iv:pick")], BACK))


@router.callback_query(F.data == "m:ref")
async def referral(cb: CallbackQuery):
    await cb.answer()
    from routes_user import referral as ref_data
    d = await ref_data(u=await me(cb))
    earned = "\n".join(f"  {t(a)}: {v}" for a, v in d["earned"].items())
    await show(cb, f"<b>Рефералы</b>\n\nПриглашайте друзей и получайте <b>{d['percent']}%</b> от комиссий, которые они платят.\n\n"
                   f"Ваша ссылка:\n{d['link'] or 'бот не настроен'}\n\nПриглашено: <b>{d['invited']}</b>\nЗаработано:\n{earned}", BACK_KB)


@router.callback_query(F.data == "m:fees")
async def fees_screen(cb: CallbackQuery):
    await cb.answer()
    s = await get_settings()
    usdt_ton = fmt("USDT_TON", await fees.withdraw_fee("USDT_TON", None, s))
    trc_new = fmt("USDT_TRC20", await fees.withdraw_fee("USDT_TRC20", None, s))
    s2 = {**s, "fees": {**s["fees"], "tron_energy_new": s["fees"]["tron_energy_existing"]}}
    trc_old = fmt("USDT_TRC20", await fees.withdraw_fee("USDT_TRC20", None, s2))
    dep = "\n".join(f"  {t(a)}: {c['deposit_fee']} (не больше 10% суммы)" for a, c in s["assets"].items() if float(c["deposit_fee"]) > 0)
    await show(cb, "<b>Комиссии</b>\n\n"
                   "Переводы по @username, чеки, счета: <b>0</b>\n"
                   f"Обмен TON ↔ USDT: {s['swap']['fee_pct']}% от суммы\n\n"
                   f"Вывод:\n  TON: {s['assets']['TON']['withdraw_fee']} TON\n  USDT (TON): {usdt_ton} USDT\n"
                   f"  USDT (TRC20): {trc_old} USDT, на новый адрес {trc_new} USDT\n\n"
                   f"Пополнение:\n  TON и USDT (TON): 0\n{dep}\n\n"
                   "Комиссия вывода USDT следует за реальной ценой газа сети и может немного меняться. "
                   "Точная сумма показывается перед подтверждением.", BACK_KB)


# ---------------- deposit ----------------
@router.callback_query(F.data == "m:dep")
async def deposit(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await show(cb, "<b>Пополнить</b>\n\nВыберите сеть:", kb([("TON · USDT (TON)", "dep:ton")], [("TRON · USDT (TRC20)", "dep:tron")], BACK))


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
            return await show(cb, "Сеть временно отключена.", BACK_KB)
        d = await deposit_address("user", u["_id"], net)
    except HTTPException as e:
        return await show(cb, f"Не получилось: {e.detail}", BACK_KB)
    buf = io.BytesIO()
    qrcode.make(d["address"]).save(buf, format="PNG")
    assets = [a for a, m in ASSETS.items() if m["network"] == net]
    names = ", ".join(t(a) for a in assets)
    fee_note = "".join(f"\nКомиссия за пополнение {t(a)}: {s['assets'][a]['deposit_fee']} (не больше 10% суммы)."
                       for a in assets if float(s["assets"][a]["deposit_fee"]) > 0)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer_photo(BufferedInputFile(buf.getvalue(), "address.png"), parse_mode=H, reply_markup=BACK_KB, caption=(
        f"<b>Адрес для пополнения</b> ({names}):\n\n<code>{d['address']}</code>\n\n"
        f"Отправляйте только {names}. Мемо не нужно. Зачислим после {s['networks'][net]['confirmations']} "
        f"подтверждений и пришлём уведомление.{fee_note}"))


# ---------------- choose asset (shared) ----------------
@router.callback_query(F.data.in_({"m:tr", "m:wd", "m:sw"}))
async def flow_menu(cb: CallbackQuery, state: FSMContext):
    await begin(cb, state, cb.data[2:])


async def begin(cb: CallbackQuery, state: FSMContext, flow: str):
    await state.clear()
    await cb.answer()
    feature = {"tr": "transfers", "ck": "checks", "iv": "invoices", "sw": "swap"}.get(flow)
    try:
        if feature:
            await require_feature(feature)
        not_frozen(await me(cb))
    except HTTPException as e:
        return await show(cb, f"Не получилось: {e.detail}", BACK_KB)
    await show(cb, f"Выберите актив для {FLOW_TITLE[flow]}:",
               kb([(t(a), f"as:{flow}:{a}") for a in ASSETS], [("Отмена", "x")]))


@router.callback_query(F.data.startswith("as:"))
async def asset_chosen(cb: CallbackQuery, state: FSMContext):
    _, flow, asset = cb.data.split(":")
    if asset == "pick":
        return await begin(cb, state, flow)
    await cb.answer()
    if asset not in ASSETS:
        return
    await state.set_data({"asset": asset, "idem": uuid.uuid4().hex})
    if flow == "tr":
        await state.set_state(Tr.username)
        await show(cb, f"Перевод {t(asset)}.\nВведите @username получателя:", CANCEL_KB)
    elif flow == "wd":
        await state.set_state(Wd.address)
        net = "TON" if ASSETS[asset]["network"] == "ton" else "TRON"
        await show(cb, f"Вывод {t(asset)}.\nВведите адрес кошелька в сети {net}:", CANCEL_KB)
    elif flow == "ck":
        await state.set_state(Ck.amount)
        await show(cb, f"Чек в {t(asset)}.\nВведите сумму чека:", CANCEL_KB)
    elif flow == "iv":
        await state.set_state(Iv.amount)
        await show(cb, f"Счёт в {t(asset)}.\nВведите сумму к оплате:", CANCEL_KB)
    elif flow == "sw":
        await show(cb, f"Отдаёте {t(asset)}. Что получить?",
                   kb([(t(a), f"sw2:{a}") for a in ASSETS if a != asset], [("Отмена", "x")]))


# ---------------- swap ----------------
@router.callback_query(F.data.startswith("sw2:"))
async def sw_to(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    d = await state.get_data()
    to = cb.data[4:]
    if to not in ASSETS or not d.get("asset") or to == d["asset"]:
        return await done(cb, "Начните заново.")
    await state.update_data(to=to)
    await state.set_state(Sw.amount)
    bal = (await user_balances((await me(cb))["_id"]))[d["asset"]]["available"]
    await show(cb, f"Обмен {t(d['asset'])} → {t(to)}.\nСколько {t(d['asset'])} отдать? (доступно {fmt(d['asset'], bal)})", CANCEL_KB)


@router.message(Sw.amount)
async def sw_amount(msg: Message, state: FSMContext):
    import swap
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if not v:
        return
    try:
        q = (await swap.quote(d["asset"], d["to"], v))["out"]
    except HTTPException as e:
        return await msg.answer(f"{e.detail}. Введите другую сумму:", reply_markup=CANCEL_KB)
    await state.update_data(amount=v, min_receive=q["receive"])
    await state.set_state(Sw.confirm)
    await msg.answer(f"Отдаёте: <b>{q['amount']} {t(d['asset'])}</b>\nПолучите: <b>{q['receive']} {t(d['to'])}</b>\n"
                     f"Курс: 1 {t(d['asset'])} = {q['rate']} {t(d['to'])}\nКомиссия обмена: {q['fee']} ({q['fee_pct']}%)",
                     reply_markup=CONFIRM_KB, parse_mode=H)


@router.callback_query(Sw.confirm, F.data == "ok")
async def sw_ok(cb: CallbackQuery, state: FSMContext):
    import swap
    d = await state.get_data()
    await state.clear()
    await cb.answer()
    try:
        r = await swap.execute(await me(cb), d["asset"], d["to"], d["amount"], d["idem"], d["min_receive"])
    except HTTPException as e:
        return await done(cb, f"Не получилось: {e.detail}")
    await done(cb, f"Обмен выполнен: получено <b>{r.get('receive', '')} {t(d['to'])}</b>.")


# ---------------- inline checks: "@bot 5 usdt" in any chat ----------------
INLINE_ALIASES = {"ton": ["TON"], "usdt": ["USDT_TON", "USDT_TRC20"], "trc20": ["USDT_TRC20"], "trc": ["USDT_TRC20"],
                  "tron": ["USDT_TRC20"], "usdtton": ["USDT_TON"]}


@router.inline_query()
async def inline(q: InlineQuery):
    u = await upsert_tg_user(q.from_user.model_dump())
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z0-9]*)", q.query or "")
    hint = InlineQueryResultsButton(text="Как отправить чек: «5 usdt» или «1 ton»", start_parameter="inline")
    if not m or u.get("frozen") or not (await get_settings())["features"]["checks"]:
        return await q.answer([], cache_time=0, is_personal=True, button=hint)
    value = m.group(1).replace(",", ".")
    assets = INLINE_ALIASES.get(m.group(2).lower(), list(ASSETS)) if m.group(2) else list(ASSETS)
    bals = await user_balances(u["_id"])
    results = []
    for a in assets:
        try:
            units = to_units(a, value)
        except HTTPException:
            continue
        if bals[a]["available"] < units:
            continue
        nonce = new_id("ic_")
        await db.inline_checks.insert_one({"_id": nonce, "creator": u["_id"], "asset": a, "amount": units,
                                           "status": "pending", "created_at": now()})
        name = f"@{u['username']}" if u.get("username") else u.get("first_name", "")
        results.append(InlineQueryResultArticle(
            id=nonce, title=f"Отправить чек {fmt(a, units)} {t(a)}",
            description=f"Баланс: {fmt(a, bals[a]['available'])} {t(a)}. Спишется, когда чек заберут.",
            input_message_content=InputTextMessageContent(
                message_text=f"<b>Чек на {fmt(a, units)} {t(a)}</b> от {name}\nНажмите кнопку, чтобы забрать.", parse_mode=H),
            reply_markup=kb([("Забрать чек", f"ic:{nonce}")])))
    if not results:
        hint = InlineQueryResultsButton(text="Недостаточно средств — пополнить", start_parameter="deposit")
    await q.answer(results, cache_time=0, is_personal=True, button=hint)


@router.callback_query(F.data.startswith("ic:"))
async def inline_claim(cb: CallbackQuery):
    from ledger import post, txn, Insufficient
    from core import bad
    nonce = cb.data[3:]
    doc = await db.inline_checks.find_one({"_id": nonce})
    if not doc or doc["status"] != "pending":
        return await cb.answer("Чек уже забрали", show_alert=True)
    u = await me(cb)
    if doc["creator"] == u["_id"]:
        return await cb.answer("Это ваш чек — его заберёт получатель", show_alert=True)
    creator = await db.users.find_one({"_id": doc["creator"]})
    if u.get("frozen") or not creator or creator.get("frozen"):
        return await cb.answer("Чек недоступен", show_alert=True)

    async def fn(s):
        r = await db.inline_checks.update_one({"_id": nonce, "status": "pending"},
                                              {"$set": {"status": "claimed", "claimer": u["_id"], "claimed_at": now()}}, session=s)
        if not r.modified_count:
            bad("Чек уже забрали", 409)
        await post(s, "inline_check", [(acct(doc["creator"]), doc["asset"], -doc["amount"]), (acct(u["_id"]), doc["asset"], doc["amount"])],
                   idem=f"ic:{nonce}", ref=nonce, meta={"from": doc["creator"], "to": u["_id"]})
    try:
        await txn(fn)
    except Insufficient:
        return await cb.answer("У отправителя недостаточно средств", show_alert=True)
    except HTTPException as e:
        return await cb.answer(e.detail, show_alert=True)
    amount = f"{fmt(doc['asset'], doc['amount'])} {t(doc['asset'])}"
    who = f"@{u['username']}" if u.get("username") else u.get("first_name", "")
    await cb.answer(f"Зачислено {amount}. Откройте бота, чтобы увидеть баланс", show_alert=True)
    if cb.inline_message_id:
        try:
            await cb.bot.edit_message_text(inline_message_id=cb.inline_message_id, parse_mode=H,
                                           text=f"<b>Чек на {amount}</b> забрал {who}.")
        except Exception:
            pass
    from services import notify
    notify(doc["creator"], f"Ваш чек на {amount} забрал {who}")


async def read_amount(msg: Message, asset: str) -> str | None:
    v = (msg.text or "").strip().replace(",", ".")
    try:
        to_units(asset, v)
        return v
    except HTTPException as e:
        await msg.answer(f"{e.detail}. Введите сумму числом, например 1.5", reply_markup=CANCEL_KB)
        return None


async def done(cb: CallbackQuery, text: str):
    await show(cb, text, BACK_KB)


# ---------------- transfer ----------------
@router.message(Tr.username)
async def tr_username(msg: Message, state: FSMContext):
    try:
        to = await find_user_by_username(msg.text or "")
    except HTTPException as e:
        return await msg.answer(e.detail + ". Введите другой @username:", reply_markup=CANCEL_KB)
    await state.update_data(to=to["_id"], to_name=to.get("username"))
    await state.set_state(Tr.amount)
    d = await state.get_data()
    bal = (await user_balances((await me(msg))["_id"]))[d["asset"]]["available"]
    await msg.answer(f"Введите сумму перевода (доступно {fmt(d['asset'], bal)} {t(d['asset'])}):", reply_markup=CANCEL_KB)


@router.message(Tr.amount)
async def tr_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if v:
        await state.update_data(amount=v)
        await state.set_state(Tr.comment)
        await msg.answer("Комментарий к переводу:", reply_markup=kb([("Без комментария", "nocomment")], [("Отмена", "x")]))


async def tr_ask_confirm(msg: Message, state: FSMContext, comment: str):
    await state.update_data(comment=comment[:200])
    await state.set_state(Tr.confirm)
    d = await state.get_data()
    await msg.answer(f"Перевести <b>{d['amount']} {t(d['asset'])}</b> пользователю @{d['to_name']}?\nКомиссия: 0"
                     + (f"\nКомментарий: {comment[:200]}" if comment else ""), reply_markup=CONFIRM_KB, parse_mode=H)


@router.message(Tr.comment)
async def tr_comment(msg: Message, state: FSMContext):
    await tr_ask_confirm(msg, state, (msg.text or "").strip())


@router.callback_query(Tr.comment, F.data == "nocomment")
async def tr_nocomment(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await tr_ask_confirm(cb.message, state, "")


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
        return await done(cb, f"Не получилось: {e.detail}")
    await done(cb, f"Готово: <b>{r.get('amount', d['amount'])} {t(d['asset'])}</b> отправлено @{d['to_name']}.")


# ---------------- withdraw ----------------
@router.message(Wd.address)
async def wd_address(msg: Message, state: FSMContext):
    import chains
    d = await state.get_data()
    addr = (msg.text or "").strip()
    if not chains.valid_address(ASSETS[d["asset"]]["network"], addr):
        return await msg.answer("Некорректный адрес. Проверьте и введите ещё раз:", reply_markup=CANCEL_KB)
    s = await get_settings()
    fee = fmt(d["asset"], await fees.withdraw_fee(d["asset"], addr, s))
    await state.update_data(address=addr, fee=fee)
    cfg = s["assets"][d["asset"]]
    bal = (await user_balances((await me(msg))["_id"]))[d["asset"]]["available"]
    await state.set_state(Wd.amount)
    await msg.answer(f"Введите сумму вывода.\nДоступно {fmt(d['asset'], bal)}, минимум {cfg['withdraw_min']}, "
                     f"комиссия сети {fee} {t(d['asset'])}.", reply_markup=CANCEL_KB)


@router.message(Wd.amount)
async def wd_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if not v:
        return
    await state.update_data(amount=v)
    await state.set_state(Wd.confirm)
    await msg.answer(f"Вывести <b>{v} {t(d['asset'])}</b>\nна адрес <code>{d['address']}</code>?\n\n"
                     f"Комиссия {d['fee']} {t(d['asset'])} спишется дополнительно. Перевод в блокчейне необратим — "
                     f"проверьте адрес.", reply_markup=CONFIRM_KB, parse_mode=H)


@router.callback_query(Wd.confirm, F.data == "ok")
async def wd_ok(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    await cb.answer()
    try:
        w = await create_withdrawal(await me(cb), d["asset"], d["address"], d["amount"], d["idem"], source="bot")
    except HTTPException as e:
        return await done(cb, f"Не получилось: {e.detail}")
    await done(cb, f"Заявка на вывод создана: <b>{w['amount']} {t(w['asset'])}</b> (комиссия {w['fee']}).\n"
                   f"Статус: {w['status_text']}. Пришлём уведомление, когда средства уйдут.")


# ---------------- checks ----------------
@router.callback_query(F.data == "m:ck")
async def checks_screen(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    u = await me(cb)
    name = await bot.username()
    items = await db.checks.find({"creator_id": u["_id"], "status": "active"}).sort("created_at", -1).limit(5).to_list(5)
    lines = [f"• <b>{fmt(c['asset'], c['amount_per'])} {t(c['asset'])}</b>"
             + (f" × {c['remaining']}/{c['activations']}" if c["kind"] == "multi" else "") + f"\n  {public_check(c, name, True)['link']}"
             for c in items]
    rows = [[("Создать чек", "as:ck:pick")]] + [[(f"Отменить {fmt(c['asset'], c['amount_per'])} {t(c['asset'])}", f"ckx:{c['_id']}")] for c in items]
    await show(cb, "<b>Чеки</b>\n\nЧек — ссылка, по которой получатель заберёт крипту. Если чек отменить, деньги вернутся.\n\n"
                   + ("Активные чеки:\n" + "\n".join(lines) if lines else "Активных чеков нет.")
                   + "\n\nМульти-чеки с паролем, капчей и подпиской на канал — в приложении.", kb(*rows, BACK))


@router.callback_query(F.data.startswith("ckx:"))
async def check_cancel(cb: CallbackQuery, state: FSMContext):
    try:
        r = await close_check(cb.data[4:], "cancelled", by_creator=(await me(cb))["_id"])
        await cb.answer(f"Чек отменён, возвращено {r['refunded']}", show_alert=True)
    except HTTPException as e:
        await cb.answer(e.detail, show_alert=True)
    await checks_screen(cb, state)


@router.message(Ck.amount)
async def ck_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if v:
        await state.update_data(amount=v)
        await state.set_state(Ck.confirm)
        await msg.answer(f"Создать чек на <b>{v} {t(d['asset'])}</b>? Сумма спишется с баланса и вернётся, если чек отменить.",
                         reply_markup=CONFIRM_KB, parse_mode=H)


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
        return await done(cb, f"Не получилось: {e.detail}")
    link = public_check(c, await bot.username(), True)["link"]
    await done(cb, f"Чек на <b>{d['amount']} {t(d['asset'])}</b> создан.\nОтправьте ссылку получателю:\n{link}")


async def show_check(msg: Message, check_code: str):
    c = await db.checks.find_one({"code": check_code})
    if not c or c["status"] != "active":
        return await msg.answer("Чек не найден или уже использован.", reply_markup=MENU)
    text = f"<b>Чек на {fmt(c['asset'], c['amount_per'])} {t(c['asset'])}</b>" + (f"\n{c['description']}" if c.get("description") else "")
    if c.get("password_hash") or c.get("captcha"):
        return await msg.answer(text + "\n\nДля этого чека нужно пройти проверку в приложении.", parse_mode=H,
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[app_btn("Забрать чек", f"c_{check_code}")]]))
    await msg.answer(text, parse_mode=H, reply_markup=kb([("Забрать чек", f"claim:{check_code}")]))


@router.callback_query(F.data.startswith("claim:"))
async def claim(cb: CallbackQuery):
    await cb.answer()
    try:
        u = await me(cb)
        not_frozen(u)
        await require_feature("checks")
        r = await claim_check(u, cb.data[6:], {})
    except HTTPException as e:
        return await done(cb, f"Не получилось: {e.detail}")
    await done(cb, f"Зачислено <b>{r['amount']} {t(r['asset'])}</b>.")


# ---------------- invoices ----------------
@router.callback_query(F.data == "m:iv")
async def invoices_screen(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    u = await me(cb)
    name = await bot.username()
    items = await db.invoices.find({"creator_id": u["_id"], "status": "active"}).sort("created_at", -1).limit(5).to_list(5)
    lines = [f"• <b>{fmt(i['asset'], i['amount'])} {t(i['asset'])}</b> {i['description'][:40]}\n  {public_invoice(i, name)['pay_url']}"
             for i in items]
    rows = [[("Выставить счёт", "as:iv:pick")]] + [[(f"Отменить #{i['code']}", f"ivx:{i['_id']}")] for i in items]
    await show(cb, "<b>Счета</b>\n\nСчёт — ссылка на оплату. Плательщик оплатит с баланса EasyCrypto или переводом из любого кошелька.\n\n"
                   + ("Активные счета:\n" + "\n".join(lines) if lines else "Активных счетов нет."), kb(*rows, BACK))


@router.callback_query(F.data.startswith("ivx:"))
async def invoice_cancel(cb: CallbackQuery, state: FSMContext):
    try:
        await cancel_invoice(cb.data[4:], by_user=(await me(cb))["_id"])
        await cb.answer("Счёт отменён", show_alert=True)
    except HTTPException as e:
        await cb.answer(e.detail, show_alert=True)
    await invoices_screen(cb, state)


@router.message(Iv.amount)
async def iv_amount(msg: Message, state: FSMContext):
    d = await state.get_data()
    v = await read_amount(msg, d["asset"])
    if v:
        await state.update_data(amount=v)
        await state.set_state(Iv.desc)
        await msg.answer("За что счёт? Короткое описание:", reply_markup=kb([("Без описания", "nodesc")], [("Отмена", "x")]))


async def iv_create(msg: Message, state: FSMContext, user_ev, desc: str):
    d = await state.get_data()
    await state.clear()
    try:
        u = await me(user_ev)
        not_frozen(u)
        inv = await create_invoice(u, d["asset"], d["amount"], desc)
    except HTTPException as e:
        return await msg.answer(f"Не получилось: {e.detail}", reply_markup=BACK_KB)
    url = public_invoice(inv, await bot.username())["pay_url"]
    await msg.answer(f"Счёт на <b>{d['amount']} {t(d['asset'])}</b> создан.\nСсылка для оплаты:\n{url}",
                     reply_markup=BACK_KB, parse_mode=H)


@router.message(Iv.desc)
async def iv_desc(msg: Message, state: FSMContext):
    await iv_create(msg, state, msg, (msg.text or "").strip())


@router.callback_query(Iv.desc, F.data == "nodesc")
async def iv_nodesc(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await iv_create(cb.message, state, cb, "")


async def show_invoice(msg: Message, inv_code: str):
    inv = await db.invoices.find_one({"code": inv_code})
    if not inv or inv["status"] != "active":
        return await msg.answer("Счёт не найден или уже закрыт.", reply_markup=MENU)
    amount = fmt(inv["asset"], inv["amount"])
    await msg.answer(f"<b>Счёт #{inv['code']}: {amount} {t(inv['asset'])}</b>" + (f"\n{inv['description']}" if inv.get("description") else ""),
                     parse_mode=H, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                         [InlineKeyboardButton(text=f"Оплатить {amount} {t(inv['asset'])} с баланса", callback_data=f"pay:{inv_code}")],
                         [app_btn("Другие способы оплаты", f"i_{inv_code}")]]))


@router.callback_query(F.data.startswith("pay:"))
async def pay(cb: CallbackQuery):
    await cb.answer()
    try:
        u = await me(cb)
        not_frozen(u)
        await require_feature("invoices")
        await pay_invoice(u, cb.data[4:])
    except HTTPException as e:
        return await done(cb, f"Не получилось: {e.detail}")
    await done(cb, "Счёт оплачен.")


@router.callback_query(F.data.in_({"ok", "nocomment", "nodesc"}))
async def stale(cb: CallbackQuery):
    await cb.answer("Операция устарела, начните заново", show_alert=True)


@router.message(F.text)
async def other(msg: Message):
    await send_card(msg, await me(msg))
