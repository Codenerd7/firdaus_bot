import sqlite3
from datetime import datetime

DB_PATH = "database/bot_db.sqlite3"

def shift_one_month_back(dt: datetime) -> datetime:
    """Сдвигаем дату на месяц назад, сохраняя день и время"""
    if dt.month == 1:
        return dt.replace(year=dt.year - 1, month=12)
    else:
        # Если, например, 31 марта → сдвиг на февраль (но февраля нет 31)
        # тогда уменьшаем число до последнего доступного дня месяца
        new_month = dt.month - 1
        new_year = dt.year
        day = dt.day
        while True:
            try:
                return dt.replace(year=new_year, month=new_month, day=day)
            except ValueError:
                day -= 1  # уменьшаем день пока не получится (например 31 → 30 → 28)

with sqlite3.connect(DB_PATH) as conn:
    cur = conn.cursor()
    cur.execute("SELECT id, created_at FROM contributions")
    rows = cur.fetchall()

    for id_, created_at in rows:
        dt = datetime.fromisoformat(created_at)
        new_dt = shift_one_month_back(dt)
        cur.execute("UPDATE contributions SET created_at = ? WHERE id = ?", (new_dt.isoformat(), id_))

    conn.commit()

print("✅ Все взносы сдвинуты на месяц назад")
