import streamlit as st
import pandas as pd

from sqlalchemy import update

from db.connection import get_session
from db.models import Processo
from core.processos_service import ProcessosService, ProcessoCreate, ProcessoUpdate
from app.ui.theme import inject_global_css


TIPOS_TRABALHO = (
    "Perito Judicial",
    "Assistente Técnico",
    "Trabalho Particular",
)

STATUS_VALIDOS = ("Ativo", "Concluído", "Suspenso")


def _norm_tipo_trabalho(val: str | None) -> str:
    """
    Normaliza valores antigos para o padrão atual.
    """
    v = (val or "").strip()

    if not v:
        return "Assistente Técnico"

    v_low = v.lower()

    # antigos
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

    # se já veio um valor padrão correto, mantém
    if v in TIPOS_TRABALHO:
        return v

    # fallback: não perde informação, mas evita filtro quebrar
    return v


def render(owner_user_id: int):
    inject_global_css()
    st.header("🗂️ Processos")

    # -------------------------
    # Ferramentas (MVP seguro)
    # -------------------------
    with st.expander("🧰 Ferramentas", expanded=False):
        st.caption(
            "Utilidades rápidas para manter o cadastro padronizado (sem alterar o banco)."
        )
        if st.button(
            "🔧 Normalizar Tipo de Trabalho (dados antigos)", type="secondary"
        ):
            try:
                with get_session() as s:
                    # Carrega apenas id/papel para normalizar com segurança
                    rows = (
                        s.query(Processo.id, Processo.papel)
                        .filter(Processo.owner_user_id == owner_user_id)
                        .all()
                    )

                    changed = 0
                    for pid, papel in rows:
                        novo = _norm_tipo_trabalho(papel)
                        if (papel or "").strip() != novo:
                            s.execute(
                                update(Processo)
                                .where(Processo.id == int(pid))
                                .values(papel=novo)
                            )
                            changed += 1

                    s.commit()

                st.success(f"Normalização concluída. Registros atualizados: {changed}")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao normalizar: {e}")

    # -------------------------
    # Criar (Form)
    # -------------------------
    with st.expander("➕ Novo processo", expanded=True):
        with st.form("form_processo_create", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            numero = c1.text_input(
                "Número do processo / Código interno *",
                placeholder="0000000-00.0000.0.00.0000 ou AP-2026-001",
                key="proc_create_numero",
            )
            comarca = c2.text_input("Comarca", key="proc_create_comarca")
            vara = c3.text_input("Vara", key="proc_create_vara")

            c4, c5, c6 = st.columns(3)
            tipo_acao = c4.text_input("Tipo de ação", key="proc_create_tipo")
            contratante = c5.text_input(
                "Contratante/Cliente", key="proc_create_contratante"
            )
            tipo_trabalho = c6.selectbox(
                "Tipo de Trabalho *",
                list(TIPOS_TRABALHO),
                index=1,  # Assistente Técnico como padrão
                key="proc_create_papel",
            )

            c7, c8 = st.columns(2)
            status = c7.selectbox(
                "Status",
                list(STATUS_VALIDOS),
                index=0,
                key="proc_create_status",
            )
            pasta = c8.text_input(
                "Pasta local (opcional)",
                placeholder=r"D:\PROCESSOS\0001246-...",
                key="proc_create_pasta",
            )

            obs = st.text_area("Observações", key="proc_create_obs")

            submitted = st.form_submit_button("Salvar processo", type="primary")

        if submitted:
            try:
                with get_session() as s:
                    ProcessosService.create(
                        s,
                        owner_user_id=owner_user_id,
                        payload=ProcessoCreate(
                            numero_processo=numero,
                            comarca=comarca,
                            vara=vara,
                            tipo_acao=tipo_acao,
                            contratante=contratante,
                            papel=tipo_trabalho,
                            status=status,
                            pasta_local=pasta,
                            observacoes=obs,
                        ),
                    )
                st.success("Processo criado.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao criar processo: {e}")

    st.divider()

    # -------------------------
    # Listar
    # -------------------------
    st.subheader("📋 Lista")

    cF1, cF2, cF3 = st.columns([2, 2, 4])
    filtro_status = cF1.selectbox(
        "Status",
        ["(Todos)"] + list(STATUS_VALIDOS),
        index=0,
        key="proc_list_filtro_status",
    )
    filtro_tipo = cF2.selectbox(
        "Tipo de Trabalho",
        ["(Todos)"] + list(TIPOS_TRABALHO),
        index=0,
        key="proc_list_filtro_tipo",
    )
    filtro_q = cF3.text_input(
        "Buscar (nº/código, comarca, vara, contratante, tipo de ação)",
        value="",
        key="proc_list_busca",
    )

    with get_session() as s:
        status_val = None if filtro_status == "(Todos)" else filtro_status
        processos = ProcessosService.list(
            s, owner_user_id=owner_user_id, status=status_val
        )

    if not processos:
        st.info("Nenhum processo cadastrado.")
        return

    df = pd.DataFrame(
        [
            {
                "id": p.id,
                "numero_processo": p.numero_processo,
                "comarca": p.comarca or "",
                "vara": p.vara or "",
                "tipo_acao": p.tipo_acao or "",
                "contratante": p.contratante or "",
                "tipo_trabalho": _norm_tipo_trabalho(p.papel),
                "status": p.status,
                "pasta_local": p.pasta_local or "",
            }
            for p in processos
        ]
    )

    # filtro tipo (client-side: não depende do service)
    if filtro_tipo != "(Todos)":
        df = df[df["tipo_trabalho"] == filtro_tipo]

    # busca (client-side)
    q = (filtro_q or "").strip().lower()
    if q:
        mask = (
            df["numero_processo"].str.lower().str.contains(q, na=False)
            | df["comarca"].str.lower().str.contains(q, na=False)
            | df["vara"].str.lower().str.contains(q, na=False)
            | df["tipo_acao"].str.lower().str.contains(q, na=False)
            | df["contratante"].str.lower().str.contains(q, na=False)
            | df["tipo_trabalho"].str.lower().str.contains(q, na=False)
        )
        df = df[mask]

    # ordenação simples
    cO1, cO2 = st.columns([2, 8])
    ordem = cO1.selectbox(
        "Ordenar", ["Mais recentes", "Mais antigos"], index=0, key="proc_list_order"
    )
    df = df.sort_values(by="id", ascending=(ordem == "Mais antigos"))

    st.dataframe(
        df[
            [
                "id",
                "numero_processo",
                "tipo_trabalho",
                "status",
                "contratante",
                "tipo_acao",
                "comarca",
                "vara",
                "pasta_local",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # -------------------------
    # Editar/Excluir (Form)
    # -------------------------
    st.subheader("✏️ Editar / 🗑️ Excluir")

    ids = df["id"].astype(int).tolist()
    if not ids:
        st.info("Nenhum processo corresponde aos filtros atuais.")
        return

    processo_id = st.selectbox(
        "Selecione o ID do processo",
        ids,
        key="proc_edit_select_id",
    )

    with get_session() as s:
        p = ProcessosService.get(s, owner_user_id, int(processo_id))

    if not p:
        st.error("Processo não encontrado.")
        return

    papel_atual = _norm_tipo_trabalho(p.papel)

    with st.form(f"form_processo_edit_{processo_id}"):
        c1, c2, c3 = st.columns(3)
        numero_e = c1.text_input(
            "Número / Código interno",
            value=p.numero_processo,
            key=f"proc_edit_numero_{processo_id}",
        )
        comarca_e = c2.text_input(
            "Comarca",
            value=p.comarca or "",
            key=f"proc_edit_comarca_{processo_id}",
        )
        vara_e = c3.text_input(
            "Vara",
            value=p.vara or "",
            key=f"proc_edit_vara_{processo_id}",
        )

        c4, c5, c6 = st.columns(3)
        tipo_acao_e = c4.text_input(
            "Tipo de ação",
            value=p.tipo_acao or "",
            key=f"proc_edit_tipo_{processo_id}",
        )
        contratante_e = c5.text_input(
            "Contratante/Cliente",
            value=p.contratante or "",
            key=f"proc_edit_contratante_{processo_id}",
        )
        tipo_trabalho_e = c6.selectbox(
            "Tipo de Trabalho",
            list(TIPOS_TRABALHO),
            index=(
                list(TIPOS_TRABALHO).index(papel_atual)
                if papel_atual in TIPOS_TRABALHO
                else 1
            ),
            key=f"proc_edit_papel_{processo_id}",
        )

        c7, c8 = st.columns(2)
        status_e = c7.selectbox(
            "Status",
            list(STATUS_VALIDOS),
            index=(
                list(STATUS_VALIDOS).index(p.status)
                if p.status in STATUS_VALIDOS
                else 0
            ),
            key=f"proc_edit_status_{processo_id}",
        )
        pasta_e = c8.text_input(
            "Pasta local",
            value=p.pasta_local or "",
            key=f"proc_edit_pasta_{processo_id}",
        )

        obs_e = st.text_area(
            "Observações",
            value=p.observacoes or "",
            key=f"proc_edit_obs_{processo_id}",
        )

        cbtn1, cbtn2 = st.columns(2)
        atualizar = cbtn1.form_submit_button("Atualizar", type="primary")
        excluir = cbtn2.form_submit_button("Excluir (irreversível)")

    if atualizar:
        try:
            with get_session() as s:
                ProcessosService.update(
                    s,
                    owner_user_id,
                    int(processo_id),
                    ProcessoUpdate(
                        numero_processo=numero_e,
                        comarca=comarca_e,
                        vara=vara_e,
                        tipo_acao=tipo_acao_e,
                        contratante=contratante_e,
                        papel=tipo_trabalho_e,
                        status=status_e,
                        pasta_local=pasta_e,
                        observacoes=obs_e,
                    ),
                )
            st.success("Processo atualizado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")

    if excluir:
        try:
            with get_session() as s:
                ProcessosService.delete(s, owner_user_id, int(processo_id))
            st.warning("Processo excluído.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao excluir: {e}")
