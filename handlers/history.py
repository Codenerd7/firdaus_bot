# =============================
# handlers/history.py
# =============================
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError
import aiosqlite

from keyboards.history import history_destination_kb
from services.history_service import (
    get_user_contributions,
    get_user_loans,
    get_user_repayments,
    format_history_message_full,
)

history_router = Router()

DB_PATH = "database/bot_db.sqlite3"  # поправьте под свой проект


@history_router.message(Command("history"))
async def cmd_history_entry(message: Message):
    """
    Работает и в группе, и в ЛС. В группе предложит выбор куда отправить историю.
    В ЛС — сразу выдаст историю пользователя.
    """
    if message.chat.type in {"group", "supergroup"}:
        await message.reply(
            "Где показать вашу историю?",
            reply_markup=history_destination_kb(),
            disable_web_page_preview=True,
        )
    else:
        # Прямо в ЛС: выдаём историю
        await _send_history_pm(message)


@history_router.callback_query(F.data.startswith("history:"))
async def on_history_destination(cb: CallbackQuery):
    dst = cb.data.split(":", 1)[1]

    if dst == "pm":
        # Пытаемся отправить в ЛС
        try:
            await _send_history_pm(cb.message, user_id=cb.from_user.id)
            await cb.message.answer("✅ Вам в ЛС отправлена история ваших действий.")
        except TelegramForbiddenError:
            await cb.message.answer(
                "❗ Не удалось написать вам в ЛС. Пожалуйста, сначала откройте чат с ботом и нажмите /start, затем повторите попытку."
            )
        await cb.answer()
        return

    if dst == "group":
        # Публикация в текущем чате
        async with aiosqlite.connect(DB_PATH) as db:
            contributions = await get_user_contributions(db, cb.from_user.id, limit=20)
            loans = await get_user_loans(db, cb.from_user.id, limit=20)
            repayments = await get_user_repayments(db, cb.from_user.id, limit=20)
        mention = cb.from_user.mention_html() if cb.from_user else None
        text = format_history_message_full(contributions, loans, repayments, mention=mention)
        await cb.message.answer(text, disable_web_page_preview=True)
        await cb.answer("Опубликовано в чате")


async def _send_history_pm(message_or_obj: Message, user_id: int | None = None):
    target_user_id = user_id or message_or_obj.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        contributions = await get_user_contributions(db, target_user_id, limit=20)
        loans = await get_user_loans(db, target_user_id, limit=20)
        repayments = await get_user_repayments(db, target_user_id, limit=20)
    text = format_history_message_full(contributions, loans, repayments)
    await message_or_obj.bot.send_message(chat_id=target_user_id, text=text)