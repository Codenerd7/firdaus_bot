# =============================
# services/history_service.py
# =============================
from dataclasses import dataclass
from typing import List, Optional, Literal, Tuple
import aiosqlite

HistoryType = Literal["contribution", "loan", "repayment", "adjustment"]

@dataclass
class ContributionItem:
    dt: str
    amount: int
    receipt_last4: Optional[str]

@dataclass
class LoanItem:
    dt: str
    amount: int
    status: str  # 'paid' | 'unpaid'

@dataclass
class RepaymentItem:
    dt: str
    amount: int
    related_loan_id: Optional[int]


async def ensure_transactions_table(db: aiosqlite.Connection):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('contribution','loan','repayment','adjustment')),
            amount INTEGER NOT NULL,
            receipt_last4 TEXT,
            status TEXT DEFAULT NULL,
            related_loan_id INTEGER,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    await db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);")
    await db.commit()


# ---------- Loaders ----------
async def get_user_contributions(db: aiosqlite.Connection, user_id: int, limit: int = 20) -> List[ContributionItem]:
    sql = (
        "SELECT created_at, amount, COALESCE(receipt_last4, '') "
        "FROM transactions WHERE user_id=? AND type='contribution' "
        "ORDER BY created_at DESC LIMIT ?"
    )
    cur = await db.execute(sql, (user_id, limit))
    rows = await cur.fetchall()
    await cur.close()
    return [ContributionItem(dt=r[0], amount=r[1], receipt_last4=r[2] or None) for r in rows]


async def get_user_loans(db: aiosqlite.Connection, user_id: int, limit: int = 20) -> List[LoanItem]:
    sql = (
        "SELECT created_at, amount, COALESCE(status,'unpaid') "
        "FROM transactions WHERE user_id=? AND type='loan' "
        "ORDER BY created_at DESC LIMIT ?"
    )
    cur = await db.execute(sql, (user_id, limit))
    rows = await cur.fetchall()
    await cur.close()
    return [LoanItem(dt=r[0], amount=r[1], status=r[2]) for r in rows]


async def get_user_repayments(db: aiosqlite.Connection, user_id: int, limit: int = 20) -> List[RepaymentItem]:
    sql = (
        "SELECT created_at, amount, related_loan_id "
        "FROM transactions WHERE user_id=? AND type='repayment' "
        "ORDER BY created_at DESC LIMIT ?"
    )
    cur = await db.execute(sql, (user_id, limit))
    rows = await cur.fetchall()
    await cur.close()
    return [RepaymentItem(dt=r[0], amount=r[1], related_loan_id=r[2]) for r in rows]


# ---------- Helpers ----------
async def get_loan_totals(db: aiosqlite.Connection, loan_id: int) -> Tuple[int, int, int]:
    """Возвращает (loan_amount, repaid_amount, remaining)."""
    # Сумма займа
    cur = await db.execute(
        "SELECT amount, COALESCE(status,'unpaid') FROM transactions WHERE id=? AND type='loan'",
        (loan_id,),
    )
    row = await cur.fetchone()
    await cur.close()
    if not row:
        raise ValueError(f"Loan #{loan_id} not found")
    loan_amount = int(row[0])

    # Сколько уже погашено
    cur = await db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='repayment' AND related_loan_id=?",
        (loan_id,),
    )
    repaid = int((await cur.fetchone())[0])
    await cur.close()

    remaining = max(loan_amount - repaid, 0)
    return loan_amount, repaid, remaining


async def close_loan_if_fully_paid(db: aiosqlite.Connection, loan_id: int) -> bool:
    """Если по займу выплачено >= суммы займа — отмечаем как paid. Возвращает True, если был апдейт."""
    loan_amount, repaid, remaining = await get_loan_totals(db, loan_id)
    if repaid >= loan_amount:
        await db.execute(
            "UPDATE transactions SET status='paid' WHERE id=? AND type='loan' AND COALESCE(status,'unpaid')!='paid'",
            (loan_id,),
        )
        await db.commit()
        return True
    return False


async def record_repayment(
    db: aiosqlite.Connection,
    *,
    user_id: int,
    loan_id: int,
    amount: int,
    note: Optional[str] = None,
) -> int:
    """Создаёт запись возврата, связывает с займом и при необходимости закрывает займ. Возвращает id возврата."""
    cur = await db.execute(
        "INSERT INTO transactions(user_id, type, amount, related_loan_id, note) VALUES (?,?,?,?,?)",
        (user_id, 'repayment', amount, loan_id, note),
    )
    await db.commit()
    repayment_id = cur.lastrowid
    await cur.close()

    # Проверяем закрытие займа
    await close_loan_if_fully_paid(db, loan_id)
    return repayment_id


# ---------- Formatting ----------

def _fmt_money(v: int) -> str:
    return f"{v:,} ₸".replace(",", " ")


