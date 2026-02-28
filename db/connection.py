from __future__ import annotations

import os
import sqlite3
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def get_db_url() -> str:
    return os.getenv("DB_URL", "sqlite:///data/app.db")


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


_engine: Optional[Engine] = None
_SessionLocal = None


def _build_connect_args(db_url: str) -> dict:
    if db_url.startswith("sqlite"):
        return {
            "check_same_thread": False,
            "detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        }
    return {}


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        db_url = get_db_url()
        connect_args = _build_connect_args(db_url)

        _engine = create_engine(
            db_url,
            echo=False,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
        )

        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            future=True,
        )

    return _engine


def get_session():
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal()
