import os
import sqlite3
from datetime import datetime
from sqlalchemy import create_engine, text

SQLITE_PATH = "data/app.db"
PG_URL = os.environ["PG_URL"]


def norm_key(data, escopo, local):
    # normalização igual a usada no seed
    esc = (escopo or "").strip().upper()
    loc = (local or "").strip().lower()
    # data como string ISO (mantém precisão)
    d = str(data)
    return (d, esc, loc)


def main():
    # SQLite
    sconn = sqlite3.connect(SQLITE_PATH)
    sconn.row_factory = sqlite3.Row
    srows = sconn.execute(
        "SELECT data, escopo, local, descricao, fonte FROM feriados"
    ).fetchall()
    sconn.close()

    sqlite_map = {}
    for r in srows:
        k = norm_key(r["data"], r["escopo"], r["local"])
        sqlite_map[k] = dict(r)

    # Postgres
    engine = create_engine(
        PG_URL, future=True, pool_pre_ping=True, connect_args={"sslmode": "require"}
    )
    with engine.connect() as conn:
        prows = (
            conn.execute(
                text('SELECT data, escopo, local, descricao, fonte FROM "feriados"')
            )
            .mappings()
            .all()
        )

    pg_set = set(norm_key(r["data"], r["escopo"], r["local"]) for r in prows)
    sqlite_set = set(sqlite_map.keys())

    missing_in_pg = sorted(list(sqlite_set - pg_set))
    extra_in_pg = sorted(list(pg_set - sqlite_set))

    print(f"SQLite: {len(sqlite_set)} keys")
    print(f"Postgres: {len(pg_set)} keys")
    print(f"Missing in Postgres: {len(missing_in_pg)}")
    for k in missing_in_pg:
        r = sqlite_map.get(k, {})
        print(" -", k, "|", r.get("descricao"), "|", r.get("fonte"))

    print(f"\nExtra in Postgres (não esperado): {len(extra_in_pg)}")
    for k in extra_in_pg:
        print(" +", k)


if __name__ == "__main__":
    main()
