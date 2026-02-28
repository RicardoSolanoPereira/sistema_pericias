import streamlit as st
import pandas as pd
from datetime import datetime, date, time

from sqlalchemy import select

from db.connection import get_session
from db.models import Processo
from core.financeiro_service import (
    FinanceiroService,
    LancamentoCreate,
    LancamentoUpdate,
)


# -------------------------
# Helpers
# -------------------------
def _proc_label(p: Processo) -> str:
    tipo = (p.tipo_acao or "").strip()
    if tipo:
        return f"[{p.id}] {p.numero_processo} – {tipo}"
    return f"[{p.id}] {p.numero_processo}"


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dt_ini_from_date(d: date | None) -> datetime | None:
    if not d:
        return None
    return datetime(d.year, d.month, d.day, 0, 0, 0)


def _dt_fim_from_date(d: date | None) -> datetime | None:
    if not d:
        return None
    return datetime(d.year, d.month, d.day, 23, 59, 59)


def _lanc_label(l, proc_label_by_id: dict[int, str]) -> str:
    proc = proc_label_by_id.get(l.processo_id, f"[{l.processo_id}]")
    dt = l.data_lancamento.strftime("%d/%m/%Y")
    tipo = (l.tipo or "").strip()
    cat = (l.categoria or "").strip()
    val = _brl(float(l.valor))
    # ex.: 28/02/2026 | Receita | R$ 1.500,00 | [10] 000... | Honorários
    return f"{dt} | {tipo} | {val} | {proc} | {cat}"


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


