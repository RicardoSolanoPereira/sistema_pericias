from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


def now_br() -> datetime:
    return datetime.now(BRAZIL_TZ)


def date_to_br_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=BRAZIL_TZ)


def _parse_dt_like(value) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return date_to_br_datetime(value)

    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None

        try:
            return datetime.fromisoformat(v.replace("Z", ""))
        except Exception:
            pass

        try:
            return datetime.strptime(v, "%d/%m/%Y")
        except Exception:
            return None

    return None


def ensure_br(dt: datetime | date | str) -> datetime:
    parsed = _parse_dt_like(dt)
    if parsed is None:
        raise ValueError(f"Data inválida para ensure_br: {dt!r}")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BRAZIL_TZ)
    return parsed.astimezone(BRAZIL_TZ)


def format_date_br(dt: datetime | date | str) -> str:
    dt_br = ensure_br(dt)
    return dt_br.strftime("%d/%m/%Y")
