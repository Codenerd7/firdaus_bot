from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.db import (
    get_payment_by_id,
    confirm_payment,
    reject_payment,
    process_contribution_with_debt
)
from config import ADMINS, bot

router = Router()


def payment_kb(payment_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для заявки на пополнение"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"pay_confirm:{payment_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pay_reject:{payment_id}")
    ]])


@router.callback_query(F.data.startswith("pay_confirm:"))
async def confirm_payment_cb(call: CallbackQuery):
    payment_id = int(call.data.split(":")[1])

    # Проверка на админа
    if call.from_user.id not in ADMINS:
        await call.answer("Только администратор может подтвердить!", show_alert=True)
        return

    payment = await get_payment_by_id(payment_id)
    if not payment:
        await call.answer("Заявка не найдена", show_alert=True)
        return

    if payment["status"] != "pending":
        await call.answer("Заявка уже обработана", show_alert=True)
        return

    # Подтверждаем заявку
    await confirm_payment(payment_id, call.from_user.id)

    # Зачисляем средства (с учётом долгов)
    result_text = await process_contribution_with_debt(
        user_id=payment["user_id"],
        username=payment["username"],
        amount=payment["amount"]
    )

    user_link = f"<a href='tg://user?id={payment['user_id']}'>{payment.get('username') or payment['user_id']}</a>"

    # Обновляем сообщение в группе
    await call.message.edit_text(
        f"✅ Заявка #{payment_id} подтверждена\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"💰 Сумма: {payment['amount']} ₸\n"
        f"📎 Квитанция: {'✅' if payment.get('proof_file_id') else '❌'}\n\n"
        f"Администратор: {call.from_user.full_name}",
        reply_markup=None
    )
    await call.answer("Заявка подтверждена")

    # Уведомляем пользователя в ЛС
    try:
        await bot.send_message(
            payment["user_id"],
            f"✅ Ваша заявка на пополнение подтверждена!\n\n{result_text}"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_reject:"))
async def reject_payment_cb(call: CallbackQuery):
    payment_id = int(call.data.split(":")[1])

    # Проверка на админа
    if call.from_user.id not in ADMINS:
        await call.answer("Только администратор может отклонить!", show_alert=True)
        return

    payment = await get_payment_by_id(payment_id)
    if not payment:
        await call.answer("Заявка не найдена", show_alert=True)
        return

    if payment["status"] != "pending":
        await call.answer("Заявка уже обработана", show_alert=True)
        return

    # Отклоняем заявку
    await reject_payment(payment_id, call.from_user.id)

    user_link = f"<a href='tg://user?id={payment['user_id']}'>{payment.get('username') or payment['user_id']}</a>"

    # Обновляем сообщение в группе
    await call.message.edit_text(
        f"❌ Заявка #{payment_id} отклонена\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"💰 Сумма: {payment['amount']} ₸\n\n"
        f"Администратор: {call.from_user.full_name}",
        reply_markup=None
    )
    await call.answer("Заявка отклонена")

    # Уведомляем пользователя в ЛС
    try:
        await bot.send_message(
            payment["user_id"],
            f"❌ Ваша заявка на пополнение на сумму {payment['amount']} ₸ была отклонена.\n"
            "Свяжитесь с администратором для уточнения."
        )
    except Exception:
        pass
