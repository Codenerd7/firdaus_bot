from aiogram import Router, F
from aiogram.types import Message

from database.db import get_fund_summary_for_ui
from utils.limits import calculate_monthly_limit
from keyboards.default import main_kb, BTN_CHECK_BALANCE

router = Router()


def _fmt_money(x: int) -> str:
    return f"{int(x):,}".replace(",", " ")


@router.message(F.text == BTN_CHECK_BALANCE)
async def check_balance(message: Message):
    summary = await get_fund_summary_for_ui()
    monthly_limit = await calculate_monthly_limit()

    text = (
        "<b>📊 Финансы фонда:</b>\n"
        f"💰 Всего внесено: <b>{_fmt_money(summary['total_contributions'])}</b> ₸\n"
        f"📤 Выдано займов: <b>{_fmt_money(summary['total_issued_loans'])}</b> ₸\n"
        f"📥 Возвращено: <b>{_fmt_money(summary['total_repaid'])}</b> ₸\n\n"
        f"📉 Общий долг: <b>{_fmt_money(summary['total_debt'])}</b> ₸\n"
        f"🔓 Свободно: <b>{_fmt_money(summary['free_sum'])}</b> ₸\n\n"
        f"📌 Месячный лимит займа: <b>{_fmt_money(monthly_limit)}</b> ₸"
    )

    await message.answer(text, reply_markup=main_kb)