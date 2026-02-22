from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime

from sqlalchemy import select, update, delete, desc, func, case
from sqlalchemy.orm import Session

from db.models import LancamentoFinanceiro, Processo


@dataclass
class LancamentoCreate:
    processo_id: int
    data_lancamento: datetime
    tipo: str  # Receita/Despesa
    categoria: Optional[str] = None
    descricao: Optional[str] = None
    valor: float = 0.0


@dataclass
class LancamentoUpdate:
    processo_id: Optional[int] = None
    data_lancamento: Optional[datetime] = None
    tipo: Optional[str] = None
    categoria: Optional[str] = None
    descricao: Optional[str] = None
    valor: Optional[float] = None


class FinanceiroService:
    # -------------------------
    # Helpers
    # -------------------------
    @staticmethod
    def _clean_str(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        val = val.strip()
        return val if val else None

    @staticmethod
    def _normalize_tipo(tipo: str) -> str:
        t = (tipo or "").strip()
        if t not in ("Receita", "Despesa"):
            raise ValueError("tipo inválido (use Receita ou Despesa)")
        return t

    @staticmethod
    def _normalize_valor(valor) -> float:
        """
        Aceita float/int/str. Ex.: "1.234,56" ou "1234.56"
        Retorna float > 0
        """
        if valor is None:
            raise ValueError("valor inválido")

        if isinstance(valor, str):
            vtxt = valor.strip()
            if not vtxt:
                raise ValueError("valor inválido")
            vtxt = vtxt.replace(".", "").replace(",", ".")
            try:
                v = float(vtxt)
            except Exception:
                raise ValueError("valor inválido")
        else:
            try:
                v = float(valor)
            except Exception:
                raise ValueError("valor inválido")

        if v <= 0:
            raise ValueError("valor deve ser maior que zero")
        return v

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

    # -------------------------
    # CRUD
    # -------------------------
    @staticmethod
    def create(
        session: Session, owner_user_id: int, payload: LancamentoCreate
    ) -> LancamentoFinanceiro:
        FinanceiroService._assert_processo_owner(
            session, owner_user_id, int(payload.processo_id)
        )
        tipo = FinanceiroService._normalize_tipo(payload.tipo)
        valor = FinanceiroService._normalize_valor(payload.valor)

        l = LancamentoFinanceiro(
            processo_id=int(payload.processo_id),
            data_lancamento=payload.data_lancamento,
            tipo=tipo,
            categoria=FinanceiroService._clean_str(payload.categoria),
            descricao=FinanceiroService._clean_str(payload.descricao),
            valor=valor,
        )
        session.add(l)
        session.commit()
        session.refresh(l)
        return l

    @staticmethod
    def list(
        session: Session,
        owner_user_id: int,
        processo_id: Optional[int] = None,
        tipo: Optional[str] = None,
        q: Optional[str] = None,
        dt_ini: Optional[datetime] = None,
        dt_fim: Optional[datetime] = None,
        limit: int = 300,
    ) -> List[LancamentoFinanceiro]:
        stmt = (
            select(LancamentoFinanceiro)
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
        )

        if processo_id:
            stmt = stmt.where(LancamentoFinanceiro.processo_id == int(processo_id))

        if tipo and tipo != "(Todos)":
            stmt = stmt.where(LancamentoFinanceiro.tipo == tipo)

        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                (LancamentoFinanceiro.categoria.ilike(like))
                | (LancamentoFinanceiro.descricao.ilike(like))
            )

        if dt_ini:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento >= dt_ini)
        if dt_fim:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento <= dt_fim)

        stmt = stmt.order_by(
            desc(LancamentoFinanceiro.data_lancamento), desc(LancamentoFinanceiro.id)
        ).limit(int(limit))

        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def get(
        session: Session, owner_user_id: int, lancamento_id: int
    ) -> Optional[LancamentoFinanceiro]:
        stmt = (
            select(LancamentoFinanceiro)
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(
                LancamentoFinanceiro.id == int(lancamento_id),
                Processo.owner_user_id == owner_user_id,
            )
        )
        return session.execute(stmt).scalars().first()

    @staticmethod
    def update(
        session: Session,
        owner_user_id: int,
        lancamento_id: int,
        payload: LancamentoUpdate,
    ) -> None:
        l = FinanceiroService.get(session, owner_user_id, int(lancamento_id))
        if not l:
            raise ValueError("Lançamento não encontrado")

        data = {}

        if payload.processo_id is not None:
            pid = int(payload.processo_id)
            FinanceiroService._assert_processo_owner(session, owner_user_id, pid)
            data["processo_id"] = pid

        if payload.data_lancamento is not None:
            data["data_lancamento"] = payload.data_lancamento

        if payload.tipo is not None:
            data["tipo"] = FinanceiroService._normalize_tipo(payload.tipo)

        if payload.categoria is not None:
            data["categoria"] = FinanceiroService._clean_str(payload.categoria)

        if payload.descricao is not None:
            data["descricao"] = FinanceiroService._clean_str(payload.descricao)

        if payload.valor is not None:
            data["valor"] = FinanceiroService._normalize_valor(payload.valor)

        if data:
            session.execute(
                update(LancamentoFinanceiro)
                .where(LancamentoFinanceiro.id == int(lancamento_id))
                .values(**data)
            )
            session.commit()

    @staticmethod
    def delete(session: Session, owner_user_id: int, lancamento_id: int) -> None:
        l = FinanceiroService.get(session, owner_user_id, int(lancamento_id))
        if not l:
            raise ValueError("Lançamento não encontrado")

        session.execute(
            delete(LancamentoFinanceiro).where(
                LancamentoFinanceiro.id == int(lancamento_id)
            )
        )
        session.commit()

    # -------------------------
    # Totais / Resumos (para UI)
    # -------------------------
    @staticmethod
    def totals(
        session: Session,
        owner_user_id: int,
        processo_id: Optional[int] = None,
        dt_ini: Optional[datetime] = None,
        dt_fim: Optional[datetime] = None,
    ) -> Dict[str, float]:
        receitas = func.coalesce(
            func.sum(
                case(
                    (
                        LancamentoFinanceiro.tipo == "Receita",
                        LancamentoFinanceiro.valor,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        despesas = func.coalesce(
            func.sum(
                case(
                    (
                        LancamentoFinanceiro.tipo == "Despesa",
                        LancamentoFinanceiro.valor,
                    ),
                    else_=0,
                )
            ),
            0,
        )

        stmt = (
            select(receitas.label("receitas"), despesas.label("despesas"))
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
        )

        if processo_id:
            stmt = stmt.where(LancamentoFinanceiro.processo_id == int(processo_id))
        if dt_ini:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento >= dt_ini)
        if dt_fim:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento <= dt_fim)

        rec, desp = session.execute(stmt).first()
        rec_f = float(rec or 0)
        desp_f = float(desp or 0)
        return {"receitas": rec_f, "despesas": desp_f, "saldo": rec_f - desp_f}

    @staticmethod
    def resumo_por_processo(
        session: Session,
        owner_user_id: int,
        dt_ini: Optional[datetime] = None,
        dt_fim: Optional[datetime] = None,
    ) -> List[Dict[str, float]]:
        """
        Tab2 da UI: retorna LISTA de dicts com processo_id/receitas/despesas/saldo.
        """
        receitas = func.coalesce(
            func.sum(
                case(
                    (
                        LancamentoFinanceiro.tipo == "Receita",
                        LancamentoFinanceiro.valor,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        despesas = func.coalesce(
            func.sum(
                case(
                    (
                        LancamentoFinanceiro.tipo == "Despesa",
                        LancamentoFinanceiro.valor,
                    ),
                    else_=0,
                )
            ),
            0,
        )

        stmt = (
            select(
                LancamentoFinanceiro.processo_id.label("processo_id"),
                receitas.label("receitas"),
                despesas.label("despesas"),
            )
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
            .group_by(LancamentoFinanceiro.processo_id)
            .order_by(LancamentoFinanceiro.processo_id.desc())
        )

        if dt_ini:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento >= dt_ini)
        if dt_fim:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento <= dt_fim)

        rows = session.execute(stmt).all()

        out: List[Dict[str, float]] = []
        for pid, rec, desp in rows:
            rec_f = float(rec or 0)
            desp_f = float(desp or 0)
            out.append(
                {
                    "processo_id": int(pid),
                    "receitas": rec_f,
                    "despesas": desp_f,
                    "saldo": rec_f - desp_f,
                }
            )
        return out

    @staticmethod
    def resumo_por_categoria(
        session: Session,
        owner_user_id: int,
        processo_id: Optional[int] = None,
        dt_ini: Optional[datetime] = None,
        dt_fim: Optional[datetime] = None,
    ) -> List[Dict[str, float]]:
        """
        Tab3 da UI: lista dicts com categoria/tipo/total
        """
        total = func.coalesce(func.sum(LancamentoFinanceiro.valor), 0)

        stmt = (
            select(
                func.coalesce(LancamentoFinanceiro.categoria, "(Sem categoria)").label(
                    "categoria"
                ),
                LancamentoFinanceiro.tipo.label("tipo"),
                total.label("total"),
            )
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
            .group_by("categoria", LancamentoFinanceiro.tipo)
            .order_by(desc(total))
        )

        if processo_id:
            stmt = stmt.where(LancamentoFinanceiro.processo_id == int(processo_id))
        if dt_ini:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento >= dt_ini)
        if dt_fim:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento <= dt_fim)

        rows = session.execute(stmt).all()

        return [
            {"categoria": str(cat), "tipo": str(tipo), "total": float(t or 0)}
            for cat, tipo, t in rows
        ]

    @staticmethod
    def resumo_mensal(
        session: Session,
        owner_user_id: int,
        processo_id: Optional[int] = None,
        dt_ini: Optional[datetime] = None,
        dt_fim: Optional[datetime] = None,
    ) -> List[Dict[str, float]]:
        """
        Tab4 da UI: lista dicts com mes/receitas/despesas/saldo
        mes no formato YYYY-MM
        """
        # SQLite: strftime('%Y-%m', data_lancamento)
        mes = func.strftime("%Y-%m", LancamentoFinanceiro.data_lancamento)

        receitas = func.coalesce(
            func.sum(
                case(
                    (
                        LancamentoFinanceiro.tipo == "Receita",
                        LancamentoFinanceiro.valor,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        despesas = func.coalesce(
            func.sum(
                case(
                    (
                        LancamentoFinanceiro.tipo == "Despesa",
                        LancamentoFinanceiro.valor,
                    ),
                    else_=0,
                )
            ),
            0,
        )

        stmt = (
            select(
                mes.label("mes"),
                receitas.label("receitas"),
                despesas.label("despesas"),
            )
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(Processo.owner_user_id == owner_user_id)
            .group_by("mes")
            .order_by("mes")
        )

        if processo_id:
            stmt = stmt.where(LancamentoFinanceiro.processo_id == int(processo_id))
        if dt_ini:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento >= dt_ini)
        if dt_fim:
            stmt = stmt.where(LancamentoFinanceiro.data_lancamento <= dt_fim)

        rows = session.execute(stmt).all()

        out: List[Dict[str, float]] = []
        for m, rec, desp in rows:
            rec_f = float(rec or 0)
            desp_f = float(desp or 0)
            out.append(
                {
                    "mes": str(m),
                    "receitas": rec_f,
                    "despesas": desp_f,
                    "saldo": rec_f - desp_f,
                }
            )
        return out
