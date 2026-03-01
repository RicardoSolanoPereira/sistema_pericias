import os
from sqlalchemy import create_engine, text

PG_URL = os.environ["PG_URL"]

TABLES = [
    "users",
    "processos",
    "andamentos",
    "prazos",
    "agendamentos",
    "financeiro",
    "feriados",
]

engine = create_engine(
    PG_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"},
)


def main():
    with engine.begin() as conn:
        for t in TABLES:
            max_id = conn.execute(
                text(f'SELECT COALESCE(MAX(id), 0) FROM "{t}"')
            ).scalar_one()

            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:t, 'id')"),
                {"t": t},
            ).scalar_one()

            if not seq:
                print(f"{t}: sem sequence (ok)")
                continue

            if max_id == 0:
                # sequência não aceita 0; deixa pronta para começar em 1
                conn.execute(
                    text("SELECT setval(:seq, 1, false)"),
                    {"seq": seq},
                )
                print(f"{t}: sequence {seq} -> 1 (is_called=false)")
            else:
                # próximo nextval será max_id+1
                conn.execute(
                    text("SELECT setval(:seq, :val, true)"),
                    {"seq": seq, "val": max_id},
                )
                print(f"{t}: sequence {seq} -> {max_id}")

    print("OK. Sequences ajustadas.")


if __name__ == "__main__":
    main()