def format_history_message_full(
    contributions: List[ContributionItem],
    loans: List[LoanItem],
    repayments: List[RepaymentItem],
    mention: Optional[str] = None,
) -> str:
    if not contributions and not loans and not repayments:
        return "У вас пока нет зарегистрированных операций."

    lines: List[str] = []
    if mention:
        lines.append(f"📜 История для {mention}\n")

    # Взносы
    lines.append("💰 Взносы:")
    if contributions:
        for it in contributions:
            rec = f" — № {it.receipt_last4}" if it.receipt_last4 else ""
            lines.append(f"{it.dt} — {_fmt_money(it.amount)}{rec}")
    else:
        lines.append("— нет записей")
    lines.append("")

    # Займы
    lines.append("💳 Займы:")
    if loans:
        for it in loans:
            status_ru = "Погашен" if it.status == "paid" else "Не погашен"
            lines.append(f"{it.dt} — {_fmt_money(it.amount)} — {status_ru}")
    else:
        lines.append("— нет записей")
    lines.append("")

    # Возвраты
    lines.append("↩️ Возвраты:")
    if repayments:
        for it in repayments:
            suffix = f" — по займу №{it.related_loan_id}" if it.related_loan_id else ""
            lines.append(f"{it.dt} — {_fmt_money(it.amount)}{suffix}")
    else:
        lines.append("— нет записей")

    return "\n".join(lines)


# ---------- All-users loaders ----------

async def get_all_contributions(db: aiosqlite.Connection, limit: int = 20):
    sql = (
        "SELECT created_at, amount, COALESCE(receipt_last4, ''), user_id "
        "FROM transactions WHERE type='contribution' "
        "ORDER BY created_at DESC LIMIT ?"
    )
    cur = await db.execute(sql, (limit,))
    rows = await cur.fetchall()
    await cur.close()
    return rows


async def get_all_loans(db: aiosqlite.Connection, limit: int = 20):
    sql = (
        "SELECT created_at, amount, COALESCE(status,'unpaid'), user_id "
        "FROM transactions WHERE type='loan' "
        "ORDER BY created_at DESC LIMIT ?"
    )
    cur = await db.execute(sql, (limit,))
    rows = await cur.fetchall()
    await cur.close()
    return rows


async def get_all_repayments(db: aiosqlite.Connection, limit: int = 20):
    sql = (
        "SELECT created_at, amount, related_loan_id, user_id "
        "FROM transactions WHERE type='repayment' "
        "ORDER BY created_at DESC LIMIT ?"
    )
    cur = await db.execute(sql, (limit,))
    rows = await cur.fetchall()
    await cur.close()
    return rows


async def _build_user_labels(db: aiosqlite.Connection, user_ids: set) -> dict:
    """Ищет username каждого user_id в таблицах payments/contributions/loans."""
    if not user_ids:
        return {}
    labels: dict = {}
    for table in ("payments", "contributions", "loans"):
        missing = [uid for uid in user_ids if uid not in labels]
        if not missing:
            break
        ph = ",".join("?" * len(missing))
        cur = await db.execute(
            f"SELECT DISTINCT user_id, username FROM {table} "
            f"WHERE user_id IN ({ph}) AND username IS NOT NULL AND username != ''",
            missing,
        )
        for row in await cur.fetchall():
            if row[0] not in labels and row[1]:
                labels[row[0]] = row[1]
        await cur.close()
    return labels


def _user_display(user_id: int, labels: dict) -> str:
    username = labels.get(user_id)
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">user_{user_id}</a>'


def format_history_all_message(
    contributions, loans, repayments, labels: dict,
) -> str:
    """Форматирует общую историю фонда (все пользователи)."""
    if not contributions and not loans and not repayments:
        return "Пока нет зарегистрированных операций."

    lines: List[str] = ["📜 Общая история фонда\n"]

    # Взносы
    lines.append("💰 Взносы:")
    if contributions:
        for dt, amount, receipt_last4, uid in contributions:
            rec = f" — № {receipt_last4}" if receipt_last4 else ""
            who = _user_display(uid, labels)
            lines.append(f"{dt} — {_fmt_money(amount)}{rec} — {who}")
    else:
        lines.append("— нет записей")
    lines.append("")

    # Займы
    lines.append("💳 Займы:")
    if loans:
        for dt, amount, status, uid in loans:
            status_ru = "Погашен" if status == "paid" else "Не погашен"
            who = _user_display(uid, labels)
            lines.append(f"{dt} — {_fmt_money(amount)} — {status_ru} — {who}")
    else:
        lines.append("— нет записей")
    lines.append("")

    # Возвраты
    lines.append("↩️ Возвраты:")
    if repayments:
        for dt, amount, related_loan_id, uid in repayments:
            suffix = f" — по займу №{related_loan_id}" if related_loan_id else ""
            who = _user_display(uid, labels)
            lines.append(f"{dt} — {_fmt_money(amount)}{suffix} — {who}")
    else:
        lines.append("— нет записей")

    return "\n".join(lines)


async def build_history_all_text() -> str:
    """
    Возвращает готовый текст общей истории фонда
    (все пользователи, последние 20 записей по каждому типу).
    """
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        contributions = await get_all_contributions(db, limit=20)
        loans = await get_all_loans(db, limit=20)
        repayments = await get_all_repayments(db, limit=20)

        all_uids: set = set()
        for rows in (contributions, loans, repayments):
            for r in rows:
                all_uids.add(r[3])  # user_id — 4-й элемент

        labels = await _build_user_labels(db, all_uids)

    return format_history_all_message(contributions, loans, repayments, labels)


async def build_history_text(user_id: int, user_title: str | None = None) -> str:
    """
    Возвращает готовый текст истории пользователя
    (взносы / займы / возвраты) в едином формате.
    Единый источник — используется и кнопкой, и командой /history.
    """
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        contributions = await get_user_contributions(db, user_id, limit=20)
        loans = await get_user_loans(db, user_id, limit=20)
        repayments = await get_user_repayments(db, user_id, limit=20)
    return format_history_message_full(contributions, loans, repayments, mention=user_title)