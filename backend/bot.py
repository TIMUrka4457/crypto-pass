import asyncio
import os

from core import db, log, now, new_id

_bot = None
_dp = None
bot_username: str | None = None


def enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))


def _get_bot():
    global _bot
    if _bot is None and enabled():
        from aiogram import Bot
        _bot = Bot(os.environ["TELEGRAM_BOT_TOKEN"])
    return _bot


def miniapp_url(param: str | None = None) -> str:
    base = os.environ["MINIAPP_URL"]
    return f"{base}?start={param}" if param else base


async def send(uid: str, text: str, button: tuple | None = None) -> bool:
    b = _get_bot()
    if not b:
        return False
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    kb = None
    if button:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button[0], web_app=WebAppInfo(url=button[1]))]])
    try:
        await b.send_message(int(uid), text, reply_markup=kb)
        return True
    except Exception as e:
        log.info("bot send to %s failed: %s", uid, e)
        return False


async def is_member(channel: str, tg_id: int) -> bool:
    b = _get_bot()
    if not b:
        return False
    try:
        m = await b.get_chat_member(channel, tg_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        log.info("get_chat_member %s failed: %s", channel, e)
        return False


async def username() -> str | None:
    global bot_username
    if bot_username is None and _get_bot():
        try:
            bot_username = (await _get_bot().get_me()).username
        except Exception as e:
            log.warning("get_me failed: %s", e)
    return bot_username


def _build_dispatcher():
    from aiogram import Dispatcher, F
    from aiogram.filters import CommandStart, CommandObject
    from aiogram.types import Message
    from auth import upsert_tg_user

    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(msg: Message, command: CommandObject):
        arg = command.args or ""
        ref = arg[2:] if arg.startswith("r_") else None
        await upsert_tg_user(msg.from_user.model_dump(), ref)
        if arg.startswith("c_"):
            await send(str(msg.from_user.id), "Вам отправили чек. Откройте кошелёк, чтобы забрать его.",
                       ("Забрать чек", miniapp_url(arg)))
        elif arg.startswith("i_"):
            await send(str(msg.from_user.id), "Счёт на оплату. Откройте кошелёк, чтобы оплатить.",
                       ("Открыть счёт", miniapp_url(arg)))
        else:
            await send(str(msg.from_user.id),
                       "Кошелёк создан. Здесь можно хранить TON и USDT, переводить друзьям по @username, "
                       "создавать чеки и принимать оплату.", ("Открыть кошелёк", miniapp_url()))

    @dp.message(F.text)
    async def other(msg: Message):
        await send(str(msg.from_user.id), "Откройте кошелёк кнопкой ниже.", ("Открыть кошелёк", miniapp_url()))

    return dp


async def run_polling(stop: asyncio.Event):
    """Long-polling guarded by a Mongo lease so only one backend instance polls Telegram."""
    global _dp
    if not enabled():
        log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return
    from workers import lease
    _dp = _build_dispatcher()
    b = _get_bot()
    await username()
    while not stop.is_set():
        if not await lease("bot", 60):
            await asyncio.sleep(20)
            continue
        task = asyncio.create_task(_dp.start_polling(b, handle_signals=False))
        while not stop.is_set() and not task.done():
            await asyncio.sleep(20)
            if not await lease("bot", 60):
                break
        await _dp.stop_polling() if not task.done() else None
        task.cancel()


async def broadcast_worker():
    job = await db.broadcasts.find_one_and_update({"status": "queued"}, {"$set": {"status": "running", "started_at": now()}})
    if not job:
        return
    sent = failed = 0
    async for u in db.users.find({}, {"_id": 1}):
        ok = await send(u["_id"], job["text"])
        sent += ok
        failed += not ok
        if (sent + failed) % 50 == 0:
            await db.broadcasts.update_one({"_id": job["_id"]}, {"$set": {"sent": sent, "failed": failed}})
        await asyncio.sleep(0.05)
    await db.broadcasts.update_one({"_id": job["_id"]}, {"$set": {"status": "done", "sent": sent, "failed": failed,
                                                                  "finished_at": now()}})


async def queue_broadcast(text: str, admin: dict) -> dict:
    doc = {"_id": new_id("bc_"), "text": text[:4000], "status": "queued", "sent": 0, "failed": 0,
           "admin_email": admin["email"], "created_at": now()}
    await db.broadcasts.insert_one(doc)
    return doc
