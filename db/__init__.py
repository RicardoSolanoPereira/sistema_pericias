from db.connection import get_engine, Base


def init_db():
    from db import models  # noqa: F401  (registra as tabelas no metadata)

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
