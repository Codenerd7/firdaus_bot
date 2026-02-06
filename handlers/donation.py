from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from database.db import (
    get_pending_payment,
    create_payment,
    update_payment_message_id,
    attach_proof,
    cancel_payment,
)
from keyboards.default import BTN_CONTRIBUTE, BTN_CANCEL_PAYMENT, main_kb, pending_kb
from handlers.payment_admin import payment_kb
from config import bot, FUND_GROUP_ID

router = Router()

KASPI_PHONE = "+7 777 777 77 77"


class Donation(StatesGroup):
    waiting_amount = State()


# --- Cancel pending ---

@router.message(F.text == BTN_CANCEL_PAYMENT)
async def cancel_current_payment(message: Message, state: FSMContext):
    """Отмена текущей pending заявки"""
    await state.clear()

    pending = await get_pending_payment(message.from_user.id)
    if not pending:
        await message.answer("У вас нет активных заявок.", reply_markup=main_kb)
        return

    await cancel_payment(message.from_user.id)
    await message.answer(
        f"🚫 Заявка на {pending['amount']} ₸ отменена.\n"
        "Вы можете создать новую.",
        reply_markup=main_kb
    )


# --- Start donation flow ---

@router.message(F.text == BTN_CONTRIBUTE)
@router.message(F.text.contains("Пополнить фонд"))
async def start_donation(message: Message, state: FSMContext):
    await state.clear()

    pending = await get_pending_payment(message.from_user.id)
    if pending:
        await message.answer(
            f"У вас уже есть активная заявка на {pending['amount']} ₸.\n"
            "Отправьте квитанцию или отмените заявку.",
            reply_markup=pending_kb
        )
        return

    await message.answer(
        f"Переведите нужную сумму на Kaspi по номеру <b>{KASPI_PHONE}</b>, "
        f"затем укажите сумму (в цифрах)."
    )
    await state.set_state(Donation.waiting_amount)


# Если пользователь в состоянии ввода суммы написал НЕ число — отвечаем
@router.message(Donation.waiting_amount, ~F.text.regexp(r"^\d{1,9}([.,]\d{1,2})?$"))
async def amount_not_number(message: Message):
    await message.answer("Введите сумму числом (например: 3000).")


# Если число — принимаем
@router.message(Donation.waiting_amount, F.text.regexp(r"^\d{1,9}([.,]\d{1,2})?$"))
async def got_amount(message: Message, state: FSMContext):
    raw = message.text.replace(",", ".")
    try:
        amount_kzt = int(float(raw))
    except ValueError:
        await message.answer("Введите корректную сумму числом.")
        return

    if amount_kzt <= 0:
        await message.answer("Сумма должна быть больше нуля. Введите ещё раз.")
        return

    await create_payment(
        user_id=message.from_user.id,
        username=message.from_user.username,
        amount=amount_kzt,
        chat_id=message.chat.id
    )

    await state.clear()
    await message.answer(
        "✅ Заявка создана!\n\n"
        "Теперь отправьте скриншот / фото / PDF квитанции.\n"
        "Заявка действует 24 часа.",
        reply_markup=pending_kb
    )


# --- Proof handler (главный) ---
# ВАЖНО: ОДИН декоратор. Никаких двойных регистраций.
@router.message(F.photo | F.document)
async def handle_proof(message: Message):
    """Обработка квитанции (фото или документ)"""

    # Не реагируем на сообщения ботов
    if message.from_user and message.from_user.is_bot:
        return

    # Ищем pending
    payment = await get_pending_payment(message.from_user.id)
    if not payment:
        await message.answer(
            "У вас нет активной заявки.\n"
            "Нажмите «💰 Пополнить фонд» и укажите сумму.",
            reply_markup=main_kb
        )
        return

    # Защита от дублей
    if payment.get("proof_file_id") or payment.get("message_id"):
        await message.answer("Квитанция уже получена. Ожидайте подтверждения.", reply_markup=main_kb)
        return

    # file_id
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id

    # Сохраняем proof_file_id
    await attach_proof(payment["id"], file_id)

    # Сообщение пользователю — только если он НЕ в группе фонда
    if message.chat.id != FUND_GROUP_ID:
        await message.answer(
            "✅ Квитанция принята!\n"
            "Заявка отправлена на проверку. Ожидайте подтверждения администратором.",
            reply_markup=main_kb
        )

    # Определяем, к чему делать reply в группе
    if message.chat.id == FUND_GROUP_ID:
        # Квитанция уже в нужной группе
        reply_to_id = message.message_id
    else:
        # Квитанция в личке/другом чате — копируем в группу
        copied = await bot.copy_message(
            chat_id=FUND_GROUP_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        reply_to_id = copied.message_id

    # Карточка заявки reply к квитанции
    user_link = f"<a href='tg://user?id={payment['user_id']}'>{payment.get('username') or payment['user_id']}</a>"

    payment_msg = await bot.send_message(
        chat_id=FUND_GROUP_ID,
        text=(
            f"📥 <b>Заявка на пополнение #{payment['id']}</b>\n\n"
            f"👤 Пользователь: {user_link}\n"
            f"💰 Сумма: {payment['amount']} ₸\n\n"
            f"⏳ Ожидает подтверждения"
        ),
        reply_markup=payment_kb(payment["id"]),
        reply_to_message_id=reply_to_id
    )

    await update_payment_message_id(payment["id"], payment_msg.message_id)


# --- Fallback на “похожее на квитанцию”, но НЕ photo/document ---
# (Чтобы не спамил на всё подряд, ограничим только некоторыми типами)
@router.message(F.animation | F.video | F.voice | F.audio | F.sticker)
async def proof_fallback(message: Message):
    payment = await get_pending_payment(message.from_user.id)
    if payment and not (payment.get("proof_file_id") or payment.get("message_id")):
        await message.answer(
            "Я жду квитанцию.\n"
            "Пожалуйста, отправьте фото или PDF квитанции (как документ).",
            reply_markup=pending_kb
        )
