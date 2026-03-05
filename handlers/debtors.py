# handlers/debtors.py
from aiogram import Router, F, Bot
from aiogram.types import Message

import aiosqlite

from config import ADMINS
from database.db import DB_PATH
from datetime import datetime

router = Router()

BTN_DEBTORS = "💸 Должники"


def _fmt_user(user_id: int, username: str | None) -> str:
    if username:
        u = str(username).lstrip("@")
        return f"@{u}"
    return f"<a href=\"tg://user?id={user_id}\">Пользователь</a> (id:{user_id})"


def _fmt_money(x: int) -> str:
    return f"{x:,}".replace(",", " ") 

def _fmt_date(date_str: str | None) -> str:
    if not date_str:
        return "—"

    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str


@router.message(F.text == BTN_DEBTORS)
async def debtors_button(message: Message, bot: Bot):
    user_id = message.from_user.id

    if user_id not in ADMINS:
        await message.answer("Эта кнопка только для админа.")
        return

    q = """
    SELECT
        l.id AS loan_id,
        l.user_id,
        l.username,
        l.amount AS loan_amount,
        l.issued_at,
        (l.amount - COALESCE(SUM(r.amount), 0)) AS debt_current
    FROM loans l
    LEFT JOIN repayments r ON r.loan_id = l.id
    WHERE (l.status IS NULL OR l.status != 'rejected')
    GROUP BY l.id
    HAVING debt_current > 0
    ORDER BY COALESCE(l.issued_at, l.due_date) ASC, l.id ASC;
    """

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(q)
        rows = await cur.fetchall()

    if not rows:
        await bot.send_message(chat_id=user_id, text="Должников нет ✅")
        return

    lines: list[str] = ["💸 <b>Список должников</b>\n"]

    for i, row in enumerate(rows, start=1):
        loan_id, debtor_id, username, loan_amount, issued_at, debt_current = row

        debtor_name = _fmt_user(int(debtor_id), username)
        issued_txt = _fmt_date(issued_at)

        lines.append(
            f"{i}) 👤 {debtor_name}\n"
            f"   💰 Сумма займа: <b>{_fmt_money(int(loan_amount))}</b>\n"
            f"   📅 Дата займа: <b>{issued_txt}</b>\n"
            f"   🔻 Текущий долг: <b>{_fmt_money(int(debt_current))}</b>\n"
        )

    await bot.send_message(
        chat_id=user_id,
        text="\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True
    )