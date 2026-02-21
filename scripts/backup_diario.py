from __future__ import annotations

import shutil
from pathlib import Path
from datetime import datetime

# Pasta de backups
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

# Quantidade máxima de backups para manter
MAX_BACKUPS = 30


def find_db_path() -> Path:
    """
    Procura o arquivo app.db a partir da raiz do projeto.
    Prioriza:
    - ./app.db
    - ./db/app.db
    - qualquer outro app.db recursivo (primeiro encontrado)
    """
    candidates = [
        Path("app.db"),
        Path("db") / "app.db",
    ]
    for c in candidates:
        if c.exists():
            return c

    found = list(Path(".").rglob("app.db"))
    if found:
        return found[0]

    raise FileNotFoundError("Não foi possível localizar app.db no projeto.")


def main():
    try:
        db_path = find_db_path()
    except FileNotFoundError as e:
        print(str(e))
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = BACKUP_DIR / f"app_backup_{timestamp}.db"

    shutil.copy2(db_path, backup_file)
    print(f"Backup criado: {backup_file} (origem: {db_path})")

    backups = sorted(BACKUP_DIR.glob("app_backup_*.db"))
    if len(backups) > MAX_BACKUPS:
        for old in backups[:-MAX_BACKUPS]:
            old.unlink()
            print(f"Backup antigo removido: {old}")


if __name__ == "__main__":
    main()
