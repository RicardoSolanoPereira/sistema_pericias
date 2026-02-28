from __future__ import annotations

import os
import sqlite3
from typing import Optional
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def get_db_url() -> str:
    """
    Ordem de prioridade:
    1) Streamlit Secrets (Cloud)
    2) Variável de ambiente DB_URL
    3) Fallback SQLite local
    """

    # 1️⃣ Streamlit Secrets (Cloud)
    try:
        import streamlit as st

        if "DB_URL" in st.secrets:
            db_url = str(st.secrets["DB_URL"]).strip()
            if db_url:
                return db_url
    except Exception:
        pass

    # 2️⃣ Variável de ambiente
    env_url = os.getenv("DB_URL")
    if env_url and env_url.strip():
        return env_url.strip()

    # 3️⃣ Fallback SQLite local
    repo_root = Path(__file__).resolve().parent.parent
    db_path = repo_root / "data" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return f"sqlite:///{db_path.as_posix()}"


class Base(DeclarativeBase):
    pass


# Ativa foreign keys no SQLite
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

        # SQLite
        if db_url.startswith("sqlite"):
            connect_args = {
                "check_same_thread": False,
                "detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            }
        # PostgreSQL (Neon)
        else:
            connect_args = {"options": "-c search_path=public"}

        _engine = create_engine(
            db_url,
            echo=False,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
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
