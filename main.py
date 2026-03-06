import asyncio
import logging
from pathlib import Path
from aiogram import Dispatcher, Router, F
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
# from aiogram.enums import ParseMode  # если нужно выставлять parse_mode здесь

from config import bot  # проверь, что в config бот создан с parse_mode=HTML
from database.db import init_db
from handlers import start, donation, balance, loan, loan_admin, payment_admin
from handlers.history import history_router
from handlers.history_admin import history_admin_router
from keyboards.default import main_kb
from aiogram.fsm.context import FSMContext
from handlers.debtors import router as debtors_router

print("FIRDAUS BOT: NEW PAYMENTS FLOW ENABLED")


# настройка логов
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# отдельный роутер для дефолтного хэндлера
default_router = Router()

@default_router.message(~F.photo, ~F.document)
async def default_handler(message: Message, state: FSMContext):
    """
    Fallback.
    НЕ мешает FSM: если пользователь в процессе ввода (FSM активен) — молчим.
    """
    # ❗ Если пользователь находится в любом FSM — не перехватываем сообщение
    if await state.get_state() is not None:
        return

    await message.answer(
        "Выберите действие из меню 👇",
        reply_markup=main_kb
    )


async def main():
    # инициализация базы
    await init_db()

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # подключаем роутеры (start — первым для приоритета)
    dp.include_router(start.router)
    dp.include_router(donation.router)
    dp.include_router(balance.router)
    dp.include_router(loan.router)
    dp.include_router(loan_admin.router)
    dp.include_router(payment_admin.router)
    dp.include_router(history_admin_router)  # admin /history_all — до обычного history
    dp.include_router(history_router)   # ← ВАЖНО: history здесь
    dp.include_router(debtors_router)
    dp.include_router(default_router)   # дефолтный — последним

    logging.info("Бот запущен ✅")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")


if __name__ == "__main__":
    asyncio.run(main())
