# migrate.py (в корне проекта)
import sqlite3, pathlib

root = pathlib.Path(__file__).resolve().parent
db_path = root / "database" / "bot_db.sqlite3"
sql_files = [
    root / "migrations" / "2025_10_07_add_transactions.sql",
    root / "migrations" / "2025_10_07_add_views.sql",
]

con = sqlite3.connect(db_path)
try:
    for p in sql_files:
        sql_raw = p.read_text(encoding="utf-8")
        # На случай, если случайно попадут строки с '#'
        sql = "\n".join(line for line in sql_raw.splitlines() if not line.lstrip().startswith("#"))
        con.executescript(sql)
        print(f"✅ Applied: {p.name}")
finally:
    con.close()

print("✅ Done")
