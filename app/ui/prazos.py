import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date

from sqlalchemy import select

from db.connection import get_session
from db.models import Processo
from core.prazos_service import PrazosService, PrazoCreate, PrazoUpdate
from core.utils import now_br, ensure_br, format_date_br, date_to_br_datetime
from app.ui.theme import inject_global_css


TIPOS_TRABALHO = (
    "Perito Judicial",
    "Assistente Técnico",
    "Trabalho Particular",
)

PRIORIDADES = ("Baixa", "Média", "Alta")


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


def _proc_label(p: Processo) -> str:
    tipo = (p.tipo_acao or "").strip()
    papel = (p.papel or "").strip()
    base = f"[{p.id}] {p.numero_processo}"
    if tipo:
        base += f" – {tipo}"
    if papel:
        base += f"  •  {papel}"
    return base


def _filter_text(prazo, proc) -> str:
    # Campo texto para busca (tudo minúsculo)
    return " ".join(
        [
            str(proc.numero_processo or ""),
            str(proc.tipo_acao or ""),
            str(proc.comarca or ""),
            str(proc.vara or ""),
            str(proc.contratante or ""),
            str(proc.papel or ""),
            str(prazo.evento or ""),
            str(prazo.origem or ""),
            str(prazo.referencia or ""),
            str(prazo.observacoes or ""),
        ]
    ).lower()


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