def _section_filters(proc_labels: list[str], proc_label_to_id: dict[str, int]):
    with st.expander("🔎 Filtros (período e processo)", expanded=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        visao = c1.selectbox(
            "Processo", ["(Todos)"] + proc_labels, index=0, key="fin_visao_proc"
        )

        dt_ini_d = c2.date_input("De", value=None, key="fin_dt_ini")
        dt_fim_d = c3.date_input("Até", value=None, key="fin_dt_fim")

        processo_id_visao = None if visao == "(Todos)" else int(proc_label_to_id[visao])

        dt_ini = _dt_ini_from_date(dt_ini_d) if isinstance(dt_ini_d, date) else None
        dt_fim = _dt_fim_from_date(dt_fim_d) if isinstance(dt_fim_d, date) else None

        if dt_ini and dt_fim and dt_ini > dt_fim:
            st.error(
                "O período está inválido: **'De'** não pode ser maior que **'Até'**."
            )
            # mantém mesmo assim, mas evita efeitos colaterais
            dt_ini, dt_fim = None, None

    return processo_id_visao, dt_ini, dt_fim


def _section_totals(
    owner_user_id: int,
    processo_id_visao: int | None,
    dt_ini: datetime | None,
    dt_fim: datetime | None,
):
    with get_session() as s:
        tot = FinanceiroService.totals(
            s,
            owner_user_id=owner_user_id,
            processo_id=processo_id_visao,
            dt_ini=dt_ini,
            dt_fim=dt_fim,
        )

    st.subheader("📌 Totais (com filtros)")
    cA, cB, cC = st.columns(3)
    cA.metric("Receitas", _brl(tot["receitas"]))
    cB.metric("Despesas", _brl(tot["despesas"]))
    cC.metric("Saldo", _brl(tot["saldo"]))


def _section_create(
    owner_user_id: int, proc_labels: list[str], proc_label_to_id: dict[str, int]
):
    with st.expander("➕ Novo lançamento", expanded=False):
        with st.form("form_fin_create", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            proc_lbl = c1.selectbox("Processo *", proc_labels, key="fin_create_proc")
            tipo = c2.selectbox("Tipo *", ["Receita", "Despesa"], key="fin_create_tipo")
            d = c3.date_input("Data *", value=date.today(), key="fin_create_data")

            c4, c5 = st.columns([2, 1])
            categoria = c4.text_input(
                "Categoria",
                placeholder="Honorários / Custas / Deslocamento...",
                key="fin_create_cat",
            )
            valor = c5.number_input(
                "Valor (R$) *",
                min_value=0.0,
                step=50.0,
                value=0.0,
                key="fin_create_valor",
            )

            descricao = st.text_area("Descrição", key="fin_create_desc")
            submitted = st.form_submit_button("Salvar lançamento", type="primary")

        if not submitted:
            return

        # validações
        if float(valor) <= 0:
            st.error("Informe um **valor maior que zero**.")
            return

        try:
            processo_id = int(proc_label_to_id[proc_lbl])
            # padrão: meio-dia (evita problemas de timezone/horário em relatórios)
            dt = datetime(d.year, d.month, d.day, 12, 0, 0)

            payload = LancamentoCreate(
                processo_id=processo_id,
                data_lancamento=dt,
                tipo=tipo,
                categoria=(categoria or "").strip() or None,
                descricao=(descricao or "").strip() or None,
                valor=float(valor),
            )

            with get_session() as s:
                FinanceiroService.create(
                    s, owner_user_id=owner_user_id, payload=payload
                )

            st.success("Lançamento criado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao criar lançamento: {e}")


def _list_rows(
    owner_user_id: int,
    processo_id_visao: int | None,
    dt_ini: datetime | None,
    dt_fim: datetime | None,
    tipo_val: str | None,
    q: str | None,
    limit: int,
):
    with get_session() as s:
        return FinanceiroService.list(
            s,
            owner_user_id=owner_user_id,
            processo_id=processo_id_visao,
            tipo=tipo_val,
            q=q,
            dt_ini=dt_ini,
            dt_fim=dt_fim,
            limit=limit,
        )


def _rows_to_df(rows, proc_label_by_id: dict[int, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": l.id,
                "processo": proc_label_by_id.get(l.processo_id, f"[{l.processo_id}]"),
                "data": l.data_lancamento.strftime("%d/%m/%Y"),
                "tipo": l.tipo,
                "categoria": l.categoria or "",
                "descricao": l.descricao or "",
                "valor": float(l.valor),
            }
            for l in rows
        ]
    )


def _section_lancamentos(
    owner_user_id: int,
    processo_id_visao,
    dt_ini,
    dt_fim,
    proc_labels,
    proc_label_to_id,
    proc_label_by_id,
):
    st.subheader("📋 Lançamentos")

    cF1, cF2, cF3 = st.columns([2, 3, 1])
    filtro_tipo = cF1.selectbox(
        "Tipo", ["(Todos)", "Receita", "Despesa"], index=0, key="fin_list_tipo"
    )
    filtro_q = cF2.text_input(
        "Buscar (categoria/descrição)", value="", key="fin_list_q"
    )
    filtro_limit = cF3.selectbox(
        "Limite", [100, 200, 300, 500], index=1, key="fin_list_limit"
    )

    tipo_val = None if filtro_tipo == "(Todos)" else filtro_tipo

    rows = _list_rows(
        owner_user_id=owner_user_id,
        processo_id_visao=processo_id_visao,
        dt_ini=dt_ini,
        dt_fim=dt_fim,
        tipo_val=tipo_val,
        q=(filtro_q or None),
        limit=int(filtro_limit),
    )

    if not rows:
        st.info("Nenhum lançamento cadastrado para os filtros atuais.")
        return

    df = _rows_to_df(rows, proc_label_by_id)

    df_display = df.copy()
    df_display["valor"] = df_display["valor"].apply(_brl)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.divider()

    # ---- Editar / Excluir com label amigável
    st.subheader("✏️ Editar / 🗑️ Excluir")

    options = {_lanc_label(l, proc_label_by_id): l.id for l in rows}
    sel_label = st.selectbox(
        "Selecione o lançamento", list(options.keys()), key="fin_edit_select"
    )
    lanc_id = int(options[sel_label])

    with get_session() as s:
        l = FinanceiroService.get(s, owner_user_id, lanc_id)

    if not l:
        st.error("Lançamento não encontrado.")
        return

    proc_atual_lbl = proc_label_by_id.get(l.processo_id, proc_labels[0])

    with st.form(f"form_fin_edit_{lanc_id}"):
        c1, c2, c3 = st.columns([3, 1, 1])

        proc_lbl_e = c1.selectbox(
            "Processo",
            proc_labels,
            index=(
                proc_labels.index(proc_atual_lbl)
                if proc_atual_lbl in proc_labels
                else 0
            ),
            key=f"fin_edit_proc_{lanc_id}",
        )

        tipo_e = c2.selectbox(
            "Tipo",
            ["Receita", "Despesa"],
            index=0 if l.tipo == "Receita" else 1,
            key=f"fin_edit_tipo_{lanc_id}",
        )

        d_e = c3.date_input(
            "Data", value=l.data_lancamento.date(), key=f"fin_edit_data_{lanc_id}"
        )

        c4, c5 = st.columns([2, 1])
        cat_e = c4.text_input(
            "Categoria", value=l.categoria or "", key=f"fin_edit_cat_{lanc_id}"
        )
        valor_e = c5.number_input(
            "Valor (R$) *",
            min_value=0.0,
            step=50.0,
            value=float(l.valor),
            key=f"fin_edit_valor_{lanc_id}",
        )

        desc_e = st.text_area(
            "Descrição", value=l.descricao or "", key=f"fin_edit_desc_{lanc_id}"
        )

        cbtn1, cbtn2 = st.columns(2)
        atualizar = cbtn1.form_submit_button("Salvar alterações", type="primary")
        excluir = cbtn2.form_submit_button("Excluir")

    if atualizar:
        if float(valor_e) <= 0:
            st.error("Informe um **valor maior que zero**.")
            return

        try:
            processo_id_e = int(proc_label_to_id[proc_lbl_e])
            dt_e = datetime(d_e.year, d_e.month, d_e.day, 12, 0, 0)

            payload = LancamentoUpdate(
                processo_id=processo_id_e,
                data_lancamento=dt_e,
                tipo=tipo_e,
                categoria=(cat_e or "").strip() or None,
                descricao=(desc_e or "").strip() or None,
                valor=float(valor_e),
            )

            with get_session() as s:
                FinanceiroService.update(s, owner_user_id, lanc_id, payload)

            st.success("Lançamento atualizado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")

    if excluir:
        with st.container(border=True):
            st.warning("⚠️ Exclusão irreversível.")
            confirm = st.checkbox(
                "Confirmo que desejo excluir este lançamento.",
                key=f"fin_del_confirm_{lanc_id}",
            )
            if st.button(
                "Confirmar exclusão",
                type="primary",
                disabled=not confirm,
                key=f"fin_del_btn_{lanc_id}",
            ):
                try:
                    with get_session() as s:
                        FinanceiroService.delete(s, owner_user_id, lanc_id)
                    st.success("Lançamento excluído.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")

    st.divider()

    # ---- Exportação CSV (filtros atuais)
    st.subheader("⬇️ Exportar")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Baixar CSV (filtros atuais)",
        data=csv,
        file_name="financeiro_export.csv",
        mime="text/csv",
    )


