from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Almaty")


def normalize_due_date(raw: str) -> str:
    """
    Принимает строго дату в формате dd.mm.yyyy
    Возвращает нормализованную строку тоже в формате dd.mm.yyyy
    Например:
    1.2.2026 -> 01.02.2026
    """
    raw = (raw or "").strip()
    dt = datetime.strptime(raw, "%d.%m.%Y")
    return dt.strftime("%d.%m.%Y")


def validate_due_date_not_past(ddmmyyyy: str) -> None:
    """
    Проверяет, что дата не в прошлом.
    Сегодняшнюю дату разрешаем.
    """
    dt = datetime.strptime(ddmmyyyy, "%d.%m.%Y")
    today = datetime.now(TZ).date()

    if dt.date() < today:
        raise ValueError("past")