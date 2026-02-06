import aiosqlite
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB_PATH = Path("database/bot_db.sqlite3")
TZ = ZoneInfo("Asia/Almaty")


# --- helpers ---

def sqlite_utc_now_str() -> str:
    """
    Формат, который SQLite datetime() стабильно понимает:
    YYYY-MM-DD HH:MM:SS (UTC)
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # Взносы
        await db.execute("""
        CREATE TABLE IF NOT EXISTS contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL CHECK(amount >= 0),
            created_at TEXT NOT NULL,
            username TEXT
        )
        """)

        # Займы
        await db.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            amount INTEGER NOT NULL CHECK(amount > 0),
            due_date TEXT NOT NULL,
            issued_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            reject_reason TEXT
        )
        """)

        # Свидетели (с username + full_name)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS loan_witnesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            UNIQUE(loan_id, user_id)
        )
        """)

        # Поручители (с username + full_name)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS loan_guarantor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT
        )
        """)

        # Попытки превышения лимита
        await db.execute("""
        CREATE TABLE IF NOT EXISTS loan_attempts (
            user_id INTEGER PRIMARY KEY,
            attempts INTEGER NOT NULL DEFAULT 0,
            blocked_until TEXT
        )
        """)

        # Возвраты
        await db.execute("""
        CREATE TABLE IF NOT EXISTS repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            paid_at TEXT NOT NULL
        )
        """)

        # Месячные лимиты (фиксируются 1-го числа каждого месяца)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS monthly_limits (
            ym TEXT PRIMARY KEY,           -- формат YYYY-MM
            limit_amount INTEGER NOT NULL  -- сумма лимита
        )
        """)

        # Заявки на пополнение (ожидают подтверждения админа)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            amount INTEGER NOT NULL CHECK(amount > 0),
            status TEXT NOT NULL DEFAULT 'pending',
            proof_file_id TEXT,
            chat_id INTEGER,
            message_id INTEGER,
            created_at TEXT NOT NULL,
            confirmed_at TEXT,
            admin_id INTEGER
        )
        """)

        await db.commit()


# --- Баланс фонда ---

async def get_total_contributions():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COALESCE(SUM(amount), 0) FROM contributions")
        return (await cursor.fetchone())[0]


async def get_active_loans():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COALESCE(SUM(amount), 0) FROM loans WHERE status = 'approved'")
        return (await cursor.fetchone())[0]


async def get_fund_summary_for_ui():
    total_contributions = await get_total_contributions()
    active_loans = await get_active_loans()
    free_sum = total_contributions - active_loans
    if free_sum < 0:
        free_sum = 0
    return {
        "total_contributions": total_contributions,
        "active_loans": active_loans,
        "free_sum": free_sum
    }


# --- Попытки лимита ---

