import streamlit as st
import pandas as pd
from datetime import date, datetime

from sqlalchemy import select

from db.connection import get_session
from db.models import Processo
from core.prazos_service import PrazosService, PrazoCreate, PrazoUpdate
from core.utils import now_br, ensure_br, format_date_br, date_to_br_datetime


def _dias_restantes(dt: datetime) -> int:
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


def _filtro_aplica_abertos(dias_restantes: int, filtro: str) -> bool:
    if filtro == "Abertos (todos)":
        return True
    if filtro == "Atrasados":
        return dias_restantes < 0
    if filtro == "Vencem em 7 dias":
        return 0 <= dias_restantes <= 7
    if filtro == "Vencem em 15 dias":
        return 0 <= dias_restantes <= 15
    if filtro == "Vencem em 30 dias":
        return 0 <= dias_restantes <= 30
    return True


def render(owner_user_id: int):
    st.header("⏰ Prazos")

    hoje_sp = now_br().date()

    # -------------------------
    # Processos do usuário
    # -------------------------
    with get_session() as s:
        processos = (
            s.execute(
                select(Processo)
                .where(Processo.owner_user_id == owner_user_id)
                .order_by(Processo.id.desc())
            )
            .scalars()
            .all()
        )

    if not processos:
        st.info("Cadastre um processo primeiro.")
        return

    proc_labels = [
        f"[{p.id}] {p.numero_processo} – {p.tipo_acao or 'Sem tipo de ação'}"
        for p in processos
    ]
    label_to_id = {proc_labels[i]: processos[i].id for i in range(len(processos))}

    # -------------------------
    # Novo prazo
    # -------------------------
    st.subheader("➕ Novo prazo")
    with st.form("form_prazo_create", clear_on_submit=True):
        sel = st.selectbox("Processo", proc_labels, key="prazo_create_proc")
        processo_id = label_to_id[sel]

        c1, c2, c3 = st.columns(3)
        evento = c1.text_input("Evento *", key="prazo_create_evento")
        data_lim = c2.date_input(
            "Data limite *", value=hoje_sp, key="prazo_create_data"
        )
        prioridade = c3.selectbox(
            "Prioridade", ["Baixa", "Média", "Alta"], index=1, key="prazo_create_prio"
        )

        obs = st.text_area("Observações", key="prazo_create_obs")
        ok = st.form_submit_button("Salvar prazo", type="primary")

    if ok:
        try:
            dt_lim = date_to_br_datetime(data_lim)
            with get_session() as s:
                PrazosService.create(
                    s,
                    owner_user_id,
                    PrazoCreate(
                        processo_id=int(processo_id),
                        evento=evento,
                        data_limite=dt_lim,
                        prioridade=prioridade,
                        observacoes=obs,
                    ),
                )
            st.success("Prazo criado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao criar prazo: {e}")

    st.divider()

    # -------------------------
    # Abas: Abertos x Concluídos
    # -------------------------
    tab_abertos, tab_conc = st.tabs(["📋 Abertos", "✅ Concluídos"])

    # =========================================================
    # TAB ABERTOS
    # =========================================================
    with tab_abertos:
        st.subheader("📋 Prazos (abertos)")

        cfil1, cfil2 = st.columns([2, 2])
        filtro_proc = cfil1.selectbox(
            "Filtrar por processo",
            ["(Todos)"] + proc_labels,
            key="prazo_open_filter_proc",
        )
        filtro_tipo = cfil2.selectbox(
            "Filtro de vencimento",
            [
                "Abertos (todos)",
                "Atrasados",
                "Vencem em 7 dias",
                "Vencem em 15 dias",
                "Vencem em 30 dias",
            ],
            key="prazo_open_filter_tipo",
        )

        data = []

        with get_session() as s:
            if filtro_proc == "(Todos)":
                rows = PrazosService.list_all(s, owner_user_id, only_open=True)
                for prazo, proc in rows:
                    dias = _dias_restantes(prazo.data_limite)
                    if not _filtro_aplica_abertos(dias, filtro_tipo):
                        continue

                    proc_txt = f"{proc.numero_processo} – {proc.tipo_acao or 'Sem tipo de ação'}"
                    data.append(
                        {
                            "prazo_id": prazo.id,
                            "processo": proc_txt,
                            "evento": prazo.evento,
                            "data_limite": format_date_br(prazo.data_limite),
                            "dias_restantes": dias,
                            "status": _semaforo(dias),
                            "prioridade": prazo.prioridade,
                        }
                    )
            else:
                pid = label_to_id[filtro_proc]
                prazos = PrazosService.list_by_processo(
                    s, owner_user_id, pid, only_open=True
                )

                proc_obj = next(p for p in processos if p.id == pid)
                proc_txt = f"{proc_obj.numero_processo} – {proc_obj.tipo_acao or 'Sem tipo de ação'}"

                for prazo in prazos:
                    dias = _dias_restantes(prazo.data_limite)
                    if not _filtro_aplica_abertos(dias, filtro_tipo):
                        continue

                    data.append(
                        {
                            "prazo_id": prazo.id,
                            "processo": proc_txt,
                            "evento": prazo.evento,
                            "data_limite": format_date_br(prazo.data_limite),
                            "dias_restantes": dias,
                            "status": _semaforo(dias),
                            "prioridade": prazo.prioridade,
                        }
                    )

        if not data:
            st.info("Nenhum prazo aberto com os filtros selecionados.")
        else:
            df = pd.DataFrame(data).sort_values(by=["dias_restantes"], ascending=[True])
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("✏️ Editar / ✅ Concluir / 🗑️ Excluir (Abertos)")
            prazo_id = st.selectbox(
                "Selecione o prazo_id",
                df["prazo_id"].tolist(),
                key="prazo_open_edit_select",
            )

            with get_session() as s:
                pz = PrazosService.get(s, owner_user_id, int(prazo_id))

            if not pz:
                st.error("Prazo não encontrado.")
            else:
                with st.form(f"form_prazo_open_edit_{prazo_id}"):
                    c1, c2, c3 = st.columns(3)
                    evento_e = c1.text_input(
                        "Evento", value=pz.evento, key=f"prazo_open_evento_{prazo_id}"
                    )
                    data_e = c2.date_input(
                        "Data limite",
                        value=ensure_br(pz.data_limite).date(),
                        key=f"prazo_open_data_{prazo_id}",
                    )
                    prio_e = c3.selectbox(
                        "Prioridade",
                        ["Baixa", "Média", "Alta"],
                        index=["Baixa", "Média", "Alta"].index(pz.prioridade),
                        key=f"prazo_open_prio_{prazo_id}",
                    )

                    concl = st.checkbox(
                        "Concluído",
                        value=bool(pz.concluido),
                        key=f"prazo_open_conc_{prazo_id}",
                    )
                    obs_e = st.text_area(
                        "Observações",
                        value=pz.observacoes or "",
                        key=f"prazo_open_obs_{prazo_id}",
                    )

                    b1, b2 = st.columns(2)
                    salvar = b1.form_submit_button("Salvar alterações", type="primary")
                    excluir = b2.form_submit_button("Excluir")

                if salvar:
                    try:
                        with get_session() as s:
                            PrazosService.update(
                                s,
                                owner_user_id,
                                int(prazo_id),
                                PrazoUpdate(
                                    evento=evento_e,
                                    data_limite=date_to_br_datetime(data_e),
                                    prioridade=prio_e,
                                    concluido=concl,
                                    observacoes=obs_e,
                                ),
                            )
                        st.success("Prazo atualizado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

                if excluir:
                    try:
                        with get_session() as s:
                            PrazosService.delete(s, owner_user_id, int(prazo_id))
                        st.warning("Prazo excluído.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")

    # =========================================================
    # TAB CONCLUÍDOS
    # =========================================================
    with tab_conc:
        st.subheader("✅ Prazos concluídos")

        c1, c2 = st.columns([2, 2])
        filtro_proc_c = c1.selectbox(
            "Filtrar por processo",
            ["(Todos)"] + proc_labels,
            key="prazo_done_filter_proc",
        )
        busca = c2.text_input("Buscar no evento/observações", key="prazo_done_search")

        data_c = []

        with get_session() as s:
            if filtro_proc_c == "(Todos)":
                rows = PrazosService.list_all(s, owner_user_id, only_open=False)
                for prazo, proc in rows:
                    proc_txt = f"{proc.numero_processo} – {proc.tipo_acao or 'Sem tipo de ação'}"
                    txt = f"{prazo.evento} {(prazo.observacoes or '')}".lower()
                    if busca and busca.lower() not in txt:
                        continue

                    data_c.append(
                        {
                            "prazo_id": prazo.id,
                            "processo": proc_txt,
                            "evento": prazo.evento,
                            "data_limite": format_date_br(prazo.data_limite),
                            "prioridade": prazo.prioridade,
                        }
                    )
            else:
                pid = label_to_id[filtro_proc_c]
                prazos = PrazosService.list_by_processo(
                    s, owner_user_id, pid, only_open=False
                )

                proc_obj = next(p for p in processos if p.id == pid)
                proc_txt = f"{proc_obj.numero_processo} – {proc_obj.tipo_acao or 'Sem tipo de ação'}"

                for prazo in prazos:
                    txt = f"{prazo.evento} {(prazo.observacoes or '')}".lower()
                    if busca and busca.lower() not in txt:
                        continue

                    data_c.append(
                        {
                            "prazo_id": prazo.id,
                            "processo": proc_txt,
                            "evento": prazo.evento,
                            "data_limite": format_date_br(prazo.data_limite),
                            "prioridade": prazo.prioridade,
                        }
                    )

        if not data_c:
            st.info("Nenhum prazo concluído encontrado.")
        else:
            dfc = pd.DataFrame(data_c)
            st.dataframe(dfc, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("♻️ Reabrir ou excluir (Concluídos)")

            prazo_id_c = st.selectbox(
                "Selecione o prazo_id",
                dfc["prazo_id"].tolist(),
                key="prazo_done_edit_select",
            )

            with get_session() as s:
                pz = PrazosService.get(s, owner_user_id, int(prazo_id_c))

            if not pz:
                st.error("Prazo não encontrado.")
            else:
                b1, b2 = st.columns(2)
                if b1.button(
                    "Reabrir prazo (marcar como não concluído)",
                    key=f"prazo_reopen_{prazo_id_c}",
                ):
                    try:
                        with get_session() as s:
                            PrazosService.update(
                                s,
                                owner_user_id,
                                int(prazo_id_c),
                                PrazoUpdate(concluido=False),
                            )
                        st.success("Prazo reaberto.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao reabrir: {e}")

                if b2.button(
                    "Excluir prazo concluído", key=f"prazo_del_done_{prazo_id_c}"
                ):
                    try:
                        with get_session() as s:
                            PrazosService.delete(s, owner_user_id, int(prazo_id_c))
                        st.warning("Prazo excluído.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")
