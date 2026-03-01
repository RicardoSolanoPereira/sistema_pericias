import os
from sqlalchemy import create_engine, text

PG_URL = os.environ["PG_URL"]
engine = create_engine(
    PG_URL, future=True, pool_pre_ping=True, connect_args={"sslmode": "require"}
)

tables = [
    "users",
    "processos",
    "andamentos",
    "prazos",
    "agendamentos",
    "financeiro",
    "feriados",
]

print("POSTGRES COUNTS:")
with engine.connect() as conn:
    for t in tables:
        try:
            n = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one()
            print(f"{t}: {n}")
        except Exception as e:
            print(f"{t}: ERRO ({type(e).__name__}: {e})")
