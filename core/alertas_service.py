from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Tuple

from sqlalchemy import select

from db.models import Agendamento, Prazo, Processo
from core.utils import now_br, ensure_br, format_date_br


@dataclass(frozen=True)
class PrazoAlertaItem:
    prazo_id: int
    processo_id: int
    processo_numero: str
    tipo_acao: str
    evento: str
    prioridade: str
    data_limite_br: str
    dias_restantes: int


class AlertasService:
    """
    Coleta de itens elegíveis para alerta (prazos e agendamentos).

    Observações importantes:
    - Agendamentos: o coletor depende das flags alerta_*_enviado.
      Se o usuário editar a data/hora do agendamento, a camada de UPDATE
      deve resetar as flags para False, senão o agendamento não volta a ser alertado.
    """

    # -------------------------
    # PRAZOS
    # -------------------------
    @staticmethod
    def coletar_prazos_alerta(
        session,
        owner_user_id: int,
        due_days: int = 3,
    ) -> Tuple[List[PrazoAlertaItem], List[PrazoAlertaItem]]:
        """
        Retorna:
          - atrasados: prazos com dias_restantes < 0
          - vencendo: prazos com 0 <= dias_restantes <= due_days
        """
        hoje = now_br().date()

        rows = session.execute(
            select(
                Prazo.id,
                Prazo.processo_id,
                Prazo.evento,
                Prazo.data_limite,
                Prazo.prioridade,
                Processo.numero_processo,
                Processo.tipo_acao,
            )
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Prazo.concluido == False,  # noqa: E712
            )
            .order_by(Prazo.data_limite.asc())
        ).all()

        atrasados: List[PrazoAlertaItem] = []
        vencendo: List[PrazoAlertaItem] = []

        for (
            prazo_id,
            processo_id,
            evento,
            data_limite,
            prioridade,
            numero_proc,
            tipo_acao,
        ) in rows:
            dt_br = ensure_br(data_limite)
            dias = (dt_br.date() - hoje).days

            item = PrazoAlertaItem(
                prazo_id=int(prazo_id),
                processo_id=int(processo_id),
                processo_numero=str(numero_proc),
                tipo_acao=(tipo_acao or "Sem tipo de ação"),
                evento=str(evento),
                prioridade=(prioridade or "Média"),
                data_limite_br=format_date_br(data_limite),
                dias_restantes=int(dias),
            )

            if dias < 0:
                atrasados.append(item)
            elif 0 <= dias <= int(due_days):
                vencendo.append(item)

        return atrasados, vencendo

    # -------------------------
    # AGENDAMENTOS
    # -------------------------
    @staticmethod
    def _now_naive_for_db():
        """
        SQLite/Streamlit frequentemente gravam datetime naive.
        Padroniza o "now" para naive para comparações consistentes.
        """
        now = now_br()
        if getattr(now, "tzinfo", None) is not None:
            now = now.replace(tzinfo=None)
        return now

    @staticmethod
    def coletar_agendamentos_alerta(session, owner_user_id: int):
        """
        Retorna (ag_1, ag_2) onde cada item é (Agendamento, Processo)

        Regra robusta (não depende de "janela" em minutos):
        - ag_2: eventos entre agora e agora + h2 e alerta_2h_enviado=False
        - ag_1: eventos entre agora + h2 e agora + h1 e alerta_24h_enviado=False

        Assim o agendador pode rodar em qualquer horário sem perder disparos.
        """
        now = AlertasService._now_naive_for_db()

        h1 = int(os.getenv("ALERTS_AG_1_HOURS", "24"))
        h2 = int(os.getenv("ALERTS_AG_2_HOURS", "2"))

        # Segurança contra config invertida
        if h2 > h1:
            h2 = h1

        limite_2 = now + timedelta(hours=h2)
        limite_1 = now + timedelta(hours=h1)

        base = (
            select(Agendamento, Processo)
            .join(Processo, Processo.id == Agendamento.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Agendamento.status == "Agendado",
            )
            .order_by(Agendamento.inicio.asc())
        )

        # ALERTA 2 (mais próximo): agora .. h2
        ag_2 = session.execute(
            base.where(
                Agendamento.alerta_2h_enviado == False,  # noqa: E712
                Agendamento.inicio >= now,
                Agendamento.inicio <= limite_2,
            )
        ).all()

        # ALERTA 1 (antecedência maior): (h2 .. h1]
        ag_1 = session.execute(
            base.where(
                Agendamento.alerta_24h_enviado == False,  # noqa: E712
                Agendamento.inicio > limite_2,
                Agendamento.inicio <= limite_1,
            )
        ).all()

        return ag_1, ag_2
