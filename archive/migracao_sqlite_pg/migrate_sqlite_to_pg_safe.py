# migrate_sqlite_to_pg_safe.py
# Migração segura SQLite -> Postgres (Neon)
# - Copia apenas tabelas principais (exceto users/feriados)
# - Mantém IDs (para preservar relacionamentos)
# - Usa ON CONFLICT (id) DO NOTHING (idempotente)
# - Normaliza booleans (SQLite 0/1 -> Postgres True/False)

from __future__ import annotations

import os
import sqlite3
from typing import Any

from sqlalchemy import create_engine, text


SQLITE_PATH = "data/app.db"
PG_URL = os.environ["PG_URL"]

# Tabelas que vamos migrar (as que estavam vazias no Postgres)
TABLES = ["processos", "andamentos", "prazos", "agendamentos", "financeiro"]


def normalize_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """
    Normaliza tipos do SQLite para Postgres.
    - booleans: SQLite frequentemente usa 0/1; Postgres espera True/False
    """
    r = dict(row)

    if table == "prazos":
        if "concluido" in r and r["concluido"] is not None:
            r["concluido"] = bool(r["concluido"])

    if table == "agendamentos":
        for k in ("alerta_24h_enviado", "alerta_2h_enviado"):
            if k in r and r[k] is not None:
                r[k] = bool(r[k])

    return r


def fetch_sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    cur = conn.cursor()
    rows = cur.execute(f"SELECT * FROM {table}").fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []

    data = [dict(zip(cols, r)) for r in rows]
    return [normalize_row(table, x) for x in data]


def insert_pg_rows(pg_conn, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    cols = list(rows[0].keys())
    col_list = ", ".join([f'"{c}"' for c in cols])
    val_list = ", ".join([f":{c}" for c in cols])

    # Inserção idempotente por PK "id"
    stmt = text(
        f'INSERT INTO "{table}" ({col_list}) VALUES ({val_list}) '
        f'ON CONFLICT ("id") DO NOTHING'
    )
    pg_conn.execute(stmt, rows)
    return len(rows)


def main() -> None:
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    pg_engine = create_engine(
        PG_URL,
        future=True,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"},
    )

    print("MIGRANDO SQLite -> Postgres (SAFE)...")
    with pg_engine.begin() as pg_conn:
        for t in TABLES:
            rows = fetch_sqlite_rows(sqlite_conn, t)
            inserted = insert_pg_rows(pg_conn, t, rows)
            print(
                f"{t}: {len(rows)} lidos do SQLite, enviados {inserted} (conflict por id ignora)"
            )

    sqlite_conn.close()
    print("OK. Migração concluída.")


if __name__ == "__main__":
    main()
