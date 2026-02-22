from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import asc, delete, desc, select, update
from sqlalchemy.orm import Session

from db.models import Agendamento, Processo


STATUS_VALIDOS = ("Agendado", "Realizado", "Cancelado")
TIPOS_VALIDOS = ("Vistoria", "Reunião", "Audiência", "Outro")


@dataclass(frozen=True)
class AgendamentoCreate:
    processo_id: int
    tipo: str
    inicio: datetime
    fim: Optional[datetime] = None
    local: Optional[str] = None
    descricao: Optional[str] = None
    status: str = "Agendado"


@dataclass(frozen=True)
class AgendamentoUpdate:
    processo_id: Optional[int] = None
    tipo: Optional[str] = None
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None
    local: Optional[str] = None
    descricao: Optional[str] = None
    status: Optional[str] = None


class AgendamentosService:
    # -------------------------
    # Helpers
    # -------------------------
    @staticmethod
    def _clean_str(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        s = val.strip()
        return s if s else None

    @staticmethod
    def _normalize_tipo(tipo: str) -> str:
        t = (tipo or "").strip()
        if t not in TIPOS_VALIDOS:
            raise ValueError(f"tipo inválido (use: {', '.join(TIPOS_VALIDOS)})")
        return t

    @staticmethod
    def _normalize_status(status: str) -> str:
        s = (status or "").strip()
        if s not in STATUS_VALIDOS:
            raise ValueError(f"status inválido (use: {', '.join(STATUS_VALIDOS)})")
        return s

    @staticmethod
    def _validate_interval(inicio: datetime, fim: Optional[datetime]) -> None:
        if fim is not None and fim < inicio:
            raise ValueError("fim não pode ser anterior ao início")

    @staticmethod
    def _assert_processo_owner(
        session: Session, owner_user_id: int, processo_id: int
    ) -> None:
        proc = (
            session.execute(
                select(Processo).where(
                    Processo.id == int(processo_id),
                    Processo.owner_user_id == int(owner_user_id),
                )
            )
            .scalars()
            .first()
        )
        if not proc:
            raise ValueError("Processo não encontrado (ou não pertence ao usuário)")

    @staticmethod
    def _compute_flags_for_update(
        *,
        inicio_old: datetime,
        fim_old: Optional[datetime],
        status_old: str,
        inicio_new: datetime,
        fim_new: Optional[datetime],
        status_new: str,
    ) -> dict:
        """
        Flags corretas:
        - Se status_new != Agendado => flags True (não alertar)
        - Se status_new == Agendado:
            - se mudou horário OU voltou p/ Agendado => flags False (rearmar alertas)
            - caso contrário não mexe nas flags
        """
        if status_new != "Agendado":
            return {"alerta_24h_enviado": True, "alerta_2h_enviado": True}

        voltou_para_agendado = status_old != "Agendado" and status_new == "Agendado"
        mudou_horario = (inicio_new != inicio_old) or (fim_new != fim_old)

        if voltou_para_agendado or mudou_horario:
            return {"alerta_24h_enviado": False, "alerta_2h_enviado": False}

        return {}

    # -------------------------
    # CRUD
    # -------------------------
    @staticmethod
    def create(
        session: Session, owner_user_id: int, payload: AgendamentoCreate
    ) -> Agendamento:
        if not payload.processo_id:
            raise ValueError("processo_id é obrigatório")

        AgendamentosService._assert_processo_owner(
            session, owner_user_id, int(payload.processo_id)
        )

        tipo = AgendamentosService._normalize_tipo(payload.tipo)
        status = AgendamentosService._normalize_status(payload.status or "Agendado")

        AgendamentosService._validate_interval(payload.inicio, payload.fim)

        a = Agendamento(
            processo_id=int(payload.processo_id),
            tipo=tipo,
            inicio=payload.inicio,
            fim=payload.fim,
            local=AgendamentosService._clean_str(payload.local),
            descricao=AgendamentosService._clean_str(payload.descricao),
            status=status,
            alerta_24h_enviado=False,
            alerta_2h_enviado=False,
            atualizado_em=datetime.utcnow(),
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
        tipo: Optional[str] = None,
        status: Optional[str] = None,
        q: Optional[str] = None,
        order: str = "asc",
        limit: int = 300,
    ) -> List[Agendamento]:
        limit = int(limit)
        if limit <= 0:
            limit = 100
        if limit > 1000:
            limit = 1000

        stmt = (
            select(Agendamento)
            .join(Processo, Processo.id == Agendamento.processo_id)
            .where(Processo.owner_user_id == int(owner_user_id))
        )

        if processo_id is not None:
            stmt = stmt.where(Agendamento.processo_id == int(processo_id))

        if tipo:
            stmt = stmt.where(Agendamento.tipo == tipo)

        if status:
            stmt = stmt.where(Agendamento.status == status)

        q_clean = AgendamentosService._clean_str(q)
        if q_clean:
            like = f"%{q_clean}%"
            stmt = stmt.where(
                (Agendamento.local.ilike(like)) | (Agendamento.descricao.ilike(like))
            )

        stmt = stmt.order_by(
            asc(Agendamento.inicio) if order == "asc" else desc(Agendamento.inicio)
        )
        return list(session.execute(stmt.limit(limit)).scalars().all())

    @staticmethod
    def get(
        session: Session, owner_user_id: int, agendamento_id: int
    ) -> Optional[Agendamento]:
        stmt = (
            select(Agendamento)
            .join(Processo, Processo.id == Agendamento.processo_id)
            .where(
                Agendamento.id == int(agendamento_id),
                Processo.owner_user_id == int(owner_user_id),
            )
        )
        return session.execute(stmt).scalars().first()

    @staticmethod
    def update(
        session: Session,
        owner_user_id: int,
        agendamento_id: int,
        payload: AgendamentoUpdate,
    ) -> Agendamento:
        a = AgendamentosService.get(session, owner_user_id, int(agendamento_id))
        if not a:
            raise ValueError("Agendamento não encontrado")

        # snapshot antigo
        inicio_old = a.inicio
        fim_old = a.fim
        status_old = a.status

        data: dict = {}

        if payload.processo_id is not None:
            pid = int(payload.processo_id)
            AgendamentosService._assert_processo_owner(session, owner_user_id, pid)
            data["processo_id"] = pid

        if payload.tipo is not None:
            data["tipo"] = AgendamentosService._normalize_tipo(payload.tipo)

        if payload.status is not None:
            data["status"] = AgendamentosService._normalize_status(payload.status)

        if payload.inicio is not None:
            data["inicio"] = payload.inicio

        # ✅ permite limpar fim explicitamente (fim=None)
        if payload.fim is not None or payload.fim is None:
            data["fim"] = payload.fim

        if payload.local is not None:
            data["local"] = AgendamentosService._clean_str(payload.local)

        if payload.descricao is not None:
            data["descricao"] = AgendamentosService._clean_str(payload.descricao)

        # finais
        inicio_new = data.get("inicio", a.inicio)
        fim_new = data.get("fim", a.fim)
        status_new = data.get("status", a.status)

        AgendamentosService._validate_interval(inicio_new, fim_new)

        # flags (rearmar quando apropriado)
        data.update(
            AgendamentosService._compute_flags_for_update(
                inicio_old=inicio_old,
                fim_old=fim_old,
                status_old=status_old,
                inicio_new=inicio_new,
                fim_new=fim_new,
                status_new=status_new,
            )
        )

        data["atualizado_em"] = datetime.utcnow()

        session.execute(
            update(Agendamento)
            .where(Agendamento.id == int(agendamento_id))
            .values(**data)
        )
        session.commit()

        a2 = AgendamentosService.get(session, owner_user_id, int(agendamento_id))
        if not a2:
            raise RuntimeError("Falha ao recarregar agendamento após update")
        return a2

    @staticmethod
    def set_status(
        session: Session, owner_user_id: int, agendamento_id: int, status: str
    ) -> Agendamento:
        a = AgendamentosService.get(session, owner_user_id, int(agendamento_id))
        if not a:
            raise ValueError("Agendamento não encontrado")

        stt = AgendamentosService._normalize_status(status)

        data = {
            "status": stt,
            "atualizado_em": datetime.utcnow(),
        }

        # ✅ CORREÇÃO CRÍTICA:
        # Reativar (Agendado) deve SEMPRE rearmar alertas, mesmo se já estava Agendado.
        if stt == "Agendado":
            data["alerta_24h_enviado"] = False
            data["alerta_2h_enviado"] = False
        else:
            data["alerta_24h_enviado"] = True
            data["alerta_2h_enviado"] = True

        session.execute(
            update(Agendamento)
            .where(Agendamento.id == int(agendamento_id))
            .values(**data)
        )
        session.commit()

        a2 = AgendamentosService.get(session, owner_user_id, int(agendamento_id))
        if not a2:
            raise RuntimeError("Falha ao recarregar agendamento após set_status")
        return a2

    @staticmethod
    def delete(session: Session, owner_user_id: int, agendamento_id: int) -> None:
        a = AgendamentosService.get(session, owner_user_id, int(agendamento_id))
        if not a:
            raise ValueError("Agendamento não encontrado")

        session.execute(
            delete(Agendamento).where(Agendamento.id == int(agendamento_id))
        )
        session.commit()
