from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from db.models import Processo


@dataclass
class ProcessoCreate:
    numero_processo: str
    vara: Optional[str] = None
    comarca: Optional[str] = None
    tipo_acao: Optional[str] = None
    contratante: Optional[str] = None
    papel: str = "Assistente Técnico"  # "Perito" / "Assistente Técnico"
    status: str = "Ativo"  # "Ativo" / "Concluído" / "Suspenso"
    pasta_local: Optional[str] = None
    observacoes: Optional[str] = None


@dataclass
class ProcessoUpdate:
    numero_processo: Optional[str] = None
    vara: Optional[str] = None
    comarca: Optional[str] = None
    tipo_acao: Optional[str] = None
    contratante: Optional[str] = None
    papel: Optional[str] = None
    status: Optional[str] = None
    pasta_local: Optional[str] = None
    observacoes: Optional[str] = None


class ProcessosService:
    @staticmethod
    def create(
        session: Session, owner_user_id: int, payload: ProcessoCreate
    ) -> Processo:
        numero = (payload.numero_processo or "").strip()
        if not numero:
            raise ValueError("numero_processo é obrigatório")

        proc = Processo(
            owner_user_id=owner_user_id,
            numero_processo=numero,
            vara=(payload.vara or "").strip() or None,
            comarca=(payload.comarca or "").strip() or None,
            tipo_acao=(payload.tipo_acao or "").strip() or None,
            contratante=(payload.contratante or "").strip() or None,
            papel=payload.papel,
            status=payload.status,
            pasta_local=(payload.pasta_local or "").strip() or None,
            observacoes=(payload.observacoes or "").strip() or None,
        )
        session.add(proc)
        session.commit()
        session.refresh(proc)
        return proc

    @staticmethod
    def list(
        session: Session, owner_user_id: int, status: Optional[str] = None
    ) -> List[Processo]:
        stmt = select(Processo).where(Processo.owner_user_id == owner_user_id)
        if status:
            stmt = stmt.where(Processo.status == status)
        stmt = stmt.order_by(Processo.id.desc())
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def get(
        session: Session, owner_user_id: int, processo_id: int
    ) -> Optional[Processo]:
        stmt = select(Processo).where(
            Processo.id == processo_id, Processo.owner_user_id == owner_user_id
        )
        return session.execute(stmt).scalars().first()

    @staticmethod
    def update(
        session: Session, owner_user_id: int, processo_id: int, payload: ProcessoUpdate
    ) -> None:
        proc = ProcessosService.get(session, owner_user_id, processo_id)
        if not proc:
            raise ValueError("Processo não encontrado")

        data = {}
        for field in payload.__dict__:
            val = getattr(payload, field)
            if val is None:
                continue
            if isinstance(val, str):
                val = val.strip()
                val = val if val else None
            data[field] = val

        if "numero_processo" in data and not data["numero_processo"]:
            raise ValueError("numero_processo não pode ficar vazio")

        if data:
            session.execute(
                update(Processo)
                .where(
                    Processo.id == processo_id, Processo.owner_user_id == owner_user_id
                )
                .values(**data)
            )
            session.commit()

    @staticmethod
    def delete(session: Session, owner_user_id: int, processo_id: int) -> None:
        proc = ProcessosService.get(session, owner_user_id, processo_id)
        if not proc:
            raise ValueError("Processo não encontrado")

        session.delete(
            proc
        )  # ✅ dispara cascade ORM (prazos/andamentos/agenda/financeiro)
        session.commit()
