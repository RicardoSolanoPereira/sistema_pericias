import streamlit as st
import pandas as pd
import sys
import subprocess
from datetime import datetime, timedelta, time
from pathlib import Path

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


# -------------------------
# Helpers (time/format)
# -------------------------
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


# -------------------------
# Paths / Backup
# -------------------------
def _project_root() -> Path:
    """
    Raiz estável do projeto:
    app/ui/dashboard.py -> app -> <raiz>
    """
    return Path(__file__).resolve().parents[2]


def _get_last_backup_info() -> dict:
    """
    Procura o último backup em <raiz>/backups, independente do CWD.
    Espera arquivos: app_backup_*.db
    """
    backup_dir = _project_root() / "backups"
    if not backup_dir.exists():
        return {"status": "missing_dir", "backup_dir": str(backup_dir)}

    backups = list(backup_dir.glob("app_backup_*.db"))
    if not backups:
        return {"status": "empty", "backup_dir": str(backup_dir)}

    last = max(backups, key=lambda p: p.stat().st_mtime)
    dt = datetime.fromtimestamp(last.stat().st_mtime)
    size_mb = last.stat().st_size / (1024 * 1024)

    return {
        "status": "ok",
        "backup_dir": str(backup_dir),
        "file": last.name,
        "dt": dt,
        "size_mb": size_mb,
    }


