from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, update, delete, and_
from sqlalchemy.orm import Session

from db.models import Prazo, Processo


@dataclass
class PrazoCreate:
    processo_id: int
    evento: str
    data_limite: datetime
    prioridade: str = "Média"  # Baixa/Média/Alta
    observacoes: Optional[str] = None


@dataclass
class PrazoUpdate:
    evento: Optional[str] = None
    data_limite: Optional[datetime] = None
    prioridade: Optional[str] = None
    concluido: Optional[bool] = None
    observacoes: Optional[str] = None


class PrazosService:
    @staticmethod
    def _owned_processo(session: Session, owner_user_id: int, processo_id: int) -> bool:
        stmt = select(Processo.id).where(
            Processo.id == processo_id, Processo.owner_user_id == owner_user_id
        )
        return session.execute(stmt).first() is not None

    @staticmethod
    def create(session: Session, owner_user_id: int, payload: PrazoCreate) -> Prazo:
        evento = (payload.evento or "").strip()
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
            prioridade=payload.prioridade,
            concluido=False,
            observacoes=(payload.observacoes or "").strip() or None,
        )
        session.add(prazo)
        session.commit()
        session.refresh(prazo)
        return prazo

    @staticmethod
    def list_by_processo(
        session: Session,
        owner_user_id: int,
        processo_id: int,
        only_open: Optional[bool] = None,
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
        if only_open is True:
            stmt = stmt.where(Prazo.concluido == False)
        if only_open is False:
            stmt = stmt.where(Prazo.concluido == True)
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def list_all(
        session: Session, owner_user_id: int, only_open: Optional[bool] = True
    ) -> List[tuple[Prazo, Processo]]:
        stmt = (
            select(Prazo, Processo)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
            .order_by(Prazo.concluido.asc(), Prazo.data_limite.asc(), Prazo.id.desc())
        )
        if only_open is True:
            stmt = stmt.where(Prazo.concluido == False)
        if only_open is False:
            stmt = stmt.where(Prazo.concluido == True)

        return list(session.execute(stmt).all())

    @staticmethod
    def get(session: Session, owner_user_id: int, prazo_id: int) -> Optional[Prazo]:
        stmt = (
            select(Prazo)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(Processo.owner_user_id == owner_user_id, Prazo.id == prazo_id)
        )
        return session.execute(stmt).scalars().first()

    @staticmethod
    def update(
        session: Session, owner_user_id: int, prazo_id: int, payload: PrazoUpdate
    ) -> None:
        p = PrazosService.get(session, owner_user_id, prazo_id)
        if not p:
            raise ValueError("Prazo não encontrado")

        data = {}
        for field, val in payload.__dict__.items():
            if val is None:
                continue
            if isinstance(val, str):
                val = val.strip()
                val = val if val else None
            data[field] = val

        if "evento" in data and not data["evento"]:
            raise ValueError("evento não pode ficar vazio")

        if data:
            session.execute(update(Prazo).where(Prazo.id == prazo_id).values(**data))
            session.commit()

    @staticmethod
    def delete(session: Session, owner_user_id: int, prazo_id: int) -> None:
        p = PrazosService.get(session, owner_user_id, prazo_id)
        if not p:
            raise ValueError("Prazo não encontrado")

        session.execute(delete(Prazo).where(Prazo.id == prazo_id))
        session.commit()
