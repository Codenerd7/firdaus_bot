# =============================
# handlers/history_admin.py
# =============================
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from config import ADMINS
from services.history_service import build_history_all_text

history_admin_router = Router()


@history_admin_router.message(Command("history_all"))
async def cmd_history_all(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔ Недостаточно прав")
        return

    text = await build_history_all_text()
    await message.answer(text, disable_web_page_preview=True)
