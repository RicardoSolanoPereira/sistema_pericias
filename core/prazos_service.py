from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple, Literal

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from db.models import Prazo, Processo


PrazoStatusFilter = Literal["all", "open", "closed"]


# ============================================================
# DTOs
# ============================================================


@dataclass(frozen=True)
class PrazoCreate:
    processo_id: int
    evento: str
    data_limite: datetime
    prioridade: str = "Média"
    origem: Optional[str] = None
    referencia: Optional[str] = None
    observacoes: Optional[str] = None


@dataclass(frozen=True)
class PrazoUpdate:
    evento: Optional[str] = None
    data_limite: Optional[datetime] = None
    prioridade: Optional[str] = None
    concluido: Optional[bool] = None
    origem: Optional[str] = None
    referencia: Optional[str] = None
    observacoes: Optional[str] = None


# ============================================================
# Service
# ============================================================


class PrazosService:
    _UPDATABLE_FIELDS = {
        "evento",
        "data_limite",
        "prioridade",
        "concluido",
        "origem",
        "referencia",
        "observacoes",
    }

    @staticmethod
    def _clean_str(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        v = val.strip()
        return v if v else None

    @staticmethod
    def _owned_processo(session: Session, owner_user_id: int, processo_id: int) -> bool:
        stmt = select(Processo.id).where(
            Processo.id == processo_id,
            Processo.owner_user_id == owner_user_id,
        )
        return session.execute(stmt).first() is not None

    @staticmethod
    def _apply_status_filter(stmt, status: PrazoStatusFilter):
        if status == "open":
            return stmt.where(Prazo.concluido.is_(False))
        if status == "closed":
            return stmt.where(Prazo.concluido.is_(True))
        # "all"
        return stmt

    # ----------------------------
    # CREATE
    # ----------------------------
    @staticmethod
    def create(session: Session, owner_user_id: int, payload: PrazoCreate) -> Prazo:
        evento = PrazosService._clean_str(payload.evento)
        if not evento:
            raise ValueError("evento é obrigatório")

        if not PrazosService._owned_processo(
            session, owner_user_id, payload.processo_id
        ):
            raise ValueError("processo_id inválido (não pertence ao usuário)")

        prazo = Prazo(
            processo_id=payload.processo_id,
            evento=evento,
            data_limite=payload.data_limite,
            prioridade=payload.prioridade or "Média",
            concluido=False,
            origem=PrazosService._clean_str(payload.origem),
            referencia=PrazosService._clean_str(payload.referencia),
            observacoes=PrazosService._clean_str(payload.observacoes),
        )

        session.add(prazo)
        session.commit()
        session.refresh(prazo)
        return prazo

    # ----------------------------
    # LIST BY PROCESSO
    # ----------------------------
    @staticmethod
    def list_by_processo(
        session: Session,
        owner_user_id: int,
        processo_id: int,
        status: PrazoStatusFilter = "open",
    ) -> List[Prazo]:
        stmt = (
            select(Prazo)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Prazo.processo_id == processo_id,
            )
            .order_by(Prazo.concluido.asc(), Prazo.data_limite.asc(), Prazo.id.desc())
        )

        stmt = PrazosService._apply_status_filter(stmt, status)
        return list(session.execute(stmt).scalars().all())

    # ----------------------------
    # LIST ALL
    # ----------------------------
    @staticmethod
    def list_all(
        session: Session,
        owner_user_id: int,
        status: PrazoStatusFilter = "open",
    ) -> List[Tuple[Prazo, Processo]]:
        stmt = (
            select(Prazo, Processo)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
            .order_by(Prazo.concluido.asc(), Prazo.data_limite.asc(), Prazo.id.desc())
        )

        stmt = PrazosService._apply_status_filter(stmt, status)
        return list(session.execute(stmt).all())

    # ----------------------------
    # GET
    # ----------------------------
    @staticmethod
    def get(session: Session, owner_user_id: int, prazo_id: int) -> Optional[Prazo]:
        stmt = (
            select(Prazo)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Prazo.id == prazo_id,
            )
        )
        return session.execute(stmt).scalars().first()

    # ----------------------------
    # UPDATE
    # ----------------------------
    @staticmethod
    def update(
        session: Session,
        owner_user_id: int,
        prazo_id: int,
        payload: PrazoUpdate,
    ) -> None:
        p = PrazosService.get(session, owner_user_id, prazo_id)
        if not p:
            raise ValueError("Prazo não encontrado")

        data: dict = {}
        for field, val in payload.__dict__.items():
            if field not in PrazosService._UPDATABLE_FIELDS:
                continue
            if val is None:
                continue
            if isinstance(val, str):
                val = PrazosService._clean_str(val)
            data[field] = val

        if "evento" in data and not data["evento"]:
            raise ValueError("evento não pode ficar vazio")

        if data:
            session.execute(update(Prazo).where(Prazo.id == prazo_id).values(**data))
            session.commit()

    # ----------------------------
    # DELETE
    # ----------------------------
    @staticmethod
    def delete(session: Session, owner_user_id: int, prazo_id: int) -> None:
        p = PrazosService.get(session, owner_user_id, prazo_id)
        if not p:
            raise ValueError("Prazo não encontrado")

        session.execute(delete(Prazo).where(Prazo.id == prazo_id))
        session.commit()
