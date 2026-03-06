import asyncio
import aiosqlite
from database.db import DB_PATH

async def reset_month():
    ym = "2025-09"  # текущий месяц
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM monthly_limits WHERE ym = ?", (ym,))
        await db.commit()
    print(f"✅ Лимит {ym} сброшен. При следующем запросе пересчитается заново.")

if __name__ == "__main__":
    asyncio.run(reset_month())
