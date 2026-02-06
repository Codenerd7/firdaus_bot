from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from utils.limits import check_attempt
from database.db import (
    add_loan,
    add_witness,
    add_guarantor,
    get_loan_by_id,
    get_active_debt
)
from handlers.loan_admin import admin_kb  # кнопки админа

router = Router()


class LoanFSM(StatesGroup):
    amount = State()
    due_date = State()


# --- Запрос займа ---
@router.message(F.text == "📌 Займ")
async def start_loan(message: Message, state: FSMContext):
    await state.set_state(LoanFSM.amount)
    await message.answer("Введите сумму займа:")


@router.message(LoanFSM.amount)
async def set_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("Введите сумму числом!")
        return

    # --- проверка на активный долг ---
    debt = await get_active_debt(message.from_user.id)
    if debt:
        await message.answer(
            f"⛔ У вас есть непогашенный займ! "
            f"Сначала верните {debt['remaining']} ₸, "
            f"прежде чем брать новый."
        )
        await state.clear()
        return
    # ----------------------------------

    allowed, msg = await check_attempt(message.from_user.id, amount)
    if not allowed:
        await message.answer(msg)
        return

    await state.update_data(amount=amount)
    await state.set_state(LoanFSM.due_date)
    await message.answer("Введите срок возврата (например, 20.10.2025):")


@router.message(LoanFSM.due_date)
async def set_due_date(message: Message, state: FSMContext):
    data = await state.update_data(due_date=message.text)

    loan_id = await add_loan(
        user_id=message.from_user.id,
        username=message.from_user.username,
        amount=data["amount"],
        due_date=data["due_date"]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Стать свидетелем (0/2)", callback_data=f"witness:{loan_id}")],
        [InlineKeyboardButton(text="🤝 Стать поручителем (0/1)", callback_data=f"guarantor:{loan_id}")]
    ])

    borrower_name = message.from_user.full_name or message.from_user.username or str(message.from_user.id)

    await message.answer(
        f"📌 <b>Заёмщик</b>: <a href='tg://user?id={message.from_user.id}'>{borrower_name}</a>\n"
        f"💰 Сумма: {data['amount']} ₸\n"
        f"📅 Срок возврата: {data['due_date']}\n\n"
        "Нужны: 2 свидетеля.\n"
        "Опционально: поручитель.",
        reply_markup=kb
    )
    await state.clear()


# --- Свидетели ---
@router.callback_query(F.data.startswith("witness:"))
async def add_witness_cb(call: CallbackQuery):
    loan_id = int(call.data.split(":")[1])
    result, _ = await add_witness(
        loan_id,
        call.from_user.id,
        call.from_user.username,
        call.from_user.full_name
    )

    if result == "already":
        await call.answer("Вы уже являетесь свидетелем!")
        return
    if result == "author":
        await call.answer("Автор не может быть свидетелем!")
        return
    if result == "full":
        await call.answer("❌ Уже достаточно свидетелей.")
        return

    loan = await get_loan_by_id(loan_id)
    count = len(loan["witnesses"])

    if count >= 2:
        # убираем кнопки у старого сообщения
        await call.message.edit_reply_markup(reply_markup=None)

        # собираем текст с именами свидетелей
        borrower_name = loan["username"] or loan["user_id"]
        borrower_link = f"<a href='tg://user?id={loan['user_id']}'>{borrower_name}</a>"

        witnesses_links = [
            f"👤 <a href='tg://user?id={w['user_id']}'>{w['full_name'] or w['username'] or w['user_id']}</a>"
            for w in loan["witnesses"]
        ]

        guarantor_text = ""
        if loan["guarantor"]:
            g = loan["guarantor"]
            guarantor_text = f"\n🤝 Поручитель: <a href='tg://user?id={g['user_id']}'>{g['full_name'] or g['username'] or g['user_id']}</a>"

        text = (
            f"📌 <b>Заёмщик</b>: {borrower_link}\n"
            f"💰 Сумма: {loan['amount']} ₸\n"
            f"📅 Срок возврата: {loan['due_date']}\n\n"
            f"Свидетели:\n" + "\n".join(witnesses_links) +
            guarantor_text + "\n\n"
            "Админ, выбери действие:"
        )
        await call.message.answer(text, reply_markup=admin_kb(loan_id))
        await call.answer("Вы стали свидетелем!")
        return

    guarantor_text = "🤝 Поручитель подтверждён" if loan["guarantor"] else "🤝 Стать поручителем (0/1)"

    await call.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Стать свидетелем ({count}/2)", callback_data=f"witness:{loan_id}")],
            [InlineKeyboardButton(text=guarantor_text, callback_data=("none" if loan["guarantor"] else f"guarantor:{loan_id}"))]
        ])
    )
    await call.answer("Вы стали свидетелем!")


# --- Поручитель ---
@router.callback_query(F.data.startswith("guarantor:"))
async def add_guarantor_cb(call: CallbackQuery):
    loan_id = int(call.data.split(":")[1])
    result = await add_guarantor(
        loan_id,
        call.from_user.id,
        call.from_user.username,
        call.from_user.full_name
    )

    if result == "exists":
        await call.answer("У займа уже есть поручитель!")
        return
    if result == "author":
        await call.answer("Автор не может быть поручителем!")
        return
    if result == "witness":
        await call.answer("Свидетель не может быть поручителем!")
        return

    loan = await get_loan_by_id(loan_id)
    count = len(loan["witnesses"])

    # если уже есть 2 свидетеля → сразу карточка с поручителем
    if count >= 2:
        await call.message.edit_reply_markup(reply_markup=None)

        borrower_name = loan["username"] or loan["user_id"]
        borrower_link = f"<a href='tg://user?id={loan['user_id']}'>{borrower_name}</a>"

        witnesses_links = [
            f"👤 <a href='tg://user?id={w['user_id']}'>{w['full_name'] or w['username'] or w['user_id']}</a>"
            for w in loan["witnesses"]
        ]

        guarantor_text = ""
        if loan["guarantor"]:
            g = loan["guarantor"]
            guarantor_text = f"\n🤝 Поручитель: <a href='tg://user?id={g['user_id']}'>{g['full_name'] or g['username'] or g['user_id']}</a>"

        text = (
            f"📌 <b>Заёмщик</b>: {borrower_link}\n"
            f"💰 Сумма: {loan['amount']} ₸\n"
            f"📅 Срок возврата: {loan['due_date']}\n\n"
            f"Свидетели:\n" + "\n".join(witnesses_links) +
            guarantor_text + "\n\n"
            "Админ, выбери действие:"
        )
        await call.message.answer(text, reply_markup=admin_kb(loan_id))
        await call.answer("Вы стали поручителем!")
        return

    # иначе просто обновляем клавиатуру
    await call.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Стать свидетелем ({count}/2)", callback_data=f"witness:{loan_id}")],
            [InlineKeyboardButton(text="🤝 Поручитель подтверждён", callback_data="none")]
        ])
    )
    await call.answer("Вы стали поручителем!")