def render(owner_user_id: int):
    inject_global_css()
    st.header("⏰ Prazos")
    hoje_sp = now_br().date()

    # -------------------------
    # Processos do usuário
    # -------------------------
    processos = _load_processos(owner_user_id)

    if not processos:
        st.info("Cadastre um processo primeiro.")
        return

    proc_labels = [_proc_label(p) for p in processos]
    label_to_id = {proc_labels[i]: processos[i].id for i in range(len(processos))}
    proc_by_id = {p.id: p for p in processos}

    # -------------------------
    # Novo prazo (com origem / referência)
    # -------------------------
    with st.expander("➕ Novo prazo", expanded=True):
        with st.form("form_prazo_create", clear_on_submit=True):
            sel = st.selectbox("Processo *", proc_labels, key="prazo_create_proc")
            processo_id = int(label_to_id[sel])

            c1, c2, c3 = st.columns(3)
            evento = c1.text_input("Evento *", key="prazo_create_evento")
            data_lim = c2.date_input(
                "Data limite *", value=hoje_sp, key="prazo_create_data"
            )
            prioridade = c3.selectbox(
                "Prioridade", list(PRIORIDADES), index=1, key="prazo_create_prio"
            )

            c4, c5 = st.columns(2)
            origem = c4.selectbox(
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
                key="prazo_create_origem",
            )
            referencia = c5.text_input(
                "Referência (opcional)",
                placeholder="Ex.: fls. 389 / ID 12345 / mov. 12.1",
                key="prazo_create_ref",
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
                            origem=(origem or None),
                            referencia=(referencia.strip() or None),
                            observacoes=obs,
                        ),
                    )
                st.success("Prazo criado.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao criar prazo: {e}")

    st.divider()

    # -------------------------
    # Filtros globais (valem para todas as tabs)
    # -------------------------
    cF1, cF2, cF3 = st.columns([2, 2, 6])
    filtro_tipo = cF1.selectbox(
        "Tipo de Trabalho",
        ["(Todos)"] + list(TIPOS_TRABALHO),
        index=0,
        key="prazo_filtro_tipo_trabalho",
    )
    filtro_proc = cF2.selectbox(
        "Processo",
        ["(Todos)"] + proc_labels,
        index=0,
        key="prazo_filtro_proc_global",
    )
    busca = (
        cF3.text_input(
            "Buscar (processo, evento, origem, referência, observações)",
            value="",
            key="prazo_busca_global",
        )
        .strip()
        .lower()
    )

    tipo_val = None if filtro_tipo == "(Todos)" else filtro_tipo
    processo_id_val = (
        None if filtro_proc == "(Todos)" else int(label_to_id[filtro_proc])
    )

    # -------------------------
    # Carregar dados base (abertos e concluídos) uma vez
    # sem alterar services: usamos list_all e filtramos em Python
    # -------------------------
    with get_session() as s:
        rows_all = PrazosService.list_all(
            s, owner_user_id, only_open=False
        )  # list[(Prazo, Processo)]

    # aplica filtros globais em memória
    filtered = []
    for prazo, proc in rows_all:
        if tipo_val and (proc.papel or "").strip() != tipo_val:
            continue
        if processo_id_val and int(proc.id) != int(processo_id_val):
            continue
        if busca and busca not in _filter_text(prazo, proc):
            continue
        filtered.append((prazo, proc))

    # -------------------------
    # Tabs: atrasados, 7 dias, abertos, concluídos
    # -------------------------
    tab_atras, tab_7d, tab_abertos, tab_conc = st.tabs(
        ["🔴 Atrasados", "🟠 Vencem (7 dias)", "📋 Abertos", "✅ Concluídos"]
    )

    # Helpers para montar dataframe
    def build_df(items, include_status=True, include_dias=True):
        data = []
        for prazo, proc in items:
            dias = _dias_restantes(prazo.data_limite)
            row = {
                "prazo_id": int(prazo.id),
                "processo": f"{proc.numero_processo} – {proc.tipo_acao or 'Sem tipo de ação'}",
                "evento": prazo.evento,
                "data_limite": format_date_br(prazo.data_limite),
                "prioridade": prazo.prioridade,
                "origem": (prazo.origem or ""),
                "referência": (prazo.referencia or ""),
            }
            if include_dias:
                row["dias_restantes"] = int(dias)
            if include_status:
                row["status"] = _semaforo(dias)
            data.append(row)

        if not data:
            return None

        df = pd.DataFrame(data)
        if "dias_restantes" in df.columns:
            df = df.sort_values(by=["dias_restantes"], ascending=True)
        else:
            df = df.sort_values(by=["data_limite"], ascending=False)
        return df

    # -------------------------
    # TAB: Atrasados (abertos e dias < 0)
    # -------------------------
    with tab_atras:
        st.subheader("🔴 Prazos atrasados")
        items = []
        for prazo, proc in filtered:
            if bool(prazo.concluido):
                continue
            dias = _dias_restantes(prazo.data_limite)
            if dias < 0:
                items.append((prazo, proc))

        df = build_df(items, include_status=True, include_dias=True)
        if df is None:
            st.info("Nenhum prazo atrasado com os filtros atuais.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("⚡ Ações rápidas (Atrasados)")
            _acoes_rapidas_prazos(df)

    # -------------------------
    # TAB: Vencem em 7 dias (abertos e 0..7)
    # -------------------------
    with tab_7d:
        st.subheader("🟠 Prazos vencendo em até 7 dias")
        items = []
        for prazo, proc in filtered:
            if bool(prazo.concluido):
                continue
            dias = _dias_restantes(prazo.data_limite)
            if 0 <= dias <= 7:
                items.append((prazo, proc))

        df = build_df(items, include_status=True, include_dias=True)
        if df is None:
            st.info("Nenhum prazo vencendo em até 7 dias com os filtros atuais.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("⚡ Ações rápidas (7 dias)")
            _acoes_rapidas_prazos(df)

    # -------------------------
    # TAB: Abertos (todos)
    # -------------------------
    with tab_abertos:
        st.subheader("📋 Prazos abertos (todos)")

        c1, c2 = st.columns([2, 4])
        filtro_janela = c1.selectbox(
            "Janela",
            ["Todos", "Atrasados", "0–7 dias", "0–15 dias", "0–30 dias"],
            index=0,
            key="prazo_open_window",
        )
        ordem = c2.selectbox(
            "Ordenar",
            ["Mais urgentes primeiro", "Mais distantes primeiro"],
            index=0,
            key="prazo_open_order",
        )

        items = []
        for prazo, proc in filtered:
            if bool(prazo.concluido):
                continue
            dias = _dias_restantes(prazo.data_limite)

            if filtro_janela == "Atrasados" and not (dias < 0):
                continue
            if filtro_janela == "0–7 dias" and not (0 <= dias <= 7):
                continue
            if filtro_janela == "0–15 dias" and not (0 <= dias <= 15):
                continue
            if filtro_janela == "0–30 dias" and not (0 <= dias <= 30):
                continue

            items.append((prazo, proc))

        df = build_df(items, include_status=True, include_dias=True)
        if df is None:
            st.info("Nenhum prazo aberto com os filtros atuais.")
        else:
            df = df.sort_values(
                by=["dias_restantes"], ascending=(ordem == "Mais urgentes primeiro")
            )
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("✏️ Editar / ✅ Concluir / 🗑️ Excluir (Abertos)")
            _editar_excluir_prazo(df, owner_user_id)

    # -------------------------
    # TAB: Concluídos
    # -------------------------
    with tab_conc:
        st.subheader("✅ Prazos concluídos")

        items = [(prazo, proc) for prazo, proc in filtered if bool(prazo.concluido)]

        df = build_df(items, include_status=False, include_dias=False)
        if df is None:
            st.info("Nenhum prazo concluído com os filtros atuais.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("♻️ Reabrir / 🗑️ Excluir (Concluídos)")
            _reabrir_excluir_concluidos(df, owner_user_id)


# -------------------------
# Blocos de ação (helpers)
# -------------------------
def _acoes_rapidas_prazos(df: pd.DataFrame) -> None:
    ids = df["prazo_id"].astype(int).tolist()
    prazo_id = st.selectbox(
        "Selecione o prazo_id", ids, key=f"prazo_quick_{hash(tuple(ids))}"
    )

    c1, c2, c3 = st.columns(3)

    if c1.button("✅ Concluir", key=f"prazo_quick_done_{prazo_id}"):
        try:
            with get_session() as s:
                PrazosService.update(
                    s,
                    st.session_state.get("owner_user_id", None) or 0,
                    int(prazo_id),
                    PrazoUpdate(concluido=True),
                )
            st.success("Prazo concluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao concluir: {e}")

    if c2.button("♻️ Reabrir", key=f"prazo_quick_reopen_{prazo_id}"):
        try:
            with get_session() as s:
                PrazosService.update(
                    s,
                    st.session_state.get("owner_user_id", None) or 0,
                    int(prazo_id),
                    PrazoUpdate(concluido=False),
                )
            st.success("Prazo reaberto.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao reabrir: {e}")

    if c3.button("🗑️ Excluir", key=f"prazo_quick_del_{prazo_id}"):
        try:
            with get_session() as s:
                PrazosService.delete(
                    s, st.session_state.get("owner_user_id", None) or 0, int(prazo_id)
                )
            st.warning("Prazo excluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao excluir: {e}")


def _editar_excluir_prazo(df: pd.DataFrame, owner_user_id: int) -> None:
    ids = df["prazo_id"].astype(int).tolist()
    prazo_id = st.selectbox("Selecione o prazo_id", ids, key="prazo_open_edit_select")

    with get_session() as s:
        pz = PrazosService.get(s, owner_user_id, int(prazo_id))

    if not pz:
        st.error("Prazo não encontrado.")
        return

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
            list(PRIORIDADES),
            index=(
                list(PRIORIDADES).index(pz.prioridade)
                if pz.prioridade in PRIORIDADES
                else 1
            ),
            key=f"prazo_open_prio_{prazo_id}",
        )

        c4, c5 = st.columns(2)
        origem_e = c4.text_input(
            "Origem", value=pz.origem or "", key=f"prazo_open_origem_{prazo_id}"
        )
        referencia_e = c5.text_input(
            "Referência", value=pz.referencia or "", key=f"prazo_open_ref_{prazo_id}"
        )

        concl = st.checkbox(
            "Concluído", value=bool(pz.concluido), key=f"prazo_open_conc_{prazo_id}"
        )
        obs_e = st.text_area(
            "Observações", value=pz.observacoes or "", key=f"prazo_open_obs_{prazo_id}"
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
                        origem=(origem_e.strip() or None),
                        referencia=(referencia_e.strip() or None),
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


def _reabrir_excluir_concluidos(df: pd.DataFrame, owner_user_id: int) -> None:
    ids = df["prazo_id"].astype(int).tolist()
    prazo_id = st.selectbox("Selecione o prazo_id", ids, key="prazo_done_edit_select")

    c1, c2 = st.columns(2)

    if c1.button("♻️ Reabrir prazo", key=f"prazo_reopen_{prazo_id}"):
        try:
            with get_session() as s:
                PrazosService.update(
                    s, owner_user_id, int(prazo_id), PrazoUpdate(concluido=False)
                )
            st.success("Prazo reaberto.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao reabrir: {e}")

    if c2.button("🗑️ Excluir prazo", key=f"prazo_del_done_{prazo_id}"):
        try:
            with get_session() as s:
                PrazosService.delete(s, owner_user_id, int(prazo_id))
            st.warning("Prazo excluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao excluir: {e}")
