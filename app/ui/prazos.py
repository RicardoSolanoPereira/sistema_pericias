import streamlit as st
import pandas as pd
from datetime import datetime, date

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


def render(owner_user_id: int):
    st.header("⏰ Prazos")

    # Carrega processos do usuário
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

    # ✅ Aqui: label do processo com número + tipo de ação
    proc_labels = [
        f"[{p.id}] {p.numero_processo} – {p.tipo_acao or 'Sem tipo de ação'}"
        for p in processos
    ]
    label_to_id = {proc_labels[i]: processos[i].id for i in range(len(processos))}

    # -------------------------
    # Criar prazo
    # -------------------------
    st.subheader("➕ Novo prazo")
    with st.form("form_prazo_create", clear_on_submit=True):
        sel = st.selectbox("Processo", proc_labels, key="prazo_create_proc")
        processo_id = label_to_id[sel]

        c1, c2, c3 = st.columns(3)
        evento = c1.text_input("Evento *", key="prazo_create_evento")
        data_lim = c2.date_input(
            "Data limite *", value=date.today(), key="prazo_create_data"
        )
        prioridade = c3.selectbox(
            "Prioridade", ["Baixa", "Média", "Alta"], index=1, key="prazo_create_prio"
        )

        obs = st.text_area("Observações", key="prazo_create_obs")
        ok = st.form_submit_button("Salvar prazo", type="primary")

    if ok:
        try:
            # ✅ Aqui: converte date -> datetime no fuso Brasil
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
    # Listar prazos abertos
    # -------------------------
    st.subheader("📋 Prazos (abertos)")
    filtro_proc = st.selectbox(
        "Filtrar por processo", ["(Todos)"] + proc_labels, key="prazo_list_filter_proc"
    )

    data = []

    with get_session() as s:
        if filtro_proc == "(Todos)":
            rows = PrazosService.list_all(s, owner_user_id, only_open=True)
            for prazo, proc in rows:
                dias = _dias_restantes(prazo.data_limite)
                # ✅ Aqui: mostra processo + tipo de ação
                proc_txt = (
                    f"{proc.numero_processo} – {proc.tipo_acao or 'Sem tipo de ação'}"
                )
                data.append(
                    {
                        "prazo_id": prazo.id,
                        "processo": proc_txt,
                        "evento": prazo.evento,
                        # ✅ Aqui: data em padrão BR
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
        st.info("Nenhum prazo aberto.")
        return

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # -------------------------
    # Editar / Concluir / Excluir
    # -------------------------
    st.subheader("✏️ Editar / ✅ Concluir / 🗑️ Excluir")
    prazo_id = st.selectbox(
        "Selecione o prazo_id", df["prazo_id"].tolist(), key="prazo_edit_select"
    )

    with get_session() as s:
        pz = PrazosService.get(s, owner_user_id, int(prazo_id))

    if not pz:
        st.error("Prazo não encontrado.")
        return

    with st.form(f"form_prazo_edit_{prazo_id}"):
        c1, c2, c3 = st.columns(3)
        evento_e = c1.text_input(
            "Evento", value=pz.evento, key=f"prazo_edit_evento_{prazo_id}"
        )

        # ✅ Aqui: exibimos o date_input como date (BR), mantendo base no fuso
        data_e = c2.date_input(
            "Data limite",
            value=ensure_br(pz.data_limite).date(),
            key=f"prazo_edit_data_{prazo_id}",
        )

        prio_e = c3.selectbox(
            "Prioridade",
            ["Baixa", "Média", "Alta"],
            index=["Baixa", "Média", "Alta"].index(pz.prioridade),
            key=f"prazo_edit_prio_{prazo_id}",
        )

        concl = st.checkbox(
            "Concluído", value=bool(pz.concluido), key=f"prazo_edit_conc_{prazo_id}"
        )
        obs_e = st.text_area(
            "Observações", value=pz.observacoes or "", key=f"prazo_edit_obs_{prazo_id}"
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
                        # ✅ Aqui: salva no fuso Brasil
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
