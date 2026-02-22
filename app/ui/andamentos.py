import streamlit as st
import pandas as pd
from datetime import datetime, date

from sqlalchemy import select

from db.connection import get_session
from db.models import Processo
from core.andamentos_service import AndamentosService, AndamentoCreate, AndamentoUpdate


def _proc_label(p: Processo) -> str:
    tipo = (p.tipo_acao or "").strip()
    if tipo:
        return f"[{p.id}] {p.numero_processo} – {tipo}"
    return f"[{p.id}] {p.numero_processo}"


def render(owner_user_id: int):
    st.header("🧾 Andamentos")

    # -------------------------
    # Carregar processos (para selects)
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
        st.info("Cadastre um processo primeiro para registrar andamentos.")
        return

    proc_labels = [_proc_label(p) for p in processos]
    proc_label_to_id = {_proc_label(p): p.id for p in processos}
    proc_label_by_id = {p.id: _proc_label(p) for p in processos}

    # -------------------------
    # Criar (Form)
    # -------------------------
    with st.expander("➕ Novo andamento", expanded=True):
        with st.form("form_andamento_create", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1, 1])

            proc_lbl = c1.selectbox("Processo *", proc_labels, key="and_create_proc")
            d = c2.date_input("Data *", value=date.today(), key="and_create_date")

            # opcional agora (você pode remover se quiser só data)
            hora = c3.time_input(
                "Hora",
                value=datetime.now().replace(second=0, microsecond=0).time(),
                key="and_create_time",
            )

            titulo = st.text_input(
                "Título *",
                placeholder="Ex.: Juntada de petição / Intimação / Despacho",
                key="and_create_titulo",
            )
            descricao = st.text_area("Descrição", key="and_create_desc")

            submitted = st.form_submit_button("Salvar andamento", type="primary")

        if submitted:
            try:
                processo_id = int(proc_label_to_id[proc_lbl])
                dt_evento = datetime(d.year, d.month, d.day, hora.hour, hora.minute, 0)

                payload = AndamentoCreate(
                    processo_id=processo_id,
                    data_evento=dt_evento,
                    titulo=titulo,
                    descricao=descricao,
                )

                with get_session() as s:
                    AndamentosService.create(s, owner_user_id, payload)

                st.success("Andamento criado.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao criar andamento: {e}")

    st.divider()

    # -------------------------
    # Listar
    # -------------------------
    st.subheader("📋 Lista")

    cF1, cF2, cF3 = st.columns([3, 2, 1])
    filtro_proc = cF1.selectbox(
        "Filtrar por processo",
        ["(Todos)"] + proc_labels,
        index=0,
        key="and_list_filtro_proc",
    )
    filtro_q = cF2.text_input("Buscar texto", value="", key="and_list_busca")
    filtro_limit = cF3.selectbox(
        "Limite", [100, 200, 300, 500], index=1, key="and_list_limit"
    )

    processo_id = None
    if filtro_proc != "(Todos)":
        processo_id = int(proc_label_to_id[filtro_proc])

    with get_session() as s:
        andamentos = AndamentosService.list(
            s,
            owner_user_id=owner_user_id,
            processo_id=processo_id,
            q=(filtro_q or None),
            limit=int(filtro_limit),
        )

    if not andamentos:
        st.info("Nenhum andamento cadastrado.")
        return

    df = pd.DataFrame(
        [
            {
                "id": a.id,
                "processo": proc_label_by_id.get(a.processo_id, f"[{a.processo_id}]"),
                "data_evento": a.data_evento.strftime("%d/%m/%Y %H:%M"),
                "titulo": a.titulo,
                "descricao": a.descricao or "",
            }
            for a in andamentos
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # -------------------------
    # Editar/Excluir (Form)
    # -------------------------
    st.subheader("✏️ Editar / 🗑️ Excluir")
    ids = df["id"].tolist()

    andamento_id = st.selectbox(
        "Selecione o ID do andamento",
        ids,
        key="and_edit_select_id",
    )

    with get_session() as s:
        a = AndamentosService.get(s, owner_user_id, int(andamento_id))

    if not a:
        st.error("Andamento não encontrado.")
        return

    proc_atual_lbl = proc_label_by_id.get(a.processo_id, proc_labels[0])

    with st.form(f"form_andamento_edit_{andamento_id}"):
        c1, c2, c3 = st.columns([3, 1, 1])

        proc_lbl_e = c1.selectbox(
            "Processo",
            proc_labels,
            index=(
                proc_labels.index(proc_atual_lbl)
                if proc_atual_lbl in proc_labels
                else 0
            ),
            key=f"and_edit_proc_{andamento_id}",
        )

        d_e = c2.date_input(
            "Data",
            value=a.data_evento.date(),
            key=f"and_edit_date_{andamento_id}",
        )

        hora_e = c3.time_input(
            "Hora",
            value=a.data_evento.time().replace(second=0, microsecond=0),
            key=f"and_edit_time_{andamento_id}",
        )

        titulo_e = st.text_input(
            "Título", value=a.titulo, key=f"and_edit_titulo_{andamento_id}"
        )
        desc_e = st.text_area(
            "Descrição", value=a.descricao or "", key=f"and_edit_desc_{andamento_id}"
        )

        cbtn1, cbtn2 = st.columns(2)
        atualizar = cbtn1.form_submit_button("Atualizar", type="primary")
        excluir = cbtn2.form_submit_button("Excluir (irreversível)")

    if atualizar:
        try:
            processo_id_e = int(proc_label_to_id[proc_lbl_e])
            dt_evento_e = datetime(
                d_e.year, d_e.month, d_e.day, hora_e.hour, hora_e.minute, 0
            )

            payload = AndamentoUpdate(
                processo_id=processo_id_e,
                data_evento=dt_evento_e,
                titulo=titulo_e,
                descricao=desc_e,
            )

            with get_session() as s:
                AndamentosService.update(s, owner_user_id, int(andamento_id), payload)

            st.success("Andamento atualizado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")

    if excluir:
        try:
            with get_session() as s:
                AndamentosService.delete(s, owner_user_id, int(andamento_id))
            st.warning("Andamento excluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao excluir: {e}")
