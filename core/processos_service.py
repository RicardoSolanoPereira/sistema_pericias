from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db.models import Processo


@dataclass
class ProcessoCreate:
    numero_processo: str
    vara: Optional[str] = None
    comarca: Optional[str] = None
    tipo_acao: Optional[str] = None
    contratante: Optional[str] = None
    categoria_servico: Optional[str] = None  # ✅

    papel: str = "Assistente Técnico"
    status: str = "Ativo"

    pasta_local: Optional[str] = None
    observacoes: Optional[str] = None


@dataclass
class ProcessoUpdate:
    numero_processo: Optional[str] = None
    vara: Optional[str] = None
    comarca: Optional[str] = None
    tipo_acao: Optional[str] = None
    contratante: Optional[str] = None
    categoria_servico: Optional[str] = None  # ✅

    papel: Optional[str] = None
    status: Optional[str] = None

    pasta_local: Optional[str] = None
    observacoes: Optional[str] = None


def _clean_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v2 = v.strip()
    return v2 if v2 else None


def _like(q: str) -> str:
    return f"%{q}%"


def _extract_categoria_prefix(obs: str) -> Optional[str]:
    if not obs:
        return None
    s = obs.strip()
    if not s.startswith("[Categoria:"):
        return None
    end = s.find("]")
    if end == -1:
        return None
    inside = s[len("[Categoria:") : end].strip()
    return inside if inside else None


def _remove_categoria_prefix(obs: str) -> str:
    if not obs:
        return ""
    s = obs.strip()
    if not s.startswith("[Categoria:"):
        return obs
    end = s.find("]")
    if end == -1:
        return obs
    return s[end + 1 :].lstrip()


class ProcessosService:
    @staticmethod
    def create(
        session: Session, owner_user_id: int, payload: ProcessoCreate
    ) -> Processo:
        numero = _clean_str(payload.numero_processo)
        if not numero:
            raise ValueError("numero_processo é obrigatório")

        proc = Processo(
            owner_user_id=owner_user_id,
            numero_processo=numero,
            vara=_clean_str(payload.vara),
            comarca=_clean_str(payload.comarca),
            tipo_acao=_clean_str(payload.tipo_acao),
            contratante=_clean_str(payload.contratante),
            categoria_servico=_clean_str(payload.categoria_servico),
            papel=_clean_str(payload.papel) or "Assistente Técnico",
            status=_clean_str(payload.status) or "Ativo",
            pasta_local=_clean_str(payload.pasta_local),
            observacoes=_clean_str(payload.observacoes),
        )
        session.add(proc)
        session.commit()
        session.refresh(proc)
        return proc

    @staticmethod
    def list(
        session: Session,
        owner_user_id: int,
        status: Optional[str] = None,
        papel: Optional[str] = None,
        categoria_servico: Optional[str] = None,
        q: Optional[str] = None,
        order_desc: bool = True,
        limit: Optional[int] = None,
    ) -> List[Processo]:
        stmt = select(Processo).where(Processo.owner_user_id == owner_user_id)

        if status:
            stmt = stmt.where(Processo.status == status)
        if papel:
            stmt = stmt.where(Processo.papel == papel)
        if categoria_servico:
            stmt = stmt.where(Processo.categoria_servico == categoria_servico)

        qv = _clean_str(q)
        if qv:
            like = _like(qv)
            stmt = stmt.where(
                (Processo.numero_processo.like(like))
                | (Processo.comarca.like(like))
                | (Processo.vara.like(like))
                | (Processo.contratante.like(like))
                | (Processo.tipo_acao.like(like))
                | (Processo.categoria_servico.like(like))
                | (Processo.papel.like(like))
                | (Processo.status.like(like))
                | (Processo.observacoes.like(like))
            )

        stmt = stmt.order_by(Processo.id.desc() if order_desc else Processo.id.asc())

        if limit and limit > 0:
            stmt = stmt.limit(int(limit))

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
        for field, val in payload.__dict__.items():
            if val is None:
                continue
            if isinstance(val, str):
                val = _clean_str(val)
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
        session.delete(proc)
        session.commit()

    @staticmethod
    def backfill_categoria_from_observacoes(
        session: Session,
        owner_user_id: int,
        remove_prefix: bool = True,
        only_if_empty: bool = True,
    ) -> int:
        stmt = select(Processo).where(Processo.owner_user_id == owner_user_id)
        rows = list(session.execute(stmt).scalars().all())

        changed = 0
        for p in rows:
            current_cat = _clean_str(getattr(p, "categoria_servico", None))
            if only_if_empty and current_cat:
                continue

            obs = (p.observacoes or "").strip()
            cat = _extract_categoria_prefix(obs)
            if not cat:
                continue

            new_obs = (
                _remove_categoria_prefix(obs)
                if remove_prefix
                else (p.observacoes or None)
            )

            session.execute(
                update(Processo)
                .where(Processo.id == p.id, Processo.owner_user_id == owner_user_id)
                .values(
                    categoria_servico=cat,
                    observacoes=(
                        _clean_str(new_obs)
                        if remove_prefix
                        else (p.observacoes or None)
                    ),
                )
            )
            changed += 1

        if changed:
            session.commit()
        return changed