def _section_resumo(
    owner_user_id: int,
    processo_id_visao: int | None,
    dt_ini: datetime | None,
    dt_fim: datetime | None,
    proc_label_by_id: dict[int, str],
):
    st.subheader("📊 Resumo por processo")

    if processo_id_visao:
        st.info(
            "Selecione '(Todos)' no filtro de Processo para ver o resumo por processo."
        )
        return

    with get_session() as s:
        resumo = FinanceiroService.resumo_por_processo(
            s, owner_user_id=owner_user_id, dt_ini=dt_ini, dt_fim=dt_fim
        )

    if not resumo:
        st.info("Sem dados para os filtros atuais.")
        return

    df_res = pd.DataFrame(
        [
            {
                "processo": proc_label_by_id.get(
                    x["processo_id"], f"[{x['processo_id']}]"
                ),
                "receitas": _brl(x["receitas"]),
                "despesas": _brl(x["despesas"]),
                "saldo": _brl(x["saldo"]),
            }
            for x in resumo
        ]
    )
    st.dataframe(df_res, use_container_width=True, hide_index=True)


def _section_categorias(
    owner_user_id: int,
    processo_id_visao: int | None,
    dt_ini: datetime | None,
    dt_fim: datetime | None,
):
    st.subheader("🏷️ Resumo por categoria")

    with get_session() as s:
        cats = FinanceiroService.resumo_por_categoria(
            s,
            owner_user_id=owner_user_id,
            processo_id=processo_id_visao,
            dt_ini=dt_ini,
            dt_fim=dt_fim,
        )

    if not cats:
        st.info("Sem dados para os filtros atuais.")
        return

    df_cat = pd.DataFrame(
        [
            {"categoria": x["categoria"], "tipo": x["tipo"], "total": _brl(x["total"])}
            for x in cats
        ]
    )
    st.dataframe(df_cat, use_container_width=True, hide_index=True)


