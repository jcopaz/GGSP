"""Nível 6 CAPEX — Rastreabilidade até Documento SAP (CJI3), equivalente ao
Nível 6 OPEX (nivel6_sap.py), mas pro Realizado de CAPEX de Projetos e
Obras. Só existe para Realizado — o CJI4 (Orçado) é planejamento, sem
documento/nota fiscal.

Não usa `clausula_where` de filtros.py: os filtros da sidebar do
organograma OPEX (Pacote/Centro de Custo/Coordenação/Gerência) não têm
correspondência com `e_pep_projeto`/`gerencia_obras` do CAPEX Obras (ver
capex_dados.py). Período (Ano/Trimestre/Mês) e Projeto/Elemento PEP
(`clausula_projeto_capex`, adicionado em 2026-08-11) filtram igual, porque
as colunas existem com o mesmo significado em `fact_cji3_capex_obras`.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from src.branding import render_page_banner
from src.dashboard.filtros import (
    clausula_escopo_obras,
    clausula_periodo,
    clausula_projeto_capex,
    combinar_clausulas,
    guardar_e_faixa_universo,
)
from src.dashboard.formatacao import fmt_reais, fmt_reais_abrev
from src.dashboard.capex_dados import tabelas_disponiveis


def _fmt_documento(valor) -> str:
    """"Nº documento" do CJI3 é alfanumérico (achado real: valores como
    "A00301IY00"), diferente do padrão numérico do SAP Base Analítico
    (`nivel6_sap._fmt_codigo`) — não dá pra forçar `int()` aqui. Só remove
    o ".0" de valores que vierem numéricos (célula Excel float)."""
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def render_nivel6_sap_capex(con: duckdb.DuckDBPyConnection) -> None:
    render_page_banner("🔎", "Rastreabilidade CJI3", "CJI3, no grão de lançamento — só Realizado (CJI4/Orçado é planejamento, sem documento).")
    guardar_e_faixa_universo(con, "capex_obras")  # RBAC de escopo (docs/08)

    tem_orc, tem_real = tabelas_disponiveis(con)
    if not tem_real:
        st.warning("Nenhum arquivo CJI3 (Realizado CAPEX) carregado ainda (data/raw/).")
        return

    busca = st.text_input("Buscar por projeto, documento ou texto do pedido", "", key="capex-n6-busca")

    where_periodo, params_periodo = combinar_clausulas(
        clausula_periodo(), clausula_projeto_capex(), clausula_escopo_obras()
    )
    where, params = where_periodo, list(params_periodo)
    if busca:
        where += (
            " AND (e_pep_projeto ILIKE ? OR nome_empreendimento ILIKE ? "
            "OR CAST(numero_documento AS VARCHAR) ILIKE ? OR texto_pedido ILIKE ?)"
        )
        params += [f"%{busca}%"] * 4

    # Performance (2026-10-06): esta tela mandava TODOS os lançamentos pro
    # navegador (~3 MB com a base local, mais em produção) a cada
    # interação, pra mostrar ~15 linhas visíveis. Agora as métricas saem
    # agregadas do DuckDB (exatas, sobre o recorte inteiro) e a tabela traz
    # por padrão só os maiores lançamentos — o usuário pode pedir mais.
    (n_total, valor_total, top_freq) = con.execute(
        f"""
        SELECT COUNT(*), COALESCE(SUM(valor_realizado), 0),
               MODE(e_pep_projeto) FILTER (WHERE e_pep_projeto IS NOT NULL)
        FROM fact_cji3_capex_obras WHERE 1=1{where}
        """,
        params,
    ).fetchone()

    if not n_total:
        st.info("Nenhum lançamento para os filtros selecionados.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Lançamentos", f"{n_total:,}".replace(",", "."))
    c2.metric("Valor total", fmt_reais_abrev(valor_total))
    c3.metric("Projeto mais frequente", top_freq or "—")

    _LIMITES = {"1.000 maiores": 1000, "5.000 maiores": 5000, "Todos": None}
    escolha = st.segmented_control(
        "Linhas na tabela", list(_LIMITES), default="1.000 maiores", key="capex-n6-limite",
    ) or "1.000 maiores"
    limite = _LIMITES[escolha]
    if limite and n_total > limite:
        _br = lambda n: f"{n:,}".replace(",", ".")
        st.caption(
            f"Mostrando os {_br(limite)} maiores lançamentos (por valor absoluto) de "
            f"{_br(n_total)}. Use a busca ou os filtros da barra lateral para achar "
            "um lançamento específico, ou escolha \"Todos\" (mais lento)."
        )

    with st.spinner("Carregando lançamentos..."):
        df: pd.DataFrame = con.execute(
            f"""
            SELECT data_lancamento AS "Data", numero_documento AS "Documento",
                   e_pep_projeto AS "Projeto", nome_empreendimento AS "Empreendimento",
                   gerencia_obras AS "Gerência de Obras",
                   elemento_pep AS "Elemento PEP",
                   conta_interna_id AS "Conta", conta_interna_nome AS "Descrição Conta",
                   centro_custo_parceiro AS "Centro de Custo Parceiro",
                   texto_pedido AS "Texto do Pedido",
                   valor_realizado AS "_valor"
            FROM fact_cji3_capex_obras
            WHERE 1=1{where}
            ORDER BY ABS(valor_realizado) DESC
            {f"LIMIT {int(limite)}" if limite else ""}
            """,
            params,
        ).df()

    df["Valor"] = df["_valor"].map(fmt_reais)
    df = df.drop(columns="_valor")
    df["Documento"] = df["Documento"].map(_fmt_documento)
    df["Data"] = df["Data"].dt.strftime("%d/%m/%Y").fillna("")
    for coluna in ("Empreendimento", "Gerência de Obras", "Elemento PEP", "Descrição Conta", "Centro de Custo Parceiro", "Texto do Pedido"):
        df[coluna] = df[coluna].fillna("")

    st.dataframe(
        df, hide_index=True, use_container_width=True, height=520,
        column_config={
            "Documento": st.column_config.TextColumn(width="small"),
            "Projeto": st.column_config.TextColumn(width="small"),
            "Elemento PEP": st.column_config.TextColumn(width="small"),
            "Conta": st.column_config.TextColumn(width="small"),
            "Centro de Custo Parceiro": st.column_config.TextColumn(width="small"),
            "Gerência de Obras": st.column_config.TextColumn(width="medium"),
            "Empreendimento": st.column_config.TextColumn(width="large"),
            "Descrição Conta": st.column_config.TextColumn(width="large"),
            "Texto do Pedido": st.column_config.TextColumn(width="large"),
        },
    )
