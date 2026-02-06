from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from keyboards.default import main_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    /start — сброс FSM и показ главного меню.
    Работает из любого состояния.
    """
    await state.clear()
    await message.answer(
        "Ассаляму алейкум!\n\n"
        "Это бот фонда Firdaus. Выберите действие:",
        reply_markup=main_kb
    )
