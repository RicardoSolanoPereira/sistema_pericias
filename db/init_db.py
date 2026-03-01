from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from .connection import get_engine, get_session, Base
from .models import User, Feriado


def _dt0(y: int, m: int, d: int) -> datetime:
    """Normaliza feriado como datetime 00:00 (compatível com seu model atual)."""
    return datetime(y, m, d, 0, 0, 0)


def _norm_local_for_seed(escopo: str, local: str | None) -> str:
    """
    Padroniza local para evitar bugs/duplicidade no SQLite:
    - Para escopos FIXOS (NACIONAL, ESTADUAL_SP, TJSP_GERAL): local sempre '' (vazio)
    - Para escopos locais (MUNICIPAL, TJSP_COMARCA): local obrigatório (normalizado)
    """
    esc = (escopo or "").strip().upper()
    loc = (local or "").strip().lower()

    if esc in {"NACIONAL", "ESTADUAL_SP", "TJSP_GERAL"}:
        return ""  # nunca NULL para FIXOS

    # MUNICIPAL / TJSP_COMARCA precisam de um local definido
    if not loc:
        raise ValueError(f"Escopo {esc} exige 'local' preenchido (ex.: 'ilhabela').")

    return loc


def _upsert_feriado(
    s,
    *,
    data_dt: datetime,
    escopo: str,
    local: str,
    descricao: str | None,
    fonte: str | None,
) -> None:
    """
    UPSERT compatível com SQLite e Postgres:
    - SQLite: ON CONFLICT com index_elements
    - Postgres: ON CONFLICT usando a constraint uq_feriados_data_escopo_local
    """
    dialect = s.get_bind().dialect.name

    base = dict(
        data=data_dt,
        escopo=escopo,
        local=local,
        descricao=descricao,
        fonte=fonte,
        created_at=datetime.utcnow(),
    )

    if dialect == "postgresql":
        stmt = (
            pg_insert(Feriado)
            .values(**base)
            .on_conflict_do_update(
                constraint="uq_feriados_data_escopo_local",
                set_={
                    "descricao": descricao,
                    "fonte": fonte,
                    "created_at": datetime.utcnow(),
                },
            )
        )
    else:
        stmt = (
            sqlite_insert(Feriado)
            .values(**base)
            .on_conflict_do_update(
                index_elements=["data", "escopo", "local"],
                set_={
                    "descricao": descricao,
                    "fonte": fonte,
                    "created_at": datetime.utcnow(),
                },
            )
        )

    s.execute(stmt)


def _seed_feriados_basicos(ano: int) -> None:
    """
    Seed mínimo e seguro (idempotente, pode rodar várias vezes sem duplicar):
    - Nacionais fixos
    - Estadual SP fixo (09/07)
    - Municipal Ilhabela (exemplo)
    Obs.: feriados móveis (Carnaval, Sexta Santa, Corpus Christi) e suspensões TJSP
    você pode inserir por script ou pela interface depois.
    """
    feriados = [
        # NACIONAIS FIXOS
        ("NACIONAL", None, _dt0(ano, 1, 1), "Confraternização Universal", None),
        ("NACIONAL", None, _dt0(ano, 4, 21), "Tiradentes", None),
        ("NACIONAL", None, _dt0(ano, 5, 1), "Dia do Trabalho", None),
        ("NACIONAL", None, _dt0(ano, 9, 7), "Independência do Brasil", None),
        ("NACIONAL", None, _dt0(ano, 10, 12), "Nossa Senhora Aparecida", None),
        ("NACIONAL", None, _dt0(ano, 11, 2), "Finados", None),
        ("NACIONAL", None, _dt0(ano, 11, 15), "Proclamação da República", None),
        ("NACIONAL", None, _dt0(ano, 12, 25), "Natal", None),
        # ESTADO SP (fixo)
        (
            "ESTADUAL_SP",
            "sp",
            _dt0(ano, 7, 9),
            "Revolução Constitucionalista (SP)",
            None,
        ),
        # MUNICIPAL (Ilhabela) - exemplo
        (
            "MUNICIPAL",
            "ilhabela",
            _dt0(ano, 9, 3),
            "Aniversário de Ilhabela",
            "Lei Municipal / calendário oficial",
        ),
    ]

    with get_session() as s:
        for escopo, local, data_dt, descricao, fonte in feriados:
            local_norm = _norm_local_for_seed(escopo, local)

            _upsert_feriado(
                s,
                data_dt=data_dt,
                escopo=escopo.strip().upper(),
                local=local_norm,
                descricao=descricao,
                fonte=fonte,
            )

        s.commit()


def init_db(seed_feriados: bool = True, ano_seed: int | None = None) -> None:
    load_dotenv()  # garante que DB_URL funcione no Streamlit também

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    default_email = os.getenv("DEFAULT_USER_EMAIL", "admin@local").strip()
    default_name = os.getenv("DEFAULT_USER_NAME", "Admin Local").strip()

    # Seed do usuário default (idempotente) com proteção contra corrida
    with get_session() as s:
        try:
            exists = s.execute(
                select(User).where(User.email == default_email)
            ).scalar_one_or_none()
            if not exists:
                s.add(User(name=default_name, email=default_email))
                s.commit()
        except IntegrityError:
            # outro processo/worker pode ter criado o mesmo email ao mesmo tempo
            s.rollback()

    if seed_feriados:
        ano = ano_seed or datetime.utcnow().year
        _seed_feriados_basicos(ano)


if __name__ == "__main__":
    init_db(seed_feriados=True)
    print("DB inicializado com sucesso.")
