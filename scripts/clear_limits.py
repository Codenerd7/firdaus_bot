import sqlite3

DB_PATH = "database/bot_db.sqlite3"

with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM monthly_limits;")
    conn.commit()

print("Таблица monthly_limits очищена ✅")
