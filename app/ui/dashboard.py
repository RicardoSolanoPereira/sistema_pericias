import streamlit as st
import pandas as pd
from datetime import timedelta

from sqlalchemy import select, func

from db.connection import get_session
from db.models import Processo, Prazo, LancamentoFinanceiro
from core.utils import now_br, ensure_br, format_date_br


def _dias_restantes(dt):
    dt_br = ensure_br(dt)
    hoje = now_br().date()
    return (dt_br.date() - hoje).days


def _semaforo(dias: int) -> str:
    if dias < 0:
        return "🔴 Atrasado"
    if dias <= 5:
        return "🟠 Urgente"
    if dias <= 10:
        return "🟡 Atenção"
    return "🟢 Ok"


def render(owner_user_id: int):
    st.header("📌 Dashboard")

    hoje_sp = now_br().date()
    ate_7_sp = hoje_sp + timedelta(days=7)

    # -------------------------
    # KPIs (contagens em SP)
    # -------------------------
    with get_session() as s:
        total_proc = s.execute(
            select(func.count(Processo.id)).where(
                Processo.owner_user_id == owner_user_id
            )
        ).scalar_one()

        ativos = s.execute(
            select(func.count(Processo.id)).where(
                Processo.owner_user_id == owner_user_id,
                Processo.status == "Ativo",
            )
        ).scalar_one()

        # Busca todos prazos abertos (data_limite) para contar em Python no fuso SP
        prazos_abertos_rows = s.execute(
            select(Prazo.data_limite)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(Processo.owner_user_id == owner_user_id, Prazo.concluido == False)
        ).all()

        prazos_abertos = len(prazos_abertos_rows)

        prazos_atrasados = 0
        prazos_7dias = 0

        for (data_limite,) in prazos_abertos_rows:
            d = ensure_br(data_limite).date()
            if d < hoje_sp:
                prazos_atrasados += 1
            elif hoje_sp <= d <= ate_7_sp:
                prazos_7dias += 1

        receitas = s.execute(
            select(func.coalesce(func.sum(LancamentoFinanceiro.valor), 0))
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                LancamentoFinanceiro.tipo == "Receita",
            )
        ).scalar_one()

        despesas = s.execute(
            select(func.coalesce(func.sum(LancamentoFinanceiro.valor), 0))
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                LancamentoFinanceiro.tipo == "Despesa",
            )
        ).scalar_one()

    saldo = float(receitas) - float(despesas)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Processos", int(total_proc))
    c2.metric("Ativos", int(ativos))
    c3.metric("Prazos abertos", int(prazos_abertos))
    c4.metric("Atrasados (SP)", int(prazos_atrasados))
    c5.metric("Vencem em 7 dias (SP)", int(prazos_7dias))
    c6.metric(
        "Saldo (R$)",
        f"{saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
    )

    st.divider()

    # -------------------------
    # Prazos urgentes (Top 15)
    # -------------------------
    st.subheader("⏰ Prazos urgentes (Top 15)")

    with get_session() as s:
        rows = s.execute(
            select(
                Prazo.id,
                Prazo.evento,
                Prazo.data_limite,
                Prazo.prioridade,
                Processo.numero_processo,
                Processo.tipo_acao,
            )
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(Processo.owner_user_id == owner_user_id, Prazo.concluido == False)
            .order_by(Prazo.data_limite.asc())
            .limit(15)
        ).all()

    if not rows:
        st.info("Nenhum prazo aberto cadastrado.")
    else:
        data = []
        for (
            prazo_id,
            evento,
            data_limite,
            prioridade,
            numero_processo,
            tipo_acao,
        ) in rows:
            dias = _dias_restantes(data_limite)
            data.append(
                {
                    "prazo_id": prazo_id,
                    "processo": f"{numero_processo} – {tipo_acao or 'Sem tipo de ação'}",
                    "evento": evento,
                    "data_limite": format_date_br(data_limite),
                    "dias_restantes": dias,
                    "status": _semaforo(dias),
                    "prioridade": prioridade,
                }
            )

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # -------------------------
    # Últimos processos
    # -------------------------
    st.subheader("🗂️ Últimos processos")

    with get_session() as s:
        procs = s.execute(
            select(
                Processo.id,
                Processo.numero_processo,
                Processo.tipo_acao,
                Processo.comarca,
                Processo.vara,
                Processo.status,
            )
            .where(Processo.owner_user_id == owner_user_id)
            .order_by(Processo.id.desc())
            .limit(15)
        ).all()

    if not procs:
        st.info("Nenhum processo cadastrado ainda.")
        return

    dfp = pd.DataFrame(
        procs,
        columns=["id", "numero_processo", "tipo_acao", "comarca", "vara", "status"],
    )
    dfp["tipo_acao"] = dfp["tipo_acao"].fillna("Sem tipo de ação")
    st.dataframe(dfp, use_container_width=True, hide_index=True)
