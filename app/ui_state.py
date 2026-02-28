"""app/ui_state.py

Centraliza navegação e passagem de contexto entre telas.

O projeto usa um mecanismo de navegação "segura" via `nav_target` aplicado
no `app/main.py` antes do `st.sidebar.radio()` existir.

Aqui empacotamos:
- query params (ótimo para filtros em listas)
- session_state (ótimo para abrir uma seção específica: Lista/Editar etc.)
"""

from __future__ import annotations

from typing import Any

import streamlit as st


# ------------------------------------------------------------
# Política de limpeza de estado por tela (evita "estado grudado")
# ------------------------------------------------------------
_PAGE_STATE_KEYS: dict[str, set[str]] = {
    # Prazos
    "Prazos": {
        "prazos_section",
        "prazo_open_window",
        "prazo_selected_id",
        "prazos_filter_status",
        "prazos_filter_q",
    },
    # Processos
    "Processos": {
        "processos_section",
        "processo_selected_id",
        "processos_filter_status",
        "processos_filter_q",
    },
    # Financeiro
    "Financeiro": {
        "financeiro_section",
        "financeiro_selected_id",
    },
    # Agendamentos
    "Agendamentos": {
        "agendamentos_section",
        "agendamento_selected_id",
    },
}


def _set_query_params(qp: dict[str, Any] | None) -> None:
    """Atualiza query params de forma robusta.

    Regras:
    - None / "" remove o parâmetro
    - list/tuple vira múltiplos valores (útil para multiselect no futuro)
    - tudo é convertido para str
    """
    if not qp:
        return

    for k, v in qp.items():
        if v is None or v == "":
            # remoção segura (compatível com versões que não suportam `del`)
            try:
                st.query_params.pop(k, None)  # type: ignore[attr-defined]
            except Exception:
                try:
                    del st.query_params[k]
                except Exception:
                    pass
            continue

        if isinstance(v, (list, tuple)):
            st.query_params[k] = [str(x) for x in v if x is not None and x != ""]
        else:
            st.query_params[k] = str(v)


def _set_state(state: dict[str, Any] | None) -> None:
    if not state:
        return
    for k, v in state.items():
        st.session_state[k] = v


def _clear_page_state(menu_key: str, incoming_state: dict[str, Any] | None) -> None:
    """Remove chaves de estado da tela destino, exceto as que vierem explicitamente em `incoming_state`.

    Isso evita herdar filtros/abas de uma visita anterior (ex.: prazo_open_window=Atrasados).
    """
    keys = _PAGE_STATE_KEYS.get(menu_key)
    if not keys:
        return

    incoming_state = incoming_state or {}
    for k in keys:
        # Se não veio no state atual, elimina para não "grudar"
        if k not in incoming_state:
            st.session_state.pop(k, None)


def navigate(
    menu_key: str,
    *,
    qp: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    """Navega para `menu_key` carregando parâmetros.

    Args:
        menu_key: chave do MENU (ex.: "Processos", "Prazos", "Financeiro").
        qp: query params (ex.: {"status": "Ativo"}).
        state: session_state extra (ex.: {"processos_section": "Lista"}).
    """
    # 1) Limpa o estado da tela destino (para evitar herança indevida)
    _clear_page_state(menu_key, state)

    # 2) Aplica qp/state
    _set_query_params(qp)
    _set_state(state)

    # 3) Navegação segura (main.py aplica antes do radio existir)
    st.session_state["nav_target"] = menu_key
    st.rerun()
