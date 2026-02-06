from aiogram import Router, F
from aiogram.types import Message
from database.db import get_fund_summary_for_ui
from utils.limits import calculate_monthly_limit
from keyboards.default import main_kb

router = Router()

BTN_BALANCE = "📊 Проверить баланс"


@router.message(F.text == BTN_BALANCE)
async def check_balance(message: Message):
    summary = await get_fund_summary_for_ui()
    monthly_limit = await calculate_monthly_limit()

    text = (
        "<b>📊 Баланс фонда:</b>\n"
        f"💰 Всего внесено: {summary['total_contributions']} ₸\n"
        f"💸 В займах: {summary['active_loans']} ₸\n"
        f"🔓 Свободно: {summary['free_sum']} ₸\n\n"
        f"📌 Месячный лимит займа: {monthly_limit} ₸"
    )

    await message.answer(text, reply_markup=main_kb)
