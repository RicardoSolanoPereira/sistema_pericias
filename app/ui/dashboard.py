import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time

from sqlalchemy import select, func

from db.connection import get_session
from db.models import Processo, Prazo, LancamentoFinanceiro, Agendamento
from core.utils import now_br, ensure_br, format_date_br
from app.ui.theme import inject_global_css, card


TIPOS_TRABALHO = (
    "Perito Judicial",
    "Assistente Técnico",
    "Trabalho Particular",
)


def _naive(dt: datetime) -> datetime:
    """Garante datetime naive (SQLite costuma trabalhar sem tz)."""
    try:
        if getattr(dt, "tzinfo", None) is not None:
            return dt.replace(tzinfo=None)
    except Exception:
        pass
    return dt


def _dias_restantes(dt) -> int:
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


def _fmt_money_br(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render(owner_user_id: int):
    inject_global_css()

    # Topo + filtro (não muda layout, só adiciona controle)
    col_title, col_filter, col_btn = st.columns([6, 2, 1])
    with col_title:
        st.title("📌 Dashboard")
        st.caption("Painel de risco e próximos passos (prazos e agenda)")

    with col_filter:
        filtro_tipo = st.selectbox(
            "Visualizar",
            ["(Todos)"] + list(TIPOS_TRABALHO),
            index=0,
            key="dash_filtro_tipo",
        )
        tipo_val = None if filtro_tipo == "(Todos)" else filtro_tipo

    with col_btn:
        if st.button("🔄 Atualizar"):
            st.rerun()

    now = now_br()
    now_n = _naive(now)
    hoje_sp = now.date()
    ate_7_sp = hoje_sp + timedelta(days=7)

    start_today = datetime.combine(hoje_sp, time.min)
    end_7d = datetime.combine(ate_7_sp, time.max)

    # -------------------------
    # KPIs
    # -------------------------
    with get_session() as s:
        # Total processos
        stmt_total = select(func.count(Processo.id)).where(
            Processo.owner_user_id == owner_user_id
        )
        if tipo_val:
            stmt_total = stmt_total.where(Processo.papel == tipo_val)
        total_proc = s.execute(stmt_total).scalar_one()

        # Ativos
        stmt_ativos = select(func.count(Processo.id)).where(
            Processo.owner_user_id == owner_user_id, Processo.status == "Ativo"
        )
        if tipo_val:
            stmt_ativos = stmt_ativos.where(Processo.papel == tipo_val)
        ativos = s.execute(stmt_ativos).scalar_one()

        # Prazos abertos (para contar em Python no fuso BR)
        stmt_prazos = (
            select(Prazo.data_limite)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Prazo.concluido == False,  # noqa
            )
        )
        if tipo_val:
            stmt_prazos = stmt_prazos.where(Processo.papel == tipo_val)

        prazos_abertos_rows = s.execute(stmt_prazos).all()
        prazos_abertos = len(prazos_abertos_rows)

        prazos_atrasados = 0
        prazos_7dias = 0
        for (data_limite,) in prazos_abertos_rows:
            d = ensure_br(data_limite).date()
            if d < hoje_sp:
                prazos_atrasados += 1
            elif hoje_sp <= d <= ate_7_sp:
                prazos_7dias += 1

        # Agendamentos próximos (contagens)
        stmt_ag_7d = (
            select(func.count(Agendamento.id))
            .join(Processo, Processo.id == Agendamento.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Agendamento.status == "Agendado",
                Agendamento.inicio >= now_n,
                Agendamento.inicio <= now_n + timedelta(days=7),
            )
        )
        if tipo_val:
            stmt_ag_7d = stmt_ag_7d.where(Processo.papel == tipo_val)
        ag_7d = s.execute(stmt_ag_7d).scalar_one()

        # Financeiro (saldo)
        stmt_receitas = (
            select(func.coalesce(func.sum(LancamentoFinanceiro.valor), 0))
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                LancamentoFinanceiro.tipo == "Receita",
            )
        )
        stmt_despesas = (
            select(func.coalesce(func.sum(LancamentoFinanceiro.valor), 0))
            .join(Processo, Processo.id == LancamentoFinanceiro.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                LancamentoFinanceiro.tipo == "Despesa",
            )
        )
        if tipo_val:
            stmt_receitas = stmt_receitas.where(Processo.papel == tipo_val)
            stmt_despesas = stmt_despesas.where(Processo.papel == tipo_val)

        receitas = s.execute(stmt_receitas).scalar_one()
        despesas = s.execute(stmt_despesas).scalar_one()

    saldo = float(receitas) - float(despesas)

    # Cards
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        card("Processos", str(int(total_proc)), "cadastrados")
    with c2:
        card("Ativos", str(int(ativos)), "em andamento")
    with c3:
        card("Prazos abertos", str(int(prazos_abertos)), "não concluídos")
    with c4:
        card("Atrasados", str(int(prazos_atrasados)), "prazos")
    with c5:
        card("Agendamentos (7d)", str(int(ag_7d)), "status Agendado")
    with c6:
        card("Saldo (R$)", _fmt_money_br(saldo), "receitas - despesas")

    # Mensagem de risco
    if prazos_atrasados > 0:
        st.error(
            f"⚠️ Existem {int(prazos_atrasados)} prazo(s) atrasado(s). "
            f"Filtro: {filtro_tipo}."
        )
    elif prazos_7dias > 0:
        st.warning(
            f"🟠 Existem {int(prazos_7dias)} prazo(s) vencendo nos próximos 7 dias. Filtro: {filtro_tipo}."
        )
    else:
        st.success(f"✅ Nenhum prazo crítico no momento. Filtro: {filtro_tipo}.")

    st.divider()

    # -------------------------
    # Prazos: atrasados e vencendo 7 dias
    # -------------------------
    colA, colB = st.columns([1, 1])

    with colA:
        st.subheader("🔴 Prazos atrasados (Top 10)")

        with get_session() as s:
            stmt = (
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
                    Prazo.concluido == False,  # noqa
                    Prazo.data_limite < start_today,
                )
                .order_by(Prazo.data_limite.asc())
                .limit(10)
            )
            if tipo_val:
                stmt = stmt.where(Processo.papel == tipo_val)

            rows = s.execute(stmt).all()

        if not rows:
            st.caption("Sem prazos atrasados.")
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
                        "id": int(prazo_id),
                        "processo": f"{numero_processo} – {tipo_acao or 'Sem tipo'}",
                        "evento": evento,
                        "data": format_date_br(data_limite),
                        "dias": int(dias),
                        "status": _semaforo(dias),
                        "prioridade": prioridade or "Média",
                    }
                )
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    with colB:
        st.subheader("🟠 Vencem em 7 dias (Top 10)")

        with get_session() as s:
            stmt = (
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
                    Prazo.concluido == False,  # noqa
                    Prazo.data_limite >= start_today,
                    Prazo.data_limite <= end_7d,
                )
                .order_by(Prazo.data_limite.asc())
                .limit(10)
            )
            if tipo_val:
                stmt = stmt.where(Processo.papel == tipo_val)

            rows = s.execute(stmt).all()

        if not rows:
            st.caption("Sem prazos vencendo em até 7 dias.")
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
                        "id": int(prazo_id),
                        "processo": f"{numero_processo} – {tipo_acao or 'Sem tipo'}",
                        "evento": evento,
                        "data": format_date_br(data_limite),
                        "dias": int(dias),
                        "status": _semaforo(dias),
                        "prioridade": prioridade or "Média",
                    }
                )
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    st.divider()

    # -------------------------
    # Agendamentos próximos: 24h e 7 dias
    # -------------------------
    st.subheader("📅 Agendamentos próximos")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### ⏰ Em 24 horas (Top 10)")
        with get_session() as s:
            stmt = (
                select(
                    Agendamento.id,
                    Agendamento.tipo,
                    Agendamento.inicio,
                    Agendamento.local,
                    Processo.numero_processo,
                    Processo.tipo_acao,
                )
                .join(Processo, Processo.id == Agendamento.processo_id)
                .where(
                    Processo.owner_user_id == owner_user_id,
                    Agendamento.status == "Agendado",
                    Agendamento.inicio >= now_n,
                    Agendamento.inicio <= now_n + timedelta(hours=24),
                )
                .order_by(Agendamento.inicio.asc())
                .limit(10)
            )
            if tipo_val:
                stmt = stmt.where(Processo.papel == tipo_val)

            rows = s.execute(stmt).all()

        if not rows:
            st.caption("Sem agendamentos nas próximas 24h.")
        else:
            data = []
            for ag_id, tipo, inicio, local, numero_processo, tipo_acao in rows:
                data.append(
                    {
                        "id": int(ag_id),
                        "processo": f"{numero_processo} – {tipo_acao or 'Sem tipo'}",
                        "tipo": tipo,
                        "início": ensure_br(inicio).strftime("%d/%m/%Y %H:%M"),
                        "local": local or "",
                    }
                )
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    with col2:
        st.markdown("#### 📆 Em 7 dias (Top 10)")
        with get_session() as s:
            stmt = (
                select(
                    Agendamento.id,
                    Agendamento.tipo,
                    Agendamento.inicio,
                    Agendamento.local,
                    Processo.numero_processo,
                    Processo.tipo_acao,
                )
                .join(Processo, Processo.id == Agendamento.processo_id)
                .where(
                    Processo.owner_user_id == owner_user_id,
                    Agendamento.status == "Agendado",
                    Agendamento.inicio >= now_n,
                    Agendamento.inicio <= now_n + timedelta(days=7),
                )
                .order_by(Agendamento.inicio.asc())
                .limit(10)
            )
            if tipo_val:
                stmt = stmt.where(Processo.papel == tipo_val)

            rows = s.execute(stmt).all()

        if not rows:
            st.caption("Sem agendamentos nos próximos 7 dias.")
        else:
            data = []
            for ag_id, tipo, inicio, local, numero_processo, tipo_acao in rows:
                data.append(
                    {
                        "id": int(ag_id),
                        "processo": f"{numero_processo} – {tipo_acao or 'Sem tipo'}",
                        "tipo": tipo,
                        "início": ensure_br(inicio).strftime("%d/%m/%Y %H:%M"),
                        "local": local or "",
                    }
                )
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    st.divider()

    # -------------------------
    # Últimos processos
    # -------------------------
    st.subheader("🗂️ Últimos processos")
    st.caption("Processos mais recentes cadastrados no sistema (respeita o filtro)")

    with get_session() as s:
        stmt = (
            select(
                Processo.id,
                Processo.numero_processo,
                Processo.tipo_acao,
                Processo.comarca,
                Processo.vara,
                Processo.status,
                Processo.papel,
            )
            .where(Processo.owner_user_id == owner_user_id)
            .order_by(Processo.id.desc())
            .limit(10)
        )
        if tipo_val:
            stmt = stmt.where(Processo.papel == tipo_val)

        procs = s.execute(stmt).all()

    if not procs:
        st.info("Nenhum processo cadastrado ainda para este filtro.")
        return

    dfp = pd.DataFrame(
        procs,
        columns=[
            "id",
            "numero_processo",
            "tipo_acao",
            "comarca",
            "vara",
            "status",
            "tipo_trabalho",
        ],
    )
    dfp["tipo_acao"] = dfp["tipo_acao"].fillna("Sem tipo de ação")
    dfp["tipo_trabalho"] = dfp["tipo_trabalho"].fillna("Assistente Técnico")
    st.dataframe(dfp, use_container_width=True, hide_index=True)
