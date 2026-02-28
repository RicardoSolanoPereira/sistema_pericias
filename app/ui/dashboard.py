# app/ui/dashboard.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time, date

from sqlalchemy import select, func, case

from db.connection import get_session
from db.models import Processo, Prazo, LancamentoFinanceiro, Agendamento
from core.utils import now_br, ensure_br, format_date_br
from app.ui.theme import inject_global_css, card
from app.ui_state import navigate
from app.ui.components import page_header

ATUACAO_UI = {
    "(Todas)": None,
    "Perícia (Juízo)": "Perito Judicial",
    "Assistência Técnica": "Assistente Técnico",
    "Particular / Outros serviços": "Trabalho Particular",
}


# -------------------------
# Helpers
# -------------------------
def _naive(dt: datetime) -> datetime:
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


def _status_prazo(dias: int) -> str:
    if dias < 0:
        return "🔴 Atrasado"
    if dias <= 5:
        return "🟠 Urgente"
    if dias <= 10:
        return "🟡 Atenção"
    return "🟢 Ok"


def _fmt_money_br(v: float) -> str:
    try:
        v = float(v or 0)
    except Exception:
        v = 0.0
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _apply_tipo_filter(stmt, tipo_val):
    return stmt if not tipo_val else stmt.where(Processo.papel == tipo_val)


def _pct(a: int, b: int) -> str:
    if b <= 0:
        return "0%"
    return f"{round((a / b) * 100)}%"


def _prior_badge(p: str | None) -> str:
    p = (p or "Média").strip()
    if p.lower().startswith("a"):
        return "🔥 Alta"
    if p.lower().startswith("b"):
        return "🧊 Baixa"
    return "⚖️ Média"


def _date_range_strings(hoje: date) -> tuple[str, str]:
    """Para cache_data: entradas hashable e estáveis."""
    ate7 = hoje + timedelta(days=7)
    return hoje.isoformat(), ate7.isoformat()


def _dt_bounds(hoje: date) -> tuple[datetime, datetime]:
    ate7 = hoje + timedelta(days=7)
    start_today = datetime.combine(hoje, time.min)
    end_7d = datetime.combine(ate7, time.max)
    return start_today, end_7d


def _build_prazos_df(rows) -> pd.DataFrame:
    data = []
    for (
        _id,
        evento,
        data_limite,
        prioridade,
        numero_processo,
        tipo_acao,
    ) in rows:
        dias = int(_dias_restantes(data_limite))
        data.append(
            {
                "Trabalho": f"{numero_processo} – {tipo_acao or 'Sem tipo'}",
                "Evento": evento,
                "Venc.": format_date_br(data_limite),
                "Dias": dias,
                "Status": _status_prazo(dias),
                "Prior.": _prior_badge(prioridade),
            }
        )
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data).sort_values(by=["Dias", "Venc."], ascending=True)


def _build_agenda_df(rows) -> pd.DataFrame:
    data = []
    for _id, tipo, inicio, local, numero_processo, tipo_acao in rows:
        data.append(
            {
                "Trabalho": f"{numero_processo} – {tipo_acao or 'Sem tipo'}",
                "Tipo": tipo,
                "Início": ensure_br(inicio).strftime("%d/%m/%Y %H:%M"),
                "Local": local or "",
            }
        )
    return pd.DataFrame(data) if data else pd.DataFrame()