async def get_attempt(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT attempts, blocked_until FROM loan_attempts WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row if row else (0, None)


async def update_attempt(user_id: int, attempts: int, blocked_until: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO loan_attempts (user_id, attempts, blocked_until)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET attempts = ?, blocked_until = ?
        """, (user_id, attempts, blocked_until, attempts, blocked_until))
        await db.commit()


async def reset_attempt(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM loan_attempts WHERE user_id = ?", (user_id,))
        await db.commit()


# --- Работа с долгами и пополнениями ---

async def get_active_debt(user_id: int):
    """Возвращает активный займ пользователя и остаток к возврату"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, amount,
                   COALESCE((SELECT SUM(amount) FROM repayments WHERE loan_id = loans.id), 0) as repaid
            FROM loans
            WHERE user_id = ? AND status = 'approved'
            ORDER BY id ASC LIMIT 1
        """, (user_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        loan_id, amount, repaid = row
        return {"loan_id": loan_id, "remaining": amount - repaid}


async def process_contribution_with_debt(user_id: int, username: str, amount: int):
    """
    Обрабатывает пополнение: сначала гасит долг (если есть),
    остаток или излишек идёт во вклад.
    """
    # Здесь оставляю как было (TZ isoformat), потому что фильтрации по времени нет.
    now = datetime.now(TZ).isoformat()
    debt = await get_active_debt(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        if debt:
            loan_id = debt["loan_id"]
            remaining = debt["remaining"]

            if amount < remaining:
                await db.execute("INSERT INTO repayments (loan_id, amount, paid_at) VALUES (?, ?, ?)",
                                 (loan_id, amount, now))
                await db.commit()
                return f"💸 Внесено {amount} ₸. Это зачтено как частичный возврат долга. Остаток: {remaining - amount} ₸."

            elif amount == remaining:
                await db.execute("INSERT INTO repayments (loan_id, amount, paid_at) VALUES (?, ?, ?)",
                                 (loan_id, amount, now))
                await db.execute("UPDATE loans SET status = 'repaid' WHERE id = ?", (loan_id,))
                await db.commit()
                return f"✅ Долг {amount} ₸ полностью погашен! ДжазакаЛлаху хайран."

            else:
                repayment = remaining
                surplus = amount - remaining
                await db.execute("INSERT INTO repayments (loan_id, amount, paid_at) VALUES (?, ?, ?)",
                                 (loan_id, repayment, now))
                await db.execute("UPDATE loans SET status = 'repaid' WHERE id = ?", (loan_id,))
                await db.execute("INSERT INTO contributions (user_id, amount, created_at, username) VALUES (?, ?, ?, ?)",
                                 (user_id, surplus, now, username))
                await db.commit()
                return (f"✅ Долг {repayment} ₸ полностью погашен!\n"
                        f"💰 Излишек {surplus} ₸ зачтён как пополнение фонда.")
        else:
            await db.execute("INSERT INTO contributions (user_id, amount, created_at, username) VALUES (?, ?, ?, ?)",
                             (user_id, amount, now, username))
            await db.commit()
            return f"💰 Внесено {amount} ₸ в фонд."


# --- Займы и их элементы ---

async def add_loan(user_id: int, username: str, amount: int, due_date: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO loans (user_id, username, amount, due_date, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (user_id, username, amount, due_date))
        await db.commit()
        return cursor.lastrowid


async def add_witness(loan_id: int, user_id: int, username: str = None, full_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM loans WHERE id = ?", (loan_id,))
        author = (await cursor.fetchone())[0]
        if author == user_id:
            return "author", 0

        # проверяем сколько свидетелей уже есть
        cursor = await db.execute("SELECT COUNT(*) FROM loan_witnesses WHERE loan_id = ?", (loan_id,))
        count = (await cursor.fetchone())[0]
        if count >= 2:
            return "full", count

        try:
            await db.execute(
                "INSERT INTO loan_witnesses (loan_id, user_id, username, full_name) VALUES (?, ?, ?, ?)",
                (loan_id, user_id, username, full_name)
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            return "already", count

        cursor = await db.execute("SELECT COUNT(*) FROM loan_witnesses WHERE loan_id = ?", (loan_id,))
        count = (await cursor.fetchone())[0]
        return "ok", count


async def add_guarantor(loan_id: int, user_id: int, username: str = None, full_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM loans WHERE id = ?", (loan_id,))
        author = (await cursor.fetchone())[0]
        if author == user_id:
            return "author"

        cursor = await db.execute(
            "SELECT 1 FROM loan_witnesses WHERE loan_id = ? AND user_id = ?",
            (loan_id, user_id)
        )
        if await cursor.fetchone():
            return "witness"

        try:
            await db.execute(
                "INSERT INTO loan_guarantor (loan_id, user_id, username, full_name) VALUES (?, ?, ?, ?)",
                (loan_id, user_id, username, full_name)
            )
            await db.commit()
            return "ok"
        except aiosqlite.IntegrityError:
            return "exists"


async def get_loan_by_id(loan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        keys = [d[0] for d in cursor.description]
        loan = dict(zip(keys, row))

        # свидетели
        cursor = await db.execute(
            "SELECT user_id, username, full_name FROM loan_witnesses WHERE loan_id = ?", (loan_id,)
        )
        loan["witnesses"] = [
            {"user_id": r[0], "username": r[1], "full_name": r[2]}
            for r in await cursor.fetchall()
        ]

        # поручитель
        cursor = await db.execute(
            "SELECT user_id, username, full_name FROM loan_guarantor WHERE loan_id = ?", (loan_id,)
        )
        g = await cursor.fetchone()
        if g:
            loan["guarantor"] = {"user_id": g[0], "username": g[1], "full_name": g[2]}
        else:
            loan["guarantor"] = None

        return loan


async def approve_loan(loan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        issued_at = datetime.now(TZ).isoformat()
        await db.execute("""
            UPDATE loans
            SET status = 'approved', issued_at = ?
            WHERE id = ?
        """, (issued_at, loan_id))
        await db.commit()


async def reject_loan(loan_id: int, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE loans
            SET status = 'rejected', reject_reason = ?
            WHERE id = ?
        """, (reason, loan_id))
        await db.commit()


# --- Заявки на пополнение (payments) ---

async def get_pending_payment(user_id: int):
    """Возвращает активную pending заявку пользователя (не старше 24 часов)"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, user_id, username, amount, status, proof_file_id,
                   chat_id, message_id, created_at
            FROM payments
            WHERE user_id = ? AND status = 'pending'
              AND datetime(created_at) > datetime('now', '-24 hours')
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        keys = ["id", "user_id", "username", "amount", "status", "proof_file_id",
                "chat_id", "message_id", "created_at"]
        return dict(zip(keys, row))


async def create_payment(user_id: int, username: str, amount: int, chat_id: int):
    """Создаёт заявку на пополнение"""
    now = sqlite_utc_now_str()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO payments (user_id, username, amount, chat_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, amount, chat_id, now))
        await db.commit()
        return cursor.lastrowid


async def update_payment_message_id(payment_id: int, message_id: int):
    """Обновляет message_id после публикации заявки в группе"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET message_id = ? WHERE id = ?",
            (message_id, payment_id)
        )
        await db.commit()


