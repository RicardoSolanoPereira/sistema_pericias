# app/ui/prazos.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

from sqlalchemy import select

from db.connection import get_session
from db.models import Processo
from core.prazos_service import PrazosService, PrazoCreate, PrazoUpdate
from core.utils import now_br, ensure_br, format_date_br, date_to_br_datetime
from app.ui.theme import inject_global_css, card
from app.ui.components import page_header
from core.calendario_service import CalendarioService, RegrasCalendario


# ============================================================
# CONFIG
# ============================================================
DEBUG_PRAZOS = False  # True => mostra debug


# ============================================================
# CONSTANTES
# ============================================================
TIPOS_TRABALHO = (
    "Perito Judicial",
    "Assistente Técnico",
    "Trabalho Particular",
)

PRIORIDADES = ("Baixa", "Média", "Alta")

KEY_OWNER = "owner_user_id"

# ---- Navegação/Seções ----
KEY_ACTIVE_TAB = "pz_active_tab"  # "Cadastrar" | "Lista" | "Editar / Excluir"
KEY_NAV_TO = "pz_nav_to"

# ---- Lista (sub-abas) ----
KEY_LIST_ACTIVE = (
    "pz_list_active"  # "Abertos" | "Atrasados" | "Vencem (7 dias)" | "Concluídos"
)
KEY_LIST_NAV_TO = "pz_list_nav_to"

# ---- Cadastro ----
KEY_C_PROC = "pz_create_proc"
KEY_C_MODE = "pz_create_mode"
KEY_C_BASE = "pz_create_base"
KEY_C_DIAS = "pz_create_dias"
KEY_C_USAR_TJSP = "pz_create_usar_tjsp"
KEY_C_LOCAL = "pz_create_local"
KEY_C_DATA_LIM = "pz_create_data_lim"
KEY_C_AUDIT = "pz_create_audit"
KEY_C_EVENTO = "pz_create_evento"
KEY_C_PRIO = "pz_create_prio"
KEY_C_ORIGEM = "pz_create_origem"
KEY_C_REF = "pz_create_ref"
KEY_C_OBS = "pz_create_obs"

# ---- Filtros ----
KEY_FILTER_TIPO = "pz_filter_tipo_trabalho"
KEY_FILTER_PROC = "pz_filter_proc_global"
KEY_FILTER_BUSCA = "pz_filter_busca_global"

# ---- Lista/Abertos ----
KEY_OPEN_WINDOW = "pz_open_window"
KEY_OPEN_ORDER = "pz_open_order"


# ============================================================
# TIPOS AUXILIARES
# ============================================================
@dataclass(frozen=True)
class PrazoRow:
    prazo_id: int
    processo_id: int
    processo_numero: str
    processo_tipo_acao: str | None
    processo_comarca: str | None
    processo_vara: str | None
    processo_contratante: str | None
    processo_papel: str | None

    evento: str
    data_limite: Any  # datetime|date|str
    prioridade: str
    concluido: bool
    origem: str | None
    referencia: str | None
    observacoes: str | None


# ============================================================
# NAVEGAÇÃO SEGURA
# ============================================================
def _request_tab(tab: str) -> None:
    st.session_state[KEY_NAV_TO] = tab


def _apply_requested_tab() -> None:
    # compat com navigate("Prazos", state={"prazos_section": ...})
    legacy = st.session_state.pop("prazos_section", None)
    if legacy in ("Cadastrar", "Lista", "Editar / Excluir"):
        st.session_state[KEY_ACTIVE_TAB] = legacy

    nav = st.session_state.pop(KEY_NAV_TO, None)
    if nav in ("Cadastrar", "Lista", "Editar / Excluir"):
        st.session_state[KEY_ACTIVE_TAB] = nav

    st.session_state.setdefault(KEY_ACTIVE_TAB, "Cadastrar")


