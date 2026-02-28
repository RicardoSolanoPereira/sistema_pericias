import streamlit as st
import pandas as pd
from datetime import datetime, date, time

from sqlalchemy import select

from db.connection import get_session
from db.models import Processo
from core.andamentos_service import AndamentosService, AndamentoCreate, AndamentoUpdate


def _proc_label(p: Processo) -> str:
    tipo = (p.tipo_acao or "").strip()
    if tipo:
        return f"[{p.id}] {p.numero_processo} – {tipo}"
    return f"[{p.id}] {p.numero_processo}"


def _and_label(a, proc_label_by_id: dict[int, str]) -> str:
    proc = proc_label_by_id.get(a.processo_id, f"[{a.processo_id}]")
    dt = a.data_evento.strftime("%d/%m/%Y %H:%M")
    titulo = (a.titulo or "").strip()
    return f"{dt} | {proc} | {titulo}"


def _load_processos(owner_user_id: int):
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

    proc_labels = [_proc_label(p) for p in processos]
    proc_label_to_id = {_proc_label(p): p.id for p in processos}
    proc_label_by_id = {p.id: _proc_label(p) for p in processos}
    return processos, proc_labels, proc_label_to_id, proc_label_by_id


def _section_create(
    owner_user_id: int, proc_labels: list[str], proc_label_to_id: dict[str, int]
):
    with st.expander("➕ Novo andamento", expanded=True):
        with st.form("form_andamento_create", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1, 1])

            proc_lbl = c1.selectbox("Processo *", proc_labels, key="and_create_proc")
            d = c2.date_input("Data *", value=date.today(), key="and_create_date")

            usar_hora = c3.toggle("Usar hora", value=True, key="and_create_use_time")
            hora = None
            if usar_hora:
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

        if not submitted:
            return

        # ---------- validações ----------
        titulo_ok = bool((titulo or "").strip())
        if not titulo_ok:
            st.error("Informe o **Título**.")
            return

        try:
            processo_id = int(proc_label_to_id[proc_lbl])

            # se hora não for usada, fixa 00:00 (ou você pode preferir 12:00)
            hhmm = hora if hora is not None else time(0, 0)
            dt_evento = datetime(d.year, d.month, d.day, hhmm.hour, hhmm.minute, 0)

            payload = AndamentoCreate(
                processo_id=processo_id,
                data_evento=dt_evento,
                titulo=titulo.strip(),
                descricao=(descricao or "").strip() or None,
            )

            with get_session() as s:
                AndamentosService.create(s, owner_user_id, payload)

            st.success("Andamento criado.")
            st.rerun()

        except Exception as e:
            st.error(f"Erro ao criar andamento: {e}")


def _section_list(
    owner_user_id: int,
    proc_labels: list[str],
    proc_label_to_id: dict[str, int],
    proc_label_by_id: dict[int, str],
):
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
        return [], pd.DataFrame()

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
    return andamentos, df


def _section_edit_delete(
    owner_user_id: int,
    andamentos: list,
    proc_labels: list[str],
    proc_label_to_id: dict[str, int],
    proc_label_by_id: dict[int, str],
):
    st.subheader("✏️ Editar / 🗑️ Excluir")

    # dropdown amigável (em vez de "ID seco")
    options = {_and_label(a, proc_label_by_id): a.id for a in andamentos}
    sel_label = st.selectbox(
        "Selecione o andamento", list(options.keys()), key="and_edit_select"
    )
    andamento_id = int(options[sel_label])

    with get_session() as s:
        a = AndamentosService.get(s, owner_user_id, andamento_id)

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
            "Data", value=a.data_evento.date(), key=f"and_edit_date_{andamento_id}"
        )

        usar_hora_e = c3.toggle(
            "Usar hora",
            value=True,
            key=f"and_edit_use_time_{andamento_id}",
        )
        hora_e = None
        if usar_hora_e:
            hora_e = c3.time_input(
                "Hora",
                value=a.data_evento.time().replace(second=0, microsecond=0),
                key=f"and_edit_time_{andamento_id}",
            )

        titulo_e = st.text_input(
            "Título *", value=a.titulo or "", key=f"and_edit_titulo_{andamento_id}"
        )
        desc_e = st.text_area(
            "Descrição", value=a.descricao or "", key=f"and_edit_desc_{andamento_id}"
        )

        cbtn1, cbtn2 = st.columns(2)
        atualizar = cbtn1.form_submit_button("Salvar alterações", type="primary")
        excluir = cbtn2.form_submit_button("Excluir")

    # -------- atualizar --------
    if atualizar:
        if not (titulo_e or "").strip():
            st.error("Informe o **Título**.")
            return

        try:
            processo_id_e = int(proc_label_to_id[proc_lbl_e])

            hhmm = hora_e if hora_e is not None else time(0, 0)
            dt_evento_e = datetime(
                d_e.year, d_e.month, d_e.day, hhmm.hour, hhmm.minute, 0
            )

            payload = AndamentoUpdate(
                processo_id=processo_id_e,
                data_evento=dt_evento_e,
                titulo=titulo_e.strip(),
                descricao=(desc_e or "").strip() or None,
            )

            with get_session() as s:
                AndamentosService.update(s, owner_user_id, andamento_id, payload)

            st.success("Andamento atualizado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")

    # -------- excluir (com confirmação) --------
    if excluir:
        with st.container(border=True):
            st.warning("⚠️ Exclusão irreversível.")
            confirm = st.checkbox(
                "Confirmo que desejo excluir este andamento.",
                key=f"and_del_confirm_{andamento_id}",
            )
            if st.button(
                "Confirmar exclusão",
                type="primary",
                disabled=not confirm,
                key=f"and_del_btn_{andamento_id}",
            ):
                try:
                    with get_session() as s:
                        AndamentosService.delete(s, owner_user_id, andamento_id)
                    st.success("Andamento excluído.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")


def render(owner_user_id: int):
    st.header("🧾 Andamentos")

    processos, proc_labels, proc_label_to_id, proc_label_by_id = _load_processos(
        owner_user_id
    )

    if not processos:
        st.info("Cadastre um processo primeiro para registrar andamentos.")
        return

    _section_create(owner_user_id, proc_labels, proc_label_to_id)

    st.divider()

    andamentos, df = _section_list(
        owner_user_id, proc_labels, proc_label_to_id, proc_label_by_id
    )

    if not andamentos:
        return

    st.divider()

    _section_edit_delete(
        owner_user_id, andamentos, proc_labels, proc_label_to_id, proc_label_by_id
    )
