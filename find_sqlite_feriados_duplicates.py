import sqlite3
from collections import defaultdict

SQLITE_PATH = "data/app.db"


def norm_date(v):
    s = str(v)
    # pega só a parte YYYY-MM-DD
    return s[:10]


def norm_key(data, escopo, local):
    esc = (escopo or "").strip().upper()
    loc = (local or "").strip().lower()
    # aplica regra que você usa no seed
    if esc in {"NACIONAL", "ESTADUAL_SP", "TJSP_GERAL"}:
        loc = ""
    return (norm_date(data), esc, loc)


def main():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, data, escopo, local, descricao, fonte FROM feriados"
    ).fetchall()
    conn.close()

    buckets = defaultdict(list)
    for r in rows:
        k = norm_key(r["data"], r["escopo"], r["local"])
        buckets[k].append(dict(r))

    dups = {k: v for k, v in buckets.items() if len(v) > 1}

    print(f"Total feriados (SQLite): {len(rows)}")
    print(f"Chaves únicas normalizadas: {len(buckets)}")
    print(f"Duplicidades (normalizadas): {len(dups)}\n")

    for k, items in dups.items():
        print("DUP:", k)
        for it in items:
            print(
                "  - id:",
                it["id"],
                "| data:",
                it["data"],
                "| escopo:",
                it["escopo"],
                "| local:",
                it["local"],
                "| desc:",
                it["descricao"],
            )
        print()


if __name__ == "__main__":
    main()
