from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Tuple, Literal, Mapping, Any, cast

from sqlalchemy.exc import IntegrityError

from db.connection import get_session
from db.models import Feriado


@dataclass(frozen=True)
class ImportStats:
    inserted: int = 0
    skipped: int = 0  # duplicados / violação de unicidade (na prática)
    errors: int = 0  # parsing/validação/outros


FIXOS = {"NACIONAL", "ESTADUAL_SP", "TJSP_GERAL"}

ESCOPO_ALIASES = {
    "ESTADUAL": "ESTADUAL_SP",
    "SP_ESTADUAL": "ESTADUAL_SP",
    "ESTADUAL-SP": "ESTADUAL_SP",
    "ESTADUAL SP": "ESTADUAL_SP",
    "TJSP": "TJSP_GERAL",
    "RECESSO_TJSP": "TJSP_GERAL",
    "RECESSO TJSP": "TJSP_GERAL",
    "CPC220": "TJSP_GERAL",
    "CPC 220": "TJSP_GERAL",
    "CPC_220": "TJSP_GERAL",
    "CPC-220": "TJSP_GERAL",
    "ART_220": "TJSP_GERAL",
    "ART 220": "TJSP_GERAL",
    "ARTIGO_220": "TJSP_GERAL",
    "ARTIGO 220": "TJSP_GERAL",
}

LocalNormalizeMode = Literal["none", "upper", "slug"]


def _clean_str(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    v = s.strip()
    return v if v else None


def _normalize_escopo(raw: Optional[str]) -> str:
    v = (raw or "").strip().upper()
    if not v:
        raise ValueError("escopo vazio")
    return ESCOPO_ALIASES.get(v, v)


def _parse_date(s: str) -> date:
    s = (s or "").strip()
    if not s:
        raise ValueError("data vazia")

    if "-" in s:
        return datetime.strptime(s, "%Y-%m-%d").date()
    return datetime.strptime(s, "%d/%m/%Y").date()


def parse_date_to_dt(s: str) -> datetime:
    d = _parse_date(s)
    return datetime(d.year, d.month, d.day)  # 00:00


def _validate_headers(fieldnames: list[str] | None) -> None:
    required = {"data", "escopo", "local", "descricao", "fonte"}
    got = set(fieldnames or [])
    if not required.issubset(got):
        missing = sorted(required - got)
        raise ValueError(
            f"CSV precisa ter colunas: {sorted(required)}. "
            f"Faltando: {missing}. "
            f"Encontradas: {sorted(got)}"
        )


def _strip_accents(s: str) -> str:
    # transforma "Ilhabela" -> "Ilhabela", "São Sebastião" -> "Sao Sebastiao"
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _slugify_ascii(s: str) -> str:
    v = _strip_accents((s or "").strip().lower())
    if not v:
        return ""
    v = re.sub(r"[^a-z0-9\s-]", "", v)
    v = re.sub(r"[\s_-]+", "-", v).strip("-")
    return v


def _normalize_local(local: str, mode: LocalNormalizeMode) -> str:
    v = (local or "").strip()
    if not v:
        return ""
    if mode == "none":
        return v
    if mode == "upper":
        return v.upper()
    if mode == "slug":
        return _slugify_ascii(v)
    return v


def _row_to_feriado(
    row: Mapping[str, Optional[str]],
    normalize_local_mode: LocalNormalizeMode = "none",
) -> Tuple[Feriado, str]:
    data_dt = parse_date_to_dt((row.get("data") or ""))
    escopo_final = _normalize_escopo(row.get("escopo"))

    local_raw = (row.get("local") or "").strip()
    descricao = _clean_str(row.get("descricao"))
    fonte = _clean_str(row.get("fonte"))

    if escopo_final in FIXOS:
        local_final = ""
    else:
        local_final = _normalize_local(local_raw, normalize_local_mode)

    fer = Feriado(
        data=data_dt,
        escopo=escopo_final,
        local=local_final,
        descricao=descricao,
        fonte=fonte,
    )
    return fer, escopo_final


def import_csv(
    filepath: str,
    batch_size: int = 300,
    normalize_local_mode: LocalNormalizeMode = "none",
    verbose: bool = False,
) -> ImportStats:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    stats = ImportStats()
    buffer: list[tuple[int, dict[str, Optional[str]]]] = []

    def _flush_buffer(session) -> None:
        """Tenta commitar o lote. Se falhar, faz fallback linha a linha para classificar duplicados."""
        nonlocal stats, buffer
        if not buffer:
            return

        # tenta em lote (rápido)
        try:
            for _idx, row in buffer:
                fer, _ = _row_to_feriado(row, normalize_local_mode=normalize_local_mode)
                session.add(fer)
            session.commit()
            stats = ImportStats(
                inserted=stats.inserted + len(buffer),
                skipped=stats.skipped,
                errors=stats.errors,
            )
            buffer = []
            return
        except IntegrityError as e:
            session.rollback()
            if verbose:
                print(
                    f"[WARN] Commit em lote falhou (n={len(buffer)}). Fazendo fallback linha a linha. Err={e}"
                )
        except Exception as e:
            session.rollback()
            if verbose:
                print(
                    f"[WARN] Commit em lote falhou (n={len(buffer)}). Fallback linha a linha. Err={e}"
                )

        # fallback linha a linha (lento, mas só para o lote que deu problema)
        for idx, row in buffer:
            try:
                fer, _ = _row_to_feriado(row, normalize_local_mode=normalize_local_mode)
                session.add(fer)
                session.commit()
                stats = ImportStats(
                    inserted=stats.inserted + 1,
                    skipped=stats.skipped,
                    errors=stats.errors,
                )
            except IntegrityError as e:
                session.rollback()
                stats = ImportStats(
                    inserted=stats.inserted,
                    skipped=stats.skipped + 1,
                    errors=stats.errors,
                )
                if verbose:
                    print(f"[SKIP] Linha {idx} (IntegrityError): {e}")
            except Exception as e:
                session.rollback()
                stats = ImportStats(
                    inserted=stats.inserted,
                    skipped=stats.skipped,
                    errors=stats.errors + 1,
                )
                print(f"[ERRO] Linha {idx}: {e}")

        buffer = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        _validate_headers(reader.fieldnames)

        with get_session() as s:
            for idx, row_any in enumerate(reader, start=2):
                # DictReader pode retornar Any/Optional; tipamos com segurança
                row = cast(dict[str, Optional[str]], row_any)
                buffer.append((idx, row))

                if len(buffer) >= batch_size:
                    _flush_buffer(s)

            _flush_buffer(s)

    print(
        "Import concluído: "
        f"inserted={stats.inserted} "
        f"skipped(IntegrityError)={stats.skipped} "
        f"errors={stats.errors}"
    )
    return stats


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Caminho do CSV de feriados")
    ap.add_argument(
        "--batch",
        type=int,
        default=300,
        help="Tamanho do lote para commit (performance)",
    )
    ap.add_argument(
        "--normalize-local",
        choices=["none", "upper", "slug"],
        default="none",
        help="Normalização do campo 'local' para escopos não-fixos (municipal/comarca)",
    )
    ap.add_argument(
        "--verbose", action="store_true", help="Mostra detalhes de erros/skip"
    )
    args = ap.parse_args()

    import_csv(
        args.csv,
        batch_size=args.batch,
        normalize_local_mode=cast(LocalNormalizeMode, args.normalize_local),
        verbose=args.verbose,
    )
