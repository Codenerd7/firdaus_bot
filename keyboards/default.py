from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Кнопки
BTN_CONTRIBUTE = "💰 Пополнить фонд"
BTN_LOAN = "📌 Займ"
BTN_CHECK_BALANCE = "📊 Проверить баланс"
BTN_HISTORY = "📜 История"
BTN_CANCEL_PAYMENT = "🚫 Отменить заявку"

# Главное меню
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_CONTRIBUTE)],
        [KeyboardButton(text=BTN_LOAN)],
        [KeyboardButton(text=BTN_CHECK_BALANCE)],
        [KeyboardButton(text=BTN_HISTORY)],
    ],
    resize_keyboard=True
)

# Меню с кнопкой отмены (показывается когда есть pending заявка)
pending_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_CANCEL_PAYMENT)],
        [KeyboardButton(text=BTN_CHECK_BALANCE)],
    ],
    resize_keyboard=True
)