def _run_backup_now() -> tuple[bool, str]:
    """
    Executa o backup chamando o mesmo interpretador do Streamlit.
    Retorna (ok, msg). Usa cwd na raiz do projeto para garantir paths/exports.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.backup_diario"],
            capture_output=True,
            text=True,
            cwd=str(_project_root()),
        )
        if proc.returncode != 0:
            err = (
                (proc.stderr or "").strip()
                or (proc.stdout or "").strip()
                or "Falha ao executar backup."
            )
            return False, err

        out = (proc.stdout or "").strip() or "Backup executado."
        return True, out
    except Exception as e:
        return False, str(e)


# -------------------------
# Queries (isoladas)
# -------------------------
def _apply_tipo_filter(stmt, tipo_val):
    return stmt if not tipo_val else stmt.where(Processo.papel == tipo_val)


def _fetch_kpis(owner_user_id: int, tipo_val: str | None) -> dict:
    now = now_br()
    now_n = _naive(now)
    hoje_sp = now.date()
    ate_7_sp = hoje_sp + timedelta(days=7)

    start_today = datetime.combine(hoje_sp, time.min)
    end_7d = datetime.combine(ate_7_sp, time.max)

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

        # Prazos abertos (contagem em Python por causa do fuso)
        stmt_prazos = (
            select(Prazo.data_limite)
            .join(Processo, Processo.id == Prazo.processo_id)
            .where(
                Processo.owner_user_id == owner_user_id,
                Prazo.concluido == False,  # noqa
            )
        )
        stmt_prazos = _apply_tipo_filter(stmt_prazos, tipo_val)
        prazos_rows = s.execute(stmt_prazos).all()

        prazos_abertos = len(prazos_rows)
        prazos_atrasados = 0
        prazos_7dias = 0
        for (data_limite,) in prazos_rows:
            d = ensure_br(data_limite).date()
            if d < hoje_sp:
                prazos_atrasados += 1
            elif hoje_sp <= d <= ate_7_sp:
                prazos_7dias += 1

        # Agendamentos próximos (7 dias)
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
        stmt_receitas = _apply_tipo_filter(stmt_receitas, tipo_val)
        stmt_despesas = _apply_tipo_filter(stmt_despesas, tipo_val)

        receitas = float(s.execute(stmt_receitas).scalar_one())
        despesas = float(s.execute(stmt_despesas).scalar_one())

    saldo = receitas - despesas

    return {
        "now": now,
        "now_n": now_n,
        "hoje_sp": hoje_sp,
        "ate_7_sp": ate_7_sp,
        "start_today": start_today,
        "end_7d": end_7d,
        "total_proc": total_proc,
        "ativos": ativos,
        "prazos_abertos": prazos_abertos,
        "prazos_atrasados": prazos_atrasados,
        "prazos_7dias": prazos_7dias,
        "ag_7d": ag_7d,
        "saldo": saldo,
    }


def _fetch_prazos_tables(
    owner_user_id: int,
    tipo_val: str | None,
    start_today: datetime,
    end_7d: datetime,
) -> tuple[list, list]:
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


def _fetch_agendamentos(
    owner_user_id: int, tipo_val: str | None, now_n: datetime
) -> tuple[list, list]:
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


def _fetch_ultimos_processos(owner_user_id: int, tipo_val: str | None) -> list:
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
        stmt = _apply_tipo_filter(stmt, tipo_val)
        return s.execute(stmt).all()


# -------------------------
# Render
# -------------------------
def render(owner_user_id: int):
    inject_global_css()

    # Topo + filtro + botões
    col_title, col_filter, col_actions = st.columns([6, 2, 2])
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

    with col_actions:
        # botão de refresh
        if st.button("🔄 Atualizar", use_container_width=True):
            st.rerun()

    # KPIs
    k = _fetch_kpis(owner_user_id, tipo_val)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        card("Processos", str(k["total_proc"]), "cadastrados")
    with c2:
        card("Ativos", str(k["ativos"]), "em andamento")
    with c3:
        card("Prazos abertos", str(k["prazos_abertos"]), "não concluídos")
    with c4:
        card("Atrasados", str(k["prazos_atrasados"]), "prazos")
    with c5:
        card("Agendamentos (7d)", str(k["ag_7d"]), "status Agendado")
    with c6:
        card("Saldo (R$)", _fmt_money_br(k["saldo"]), "receitas - despesas")

    # -------------------------
    # Backup (status + botão)
    # -------------------------
    st.markdown("### 🛡️ Backup")
    col_bk_info, col_bk_btn = st.columns([4, 1])

    with col_bk_btn:
        if st.button("💾 Backup agora", use_container_width=True):
            with st.spinner("Executando backup..."):
                ok, msg = _run_backup_now()
            if ok:
                st.success("Backup executado.")
                st.rerun()
            else:
                st.error("Falha ao executar backup.")
                st.caption(msg)

    info_bk = _get_last_backup_info()
    with col_bk_info:
        if info_bk["status"] == "missing_dir":
            st.warning(f"Pasta de backups não encontrada: `{info_bk['backup_dir']}`")
        elif info_bk["status"] == "empty":
            st.warning(f"Nenhum backup encontrado em: `{info_bk['backup_dir']}`")
        else:
            dt = info_bk["dt"]
            hours = (datetime.now() - dt).total_seconds() / 3600

            cb1, cb2, cb3 = st.columns([2, 1, 1])
            with cb1:
                st.write(f"**Arquivo:** {info_bk['file']}")
                st.caption(f"Pasta: {info_bk['backup_dir']}")
            with cb2:
                st.write(f"**Data/Hora:** {dt:%d/%m/%Y %H:%M:%S}")
            with cb3:
                st.write(f"**Tamanho:** {info_bk['size_mb']:.2f} MB")

            if hours > 24:
                st.error(f"⚠️ Último backup há {int(hours)} horas.")
            else:
                st.success("✅ Backup recente.")

    # -------------------------
    # Mensagem de risco (prazos)
    # -------------------------
    if k["prazos_atrasados"] > 0:
        st.error(
            f"⚠️ Existem {int(k['prazos_atrasados'])} prazo(s) atrasado(s). "
            f"Filtro: {filtro_tipo}."
        )
    elif k["prazos_7dias"] > 0:
        st.warning(
            f"🟠 Existem {int(k['prazos_7dias'])} prazo(s) vencendo nos próximos 7 dias. "
            f"Filtro: {filtro_tipo}."
        )
    else:
        st.success(f"✅ Nenhum prazo crítico no momento. Filtro: {filtro_tipo}.")

    st.divider()

    # -------------------------
    # Prazos: atrasados e vencendo 7 dias
    # -------------------------
    colA, colB = st.columns([1, 1])
    rows_atrasados, rows_7d = _fetch_prazos_tables(
        owner_user_id, tipo_val, k["start_today"], k["end_7d"]
    )

    with colA:
        st.subheader("🔴 Prazos atrasados (Top 10)")
        if not rows_atrasados:
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
            ) in rows_atrasados:
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
        if not rows_7d:
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
            ) in rows_7d:
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

    rows_24h, rows_ag_7d = _fetch_agendamentos(owner_user_id, tipo_val, k["now_n"])

    with col1:
        st.markdown("#### ⏰ Em 24 horas (Top 10)")
        if not rows_24h:
            st.caption("Sem agendamentos nas próximas 24h.")
        else:
            data = []
            for ag_id, tipo, inicio, local, numero_processo, tipo_acao in rows_24h:
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
        if not rows_ag_7d:
            st.caption("Sem agendamentos nos próximos 7 dias.")
        else:
            data = []
            for ag_id, tipo, inicio, local, numero_processo, tipo_acao in rows_ag_7d:
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

    procs = _fetch_ultimos_processos(owner_user_id, tipo_val)
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
