# scripts/check_transactions.py
import sqlite3, sys

DB = "database/bot_db.sqlite3"
if len(sys.argv) < 2:
    print("Использование: python scripts/check_transactions.py <user_id>")
    sys.exit(1)

uid = int(sys.argv[1])
con = sqlite3.connect(DB)
rows = con.execute("SELECT count(*) FROM transactions WHERE user_id=?", (uid,)).fetchone()[0]
con.close()
print("rows =", rows)
