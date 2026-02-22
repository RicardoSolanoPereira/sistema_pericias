from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.engine import Engine
import os


def get_db_url() -> str:
    # Prioriza variável de ambiente (bom pra futuro deploy)
    return os.getenv("DB_URL", "sqlite:///data/app.db")


class Base(DeclarativeBase):
    pass


# 🔐 Garante integridade referencial no SQLite
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        db_url = get_db_url()

        connect_args = (
            {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        )

        _engine = create_engine(
            db_url,
            echo=False,
            future=True,
            connect_args=connect_args,
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
