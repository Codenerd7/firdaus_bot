import aiosqlite
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from database.db import (
    get_total_contributions,
    get_active_loans,
    get_attempt,
    update_attempt,
    reset_attempt,
    DB_PATH,
)

TZ = ZoneInfo("Asia/Almaty")


async def calculate_monthly_limit() -> int:
    """
    Возвращает лимит для текущего месяца.
    Фиксируется 1-го числа и хранится в БД.
    """
    today = datetime.now(TZ)
    ym = f"{today.year}-{today.month:02d}"  # например: "2025-09"

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT limit_amount FROM monthly_limits WHERE ym = ?", (ym,))
        row = await cursor.fetchone()

        if row:  # лимит уже есть в базе
            return row[0]

        # считаем свободные средства
        contributions = await get_total_contributions()
        active_loans = await get_active_loans()
        free_sum = contributions - active_loans

        if free_sum <= 0:
            limit = 0
        else:
            limit = (free_sum // 5) // 100 * 100  # округляем вниз до сотни

        # сохраняем лимит в БД
        await db.execute(
            "INSERT OR REPLACE INTO monthly_limits (ym, limit_amount) VALUES (?, ?)",
            (ym, limit)
        )
        await db.commit()
        return limit


async def check_attempt(user_id: int, requested: int) -> tuple[bool, str]:
    """
    Проверка лимита и попыток.
    Возвращает (разрешено?, сообщение)
    """
    limit = await calculate_monthly_limit()
    attempts, blocked_until = await get_attempt(user_id)

    now = datetime.now(TZ)
    if blocked_until and now < datetime.fromisoformat(blocked_until):
        return False, f"⛔ Вы заблокированы до {blocked_until} за превышение лимита."

    if requested <= limit:
        await reset_attempt(user_id)
        return True, ""

    # превышен лимит → увеличиваем счётчик
    attempts += 1
    if attempts >= 4:
        blocked_until = (now + timedelta(hours=1)).isoformat()
        await update_attempt(user_id, attempts, blocked_until)
        return False, "❌ Вы трижды превысили лимит. Заблокированы на 1 час."
    else:
        await update_attempt(user_id, attempts)
        return False, f"Ваш лимит: {limit} ₸. Попытка {attempts}/3. Введите сумму в пределах лимита."
