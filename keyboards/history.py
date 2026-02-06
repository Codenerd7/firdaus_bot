# =============================
# keyboards/history.py
# =============================
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# callback_data формат: "history:dst" где dst ∈ {pm,group}

def history_destination_kb():
    kb = InlineKeyboardBuilder()
    kb.add(
        InlineKeyboardButton(text="📬 В ЛС", callback_data="history:pm"),
        InlineKeyboardButton(text="📢 Опубликовать здесь", callback_data="history:group"),
    )
    kb.adjust(1)
    return kb.as_markup()