# -------------------------
# Queries (cacheadas)
# -------------------------
@st.cache_data(show_spinner=False, ttl=45)
def _fetch_kpis_cached(owner_user_id: int, tipo_val: str | None, hoje_iso: str) -> dict:
    hoje_sp = date.fromisoformat(hoje_iso)

    start_today, end_7d = _dt_bounds(hoje_sp)
    now = now_br()
    now_n = _naive(now)

    with get_session() as s:
        # Total processos
        stmt_total = select(func.count(Processo.id)).where(
            Processo.owner_user_id == owner_user_id
        )
        stmt_total = _apply_tipo_filter(stmt_total, tipo_val)
        total_proc = int(s.execute(stmt_total).scalar_one())

        # Ativos
        stmt_ativos = select(func.count(Processo.id)).where(
            Processo.owner_user_id == owner_user_id,
            Processo.status == "Ativo",
        )
        stmt_ativos = _apply_tipo_filter(stmt_ativos, tipo_val)
        ativos = int(s.execute(stmt_ativos).scalar_one())

        # Prazos abertos + contagens por janela (SQL, sem loop Python)
        stmt_prazos_counts = (
            select(
                func.count(Prazo.id).label("abertos"),
                func.coalesce(
                    func.sum(case((Prazo.data_limite < start_today, 1), else_=0)),
                    0,
                ).label("atrasados"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (Prazo.data_limite >= start_today)
                                & (Prazo.data_limite <= end_7d),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("em_7d"),
            )
            .select_from(Prazo)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Prazo.concluido == False,  # noqa
            )
        )
        stmt_prazos_counts = _apply_tipo_filter(stmt_prazos_counts, tipo_val)
        prazos_abertos, prazos_atrasados, prazos_7dias = s.execute(
            stmt_prazos_counts
        ).one()

        prazos_abertos = int(prazos_abertos or 0)
        prazos_atrasados = int(prazos_atrasados or 0)
        prazos_7dias = int(prazos_7dias or 0)

        # Agenda 7 dias
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
        stmt_ag_7d = _apply_tipo_filter(stmt_ag_7d, tipo_val)
        ag_7d = int(s.execute(stmt_ag_7d).scalar_one())

        # Financeiro (duas somas)
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
        stmt_receitas = _apply_tipo_filter(stmt_receitas, tipo_val)
        stmt_despesas = _apply_tipo_filter(stmt_despesas, tipo_val)

        receitas = float(s.execute(stmt_receitas).scalar_one() or 0)
        despesas = float(s.execute(stmt_despesas).scalar_one() or 0)

    saldo = receitas - despesas

    return {
        "now": now,
        "now_n": now_n,
        "hoje_sp": hoje_sp,
        "start_today": start_today,
        "end_7d": end_7d,
        "total_proc": total_proc,
        "ativos": ativos,
        "prazos_abertos": prazos_abertos,
        "prazos_atrasados": prazos_atrasados,
        "prazos_7dias": prazos_7dias,
        "ag_7d": ag_7d,
        "receitas": receitas,
        "despesas": despesas,
        "saldo": saldo,
    }


