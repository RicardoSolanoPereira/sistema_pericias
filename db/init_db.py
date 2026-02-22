import os
from dotenv import load_dotenv
from sqlalchemy import select
from .connection import get_engine, get_session, Base
from .models import User


def init_db():
    load_dotenv()  # garante que DB_URL funcione no Streamlit também

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    default_email = os.getenv("DEFAULT_USER_EMAIL", "admin@local")
    default_name = os.getenv("DEFAULT_USER_NAME", "Admin Local")

    with get_session() as s:
        exists = s.execute(
            select(User).where(User.email == default_email)
        ).scalar_one_or_none()

        if not exists:
            s.add(User(name=default_name, email=default_email))
            s.commit()


if __name__ == "__main__":
    init_db()
    print("DB inicializado com sucesso.")
