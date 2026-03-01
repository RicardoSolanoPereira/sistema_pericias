from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import create_engine, text

SQLITE_PATH = "data/app.db"
PG_URL = os.environ["PG_URL"]


def _to_iso_datetime(v: Any) -> Optional[str]:
    """Converte valores para string datetime que o Postgres entende."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def main() -> None:
    # 1) Lê feriados do SQLite
    sconn = sqlite3.connect(SQLITE_PATH)
    sconn.row_factory = sqlite3.Row
    cur = sconn.cursor()

    rows = cur.execute(
        "SELECT id, data, escopo, local, descricao, fonte, created_at FROM feriados"
    ).fetchall()

    feriados = []
    now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    for r in rows:
        d = dict(r)

        # normalizações seguras
        d["local"] = (d.get("local") or "").strip().lower()
        d["escopo"] = (d.get("escopo") or "").strip().upper()
        d["data"] = _to_iso_datetime(d.get("data"))

        created_at = _to_iso_datetime(d.get("created_at"))
        d["created_at"] = created_at or now_iso  # ✅ garante NOT NULL no Postgres

        feriados.append(
            {
                "data": d["data"],
                "escopo": d["escopo"],
                "local": d["local"],
                "descricao": d.get("descricao"),
                "fonte": d.get("fonte"),
                "created_at": d["created_at"],
            }
        )

    sconn.close()

    print(f"SQLite feriados lidos: {len(feriados)}")

    # 2) Conecta no Postgres e faz UPSERT pela constraint
    engine = create_engine(
        PG_URL,
        future=True,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"},
    )

    upsert = text(
        """
        INSERT INTO feriados (data, escopo, local, descricao, fonte, created_at)
        VALUES (:data, :escopo, :local, :descricao, :fonte, :created_at)
        ON CONFLICT ON CONSTRAINT uq_feriados_data_escopo_local
        DO UPDATE SET
            descricao = EXCLUDED.descricao,
            fonte = EXCLUDED.fonte
        """
    )

    with engine.begin() as conn:
        before = conn.execute(text('SELECT COUNT(*) FROM "feriados"')).scalar_one()
        conn.execute(upsert, feriados)
        after = conn.execute(text('SELECT COUNT(*) FROM "feriados"')).scalar_one()

    print(f"Postgres feriados antes: {before}")
    print(f"Postgres feriados depois: {after}")
    print("OK. Sincronização concluída.")


if __name__ == "__main__":
    main()
