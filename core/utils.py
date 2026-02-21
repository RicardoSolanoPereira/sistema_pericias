from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


def now_br() -> datetime:
    """Data/hora atual no fuso do Brasil."""
    return datetime.now(BRAZIL_TZ)


def ensure_br(dt: datetime) -> datetime:
    """
    Garante datetime no fuso Brasil.
    - Se dt for naive (sem tzinfo), assume que já está no horário do Brasil.
    - Se dt tiver tzinfo, converte para Brasil.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BRAZIL_TZ)
    return dt.astimezone(BRAZIL_TZ)


def date_to_br_datetime(d: date) -> datetime:
    """Converte date -> datetime 00:00 no fuso do Brasil."""
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=BRAZIL_TZ)


def format_date_br(dt: datetime) -> str:
    """Formata datetime no padrão BR (dd/mm/aaaa) no fuso Brasil."""
    dt_br = ensure_br(dt)
    return dt_br.strftime("%d/%m/%Y")
