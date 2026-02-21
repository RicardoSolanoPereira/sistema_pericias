from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Processo, Prazo
from core.utils import now_br, ensure_br, format_date_br


@dataclass
class AlertItem:
    prazo_id: int
    processo_numero: str
    tipo_acao: str
    evento: str
    data_limite_br: str
    dias_restantes: int
    prioridade: str


def _dias_restantes(dt) -> int:
    dt_br = ensure_br(dt)
    hoje = now_br().date()
    return (dt_br.date() - hoje).days


class AlertasService:
    @staticmethod
    def coletar_prazos_alerta(
        session: Session,
        owner_user_id: int,
        due_days: int = 3,
    ) -> Tuple[List[AlertItem], List[AlertItem]]:
        """
        Retorna (atrasados, vencendo_em_due_days_ou_menos)
        Tudo calculado estritamente no fuso SP.
        """
        hoje = now_br().date()
        limite = hoje + timedelta(days=due_days)

        rows = session.execute(
            select(
                Prazo.id,
                Prazo.evento,
                Prazo.data_limite,
                Prazo.prioridade,
                Processo.numero_processo,
                Processo.tipo_acao,
            )
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Prazo.concluido == False,
            )
            .order_by(Prazo.data_limite.asc())
        ).all()

        atrasados: List[AlertItem] = []
        vencendo: List[AlertItem] = []

        for (
            prazo_id,
            evento,
            data_limite,
            prioridade,
            numero_processo,
            tipo_acao,
        ) in rows:
            dias = _dias_restantes(data_limite)
            item = AlertItem(
                prazo_id=prazo_id,
                processo_numero=numero_processo,
                tipo_acao=tipo_acao or "Sem tipo de ação",
                evento=evento,
                data_limite_br=format_date_br(data_limite),
                dias_restantes=dias,
                prioridade=prioridade,
            )

            d = ensure_br(data_limite).date()
            if d < hoje:
                atrasados.append(item)
            elif hoje <= d <= limite:
                vencendo.append(item)

        return atrasados, vencendo
