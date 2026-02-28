from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# -----------------------------
# Models
# -----------------------------
@dataclass(frozen=True)
class BackupResult:
    source_db: Path
    backup_file: Path
    created_at: datetime
    size_bytes: int
    integrity_ok: Optional[bool] = None
    integrity_message: Optional[str] = None
    integrity_checked_at: Optional[datetime] = None


# -----------------------------
# Paths / discovery
# -----------------------------
def project_root() -> Path:
    """
    Resolve raiz estável do projeto:
    scripts/backup_diario.py -> <raiz do projeto>
    """
    return Path(__file__).resolve().parents[1]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def find_db_path(root: Path, filename: str = "app.db") -> Path:
    candidates = [
        root / filename,
        root / "db" / filename,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c.resolve()

    found = next(root.rglob(filename), None)
    if found and found.exists() and found.is_file():
        return found.resolve()

    raise FileNotFoundError(
        f"Não foi possível localizar {filename} a partir de {root}."
    )


# -----------------------------
# SQLite ops
# -----------------------------
def sqlite_integrity_check(db_path: Path) -> tuple[bool, str]:
    """
    Roda PRAGMA integrity_check (retorna 'ok' quando íntegro).
    """
    db_path = db_path.resolve()
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    msg = str(row[0]) if row else "no result"
    return (msg.lower() == "ok"), msg


def sqlite_hot_backup(source_db: Path, backup_file: Path) -> None:
    """
    Backup "quente" seguro usando API nativa do SQLite.
    """
    source_db = source_db.resolve()
    backup_file = backup_file.resolve()

    src_uri = f"file:{source_db.as_posix()}?mode=ro"
    with sqlite3.connect(src_uri, uri=True) as src_conn:
        with sqlite3.connect(backup_file.as_posix()) as dst_conn:
            src_conn.backup(dst_conn)


# -----------------------------
# Manifest / cleanup
# -----------------------------
def write_last_backup_manifest(backup_dir: Path, result: BackupResult) -> Path:
    manifest = backup_dir / "last_backup.json"
    payload = {
        "source_db": str(result.source_db),
        "backup_file": result.backup_file.name,
        "created_at": result.created_at.isoformat(timespec="seconds"),
        "size_bytes": result.size_bytes,
        "integrity_ok": result.integrity_ok,
        "integrity_message": result.integrity_message,
        "integrity_checked_at": (
            result.integrity_checked_at.isoformat(timespec="seconds")
            if result.integrity_checked_at
            else None
        ),
    }
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def cleanup_old_backups(backup_dir: Path, pattern: str, keep: int) -> list[Path]:
    files = [p for p in backup_dir.glob(pattern) if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    removed: list[Path] = []
    for old in files[keep:]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            pass
    return removed


# -----------------------------
# Main orchestration
# -----------------------------
def run_backup(
    *,
    root: Path,
    db_filename: str,
    backup_dir: Path,
    prefix: str,
    max_backups: int,
    write_manifest: bool,
) -> BackupResult:
    ensure_dir(backup_dir)

    db_path = find_db_path(root, filename=db_filename)

    created_at = datetime.now()
    timestamp = created_at.strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = (backup_dir / f"{prefix}{timestamp}.db").resolve()

    # 1) backup seguro
    sqlite_hot_backup(db_path, backup_file)

    size_bytes = backup_file.stat().st_size

    # 2) integrity do BACKUP (sempre)
    integrity_checked_at = datetime.now()
    ok, msg = sqlite_integrity_check(backup_file)
    integrity_ok = ok
    integrity_message = None if ok else msg

    result = BackupResult(
        source_db=db_path,
        backup_file=backup_file,
        created_at=created_at,
        size_bytes=size_bytes,
        integrity_ok=integrity_ok,
        integrity_message=integrity_message,
        integrity_checked_at=integrity_checked_at,
    )

    # 3) manifesto
    if write_manifest:
        write_last_backup_manifest(backup_dir, result)

    # 4) limpeza
    cleanup_old_backups(backup_dir, pattern=f"{prefix}*.db", keep=max_backups)

    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Backup automático do SQLite (app.db) com retenção e manifesto."
    )
    p.add_argument(
        "--db-filename",
        default="app.db",
        help="Nome do arquivo do banco (padrão: app.db).",
    )
    p.add_argument(
        "--backup-dir",
        default="backups",
        help="Pasta de backups (relativa à raiz, se não absoluta).",
    )
    p.add_argument(
        "--prefix", default="app_backup_", help="Prefixo do nome do arquivo de backup."
    )
    p.add_argument(
        "--max-backups",
        type=int,
        default=30,
        help="Quantidade máxima de backups para manter.",
    )
    p.add_argument(
        "--no-manifest",
        action="store_true",
        help="Não escreve backups/last_backup.json.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    root = project_root()

    backup_dir = Path(args.backup_dir).expanduser()
    if not backup_dir.is_absolute():
        backup_dir = (root / backup_dir).resolve()

    try:
        result = run_backup(
            root=root,
            db_filename=args.db_filename,
            backup_dir=backup_dir,
            prefix=args.prefix,
            max_backups=max(1, int(args.max_backups)),
            write_manifest=not bool(args.no_manifest),
        )
    except Exception as e:
        print(f"[ERRO] Backup falhou: {e}", file=sys.stderr)
        return 2

    size_mb = result.size_bytes / (1024 * 1024)

    print("[OK] Backup criado")
    print(f"     Origem:  {result.source_db}")
    print(f"     Pasta:   {result.backup_file.parent}")
    print(f"     Arquivo: {result.backup_file.name}")
    print(f"     Data:    {result.created_at:%d/%m/%Y %H:%M:%S}")
    print(f"     Tamanho: {size_mb:.2f} MB")
    if result.integrity_ok:
        print("     Integrity (backup): OK")
    else:
        print(f"     Integrity (backup): FALHA ({result.integrity_message})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
