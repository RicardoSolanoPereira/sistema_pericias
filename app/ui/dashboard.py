import streamlit as st
import pandas as pd
from sqlalchemy import select, func

from db.connection import get_session
from db.models import Processo, Prazo, LancamentoFinanceiro


def render(owner_user_id: int):
    st.header("📌 Dashboard")

    with get_session() as s:
        total_proc = s.execute(
            select(func.count(Processo.id)).where(
                Processo.owner_user_id == owner_user_id
            )
        ).scalar_one()

        ativos = s.execute(
            select(func.count(Processo.id)).where(
                Processo.owner_user_id == owner_user_id, Processo.status == "Ativo"
            )
        ).scalar_one()

        prazos_abertos = s.execute(
            select(func.count(Prazo.id))
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(Processo.owner_user_id == owner_user_id, Prazo.concluido == False)
        ).scalar_one()

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

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Processos", int(total_proc))
    c2.metric("Ativos", int(ativos))
    c3.metric("Prazos abertos", int(prazos_abertos))
    c4.metric(
        "Saldo (R$)",
        f"{saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
    )

    st.divider()
    st.subheader("Últimos processos")

    with get_session() as s:
        rows = s.execute(
            select(
                Processo.id,
                Processo.numero_processo,
                Processo.comarca,
                Processo.vara,
                Processo.status,
            )
            .where(Processo.owner_user_id == owner_user_id)
            .order_by(Processo.id.desc())
            .limit(20)
        ).all()

    if not rows:
        st.info("Nenhum processo cadastrado ainda.")
        return

    df = pd.DataFrame(
        rows, columns=["id", "numero_processo", "comarca", "vara", "status"]
    )
    st.dataframe(df, use_container_width=True)