async def attach_proof(payment_id: int, file_id: str):
    """Прикрепляет квитанцию к заявке"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET proof_file_id = ? WHERE id = ?",
            (file_id, payment_id)
        )
        await db.commit()


async def get_payment_by_id(payment_id: int):
    """Получает заявку по ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, user_id, username, amount, status, proof_file_id,
                   chat_id, message_id, created_at, confirmed_at, admin_id
            FROM payments WHERE id = ?
        """, (payment_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        keys = ["id", "user_id", "username", "amount", "status", "proof_file_id",
                "chat_id", "message_id", "created_at", "confirmed_at", "admin_id"]
        return dict(zip(keys, row))


async def confirm_payment(payment_id: int, admin_id: int):
    """Подтверждает заявку и возвращает её данные"""
    now = sqlite_utc_now_str()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE payments
            SET status = 'confirmed', confirmed_at = ?, admin_id = ?
            WHERE id = ?
        """, (now, admin_id, payment_id))
        await db.commit()
    return await get_payment_by_id(payment_id)


async def reject_payment(payment_id: int, admin_id: int):
    """Отклоняет заявку"""
    now = sqlite_utc_now_str()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE payments
            SET status = 'rejected', confirmed_at = ?, admin_id = ?
            WHERE id = ?
        """, (now, admin_id, payment_id))
        await db.commit()


async def cancel_payment(user_id: int):
    """Отменяет pending заявку пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE payments
            SET status = 'cancelled'
            WHERE user_id = ? AND status = 'pending'
        """, (user_id,))
        await db.commit()
