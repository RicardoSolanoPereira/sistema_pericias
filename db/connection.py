from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os


def get_db_url() -> str:
    # Prioriza variável de ambiente (bom pra futuro deploy)
    return os.getenv("DB_URL", "sqlite:///data/app.db")


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        db_url = get_db_url()

        # SQLite local: check_same_thread False por causa do Streamlit
        connect_args = (
            {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        )

        _engine = create_engine(
            db_url, echo=False, future=True, connect_args=connect_args
        )
        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, future=True
        )

    return _engine


def get_session():
    """Retorna uma sessão SQLAlchemy. Use com 'with' quando possível."""
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal()
