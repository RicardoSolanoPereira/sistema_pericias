# app/ui/processos.py
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st
import pandas as pd

from db.connection import get_session
from core.processos_service import ProcessosService, ProcessoCreate, ProcessoUpdate
from app.ui.theme import inject_global_css, card
from app.ui.components import page_header


ATUACAO_UI = {
    "Perícia (Juízo)": "Perito Judicial",
    "Assistência Técnica": "Assistente Técnico",
    "Particular / Outros serviços": "Trabalho Particular",
}
ATUACAO_UI_ALL = {"(Todas)": None, **ATUACAO_UI}

STATUS_VALIDOS = ("Ativo", "Concluído", "Suspenso")

CATEGORIAS_UI = [
    "Perícia",
    "Assistência Técnica",
    "Consultoria",
    "Análise documental",
    "Vistoria",
    "Topografia",
    "Avaliação imobiliária",
    "Regularização",
    "Outros",
]

ROOT_TRABALHOS = Path(r"D:\TRABALHOS")


# -------------------------
# Query params utils
# -------------------------
def _qp_get(key: str, default: str = "") -> str:
    try:
        v = st.query_params.get(key)
        if v is None:
            return default
        if isinstance(v, list):
            return v[0] if v else default
        return str(v)
    except Exception:
        return default


def _clear_qp_filters() -> None:
    for k in ("status", "atuacao", "categoria", "q"):
        try:
            st.query_params.pop(k, None)  # type: ignore[attr-defined]
        except Exception:
            try:
                del st.query_params[k]
            except Exception:
                pass


def _clear_list_state() -> None:
    for k in (
        "proc_list_status",
        "proc_list_atuacao",
        "proc_list_categoria",
        "proc_list_q",
        "proc_list_ordem",
        "proc_list_action_select",
    ):
        if k in st.session_state:
            del st.session_state[k]


# -------------------------
# Normalização / labels
# -------------------------
def _norm_tipo_trabalho(val: str | None) -> str:
    v = (val or "").strip()
    if not v:
        return "Assistente Técnico"

    v_low = v.lower()
    if v_low in ("perito", "perito judicial"):
        return "Perito Judicial"
    if v_low in ("assistente", "assistente tecnico", "assistente técnico"):
        return "Assistente Técnico"
    if v_low in (
        "particular",
        "avaliacao",
        "avaliação",
        "avaliação particular",
        "trabalho particular",
    ):
        return "Trabalho Particular"
    return v


def _atuacao_label_from_db(db_val: str | None) -> str:
    v = _norm_tipo_trabalho(db_val)
    for label, db in ATUACAO_UI.items():
        if db == v:
            return label
    return v


def _atuacao_db_from_label(label: str) -> str:
    return ATUACAO_UI.get(label, "Assistente Técnico")


def _status_badge(status: str) -> str:
    s = (status or "").strip().lower()
    if s == "ativo":
        return "🟢 Ativo"
    if s in ("concluído", "concluido"):
        return "✅ Concluído"
    if s == "suspenso":
        return "⏸ Suspenso"
    return status


def _atuacao_badge(db_val: str | None) -> str:
    v = _norm_tipo_trabalho(db_val)
    if v == "Perito Judicial":
        return "⚖️ Perícia (Juízo)"
    if v == "Assistente Técnico":
        return "🛠️ Assistência Técnica"
    if v == "Trabalho Particular":
        return "🏷️ Particular"
    return v


# -------------------------
# UX helpers
# -------------------------
def _guess_pasta_local(numero: str) -> str:
    n = (numero or "").strip()
    if not n:
        return ""
    safe = re.sub(r"[\\\\/]+", "-", n)
    safe = re.sub(r'[:*?"<>|]+', "", safe)
    safe = safe.strip()
    return rf"{ROOT_TRABALHOS}\{safe}"


def _toast(msg: str) -> None:
    try:
        st.toast(msg)  # type: ignore[attr-defined]
    except Exception:
        pass