@st.cache_data(show_spinner=False, ttl=45)
def _fetch_prazos_tables_cached(
    owner_user_id: int, tipo_val: str | None, start_today_iso: str, end_7d_iso: str
) -> tuple[list, list]:
    start_today = datetime.fromisoformat(start_today_iso)
    end_7d = datetime.fromisoformat(end_7d_iso)

    with get_session() as s:
        stmt_atrasados = (
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
        stmt_atrasados = _apply_tipo_filter(stmt_atrasados, tipo_val)
        rows_atrasados = s.execute(stmt_atrasados).all()

        stmt_7d = (
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
        stmt_7d = _apply_tipo_filter(stmt_7d, tipo_val)
        rows_7d = s.execute(stmt_7d).all()

    return rows_atrasados, rows_7d


@st.cache_data(show_spinner=False, ttl=45)
def _fetch_agendamentos_cached(
    owner_user_id: int, tipo_val: str | None, now_n_iso: str
) -> tuple[list, list]:
    now_n = datetime.fromisoformat(now_n_iso)

    with get_session() as s:
        stmt_24h = (
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
        stmt_24h = _apply_tipo_filter(stmt_24h, tipo_val)
        rows_24h = s.execute(stmt_24h).all()

        stmt_7d = (
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
        stmt_7d = _apply_tipo_filter(stmt_7d, tipo_val)
        rows_7d = s.execute(stmt_7d).all()

    return rows_24h, rows_7d


@st.cache_data(show_spinner=False, ttl=60)
def _fetch_ultimos_processos_cached(owner_user_id: int, tipo_val: str | None) -> list:
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
            .limit(12)
        )
        stmt = _apply_tipo_filter(stmt, tipo_val)
        return s.execute(stmt).all()


# -------------------------
# Render
# -------------------------
def render(owner_user_id: int):
    inject_global_css()

    # CSS leve para hierarquia / espaço
    st.markdown(
        """
        <style>
        .muted { color: rgba(49,51,63,0.65); font-size: 0.92rem; }
        .panel-title { font-size: 1.05rem; font-weight: 800; margin: 0 0 6px 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    clicked_refresh = page_header(
        "Painel de Controle",
        "Visão analítica: alertas, prazos, agenda e financeiro",
        right_button_label="Recarregar",
        right_button_key="dash_btn_recarregar_top",
        right_button_help="Recarrega os dados do painel",
    )
    if clicked_refresh:
        st.cache_data.clear()
        st.rerun()

    # Filtro (Atuação)
    f1, _ = st.columns([0.28, 0.72], vertical_alignment="center")
    with f1:
        atuacao_label = st.selectbox(
            "Atuação",
            list(ATUACAO_UI.keys()),
            index=0,
            key="dash_atuacao_ui",
        )
        tipo_val = ATUACAO_UI[atuacao_label]

    hoje_sp = now_br().date()
    hoje_iso, _ = _date_range_strings(hoje_sp)
    k = _fetch_kpis_cached(owner_user_id, tipo_val, hoje_iso)

    pct_atraso = _pct(k["prazos_atrasados"], k["prazos_abertos"])
    pct_7d = _pct(k["prazos_7dias"], k["prazos_abertos"])

    # ============================================================
    # 1) ALERTAS (TOPO)
    # ============================================================
    with st.container(border=True):
        st.subheader("Alertas de hoje")
        c1, c2 = st.columns([0.72, 0.28], vertical_alignment="center")

        if k["prazos_atrasados"] > 0:
            with c1:
                st.markdown(
                    f"**🔴 Atenção:** existem **{int(k['prazos_atrasados'])}** prazo(s) atrasado(s). "
                    f"<span class='muted'>Atuação: <b>{atuacao_label}</b>.</span>",
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button(
                    "Abrir atrasados",
                    key="dash_open_atrasados",
                    use_container_width=True,
                    type="primary",
                ):
                    navigate(
                        "Prazos",
                        state={
                            "prazos_section": "Lista",
                            "pz_nav_to": "Lista",
                            "pz_list_nav_to": "Atrasados",
                        },
                    )

        elif k["prazos_7dias"] > 0:
            with c1:
                st.markdown(
                    f"**🟠 Prazos próximos:** **{int(k['prazos_7dias'])}** vence(m) em até 7 dias. "
                    f"<span class='muted'>Atuação: <b>{atuacao_label}</b>.</span>",
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button(
                    "Ver 7 dias",
                    key="dash_open_7d",
                    use_container_width=True,
                    type="primary",
                ):
                    navigate(
                        "Prazos",
                        state={
                            "prazos_section": "Lista",
                            "pz_nav_to": "Lista",
                            "pz_list_nav_to": "Vencem (7 dias)",
                        },
                    )
        else:
            with c1:
                st.markdown(
                    f"**🟢 Tudo em ordem:** nenhum prazo crítico no momento. "
                    f"<span class='muted'>Atuação: <b>{atuacao_label}</b>.</span>",
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button(
                    "Cadastrar prazo", key="dash_go_new_prazo", use_container_width=True
                ):
                    navigate("Prazos", state={"prazos_section": "Cadastro"})

    st.write("")

    # ============================================================
    # 2) MÉTRICAS (OPERACIONAL + FINANCEIRO)
    # ============================================================
    with st.container(border=True):
        st.subheader("Resumo")

        # Operacional
        st.markdown(
            "<div class='panel-title'>Operacional</div>", unsafe_allow_html=True
        )
        op1, op2, op3, op4 = st.columns(4)
        with op1:
            card("Trabalhos", f"{k['total_proc']}", "cadastrados", tone="info")
            if st.button("Ver todos", use_container_width=True, key="go_proc"):
                navigate(
                    "Processos",
                    qp={"status": None, "atuacao": None, "categoria": None, "q": None},
                    state={"processos_section": "Lista"},
                )

        with op2:
            card("Ativos", f"{k['ativos']}", "em andamento", tone="neutral")
            if st.button("Ver ativos", use_container_width=True, key="go_proc_ativos"):
                navigate(
                    "Processos",
                    qp={"status": "Ativo"},
                    state={"processos_section": "Lista"},
                )

        with op3:
            tone_pz = (
                "danger"
                if k["prazos_atrasados"] > 0
                else ("warning" if k["prazos_7dias"] > 0 else "success")
            )
            card(
                "Prazos abertos",
                f"{k['prazos_abertos']}",
                f"{pct_atraso} atrasados • {pct_7d} em 7d",
                tone=tone_pz,
            )
            if st.button("Ver prazos", use_container_width=True, key="go_prazos"):
                navigate(
                    "Prazos",
                    state={
                        "prazos_section": "Lista",
                        "pz_nav_to": "Lista",
                        "pz_list_nav_to": "Abertos",
                    },
                )

        with op4:
            card("Agenda (7 dias)", f"{k['ag_7d']}", "agendados", tone="info")
            if st.button("Ver agenda", use_container_width=True, key="go_agenda"):
                navigate("Agendamentos")

        st.write("")

        # Financeiro
        st.markdown("<div class='panel-title'>Financeiro</div>", unsafe_allow_html=True)
        fin1, fin2, fin3 = st.columns([0.28, 0.28, 0.44], vertical_alignment="top")
        with fin1:
            card(
                "Receitas (R$)",
                _fmt_money_br(k["receitas"]),
                "acumulado",
                tone="success",
            )
        with fin2:
            card(
                "Despesas (R$)",
                _fmt_money_br(k["despesas"]),
                "acumulado",
                tone="danger",
            )
        with fin3:
            tone_saldo = "success" if k["saldo"] >= 0 else "danger"
            card(
                "Saldo (R$)",
                _fmt_money_br(k["saldo"]),
                "receitas - despesas",
                tone=tone_saldo,
                emphasize=True,
            )
            if st.button(
                "Abrir financeiro",
                use_container_width=True,
                key="go_fin",
                type="primary",
            ):
                navigate("Financeiro", state={"financeiro_section": "Lançamentos"})

    st.divider()

    # ============================================================
    # 3) LISTAS ANALÍTICAS (TABS)
    # ============================================================
    tab1, tab2, tab3 = st.tabs(["⏳ Prazos", "📅 Agenda", "🗂️ Trabalhos"])

    with tab1:
        rows_atrasados, rows_7d = _fetch_prazos_tables_cached(
            owner_user_id,
            tipo_val,
            k["start_today"].isoformat(timespec="seconds"),
            k["end_7d"].isoformat(timespec="seconds"),
        )

        colA, colB = st.columns(2, vertical_alignment="top")

        with colA:
            with st.container(border=True):
                st.subheader("Prazos atrasados")
                st.caption("Top 10 por data mais antiga")
                if not rows_atrasados:
                    st.caption("Sem prazos atrasados.")
                else:
                    df = _build_prazos_df(rows_atrasados)
                    st.dataframe(
                        df, use_container_width=True, hide_index=True, height=280
                    )

        with colB:
            with st.container(border=True):
                st.subheader("Vencem em até 7 dias")
                st.caption("Top 10 por vencimento")
                if not rows_7d:
                    st.caption("Sem prazos vencendo em até 7 dias.")
                else:
                    df = _build_prazos_df(rows_7d)
                    st.dataframe(
                        df, use_container_width=True, hide_index=True, height=280
                    )

    with tab2:
        rows_24h, rows_ag_7d = _fetch_agendamentos_cached(
            owner_user_id, tipo_val, k["now_n"].isoformat(timespec="seconds")
        )

        col1, col2 = st.columns(2, vertical_alignment="top")

        with col1:
            with st.container(border=True):
                st.subheader("Próximas 24 horas")
                if not rows_24h:
                    st.caption("✅ Sem agendamentos nas próximas 24 horas.")
                else:
                    dfa = _build_agenda_df(rows_24h)
                    st.dataframe(
                        dfa, use_container_width=True, hide_index=True, height=280
                    )

        with col2:
            with st.container(border=True):
                st.subheader("Próximos 7 dias")
                if not rows_ag_7d:
                    st.caption("✅ Sem agendamentos nos próximos 7 dias.")
                else:
                    dfa = _build_agenda_df(rows_ag_7d)
                    st.dataframe(
                        dfa, use_container_width=True, hide_index=True, height=280
                    )

    with tab3:
        procs = _fetch_ultimos_processos_cached(owner_user_id, tipo_val)

        with st.container(border=True):
            st.subheader("Últimos trabalhos")
            st.caption("Registros mais recentes cadastrados (respeita a atuação)")

            if not procs:
                st.caption("Nenhum trabalho cadastrado ainda para esta atuação.")
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
            dfp["tipo_acao"] = dfp["tipo_acao"].fillna("Sem tipo")
            dfp["tipo_trabalho"] = dfp["tipo_trabalho"].fillna("Assistente Técnico")

            dfp = dfp.rename(
                columns={
                    "id": "ID",
                    "numero_processo": "Referência",
                    "tipo_acao": "Descrição",
                    "comarca": "Comarca",
                    "vara": "Vara",
                    "status": "Status",
                    "tipo_trabalho": "Atuação",
                }
            )

            st.dataframe(dfp, use_container_width=True, hide_index=True, height=380)
