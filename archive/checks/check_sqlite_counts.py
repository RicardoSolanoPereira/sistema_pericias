import sqlite3

conn = sqlite3.connect("data/app.db")
cur = conn.cursor()

tables = [
    "users",
    "processos",
    "andamentos",
    "prazos",
    "agendamentos",
    "financeiro",
    "feriados",
]

print("SQLITE COUNTS:")
for t in tables:
    try:
        count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {count}")
    except Exception as e:
        print(f"{t}: ERRO ({e})")

conn.close()