def _section_mensal(
    owner_user_id: int,
    processo_id_visao: int | None,
    dt_ini: datetime | None,
    dt_fim: datetime | None,
):
    st.subheader("🗓️ Resumo mensal")

    with get_session() as s:
        mens = FinanceiroService.resumo_mensal(
            s,
            owner_user_id=owner_user_id,
            processo_id=processo_id_visao,
            dt_ini=dt_ini,
            dt_fim=dt_fim,
        )

    if not mens:
        st.info("Sem dados para os filtros atuais.")
        return

    df_m = pd.DataFrame(mens)
    df_m_display = df_m.copy()
    df_m_display["receitas"] = df_m_display["receitas"].apply(_brl)
    df_m_display["despesas"] = df_m_display["despesas"].apply(_brl)
    df_m_display["saldo"] = df_m_display["saldo"].apply(_brl)

    st.dataframe(df_m_display, use_container_width=True, hide_index=True)

    st.caption("Gráfico (saldo por mês)")
    st.line_chart(df_m.set_index("mes")[["saldo"]])


def render(owner_user_id: int):
    st.header("💰 Financeiro")

    processos, proc_labels, proc_label_to_id, proc_label_by_id = _load_processos(
        owner_user_id
    )

    if not processos:
        st.info("Cadastre um processo primeiro para registrar lançamentos financeiros.")
        return

    processo_id_visao, dt_ini, dt_fim = _section_filters(proc_labels, proc_label_to_id)

    _section_totals(owner_user_id, processo_id_visao, dt_ini, dt_fim)

    st.divider()

    _section_create(owner_user_id, proc_labels, proc_label_to_id)

    # Navegação interna
    st.session_state.setdefault("financeiro_section", "Lançamentos")
    section = st.radio(
        "Seção",
        ["Lançamentos", "Resumo", "Categorias", "Mensal"],
        horizontal=True,
        label_visibility="collapsed",
        key="financeiro_section",
    )

    st.divider()

    if section == "Lançamentos":
        _section_lancamentos(
            owner_user_id,
            processo_id_visao,
            dt_ini,
            dt_fim,
            proc_labels,
            proc_label_to_id,
            proc_label_by_id,
        )
    elif section == "Resumo":
        _section_resumo(
            owner_user_id, processo_id_visao, dt_ini, dt_fim, proc_label_by_id
        )
    elif section == "Categorias":
        _section_categorias(owner_user_id, processo_id_visao, dt_ini, dt_fim)
    else:
        _section_mensal(owner_user_id, processo_id_visao, dt_ini, dt_fim)
