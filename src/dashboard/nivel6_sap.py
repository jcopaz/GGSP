"""Nível 6 — Rastreabilidade até Documento SAP: último nível, garante que
todo número é rastreável até a origem (Conceito/# Complemento da
Especificação.txt, seção "Nível 6 — SAP").

Só existe para Realizado — a Base Zero (Orçamento) é planejamento, não tem
documento/nota fiscal.

# GAP: "Usuário" do lançamento (campo pedido na spec) não está no export
# atual. O campo mais próximo é PONTA_FIRME (e-mail do responsável/ponta
# firme da GG) — mostrado como "Responsável", não como "Usuário", pra não
# sugerir que é quem de fato lançou no SAP.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from src.dashboard.filtros import clausula_periodo, clausula_where, combinar_clausulas
from src.dashboard.formatacao import fmt_reais, fmt_reais_abrev


def _fmt_codigo(valor: float | None) -> str:
    """Códigos (documento, NF, conta) vêm como DOUBLE do Excel — mostra sem
    o ".0" e sem notação científica; vazio quando não preenchido na fonte."""
    if valor is None or pd.isna(valor):
        return ""
    return str(int(valor))


def render_nivel6_sap(con: duckdb.DuckDBPyConnection) -> None:
    st.header("Nível 6 — Rastreabilidade até Documento SAP")
    st.caption(
        "Só para Realizado — a Base Zero (Orçamento) é planejamento, não "
        "tem documento/nota fiscal. 'Usuário' do lançamento não está no "
        "export atual; o campo mais próximo é o responsável (ponta firme). "
        "Pacote/Centro de Custo/Coordenação/Período usam os filtros da "
        "barra lateral — a busca abaixo é só texto livre."
    )

    busca = st.text_input("Buscar por fornecedor, documento ou NF", "")

    where, params = combinar_clausulas(
        clausula_where({
            "pacote_id": "pacote_id", "centro_custo_id": "centro_custo_id",
            "coordenacao": "coordenacao",
        }),
        clausula_periodo(),
    )
    if busca:
        where += (
            " AND (fornecedor ILIKE ? OR CAST(numero_documento AS VARCHAR) ILIKE ? "
            "OR CAST(numero_nota_fiscal AS VARCHAR) ILIKE ?)"
        )
        params += [f"%{busca}%"] * 3

    with st.spinner("Carregando lançamentos..."):
        df: pd.DataFrame = con.execute(
            f"""
            SELECT data_documento AS "Data", numero_documento AS "Documento",
                   numero_nota_fiscal AS "NF", fornecedor AS "Fornecedor",
                   pacote_id AS "Pacote", conta_razao_id AS "Conta",
                   conta_razao_nome AS "Descrição Conta",
                   centro_custo_id AS "Centro de Custo",
                   texto_item AS "Texto do Lançamento",
                   responsavel AS "Responsável",
                   valor_realizado AS "_valor"
            FROM fact_realizado_documento
            WHERE 1=1{where}
            ORDER BY ABS(valor_realizado) DESC
            """,
            params,
        ).df()

    if df.empty:
        st.info("Nenhum lançamento para os filtros selecionados.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Lançamentos", f"{len(df):,}".replace(",", "."))
    c2.metric("Valor total", fmt_reais_abrev(df["_valor"].sum()))
    fornecedor_top = df["Fornecedor"].dropna()
    c3.metric("Fornecedor mais frequente", fornecedor_top.mode().iloc[0] if not fornecedor_top.empty else "—")

    df["Valor"] = df["_valor"].map(fmt_reais)
    df = df.drop(columns="_valor")
    for coluna in ("Documento", "NF", "Conta"):
        df[coluna] = df[coluna].map(_fmt_codigo)
    df["Data"] = df["Data"].dt.strftime("%d/%m/%Y").fillna("")
    for coluna in ("Fornecedor", "Descrição Conta", "Texto do Lançamento", "Responsável"):
        df[coluna] = df[coluna].fillna("")

    st.dataframe(
        df, hide_index=True, use_container_width=True, height=520,
        column_config={
            "Documento": st.column_config.TextColumn(width="small"),
            "NF": st.column_config.TextColumn(width="small"),
            "Conta": st.column_config.TextColumn(width="small"),
            "Centro de Custo": st.column_config.TextColumn(width="small"),
            "Fornecedor": st.column_config.TextColumn(width="medium"),
            "Descrição Conta": st.column_config.TextColumn(width="large"),
            "Texto do Lançamento": st.column_config.TextColumn(width="large"),
        },
    )