def _request_list_tab(tab: str) -> None:
    st.session_state[KEY_LIST_NAV_TO] = tab


def _apply_requested_list_tab() -> None:
    nav = st.session_state.pop(KEY_LIST_NAV_TO, None)
    if nav in ("Abertos", "Atrasados", "Vencem (7 dias)", "Concluídos"):
        st.session_state[KEY_LIST_ACTIVE] = nav
    st.session_state.setdefault(KEY_LIST_ACTIVE, "Abertos")


# ============================================================
# UI HELPERS (estilo painel)
# ============================================================
def _inject_segmented_radio_css() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stRadio"] > div { flex-direction: row !important; gap: 8px !important; }
        div[data-testid="stRadio"] label {
            border: 1px solid rgba(49, 51, 63, 0.2);
            padding: 6px 12px;
            border-radius: 8px;
            background: white;
            margin: 0 !important;
        }
        div[data-testid="stRadio"] label > div:first-child { display: none !important; }
        div[data-testid="stRadio"] label span { font-size: 12px; }
        div[data-testid="stRadio"] input:checked + div {
            background: rgba(17, 25, 40, 0.06) !important;
            border-radius: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _section_tabs(key: str) -> str:
    options = ["Cadastrar", "Lista", "Editar / Excluir"]
    if hasattr(st, "segmented_control"):
        return st.segmented_control(
            "Seção", options, key=key, label_visibility="collapsed"
        )
    _inject_segmented_radio_css()
    return st.radio(
        "Seção", options, horizontal=True, label_visibility="collapsed", key=key
    )


def _list_tabs_selector() -> str:
    labels = ["📋 Abertos", "🔴 Atrasados", "🟠 Vencem (7 dias)", "✅ Concluídos"]
    label_to_value = {
        "📋 Abertos": "Abertos",
        "🔴 Atrasados": "Atrasados",
        "🟠 Vencem (7 dias)": "Vencem (7 dias)",
        "✅ Concluídos": "Concluídos",
    }
    value_to_label = {v: k for k, v in label_to_value.items()}

    current_value = st.session_state.get(KEY_LIST_ACTIVE, "Abertos")
    default_label = value_to_label.get(current_value, "📋 Abertos")
    st.session_state.setdefault("pz_list_selector", default_label)

    if hasattr(st, "segmented_control"):
        chosen_label = st.segmented_control(
            "Visão", labels, key="pz_list_selector", label_visibility="collapsed"
        )
    else:
        _inject_segmented_radio_css()
        chosen_label = st.radio(
            "Visão",
            labels,
            horizontal=True,
            key="pz_list_selector",
            label_visibility="collapsed",
            index=labels.index(st.session_state.get("pz_list_selector", default_label)),
        )

    chosen_value = label_to_value.get(chosen_label, "Abertos")
    st.session_state[KEY_LIST_ACTIVE] = chosen_value
    return chosen_value


# ============================================================
# HELPERS
# ============================================================
def _norm(s: str | None) -> str | None:
    if not s:
        return None
    v = s.strip()
    return v or None


def _dias_restantes(dt_like: Any) -> int:
    dt_br = ensure_br(dt_like)
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


def _proc_label(p: Processo) -> str:
    tipo = (p.tipo_acao or "").strip()
    papel = (p.papel or "").strip()
    base = f"[{p.id}] {p.numero_processo}"
    if tipo:
        base += f" – {tipo}"
    if papel:
        base += f"  •  {papel}"
    return base


def _filter_text(row: PrazoRow) -> str:
    parts = [
        row.processo_numero or "",
        row.processo_tipo_acao or "",
        row.processo_comarca or "",
        row.processo_vara or "",
        row.processo_contratante or "",
        row.processo_papel or "",
        row.evento or "",
        row.origem or "",
        row.referencia or "",
        row.observacoes or "",
    ]
    return " ".join(str(x) for x in parts).lower()


def _load_processos(owner_user_id: int) -> list[Processo]:
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


def _rows_to_dataclass(rows_all: Iterable[tuple[Any, Any]]) -> list[PrazoRow]:
    out: list[PrazoRow] = []
    for prazo, proc in rows_all:
        if proc is None or prazo is None:
            continue
        out.append(
            PrazoRow(
                prazo_id=int(prazo.id),
                processo_id=int(proc.id),
                processo_numero=str(proc.numero_processo or ""),
                processo_tipo_acao=proc.tipo_acao,
                processo_comarca=proc.comarca,
                processo_vara=proc.vara,
                processo_contratante=proc.contratante,
                processo_papel=proc.papel,
                evento=str(prazo.evento or ""),
                data_limite=prazo.data_limite,
                prioridade=str(prazo.prioridade or "Média"),
                concluido=bool(prazo.concluido),
                origem=getattr(prazo, "origem", None),
                referencia=getattr(prazo, "referencia", None),
                observacoes=getattr(prazo, "observacoes", None),
            )
        )
    return out


def _build_df(items: list[PrazoRow], mode: str) -> pd.DataFrame | None:
    if not items:
        return None

    data: list[dict[str, Any]] = []
    for r in items:
        dias = _dias_restantes(r.data_limite)
        dt_sort = ensure_br(r.data_limite)

        row: dict[str, Any] = {
            "prazo_id": int(r.prazo_id),
            "processo": f"{r.processo_numero} – {r.processo_tipo_acao or 'Sem tipo de ação'}",
            "evento": r.evento,
            "data_limite": format_date_br(r.data_limite),
            "prioridade": r.prioridade,
            "_data_sort": dt_sort,
        }

        if mode == "open":
            row["dias_restantes"] = int(dias)
            row["status"] = "✅ Concluído" if r.concluido else _semaforo(dias)

        data.append(row)

    return pd.DataFrame(data)


def _merge_obs_with_audit(obs: str | None, audit: str | None) -> str | None:
    base = (obs or "").strip()
    a = (audit or "").strip()
    if not base and not a:
        return None
    if base and not a:
        return base
    if not base and a:
        return f"🧮 {a}"
    return f"{base}\n🧮 {a}"


def _apply_pref_processo_defaults(
    proc_labels: list[str], label_to_id: dict[str, int]
) -> None:
    """
    Integra com o padrão do Painel/Trabalhos:
    - se vier st.session_state["pref_processo_id"] (setado em Trabalhos), pré-seleciona
      no Cadastro e no filtro da Lista sem quebrar estados já escolhidos pelo usuário.
    """
    pref_id = st.session_state.get("pref_processo_id")
    if not pref_id:
        return

    try:
        pref_id = int(pref_id)
    except Exception:
        return

    chosen_label = None
    for lbl, pid in label_to_id.items():
        if int(pid) == pref_id:
            chosen_label = lbl
            break
    if not chosen_label:
        return

    st.session_state.setdefault(KEY_C_PROC, chosen_label)
    st.session_state.setdefault(KEY_FILTER_PROC, chosen_label)


# ============================================================
# AÇÕES / EDITAR
# ============================================================
def _quick_actions(filtered_items: list[PrazoRow], owner_user_id: int) -> None:
    if not filtered_items:
        st.info("Nenhum prazo com os filtros atuais.")
        return

    options: list[str] = []
    id_by_label: dict[str, int] = {}
    for r in filtered_items:
        dias = _dias_restantes(r.data_limite)
        status = "✅ Concluído" if r.concluido else _semaforo(dias)
        label = (
            f"[{int(r.prazo_id)}] {r.processo_numero} | "
            f"{r.evento} | {format_date_br(r.data_limite)} | {status}"
        )
        options.append(label)
        id_by_label[label] = int(r.prazo_id)

    sel = st.selectbox("Selecione um prazo", options, key="pz_quick_select")
    prazo_id = id_by_label[sel]

    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Concluir", key="pz_quick_done", use_container_width=True):
        try:
            with get_session() as s:
                PrazosService.update(
                    s, owner_user_id, int(prazo_id), PrazoUpdate(concluido=True)
                )
            st.success("Prazo concluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao concluir: {e}")

    if c2.button("♻️ Reabrir", key="pz_quick_reopen", use_container_width=True):
        try:
            with get_session() as s:
                PrazosService.update(
                    s, owner_user_id, int(prazo_id), PrazoUpdate(concluido=False)
                )
            st.success("Prazo reaberto.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao reabrir: {e}")

    if c3.button("🗑️ Excluir", key="pz_quick_del", use_container_width=True):
        try:
            with get_session() as s:
                PrazosService.delete(s, owner_user_id, int(prazo_id))
            st.warning("Prazo excluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao excluir: {e}")


def _editar_excluir_prazo(items: list[PrazoRow], owner_user_id: int) -> None:
    if not items:
        st.info("Nenhum prazo disponível para editar.")
        return

    options: list[str] = []
    id_by_label: dict[str, int] = {}
    for r in items:
        dias = _dias_restantes(r.data_limite)
        status = "✅ Concluído" if r.concluido else _semaforo(dias)
        label = f"[{r.prazo_id}] {r.processo_numero} — {r.evento} — {format_date_br(r.data_limite)} — {status}"
        options.append(label)
        id_by_label[label] = int(r.prazo_id)

    sel = st.selectbox("Selecione um prazo para editar", options, key="pz_edit_select")
    prazo_id = id_by_label[sel]

    with get_session() as s:
        pz = PrazosService.get(s, owner_user_id, int(prazo_id))

    if not pz:
        st.error("Prazo não encontrado.")
        return

    try:
        pz_date = ensure_br(pz.data_limite).date()
    except Exception:
        pz_date = now_br().date()

    with st.form(f"form_prazo_edit_{prazo_id}"):
        c1, c2, c3 = st.columns(3)
        evento_e = c1.text_input("Evento *", value=str(getattr(pz, "evento", "") or ""))
        data_e = c2.date_input("Data limite *", value=pz_date)
        prio_e = c3.selectbox(
            "Prioridade",
            list(PRIORIDADES),
            index=(
                list(PRIORIDADES).index(pz.prioridade)
                if pz.prioridade in PRIORIDADES
                else 1
            ),
        )

        c4, c5 = st.columns(2)
        origem_e = c4.text_input("Origem", value=str(getattr(pz, "origem", "") or ""))
        referencia_e = c5.text_input(
            "Referência", value=str(getattr(pz, "referencia", "") or "")
        )

        concl = st.checkbox("Concluído", value=bool(getattr(pz, "concluido", False)))
        obs_e = st.text_area(
            "Observações", value=str(getattr(pz, "observacoes", "") or "")
        )

        b1, b2 = st.columns(2)
        salvar = b1.form_submit_button(
            "Salvar alterações", type="primary", use_container_width=True
        )
        excluir = b2.form_submit_button(
            "Excluir (irreversível)", use_container_width=True
        )

    if salvar:
        if not (evento_e or "").strip():
            st.error("Evento não pode ficar vazio.")
            return
        try:
            with get_session() as s:
                PrazosService.update(
                    s,
                    owner_user_id,
                    int(prazo_id),
                    PrazoUpdate(
                        evento=(evento_e or "").strip() or "—",
                        data_limite=date_to_br_datetime(data_e),
                        prioridade=prio_e,
                        concluido=concl,
                        origem=_norm(origem_e),
                        referencia=_norm(referencia_e),
                        observacoes=(obs_e or "").strip() or None,
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


# ============================================================
# RENDER
# ============================================================
def render(owner_user_id: int) -> None:
    inject_global_css()
    st.session_state[KEY_OWNER] = owner_user_id

    # Header padrão do Painel
    clicked_refresh = page_header(
        "Prazos",
        "Cadastro, filtros e controle de prazos (judicial e extrajudicial).",
        right_button_label="Recarregar",
        right_button_key="pz_btn_recarregar",
        right_button_help="Recarrega a tela e os dados",
    )
    if clicked_refresh:
        st.rerun()

    with st.expander("Ferramentas", expanded=False):
        st.caption("Utilidades (não afetam os dados).")
        if st.button(
            "Limpar cache de feriados", key="pz_btn_clear_cache", type="secondary"
        ):
            CalendarioService.clear_cache()
            st.success("Cache de feriados limpo.")
            st.rerun()

    processos = _load_processos(owner_user_id)
    if not processos:
        st.info("Cadastre um trabalho primeiro.")
        return

    proc_labels = [_proc_label(p) for p in processos]
    label_to_id = {proc_labels[i]: processos[i].id for i in range(len(processos))}
    proc_by_id = {p.id: p for p in processos}

    # Defaults estáveis
    hoje_sp = now_br().date()
    st.session_state.setdefault(KEY_C_MODE, "Manual")
    st.session_state.setdefault(KEY_C_DATA_LIM, hoje_sp)
    st.session_state.setdefault(KEY_C_AUDIT, "")
    st.session_state.setdefault(KEY_C_BASE, hoje_sp)
    st.session_state.setdefault(KEY_C_DIAS, 15)
    st.session_state.setdefault(KEY_C_USAR_TJSP, True)
    st.session_state.setdefault(KEY_C_LOCAL, True)
    st.session_state.setdefault(KEY_C_PROC, proc_labels[0] if proc_labels else "")

    _apply_pref_processo_defaults(proc_labels, label_to_id)
    _apply_requested_tab()

    with st.container(border=True):
        section = _section_tabs(KEY_ACTIVE_TAB)

    # ========================================================
    # CADASTRAR
    # ========================================================
    if section == "Cadastrar":
        with st.container(border=True):
            st.markdown("#### Novo prazo")
            st.caption("Escolha o modo e salve. O sistema calcula quando aplicável.")

            sel_proc = st.selectbox("Trabalho *", proc_labels, index=0, key=KEY_C_PROC)
            processo_id = int(label_to_id[sel_proc])
            proc = proc_by_id.get(processo_id)
            comarca_proc = (proc.comarca or "").strip() or None if proc else None

            st.divider()

            modo = st.selectbox(
                "Modo de contagem",
                ["Manual", "Dias corridos", "Dias úteis"],
                key=KEY_C_MODE,
            )

            st.divider()

            if modo == "Manual":
                st.date_input("Data limite *", key=KEY_C_DATA_LIM)
                st.session_state[KEY_C_AUDIT] = ""

            elif modo == "Dias corridos":
                c1, c2 = st.columns(2)
                base = c1.date_input("Data base", key=KEY_C_BASE)
                dias = c2.number_input("Qtd dias", min_value=1, step=1, key=KEY_C_DIAS)

                nova = base + timedelta(days=int(dias))
                st.session_state[KEY_C_DATA_LIM] = nova
                st.session_state[KEY_C_AUDIT] = "Auto: dias corridos"
                st.caption(f"🧮 Data final: {nova.strftime('%d/%m/%Y')}")

            else:
                c1, c2 = st.columns(2)
                base = c1.date_input("Data base (disponibilização DJE)", key=KEY_C_BASE)
                dias = c2.number_input(
                    "Qtd dias úteis", min_value=1, step=1, key=KEY_C_DIAS
                )

                usar_tjsp = st.checkbox(
                    "Considerar calendário TJSP (inclui CPC art. 220 automaticamente)",
                    key=KEY_C_USAR_TJSP,
                )

                incluir_municipal = st.checkbox(
                    "Incluir feriados municipais da comarca",
                    key=KEY_C_LOCAL,
                    disabled=not bool(comarca_proc),
                    help="Requer 'Comarca' preenchida no trabalho (ex.: Ilhabela).",
                )

                regras = RegrasCalendario(
                    incluir_nacional=True,
                    incluir_estadual_sp=True,
                    incluir_tjsp_geral=bool(usar_tjsp),
                    incluir_tjsp_comarca=bool(usar_tjsp),
                    incluir_municipal=bool(incluir_municipal),
                )

                aplicar_local = bool(comarca_proc)

                nova = CalendarioService.prazo_dje_tjsp(
                    disponibilizacao=base,
                    dias_uteis=int(dias),
                    comarca=comarca_proc,
                    municipio=None,
                    aplicar_local=aplicar_local,
                    regras=regras,
                )

                st.session_state[KEY_C_DATA_LIM] = nova

                if usar_tjsp:
                    if incluir_municipal and bool(comarca_proc):
                        st.session_state[KEY_C_AUDIT] = (
                            f"Auto: DJE + dias úteis (TJSP/CPC220 + municipal {comarca_proc})"
                        )
                    else:
                        st.session_state[KEY_C_AUDIT] = (
                            "Auto: DJE + dias úteis (TJSP/CPC220)"
                        )
                else:
                    if incluir_municipal and bool(comarca_proc):
                        st.session_state[KEY_C_AUDIT] = (
                            f"Auto: DJE + dias úteis (Nac/Estadual + municipal {comarca_proc})"
                        )
                    else:
                        st.session_state[KEY_C_AUDIT] = (
                            "Auto: DJE + dias úteis (Nac/Estadual)"
                        )

                st.caption(f"🧮 Data final: {nova.strftime('%d/%m/%Y')}")

                if DEBUG_PRAZOS:
                    from datetime import date as _date

                    st.markdown("### 🔎 DEBUG PRAZO")
                    st.write("comarca_proc:", repr(comarca_proc))
                    st.write("aplicar_local:", aplicar_local)
                    st.write("incluir_municipal:", bool(incluir_municipal))
                    st.write("usar_tjsp:", bool(usar_tjsp))
                    st.write("base:", base)
                    st.write("dias:", int(dias))
                    st.write("nova:", nova)

                    ini = _date(2026, 1, 15)
                    fim = _date(2026, 2, 15)
                    fer_set = CalendarioService.feriados_aplicaveis(
                        ini,
                        fim,
                        comarca=comarca_proc,
                        municipio=None,
                        aplicar_local=aplicar_local,
                        regras=regras,
                    )
                    st.write("contém 02/02/2026?:", _date(2026, 2, 2) in fer_set)
                    st.write("feriados janela:", sorted(list(fer_set)))

            st.divider()

            with st.form("form_prazo_create", clear_on_submit=True):
                cE1, cE2, cE3 = st.columns(3)
                evento = cE1.text_input("Evento *", key=KEY_C_EVENTO)
                prioridade = cE2.selectbox(
                    "Prioridade", list(PRIORIDADES), index=1, key=KEY_C_PRIO
                )
                origem = cE3.selectbox(
                    "Origem (opcional)",
                    [
                        "",
                        "e-SAJ/TJ",
                        "Diário Oficial",
                        "E-mail",
                        "Cliente/Contratante",
                        "Outro",
                    ],
                    index=0,
                    key=KEY_C_ORIGEM,
                )

                referencia = st.text_input(
                    "Referência (opcional)",
                    placeholder="Ex.: fls. 389 / ID 12345 / mov. 12.1",
                    key=KEY_C_REF,
                )
                obs = st.text_area("Observações", key=KEY_C_OBS)

                salvar = st.form_submit_button(
                    "Salvar", type="primary", use_container_width=True
                )

            if salvar:
                if not (evento or "").strip():
                    st.error("Informe o Evento.")
                else:
                    try:
                        data_final = st.session_state.get(KEY_C_DATA_LIM, hoje_sp)
                        dt_lim = date_to_br_datetime(data_final)

                        audit_txt = (st.session_state.get(KEY_C_AUDIT) or "").strip()
                        obs_final = _merge_obs_with_audit(obs, audit_txt)

                        with get_session() as s:
                            PrazosService.create(
                                s,
                                owner_user_id,
                                PrazoCreate(
                                    processo_id=int(processo_id),
                                    evento=evento.strip(),
                                    data_limite=dt_lim,
                                    prioridade=prioridade,
                                    origem=(origem or None),
                                    referencia=_norm(referencia),
                                    observacoes=obs_final,
                                ),
                            )

                        st.success("Prazo criado.")
                        _request_tab("Lista")
                        _request_list_tab("Abertos")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro ao criar prazo: {e}")

    # ========================================================
    # LISTA
    # ========================================================
    elif section == "Lista":
        _apply_requested_list_tab()

        with st.container(border=True):
            st.markdown("#### Filtros")
            cF1, cF2, cF3 = st.columns([2, 2, 6])

            filtro_tipo = cF1.selectbox(
                "Tipo de trabalho",
                ["(Todos)"] + list(TIPOS_TRABALHO),
                index=0,
                key=KEY_FILTER_TIPO,
            )
            filtro_proc = cF2.selectbox(
                "Trabalho",
                ["(Todos)"] + proc_labels,
                index=0,
                key=KEY_FILTER_PROC,
            )
            busca = (
                cF3.text_input(
                    "Buscar",
                    placeholder="processo, evento, origem, referência, observações…",
                    value="",
                    key=KEY_FILTER_BUSCA,
                )
                .strip()
                .lower()
            )

        tipo_val = None if filtro_tipo == "(Todos)" else filtro_tipo
        processo_id_val = (
            None if filtro_proc == "(Todos)" else int(label_to_id[filtro_proc])
        )

        with get_session() as s:
            rows_all = PrazosService.list_all(s, owner_user_id, status="all")

        all_rows = _rows_to_dataclass(rows_all)

        filtered: list[PrazoRow] = []
        for r in all_rows:
            papel = (r.processo_papel or "").strip()
            if tipo_val and papel != tipo_val:
                continue
            if processo_id_val and int(r.processo_id) != int(processo_id_val):
                continue
            if busca and busca not in _filter_text(r):
                continue
            filtered.append(r)

        # KPIs no padrão Painel (baseado nos filtros atuais)
        abertos = [r for r in filtered if not r.concluido]
        atrasados = [
            r
            for r in filtered
            if (not r.concluido) and (_dias_restantes(r.data_limite) < 0)
        ]
        vencem7 = [
            r
            for r in filtered
            if (not r.concluido) and (0 <= _dias_restantes(r.data_limite) <= 7)
        ]
        concluidos = [r for r in filtered if r.concluido]

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            card("Abertos", f"{len(abertos)}", "nos filtros", tone="info")
        with k2:
            card(
                "Atrasados",
                f"{len(atrasados)}",
                "urgente",
                tone="warning" if atrasados else "neutral",
            )
        with k3:
            card(
                "Vencem (7d)",
                f"{len(vencem7)}",
                "atenção",
                tone="warning" if vencem7 else "neutral",
            )
        with k4:
            card("Concluídos", f"{len(concluidos)}", "finalizados", tone="neutral")

        with st.container(border=True):
            st.markdown("#### ⚡ Ações rápidas")
            st.caption("Concluir, reabrir ou excluir rapidamente.")
            _quick_actions(filtered, owner_user_id)

        st.divider()

        chosen_view = _list_tabs_selector()

        if chosen_view == "Atrasados":
            items = [
                r
                for r in filtered
                if (not r.concluido) and (_dias_restantes(r.data_limite) < 0)
            ]
            df = _build_df(items, mode="open")
            if df is None:
                st.info("Nenhum prazo atrasado com os filtros atuais.")
            else:
                df = df.sort_values(
                    by=["dias_restantes", "_data_sort"], ascending=[True, True]
                ).drop(columns=["_data_sort"], errors="ignore")
                st.dataframe(
                    df[
                        [
                            "prazo_id",
                            "processo",
                            "evento",
                            "data_limite",
                            "dias_restantes",
                            "prioridade",
                            "status",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=340,
                )

        elif chosen_view == "Vencem (7 dias)":
            items: list[PrazoRow] = []
            for r in filtered:
                if r.concluido:
                    continue
                dias = _dias_restantes(r.data_limite)
                if 0 <= dias <= 7:
                    items.append(r)

            df = _build_df(items, mode="open")
            if df is None:
                st.info("Nenhum prazo vencendo em até 7 dias com os filtros atuais.")
            else:
                df = df.sort_values(
                    by=["dias_restantes", "_data_sort"], ascending=[True, True]
                ).drop(columns=["_data_sort"], errors="ignore")
                st.dataframe(
                    df[
                        [
                            "prazo_id",
                            "processo",
                            "evento",
                            "data_limite",
                            "dias_restantes",
                            "prioridade",
                            "status",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=340,
                )

        elif chosen_view == "Abertos":
            c1, c2 = st.columns([2, 4])
            filtro_janela = c1.selectbox(
                "Janela",
                ["Todos", "Atrasados", "0–7 dias", "0–15 dias", "0–30 dias"],
                index=0,
                key=KEY_OPEN_WINDOW,
            )
            ordem = c2.selectbox(
                "Ordenar",
                ["Mais urgentes primeiro", "Mais distantes primeiro"],
                index=0,
                key=KEY_OPEN_ORDER,
            )

            items: list[PrazoRow] = []
            for r in filtered:
                if r.concluido:
                    continue
                dias = _dias_restantes(r.data_limite)

                if filtro_janela == "Atrasados" and not (dias < 0):
                    continue
                if filtro_janela == "0–7 dias" and not (0 <= dias <= 7):
                    continue
                if filtro_janela == "0–15 dias" and not (0 <= dias <= 15):
                    continue
                if filtro_janela == "0–30 dias" and not (0 <= dias <= 30):
                    continue

                items.append(r)

            df = _build_df(items, mode="open")
            if df is None:
                st.info("Nenhum prazo aberto com os filtros atuais.")
            else:
                asc = ordem == "Mais urgentes primeiro"
                df = df.sort_values(
                    by=["dias_restantes", "_data_sort"], ascending=[asc, True]
                ).drop(columns=["_data_sort"], errors="ignore")
                st.dataframe(
                    df[
                        [
                            "prazo_id",
                            "processo",
                            "evento",
                            "data_limite",
                            "dias_restantes",
                            "prioridade",
                            "status",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )

        else:
            items = [r for r in filtered if r.concluido]
            df = _build_df(items, mode="done")
            if df is None:
                st.info("Nenhum prazo concluído com os filtros atuais.")
            else:
                df = df.sort_values(by=["_data_sort"], ascending=False).drop(
                    columns=["_data_sort"], errors="ignore"
                )
                st.dataframe(
                    df[["prazo_id", "processo", "evento", "data_limite", "prioridade"]],
                    use_container_width=True,
                    hide_index=True,
                    height=360,
                )

    # ========================================================
    # EDITAR / EXCLUIR
    # ========================================================
    else:
        with st.container(border=True):
            st.markdown("#### Editar / Excluir")
            st.caption("Selecione um prazo e ajuste os campos necessários.")

            with get_session() as s:
                rows_all = PrazosService.list_all(s, owner_user_id, status="all")

            all_rows = _rows_to_dataclass(rows_all)
            _editar_excluir_prazo(all_rows, owner_user_id)
