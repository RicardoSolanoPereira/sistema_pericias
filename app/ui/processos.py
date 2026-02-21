import streamlit as st
import pandas as pd

from db.connection import get_session
from core.processos_service import ProcessosService, ProcessoCreate, ProcessoUpdate


def render(owner_user_id: int):
    st.header("🗂️ Processos")

    # -------------------------
    # Criar (Form)
    # -------------------------
    with st.expander("➕ Novo processo", expanded=True):
        with st.form("form_processo_create", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            numero = c1.text_input(
                "Número do processo *",
                placeholder="0000000-00.0000.0.00.0000",
                key="proc_create_numero",
            )
            comarca = c2.text_input("Comarca", key="proc_create_comarca")
            vara = c3.text_input("Vara", key="proc_create_vara")

            c4, c5, c6 = st.columns(3)
            tipo_acao = c4.text_input("Tipo de ação", key="proc_create_tipo")
            contratante = c5.text_input(
                "Contratante/Cliente", key="proc_create_contratante"
            )
            papel = c6.selectbox(
                "Papel",
                ["Perito", "Assistente Técnico"],
                index=1,
                key="proc_create_papel",
            )

            c7, c8 = st.columns(2)
            status = c7.selectbox(
                "Status",
                ["Ativo", "Concluído", "Suspenso"],
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
                            papel=papel,
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
    filtro_status = st.selectbox(
        "Filtrar por status",
        ["(Todos)", "Ativo", "Concluído", "Suspenso"],
        index=0,
        key="proc_list_filtro_status",
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
                "comarca": p.comarca,
                "vara": p.vara,
                "tipo_acao": p.tipo_acao,
                "contratante": p.contratante,
                "papel": p.papel,
                "status": p.status,
                "pasta_local": p.pasta_local,
            }
            for p in processos
        ]
    )

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # -------------------------
    # Editar/Excluir (Form)
    # -------------------------
    st.subheader("✏️ Editar / 🗑️ Excluir")
    ids = df["id"].tolist()

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

    with st.form(f"form_processo_edit_{processo_id}"):
        c1, c2, c3 = st.columns(3)
        numero_e = c1.text_input(
            "Número", value=p.numero_processo, key=f"proc_edit_numero_{processo_id}"
        )
        comarca_e = c2.text_input(
            "Comarca", value=p.comarca or "", key=f"proc_edit_comarca_{processo_id}"
        )
        vara_e = c3.text_input(
            "Vara", value=p.vara or "", key=f"proc_edit_vara_{processo_id}"
        )

        c4, c5, c6 = st.columns(3)
        tipo_acao_e = c4.text_input(
            "Tipo de ação", value=p.tipo_acao or "", key=f"proc_edit_tipo_{processo_id}"
        )
        contratante_e = c5.text_input(
            "Contratante",
            value=p.contratante or "",
            key=f"proc_edit_contratante_{processo_id}",
        )
        papel_e = c6.selectbox(
            "Papel",
            ["Perito", "Assistente Técnico"],
            index=0 if p.papel == "Perito" else 1,
            key=f"proc_edit_papel_{processo_id}",
        )

        c7, c8 = st.columns(2)
        status_e = c7.selectbox(
            "Status",
            ["Ativo", "Concluído", "Suspenso"],
            index=["Ativo", "Concluído", "Suspenso"].index(p.status),
            key=f"proc_edit_status_{processo_id}",
        )
        pasta_e = c8.text_input(
            "Pasta local",
            value=p.pasta_local or "",
            key=f"proc_edit_pasta_{processo_id}",
        )

        obs_e = st.text_area(
            "Observações", value=p.observacoes or "", key=f"proc_edit_obs_{processo_id}"
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
                        papel=papel_e,
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
