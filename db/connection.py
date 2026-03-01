from __future__ import annotations

import os
import sqlite3
from typing import Optional
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# ===============================
# DATABASE URL
# ===============================


def get_db_url() -> str:
    """
    Ordem de prioridade:
    1) Streamlit Secrets
    2) Variável de ambiente DB_URL
    3) SQLite local (fallback)
    """

    # 1) Streamlit Secrets (Cloud)
    try:
        import streamlit as st

        if "DB_URL" in st.secrets:
            url = str(st.secrets["DB_URL"]).strip()
            if url:
                return url
    except Exception:
        pass

    # 2) Variável de ambiente
    env_url = os.getenv("DB_URL")
    if env_url and env_url.strip():
        return env_url.strip()

    # 3) Fallback SQLite local
    repo_root = Path(__file__).resolve().parent.parent  # .../sistema_pericias
    db_path = repo_root / "data" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


# ===============================
# BASE
# ===============================


class Base(DeclarativeBase):
    pass


# ===============================
# SQLITE PRAGMA (ONLY SQLITE)
# ===============================


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Ativa foreign keys no SQLite.
    Importante: só executa se a conexão for sqlite3.
    """
    try:
        # sqlite3 connections come from module "sqlite3"
        if dbapi_connection.__class__.__module__.startswith("sqlite3"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    except Exception:
        pass


# ===============================
# ENGINE / SESSION
# ===============================

_engine: Optional[Engine] = None
_SessionLocal = None


def get_engine() -> Engine:
    global _engine, _SessionLocal

    if _engine is None:
        db_url = get_db_url()

        # --------------------------
        # SQLITE
        # --------------------------
        if db_url.startswith("sqlite"):
            connect_args = {
                "check_same_thread": False,
                "detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            }

            _engine = create_engine(
                db_url,
                echo=False,
                future=True,
                connect_args=connect_args,
            )

        # --------------------------
        # POSTGRESQL (NEON)
        # --------------------------
        else:
            # IMPORTANTE:
            # - deixe a DB_URL limpa (sem sslmode/channel_binding na URL)
            # - forçamos SSL e AUTOCOMMIT aqui para evitar "transaction is aborted"
            _engine = create_engine(
                db_url,
                echo=False,
                future=True,
                pool_pre_ping=True,
                pool_size=1,
                max_overflow=0,
                connect_args={
                    "sslmode": "require",
                    "autocommit": True,
                },
                isolation_level="AUTOCOMMIT",
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
