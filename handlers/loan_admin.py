from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from database.db import approve_loan, reject_loan, get_loan_by_id
from config import ADMINS, BOT_TOKEN, bot, DB_PATH  # импортируем bot и DB_PATH

import aiosqlite  # ⬅ для записи в transactions

router = Router()


# --- клавиатура для админа ---
def admin_kb(loan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить займ", callback_data=f"approve:{loan_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{loan_id}")
        ]
    ])


# FSM для отклонения с указанием причины
class RejectFSM(StatesGroup):
    waiting_reason = State()


@router.callback_query(F.data.startswith("approve:"))
async def approve_loan_cb(call: CallbackQuery):
    loan_id = int(call.data.split(":")[1])

    # проверка на админа
    if call.from_user.id not in ADMINS:
        await call.answer("❌ Кнопка только для админа!", show_alert=True)
        await call.message.answer("Ты че админ что ли? 😅 Админ только может подтвердить!")
        return

    # обновляем статус займа в твоей основной БД/логике
    await approve_loan(loan_id)
    loan = await get_loan_by_id(loan_id)  # ожидаем dict: user_id, username, amount, ...

    borrower_link = f"<a href='tg://user?id={loan['user_id']}'>{loan.get('username') or loan['user_id']}</a>"

    # === Запись в историю (transactions): loan ===
    note_key = f"loan_id={loan_id}"
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # защита от дубликатов, если по ошибке нажмут повторно
            cur = await db.execute(
                "SELECT 1 FROM transactions WHERE type='loan' AND note=? LIMIT 1",
                (note_key,)
            )
            exists = await cur.fetchone()
            await cur.close()

            if not exists:
                await db.execute(
                    "INSERT INTO transactions(user_id, type, amount, status, note) VALUES (?,?,?,?,?)",
                    (loan["user_id"], 'loan', int(loan["amount"]), 'unpaid', note_key),
                )
                await db.commit()
    except Exception as e:
        # Не роняем поток подтверждения — просто лог
        print(f"[WARN] Не удалось записать loan в transactions: {e}")

    # убираем клавиатуру у старого сообщения и отправляем новое
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"✅ {borrower_link} одобрен займ в размере {loan['amount']} ₸!")
    await call.answer("Займ одобрен ✅")

    # уведомляем заемщика в ЛС
    try:
        await bot.send_message(
            loan["user_id"],
            f"✅ Ваш займ на сумму {loan['amount']} ₸ был одобрен!"
        )
    except Exception:
        pass  # если у бота нет доступа в ЛС


@router.callback_query(F.data.startswith("reject:"))
async def reject_loan_cb(call: CallbackQuery, state: FSMContext):
    loan_id = int(call.data.split(":")[1])

    # проверка на админа
    if call.from_user.id not in ADMINS:
        await call.answer("❌ Кнопка только для админа!", show_alert=True)
        await call.message.answer("Ты че админ что ли? 😅 Админ только может подтвердить/отклонить!")
        return

    # сохраняем loan_id и ждём причину
    await state.update_data(loan_id=loan_id)
    await state.set_state(RejectFSM.waiting_reason)

    await call.message.answer("❌ Введите причину отклонения заявки:")
    await call.answer()


@router.message(RejectFSM.waiting_reason)
async def process_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    loan_id = data.get("loan_id")
    reason = message.text

    # обновляем статус займа
    await reject_loan(loan_id, reason)
    loan = await get_loan_by_id(loan_id)

    borrower_link = f"<a href='tg://user?id={loan['user_id']}'>{loan.get('username') or loan['user_id']}</a>"

    # сообщение в чате
    await message.answer(
        f"❌ {borrower_link} заявка на займ отклонена.\n"
        f"Причина: {reason}"
    )

    # уведомление заемщику в ЛС
    try:
        await bot.send_message(
            loan["user_id"],
            f"❌ Ваш займ на сумму {loan['amount']} ₸ был отклонён.\nПричина: {reason}"
        )
    except Exception:
        pass

    await state.clear()
