from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

from sqlalchemy import select, update, delete, desc
from sqlalchemy.orm import Session

from db.models import Andamento, Processo


@dataclass
class AndamentoCreate:
    processo_id: int
    data_evento: datetime
    titulo: str
    descricao: Optional[str] = None


@dataclass
class AndamentoUpdate:
    processo_id: Optional[int] = None
    data_evento: Optional[datetime] = None
    titulo: Optional[str] = None
    descricao: Optional[str] = None


class AndamentosService:
    @staticmethod
    def _clean_str(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        val = val.strip()
        return val if val else None

    @staticmethod
    def _assert_processo_owner(
        session: Session, owner_user_id: int, processo_id: int
    ) -> None:
        proc = (
            session.execute(
                select(Processo).where(
                    Processo.id == processo_id,
                    Processo.owner_user_id == owner_user_id,
                )
            )
            .scalars()
            .first()
        )
        if not proc:
            raise ValueError("Processo não encontrado (ou não pertence ao usuário)")

    @staticmethod
    def create(
        session: Session, owner_user_id: int, payload: AndamentoCreate
    ) -> Andamento:
        titulo = AndamentosService._clean_str(payload.titulo)
        if not titulo:
            raise ValueError("titulo é obrigatório")

        AndamentosService._assert_processo_owner(
            session, owner_user_id, int(payload.processo_id)
        )

        a = Andamento(
            processo_id=int(payload.processo_id),
            data_evento=payload.data_evento,
            titulo=titulo,
            descricao=AndamentosService._clean_str(payload.descricao),
        )
        session.add(a)
        session.commit()
        session.refresh(a)
        return a

    @staticmethod
    def list(
        session: Session,
        owner_user_id: int,
        processo_id: Optional[int] = None,
        q: Optional[str] = None,
        limit: int = 300,
    ) -> List[Andamento]:
        stmt = (
            select(Andamento)
            .join(Processo, Processo.id == Andamento.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
        )

        if processo_id:
            stmt = stmt.where(Andamento.processo_id == int(processo_id))

        q_clean = AndamentosService._clean_str(q)
        if q_clean:
            q_like = f"%{q_clean}%"
            stmt = stmt.where(
                (Andamento.titulo.ilike(q_like)) | (Andamento.descricao.ilike(q_like))
            )

        stmt = stmt.order_by(desc(Andamento.data_evento), desc(Andamento.id)).limit(
            int(limit)
        )
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def get(
        session: Session, owner_user_id: int, andamento_id: int
    ) -> Optional[Andamento]:
        stmt = (
            select(Andamento)
            .join(Processo, Processo.id == Andamento.processo_id)
            .where(
                Andamento.id == int(andamento_id),
                Processo.owner_user_id == owner_user_id,
            )
        )
        return session.execute(stmt).scalars().first()

    @staticmethod
    def update(
        session: Session,
        owner_user_id: int,
        andamento_id: int,
        payload: AndamentoUpdate,
    ) -> None:
        a = AndamentosService.get(session, owner_user_id, int(andamento_id))
        if not a:
            raise ValueError("Andamento não encontrado")

        data = {}

        # processo_id
        if payload.processo_id is not None:
            pid = int(payload.processo_id)
            AndamentosService._assert_processo_owner(session, owner_user_id, pid)
            data["processo_id"] = pid

        # data_evento
        if payload.data_evento is not None:
            data["data_evento"] = payload.data_evento

        # titulo
        if payload.titulo is not None:
            titulo = AndamentosService._clean_str(payload.titulo)
            if not titulo:
                raise ValueError("titulo não pode ficar vazio")
            data["titulo"] = titulo

        # descricao
        if payload.descricao is not None:
            data["descricao"] = AndamentosService._clean_str(payload.descricao)

        if data:
            session.execute(
                update(Andamento)
                .where(Andamento.id == int(andamento_id))
                .values(**data)
            )
            session.commit()

    @staticmethod
    def delete(session: Session, owner_user_id: int, andamento_id: int) -> None:
        a = AndamentosService.get(session, owner_user_id, int(andamento_id))
        if not a:
            raise ValueError("Andamento não encontrado")

        session.execute(delete(Andamento).where(Andamento.id == int(andamento_id)))
        session.commit()
