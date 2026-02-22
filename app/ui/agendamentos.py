from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db.connection import get_session
from db.models import Processo
from core.agendamentos_service import (
    AgendamentosService,
    AgendamentoCreate,
    AgendamentoUpdate,
    TIPOS_VALIDOS,
    STATUS_VALIDOS,
)


# -------------------------
# Helpers
# -------------------------
@dataclass(frozen=True)
class ProcMaps:
    labels: List[str]
    label_to_id: Dict[str, int]
    label_by_id: Dict[int, str]


def _proc_label(p: Processo) -> str:
    tipo = (p.tipo_acao or "").strip()
    if tipo:
        return f"[{p.id}] {p.numero_processo} – {tipo}"
    return f"[{p.id}] {p.numero_processo}"


def _combine_date_time(d: date, t) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, 0)


def _sanitize_end_dt(inicio: datetime, fim: datetime) -> Optional[datetime]:
    if fim == inicio:
        return None
    if fim < inicio:
        raise ValueError("A data/hora de fim não pode ser anterior ao início.")
    return fim


def _format_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%d/%m/%Y %H:%M") if dt else ""


def _load_processos(owner_user_id: int) -> List[Processo]:
    with get_session() as s:
        return (
            s.execute(
                select(Processo)
                .where(Processo.owner_user_id == owner_user_id)
                .order_by(Processo.id.desc())
            )
            .scalars()
            .all()
        )


def _build_proc_maps(processos: List[Processo]) -> ProcMaps:
    labels = [_proc_label(p) for p in processos]
    label_to_id = {_proc_label(p): int(p.id) for p in processos}
    label_by_id = {int(p.id): _proc_label(p) for p in processos}
    return ProcMaps(labels=labels, label_to_id=label_to_id, label_by_id=label_by_id)


def _load_agendamentos_for_list(
    owner_user_id: int,
    *,
    processo_id: Optional[int],
    tipo: Optional[str],
    status: Optional[str],
    q: Optional[str],
    order: str,
    limit: int,
):
    with get_session() as s:
        return AgendamentosService.list(
            s,
            owner_user_id=owner_user_id,
            processo_id=processo_id,
            tipo=tipo,
            status=status,
            q=q,
            order=order,
            limit=limit,
        )


def _load_agendamentos_for_edit_picker(owner_user_id: int, limit: int = 500):
    """
    O seletor de edição não deve depender dos filtros da lista.
    Isso evita o bug: “tenho 2 cadastrados mas no editar só aparece 1”.
    """
    with get_session() as s:
        return AgendamentosService.list(
            s,
            owner_user_id=owner_user_id,
            processo_id=None,
            tipo=None,
            status=None,
            q=None,
            order="desc",
            limit=limit,
        )


def _build_agendamento_label(a, proc_label_by_id: Dict[int, str]) -> str:
    proc_lbl = proc_label_by_id.get(a.processo_id, f"[{a.processo_id}]")
    return f"[#{a.id}] {_format_dt(a.inicio)} — {a.tipo} — {a.status} — {proc_lbl}"


def _parse_agendamento_id_from_label(label: str) -> int:
    head = label.split("]")[0]  # "[#123"
    return int(head.replace("[#", "").strip())


