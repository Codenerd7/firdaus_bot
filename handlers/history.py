# =============================
# handlers/history.py
# =============================
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError

from keyboards.default import main_kb, BTN_HISTORY
from keyboards.history import history_destination_kb
from services.history_service import build_history_text

history_router = Router()


# ---------- Кнопка «📜 История» из ReplyKeyboard ----------
@history_router.message(F.text == BTN_HISTORY)
async def btn_history(message: Message):
    """Обработчик кнопки «📜 История» из главного меню."""
    if message.chat.type in {"group", "supergroup"}:
        await message.reply(
            "Где показать вашу историю?",
            reply_markup=history_destination_kb(),
        )
        return

    text = await build_history_text(
        user_id=message.from_user.id,
        user_title=message.from_user.full_name,
    )
    await message.answer(text, reply_markup=main_kb)


# ---------- Команда /history ----------
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
        text = await build_history_text(
            user_id=message.from_user.id,
            user_title=message.from_user.full_name,
        )
        await message.answer(text, reply_markup=main_kb)


# ---------- Inline-кнопки: «В ЛС» / «Опубликовать здесь» ----------
@history_router.callback_query(F.data.startswith("history:"))
async def on_history_destination(cb: CallbackQuery):
    dst = cb.data.split(":", 1)[1]

    if dst == "pm":
        try:
            text = await build_history_text(
                user_id=cb.from_user.id,
                user_title=cb.from_user.full_name,
            )
            await cb.message.bot.send_message(chat_id=cb.from_user.id, text=text)
            await cb.message.answer("✅ Вам в ЛС отправлена история ваших действий.")
        except TelegramForbiddenError:
            await cb.message.answer(
                "❗ Не удалось написать вам в ЛС. Пожалуйста, сначала откройте чат с ботом и нажмите /start, затем повторите попытку."
            )
        await cb.answer()
        return

    if dst == "group":
        mention = cb.from_user.mention_html() if cb.from_user else None
        text = await build_history_text(
            user_id=cb.from_user.id,
            user_title=mention,
        )
        await cb.message.answer(text, disable_web_page_preview=True)
        await cb.answer("Опубликовано в чате")