def _pick_folder_dialog(initialdir: str | None = None) -> str | None:
    """
    Abre seletor de pasta nativo (Windows Explorer) via tkinter.
    Funciona em localhost/Windows (não em servidor headless).
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        folder = filedialog.askdirectory(
            initialdir=initialdir or str(ROOT_TRABALHOS),
            title="Escolher pasta do trabalho",
            mustexist=False,
        )
        root.destroy()
        return str(folder) if folder else None
    except Exception:
        return None


# -------------------------
# Navegação programática
# -------------------------
def _request_tab(tab: str, processo_id: int | None = None) -> None:
    if processo_id is not None:
        st.session_state["proc_edit_selected_id"] = int(processo_id)
    st.session_state["proc_nav_to"] = tab


def _apply_requested_tab() -> None:
    nav = st.session_state.pop("proc_nav_to", None)
    if nav in ("Cadastrar", "Lista", "Editar / Excluir"):
        st.session_state["proc_active_tab"] = nav


def _open_edit(processo_id: int) -> None:
    _request_tab("Editar / Excluir", processo_id=processo_id)
    st.rerun()


def _sync_from_dashboard_and_qp() -> None:
    if "proc_active_tab" not in st.session_state:
        st.session_state["proc_active_tab"] = "Lista"

    if "processos_section" in st.session_state:
        sec = st.session_state.pop("processos_section", None)
        if sec in ("Lista", "Cadastrar", "Editar / Excluir"):
            st.session_state["proc_active_tab"] = sec

    qp_status = _qp_get("status", "")
    qp_atuacao = _qp_get("atuacao", "")
    qp_categoria = _qp_get("categoria", "")
    qp_q = _qp_get("q", "")

    has_qp = bool(qp_status or qp_atuacao or qp_categoria or qp_q)
    if not has_qp:
        return

    st.session_state["proc_active_tab"] = "Lista"

    status_options = ["(Todos)"] + list(STATUS_VALIDOS)
    st.session_state["proc_list_status"] = (
        qp_status if qp_status in status_options else "(Todos)"
    )

    atuacao_options = list(ATUACAO_UI_ALL.keys())
    st.session_state["proc_list_atuacao"] = (
        qp_atuacao if qp_atuacao in atuacao_options else "(Todas)"
    )

    categoria_options = ["(Todas)"] + CATEGORIAS_UI
    st.session_state["proc_list_categoria"] = (
        qp_categoria if qp_categoria in categoria_options else "(Todas)"
    )

    st.session_state["proc_list_q"] = qp_q
    if "proc_list_ordem" not in st.session_state:
        st.session_state["proc_list_ordem"] = "Mais recentes"


# -------------------------
# Render
# -------------------------
def render(owner_user_id: int):
    inject_global_css()

    st.markdown(
        """
        <style>
          .sec-title { font-weight: 850; font-size: 1.05rem; margin: 0.1rem 0 0.35rem 0; }
          .sec-cap { color: rgba(15,23,42,0.62); font-size: 0.90rem; margin-top: -0.25rem; }
          .muted { color: rgba(49,51,63,0.65); font-size: 0.92rem; }
          .danger-note { color: rgba(220,38,38,0.85); font-size: 0.90rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    clicked_refresh = page_header(
        "Trabalhos",
        "Cadastro e gestão de atividades técnicas (judicial e particular).",
        right_button_label="Recarregar",
        right_button_key="processos_btn_recarregar_top",
        right_button_help="Recarrega a tela e os dados",
    )
    if clicked_refresh:
        st.rerun()

    _sync_from_dashboard_and_qp()
    _apply_requested_tab()

    if "proc_active_tab" not in st.session_state:
        st.session_state["proc_active_tab"] = "Lista"

    section = st.segmented_control(
        "Seção",
        options=["Cadastrar", "Lista", "Editar / Excluir"],
        key="proc_active_tab",
        label_visibility="collapsed",
    )

    # ==================================================
    # CADASTRAR
    # ==================================================
    if section == "Cadastrar":
        # CTAs pós-salvar (padrão painel: card + botões)
        if st.session_state.get("proc_last_created_id"):
            last_id = int(st.session_state["proc_last_created_id"])
            last_ref = st.session_state.get("proc_last_created_ref", "")

            with st.container(border=True):
                st.markdown("### ✅ Trabalho cadastrado")
                st.caption(
                    "Próximo passo: abrir prazos, agenda ou financeiro deste trabalho."
                )

                c1, c2, c3, c4, c5 = st.columns(
                    [1, 1, 1, 1, 1], vertical_alignment="center"
                )
                if c1.button(
                    "Editar",
                    use_container_width=True,
                    type="primary",
                    key="proc_post_edit",
                ):
                    _open_edit(last_id)

                if c2.button(
                    "Prazos", use_container_width=True, key="proc_post_prazos"
                ):
                    st.session_state["pref_processo_id"] = last_id
                    st.session_state["pref_processo_ref"] = last_ref
                    from app.ui_state import navigate

                    navigate("Prazos", state={"prazos_section": "Cadastro"})

                if c3.button(
                    "Agenda", use_container_width=True, key="proc_post_agenda"
                ):
                    st.session_state["pref_processo_id"] = last_id
                    st.session_state["pref_processo_ref"] = last_ref
                    from app.ui_state import navigate

                    navigate("Agendamentos")

                if c4.button(
                    "Financeiro", use_container_width=True, key="proc_post_fin"
                ):
                    st.session_state["pref_processo_id"] = last_id
                    st.session_state["pref_processo_ref"] = last_ref
                    from app.ui_state import navigate

                    navigate("Financeiro", state={"financeiro_section": "Lançamentos"})

                if c5.button(
                    "Cadastrar outro", use_container_width=True, key="proc_post_new"
                ):
                    st.session_state.pop("proc_last_created_id", None)
                    st.session_state.pop("proc_last_created_ref", None)
                    for k in (
                        "proc_create_numero",
                        "proc_create_atuacao",
                        "proc_create_status",
                        "proc_create_categoria",
                        "proc_create_tipo_acao",
                        "proc_create_comarca",
                        "proc_create_vara",
                        "proc_create_contratante",
                        "proc_create_pasta",
                        "proc_create_obs",
                    ):
                        st.session_state.pop(k, None)
                    st.rerun()

        # Header bloco (padrão painel)
        with st.container(border=True):
            st.markdown(
                "<div class='sec-title'>Novo trabalho</div>", unsafe_allow_html=True
            )
            st.markdown(
                "<div class='sec-cap'>Cadastre o essencial primeiro; detalhes você completa depois.</div>",
                unsafe_allow_html=True,
            )
            st.write("")

            # Picker de pasta fora do form (abre Explorer)
            st.session_state.setdefault("proc_create_pasta", "")
            cpf1, cpf2 = st.columns([1.2, 3.8], vertical_alignment="center")
            if cpf1.button("📁 Escolher pasta…", key="proc_create_pick_folder"):
                chosen = _pick_folder_dialog(initialdir=str(ROOT_TRABALHOS))
                if chosen:
                    st.session_state["proc_create_pasta"] = chosen
                    st.rerun()
                else:
                    st.warning(
                        "Não foi possível abrir o Explorer (ou nenhuma pasta foi escolhida)."
                    )
            cpf2.caption(
                "Dica: use o botão para escolher a pasta no Windows Explorer (localhost)."
            )

            with st.form("form_trabalho_create", clear_on_submit=False):
                # 1) Essencial
                with st.container(border=True):
                    st.markdown("**1) Essencial**")
                    st.caption("O mínimo para começar a operar (obrigatórios).")

                    c1, c2, c3 = st.columns(3)
                    numero = c1.text_input(
                        "Número do processo / Código interno *",
                        placeholder="0000000-00.0000.0.00.0000 ou AP-2026-001",
                        key="proc_create_numero",
                    )
                    atuacao_label = c2.selectbox(
                        "Atuação *",
                        list(ATUACAO_UI.keys()),
                        index=1,
                        key="proc_create_atuacao",
                    )
                    status = c3.selectbox(
                        "Status",
                        list(STATUS_VALIDOS),
                        index=0,
                        key="proc_create_status",
                    )

                # 2) Classificação
                with st.container(border=True):
                    st.markdown("**2) Classificação**")
                    st.caption("Ajuda a filtrar e organizar na lista.")

                    c4, c5 = st.columns([1.2, 1.8])
                    categoria = c4.selectbox(
                        "Categoria / Serviço",
                        CATEGORIAS_UI,
                        index=0,
                        key="proc_create_categoria",
                    )
                    tipo_acao = c5.text_input(
                        "Descrição / Tipo",
                        placeholder="Ex.: Ação possessória / Avaliação / Vistoria técnica...",
                        key="proc_create_tipo_acao",
                    )

                # 3) Complementos
                with st.container(border=True):
                    st.markdown("**3) Complementos**")
                    st.caption("Preencha quando quiser (não bloqueia o uso).")

                    c6, c7, c8 = st.columns(3)
                    comarca = c6.text_input("Comarca", key="proc_create_comarca")
                    vara = c7.text_input("Vara", key="proc_create_vara")
                    contratante = c8.text_input(
                        "Contratante / Cliente", key="proc_create_contratante"
                    )

                    pasta = st.text_input(
                        "Pasta local (opcional)",
                        placeholder=rf"{ROOT_TRABALHOS}\AP-2026-001",
                        key="proc_create_pasta",
                    )

                    obs = st.text_area("Observações", key="proc_create_obs", height=120)

                submitted = st.form_submit_button("Salvar", type="primary")

            if submitted:
                papel_db = _atuacao_db_from_label(atuacao_label)

                if not (numero or "").strip():
                    st.error("Informe o Número do processo / Código interno.")
                else:
                    try:
                        with get_session() as s:
                            created = ProcessosService.create(
                                s,
                                owner_user_id=owner_user_id,
                                payload=ProcessoCreate(
                                    numero_processo=numero.strip(),
                                    comarca=(comarca or "").strip(),
                                    vara=(vara or "").strip(),
                                    tipo_acao=(tipo_acao or "").strip(),
                                    contratante=(contratante or "").strip(),
                                    papel=papel_db,
                                    status=status,
                                    pasta_local=(pasta or "").strip(),
                                    categoria_servico=categoria,
                                    observacoes=(obs or "").strip(),
                                ),
                            )

                        st.session_state["proc_last_created_id"] = int(
                            getattr(created, "id", 0) or 0
                        )
                        st.session_state["proc_last_created_ref"] = numero.strip()
                        _toast("✅ Trabalho cadastrado")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {e}")

        with st.expander("Ferramentas (manutenção)", expanded=False):
            st.caption("Utilidades para padronização e migração de dados antigos.")

            cA, cB = st.columns([0.55, 0.45])
            remove_prefix = cA.checkbox(
                "Remover prefixo [Categoria: ...] das observações após migrar",
                value=True,
                key="proc_backfill_remove_prefix",
            )
            only_if_empty = cB.checkbox(
                "Migrar apenas quando categoria_servico estiver vazia",
                value=True,
                key="proc_backfill_only_if_empty",
            )

            if st.button(
                "Backfill categoria (observações → categoria_servico)",
                type="secondary",
                key="proc_backfill_btn",
            ):
                try:
                    with get_session() as s:
                        changed = ProcessosService.backfill_categoria_from_observacoes(
                            s,
                            owner_user_id=owner_user_id,
                            remove_prefix=remove_prefix,
                            only_if_empty=only_if_empty,
                        )
                    st.success(f"Backfill concluído. Registros atualizados: {changed}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro no backfill: {e}")

    # ==================================================
    # LISTA
    # ==================================================
    elif section == "Lista":
        with st.container(border=True):
            st.markdown("<div class='sec-title'>Lista</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='sec-cap'>Filtre rápido. Use as ações para operar.</div>",
                unsafe_allow_html=True,
            )

            c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.4, 1.1])
            status_options = ["(Todos)"] + list(STATUS_VALIDOS)
            filtro_status = c1.selectbox(
                "Status", status_options, key="proc_list_status"
            )

            atuacao_options = list(ATUACAO_UI_ALL.keys())
            filtro_atuacao = c2.selectbox(
                "Atuação", atuacao_options, key="proc_list_atuacao"
            )

            categoria_options = ["(Todas)"] + CATEGORIAS_UI
            filtro_categoria = c3.selectbox(
                "Categoria", categoria_options, key="proc_list_categoria"
            )

            ordem = c4.selectbox(
                "Ordenar", ["Mais recentes", "Mais antigos"], key="proc_list_ordem"
            )

            c5, c6 = st.columns([3.0, 1.0])
            filtro_q = c5.text_input(
                "Buscar",
                placeholder="nº/código, comarca, vara, cliente, descrição, observações…",
                key="proc_list_q",
            )
            if c6.button(
                "Limpar filtros", use_container_width=True, key="proc_list_clear_btn"
            ):
                _clear_qp_filters()
                _clear_list_state()
                st.rerun()

        status_val = None if filtro_status == "(Todos)" else filtro_status
        papel_val = ATUACAO_UI_ALL.get(filtro_atuacao)
        categoria_val = None if filtro_categoria == "(Todas)" else filtro_categoria
        order_desc = ordem == "Mais recentes"

        with get_session() as s:
            processos = ProcessosService.list(
                s,
                owner_user_id=owner_user_id,
                status=status_val,
                papel=papel_val,
                categoria_servico=categoria_val,
                q=filtro_q,
                order_desc=order_desc,
            )

        if not processos:
            st.info("Nenhum trabalho encontrado com os filtros atuais.")
            return

        total = len(processos)
        ativos = sum(1 for p in processos if (p.status or "").lower() == "ativo")
        concl = sum(
            1 for p in processos if (p.status or "").lower().startswith("concl")
        )
        susp = sum(1 for p in processos if (p.status or "").lower() == "suspenso")

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            card("Trabalhos", f"{total}", "nos filtros", tone="info")
        with k2:
            card(
                "Ativos",
                f"{ativos}",
                "em andamento",
                tone="success" if ativos else "neutral",
            )
        with k3:
            card("Concluídos", f"{concl}", "finalizados", tone="neutral")
        with k4:
            card(
                "Suspensos",
                f"{susp}",
                "pausados",
                tone="warning" if susp else "neutral",
            )

        df = pd.DataFrame(
            [
                {
                    "id": p.id,
                    "Referência": p.numero_processo,
                    "Atuação": _atuacao_badge(p.papel),
                    "Categoria": p.categoria_servico or "",
                    "Status": _status_badge(p.status),
                    "Cliente": p.contratante or "",
                    "Descrição": p.tipo_acao or "",
                    "Comarca": p.comarca or "",
                    "Vara": p.vara or "",
                    "Pasta": p.pasta_local or "",
                    "Obs": (p.observacoes or "")[:180],
                }
                for p in processos
            ]
        )

        with st.container(border=True):
            st.caption(f"Total: **{len(df)}**")
            st.dataframe(
                df[
                    [
                        "Referência",
                        "Atuação",
                        "Categoria",
                        "Status",
                        "Cliente",
                        "Descrição",
                        "Comarca",
                        "Vara",
                        "Pasta",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                height=420,
            )

        with st.container(border=True):
            st.markdown("**Ações rápidas**")
            cA, cB, cC, cD, cE = st.columns(
                [2.2, 0.9, 0.9, 0.9, 1.1], vertical_alignment="center"
            )

            options = [f"[{r.id}] {r.numero_processo}" for r in processos]
            sel = cA.selectbox(
                "Selecionar trabalho", options, index=0, key="proc_list_action_select"
            )
            selected_id = int(sel.split("]")[0].replace("[", "").strip())
            selected_ref = sel.split("]")[1].strip() if "]" in sel else ""

            if cB.button(
                "Editar",
                use_container_width=True,
                key="proc_list_action_edit",
                type="primary",
            ):
                _open_edit(selected_id)

            if cC.button(
                "Prazos", use_container_width=True, key="proc_list_action_prazos"
            ):
                st.session_state["pref_processo_id"] = selected_id
                st.session_state["pref_processo_ref"] = selected_ref
                from app.ui_state import navigate

                navigate("Prazos", state={"prazos_section": "Lista"})

            if cD.button(
                "Agenda", use_container_width=True, key="proc_list_action_agenda"
            ):
                st.session_state["pref_processo_id"] = selected_id
                st.session_state["pref_processo_ref"] = selected_ref
                from app.ui_state import navigate

                navigate("Agendamentos")

            if cE.button(
                "Financeiro", use_container_width=True, key="proc_list_action_fin"
            ):
                st.session_state["pref_processo_id"] = selected_id
                st.session_state["pref_processo_ref"] = selected_ref
                from app.ui_state import navigate

                navigate("Financeiro", state={"financeiro_section": "Lançamentos"})

    # ==================================================
    # EDITAR / EXCLUIR
    # ==================================================
    else:
        with st.container(border=True):
            st.markdown(
                "<div class='sec-title'>Editar / Excluir</div>", unsafe_allow_html=True
            )
            st.markdown(
                "<div class='sec-cap'>Selecione um trabalho e ajuste os campos necessários.</div>",
                unsafe_allow_html=True,
            )

            busca_editar = st.text_input(
                "Buscar (nº/código, cliente, descrição...)",
                placeholder="Ex.: 0001246, Barequeçaba, avaliação, ...",
                key="proc_edit_search",
            )

            with get_session() as s:
                processos_all = ProcessosService.list(
                    s,
                    owner_user_id=owner_user_id,
                    status=None,
                    papel=None,
                    categoria_servico=None,
                    q=(busca_editar or None),
                    order_desc=True,
                    limit=None,
                )

            if not processos_all:
                st.info("Nenhum trabalho encontrado.")
                return

            pre_selected_id = st.session_state.get("proc_edit_selected_id", None)

            options = []
            for pr in processos_all:
                ref = pr.numero_processo
                cli = (pr.contratante or "").strip()
                atu = _atuacao_badge(pr.papel)
                cat = (pr.categoria_servico or "").strip()
                label = (
                    f"[{pr.id}] {ref} — {atu}"
                    + (f" — {cat}" if cat else "")
                    + (f" — {cli}" if cli else "")
                )
                options.append((label, pr.id))

            labels = [o[0] for o in options]
            ids_map = dict(options)

            idx = 0
            if pre_selected_id is not None:
                for i, (_, pid) in enumerate(options):
                    if int(pid) == int(pre_selected_id):
                        idx = i
                        break

            selected_label = st.selectbox(
                "Selecione", labels, index=idx, key="proc_edit_select"
            )
            selected_id = int(ids_map.get(selected_label))

            with get_session() as s:
                p = ProcessosService.get(s, owner_user_id, int(selected_id))

            if not p:
                st.error("Trabalho não encontrado.")
                return

            papel_atual = _norm_tipo_trabalho(p.papel)
            atuacao_atual_label = _atuacao_label_from_db(papel_atual)

        # PADRÃO PAINEL: barra de ações acima do form
        with st.container(border=True):
            pasta_key = f"proc_edit_pasta_{selected_id}"
            st.session_state.setdefault(pasta_key, p.pasta_local or "")

            cA, cB, cC = st.columns([1.2, 1.2, 2.6], vertical_alignment="center")

            if cA.button(
                "📁 Escolher pasta…", key=f"proc_edit_pick_folder_{selected_id}"
            ):
                chosen = _pick_folder_dialog(initialdir=str(ROOT_TRABALHOS))
                if chosen:
                    st.session_state[pasta_key] = chosen
                    st.rerun()
                else:
                    st.warning(
                        "Não foi possível abrir o Explorer (ou nenhuma pasta foi escolhida)."
                    )

            if cB.button(
                "🗑️ Excluir definitivamente", key=f"proc_delete_direct_{selected_id}"
            ):
                try:
                    with get_session() as s:
                        ProcessosService.delete(s, owner_user_id, int(selected_id))
                    st.success("Trabalho excluído.")
                    st.session_state.pop("proc_edit_selected_id", None)
                    st.session_state.pop("proc_edit_select", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")

            cC.markdown(
                "<div class='danger-note'>Exclusão é direta (sem confirmação).</div>",
                unsafe_allow_html=True,
            )

        # Form de edição (somente salvar aqui)
        with st.form(f"form_trabalho_edit_{selected_id}"):
            c1, c2, c3 = st.columns(3)
            numero_e = c1.text_input(
                "Número / Código interno *",
                value=p.numero_processo,
                key=f"proc_edit_numero_{selected_id}",
            )
            comarca_e = c2.text_input(
                "Comarca", value=p.comarca or "", key=f"proc_edit_comarca_{selected_id}"
            )
            vara_e = c3.text_input(
                "Vara", value=p.vara or "", key=f"proc_edit_vara_{selected_id}"
            )

            c4, c5, c6 = st.columns(3)
            tipo_acao_e = c4.text_input(
                "Descrição / Tipo",
                value=p.tipo_acao or "",
                key=f"proc_edit_tipo_acao_{selected_id}",
            )
            contratante_e = c5.text_input(
                "Contratante / Cliente",
                value=p.contratante or "",
                key=f"proc_edit_contratante_{selected_id}",
            )
            atuacao_label_e = c6.selectbox(
                "Atuação",
                list(ATUACAO_UI.keys()),
                index=(
                    list(ATUACAO_UI.keys()).index(atuacao_atual_label)
                    if atuacao_atual_label in ATUACAO_UI
                    else 1
                ),
                key=f"proc_edit_atuacao_{selected_id}",
            )
            papel_db_e = _atuacao_db_from_label(atuacao_label_e)

            c7, c8, c9 = st.columns(3)
            categoria_e = c7.selectbox(
                "Categoria / Serviço",
                CATEGORIAS_UI,
                index=(
                    CATEGORIAS_UI.index(p.categoria_servico)
                    if p.categoria_servico in CATEGORIAS_UI
                    else 0
                ),
                key=f"proc_edit_categoria_{selected_id}",
            )
            status_e = c8.selectbox(
                "Status",
                list(STATUS_VALIDOS),
                index=(
                    list(STATUS_VALIDOS).index(p.status)
                    if p.status in STATUS_VALIDOS
                    else 0
                ),
                key=f"proc_edit_status_{selected_id}",
            )

            # IMPORTANTE: sem value= aqui (evita warning com session_state)
            pasta_e = c9.text_input("Pasta local", key=pasta_key)

            obs_e = st.text_area(
                "Observações",
                value=p.observacoes or "",
                key=f"proc_edit_obs_{selected_id}",
                height=120,
            )

            atualizar = st.form_submit_button("Salvar alterações", type="primary")

        if atualizar:
            if not (numero_e or "").strip():
                st.error("Número / Código interno não pode ficar vazio.")
            else:
                try:
                    with get_session() as s:
                        ProcessosService.update(
                            s,
                            owner_user_id,
                            int(selected_id),
                            ProcessoUpdate(
                                numero_processo=(numero_e or "").strip(),
                                comarca=(comarca_e or "").strip(),
                                vara=(vara_e or "").strip(),
                                tipo_acao=(tipo_acao_e or "").strip(),
                                contratante=(contratante_e or "").strip(),
                                papel=papel_db_e,
                                status=status_e,
                                pasta_local=(pasta_e or "").strip(),
                                categoria_servico=categoria_e,
                                observacoes=(obs_e or "").strip(),
                            ),
                        )
                    _toast("✅ Trabalho atualizado")
                    st.success("Trabalho atualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao atualizar: {e}")