# -------------------------
# Page
# -------------------------
def render(owner_user_id: int):
    st.header("📅 Agendamentos")

    processos = _load_processos(owner_user_id)
    if not processos:
        st.info("Cadastre um processo primeiro para criar agendamentos.")
        return

    proc_maps = _build_proc_maps(processos)
    TIPOS = list(TIPOS_VALIDOS)
    STATUS = list(STATUS_VALIDOS)

    # =========================================================
    # CRIAR
    # =========================================================
    with st.expander("➕ Novo agendamento", expanded=True):
        with st.form("form_agendamento_create", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            proc_lbl = c1.selectbox(
                "Processo *", proc_maps.labels, key="ag_create_proc"
            )
            tipo = c2.selectbox("Tipo *", TIPOS, key="ag_create_tipo")
            status = c3.selectbox("Status *", STATUS, index=0, key="ag_create_status")

            c4, c5 = st.columns(2)
            d_ini = c4.date_input(
                "Data início *", value=date.today(), key="ag_create_dini"
            )
            h_ini = c5.time_input(
                "Hora início *",
                value=datetime.now().replace(second=0, microsecond=0).time(),
                key="ag_create_hini",
            )

            c6, c7 = st.columns(2)
            d_fim = c6.date_input(
                "Data fim (opcional)", value=d_ini, key="ag_create_dfim"
            )
            h_fim = c7.time_input(
                "Hora fim (opcional)",
                value=datetime.now().replace(second=0, microsecond=0).time(),
                key="ag_create_hfim",
            )

            local = st.text_input("Local", key="ag_create_local")
            descricao = st.text_area("Descrição", key="ag_create_desc")

            submitted = st.form_submit_button("Salvar agendamento", type="primary")

        if submitted:
            try:
                processo_id = int(proc_maps.label_to_id[proc_lbl])
                inicio = _combine_date_time(d_ini, h_ini)
                fim = _combine_date_time(d_fim, h_fim)
                fim_val = _sanitize_end_dt(inicio, fim)

                with get_session() as s:
                    AgendamentosService.create(
                        s,
                        owner_user_id=owner_user_id,
                        payload=AgendamentoCreate(
                            processo_id=processo_id,
                            tipo=tipo,
                            inicio=inicio,
                            fim=fim_val,
                            local=local,
                            descricao=descricao,
                            status=status,
                        ),
                    )

                st.success("Agendamento criado.")
                st.rerun()

            except Exception as e:
                st.error(f"Erro ao criar agendamento: {e}")

    st.divider()

    # =========================================================
    # LISTA (filtros)
    # =========================================================
    st.subheader("📋 Lista")

    cF1, cF2, cF3, cF4 = st.columns([3, 2, 2, 1])
    filtro_proc = cF1.selectbox(
        "Filtrar por processo",
        ["(Todos)"] + proc_maps.labels,
        index=0,
        key="ag_list_filtro_proc",
    )
    filtro_tipo = cF2.selectbox(
        "Filtrar por tipo",
        ["(Todos)"] + TIPOS,
        index=0,
        key="ag_list_filtro_tipo",
    )
    filtro_status = cF3.selectbox(
        "Filtrar por status",
        ["(Todos)"] + STATUS,
        index=0,
        key="ag_list_filtro_status",
    )
    filtro_limit = cF4.selectbox(
        "Limite", [100, 200, 300, 500], index=1, key="ag_list_limit"
    )

    cO1, cO2 = st.columns([1, 3])
    order = cO1.radio(
        "Ordem", ["Próximos", "Recentes"], horizontal=True, key="ag_list_order"
    )
    filtro_q = cO2.text_input("Buscar (local/descrição)", value="", key="ag_list_busca")

    order_val = "asc" if order == "Próximos" else "desc"

    processo_id = None
    if filtro_proc != "(Todos)":
        processo_id = int(proc_maps.label_to_id[filtro_proc])

    tipo_val = None if filtro_tipo == "(Todos)" else filtro_tipo
    status_val = None if filtro_status == "(Todos)" else filtro_status
    q_val = (filtro_q or "").strip() or None

    ags = _load_agendamentos_for_list(
        owner_user_id,
        processo_id=processo_id,
        tipo=tipo_val,
        status=status_val,
        q=q_val,
        order=order_val,
        limit=int(filtro_limit),
    )

    if ags:
        df = pd.DataFrame(
            [
                {
                    "id": a.id,
                    "processo": proc_maps.label_by_id.get(
                        a.processo_id, f"[{a.processo_id}]"
                    ),
                    "status": a.status,
                    "tipo": a.tipo,
                    "inicio": _format_dt(a.inicio),
                    "fim": _format_dt(a.fim),
                    "local": a.local or "",
                    "descricao": a.descricao or "",
                }
                for a in ags
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum agendamento encontrado com os filtros atuais.")

    st.divider()

    # =========================================================
    # EDITAR / EXCLUIR (seletor independente da lista)
    # =========================================================
    st.subheader("✏️ Editar / 🗑️ Excluir")

    ags_for_edit = _load_agendamentos_for_edit_picker(owner_user_id, limit=500)
    if not ags_for_edit:
        st.info("Nenhum agendamento cadastrado.")
        return

    edit_labels = [
        _build_agendamento_label(a, proc_maps.label_by_id) for a in ags_for_edit
    ]

    # seleção estável
    if "ag_edit_selected" not in st.session_state:
        st.session_state.ag_edit_selected = edit_labels[0]

    selected_label = st.selectbox(
        "Selecione um agendamento",
        options=edit_labels,
        index=(
            edit_labels.index(st.session_state.ag_edit_selected)
            if st.session_state.ag_edit_selected in edit_labels
            else 0
        ),
        key="ag_edit_picker",
    )
    st.session_state.ag_edit_selected = selected_label
    agendamento_id = _parse_agendamento_id_from_label(selected_label)

    # buscar agendamento
    with get_session() as s:
        a = AgendamentosService.get(s, owner_user_id, int(agendamento_id))
    if not a:
        st.error("Agendamento não encontrado.")
        return

    # ações rápidas sobre o selecionado
    st.caption("⚡ Ações rápidas (no agendamento selecionado)")
    cA, cB, cC = st.columns(3)
    if cA.button("✅ Marcar como Realizado", key="ag_quick_realizado"):
        try:
            with get_session() as s:
                AgendamentosService.set_status(
                    s, owner_user_id, int(agendamento_id), "Realizado"
                )
            st.success("Agendamento marcado como Realizado.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if cB.button("⛔ Cancelar", key="ag_quick_cancelar"):
        try:
            with get_session() as s:
                AgendamentosService.set_status(
                    s, owner_user_id, int(agendamento_id), "Cancelado"
                )
            st.warning("Agendamento cancelado.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if cC.button("🔁 Reativar (Agendado)", key="ag_quick_reativar"):
        try:
            with get_session() as s:
                AgendamentosService.set_status(
                    s, owner_user_id, int(agendamento_id), "Agendado"
                )
            st.success("Agendamento reativado e alertas reabilitados (se aplicável).")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    st.divider()

    proc_atual_lbl = proc_maps.label_by_id.get(a.processo_id, proc_maps.labels[0])

    with st.form("form_agendamento_edit"):
        c1, c2, c3 = st.columns([3, 1, 1])
        proc_lbl_e = c1.selectbox(
            "Processo",
            proc_maps.labels,
            index=(
                proc_maps.labels.index(proc_atual_lbl)
                if proc_atual_lbl in proc_maps.labels
                else 0
            ),
            key="ag_edit_proc",
        )
        tipo_e = c2.selectbox(
            "Tipo",
            TIPOS,
            index=TIPOS.index(a.tipo) if a.tipo in TIPOS else 0,
            key="ag_edit_tipo",
        )
        status_e = c3.selectbox(
            "Status",
            STATUS,
            index=STATUS.index(a.status) if a.status in STATUS else 0,
            key="ag_edit_status",
        )

        c4, c5 = st.columns(2)
        d_ini_e = c4.date_input(
            "Data início", value=a.inicio.date(), key="ag_edit_dini"
        )
        h_ini_e = c5.time_input(
            "Hora início",
            value=a.inicio.time().replace(second=0, microsecond=0),
            key="ag_edit_hini",
        )

        fim_dt = a.fim
        d_fim_default = fim_dt.date() if fim_dt else a.inicio.date()
        h_fim_default = (
            fim_dt.time().replace(second=0, microsecond=0)
            if fim_dt
            else a.inicio.time().replace(second=0, microsecond=0)
        )

        c6, c7 = st.columns(2)
        d_fim_e = c6.date_input("Data fim", value=d_fim_default, key="ag_edit_dfim")
        h_fim_e = c7.time_input("Hora fim", value=h_fim_default, key="ag_edit_hfim")

        local_e = st.text_input("Local", value=a.local or "", key="ag_edit_local")
        desc_e = st.text_area("Descrição", value=a.descricao or "", key="ag_edit_desc")

        cbtn1, cbtn2 = st.columns(2)
        atualizar = cbtn1.form_submit_button("Atualizar", type="primary")
        excluir = cbtn2.form_submit_button("Excluir (irreversível)")

    if atualizar:
        try:
            processo_id_e = int(proc_maps.label_to_id[proc_lbl_e])

            inicio_e = _combine_date_time(d_ini_e, h_ini_e)
            fim_e = _combine_date_time(d_fim_e, h_fim_e)
            fim_val = _sanitize_end_dt(inicio_e, fim_e)

            with get_session() as s:
                AgendamentosService.update(
                    s,
                    owner_user_id,
                    int(agendamento_id),
                    AgendamentoUpdate(
                        processo_id=processo_id_e,
                        tipo=tipo_e,
                        status=status_e,
                        inicio=inicio_e,
                        fim=fim_val,
                        local=local_e,
                        descricao=desc_e,
                    ),
                )

            st.success(
                "Agendamento atualizado. (Flags de alerta serão resetadas automaticamente pelo service quando necessário.)"
            )
            st.rerun()

        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")

    if excluir:
        try:
            with get_session() as s:
                AgendamentosService.delete(s, owner_user_id, int(agendamento_id))
            st.warning("Agendamento excluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao excluir: {e}")
