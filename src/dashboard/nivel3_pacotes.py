"""Fase 5 — Nível 3 (Pacotes): ao clicar numa categoria do waterfall do
Nível 2, ranking de pacotes que compõem aquele valor, maior → menor impacto.

A soma dos pacotes bate com o valor da categoria clicada no Nível 2 —
critério de pronto da Fase 5 (ver docs/01-plano-de-build-mvp.md). Também
funciona para "Não Justificado" (categoria calculada, não registrada no
CSV de apoio): aqui o ranking é por Delta Não Explicado por pacote.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from src.branding import render_page_banner
from src.dashboard.filtros import clausula_periodo, combinar_clausulas, filtrar_periodo_df
from src.dashboard.formatacao import fmt_pacote, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.nivel2_gg import _pacotes_do_gg
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO
from src.engine.delta_calculator import calcular_delta
from src.engine.explanation_engine import (
    CATEGORIA_CALCULADA,
    calcular_explicacao,
    carregar_explicacoes,
)


def dados_ranking_pacotes(
    con: duckdb.DuckDBPyConnection,
    gg_id: str,
    categoria: str,
    caminho_explicacoes: str,
    categorias_validas: list[str],
) -> pd.DataFrame:
    pacotes = _pacotes_do_gg(con, gg_id)
    df_explicacao = carregar_explicacoes(caminho_explicacoes)
    if pacotes is not None:
        df_explicacao = df_explicacao[df_explicacao["pacote_id"].isin(pacotes)]
    # Filtro de Período (Ano/Trimestre/Mês) — adicionado em 2026-08-11,
    # mesmo motivo do Nível 2: explicacoes.csv já tem ano/mes por linha,
    # então dá pra filtrar sem quebrar o fechamento com o waterfall.
    df_explicacao = filtrar_periodo_df(df_explicacao)

    if categoria == CATEGORIA_CALCULADA:
        # OPEX só — mesmo ajuste de 2026-08-11 do waterfall (Nível 2):
        # Realizado só tem OPEX por construção (build_star_schema.py),
        # então o Orçado usado no Delta também precisa ser só OPEX, senão
        # esta soma não bate mais com `dados_waterfall_gg`. Período
        # entra nos dois lados (Orçado e Realizado), mesmo filtro do
        # waterfall.
        where_periodo, params_periodo = clausula_periodo()
        filtro_orc_opex, params_orc_opex = combinar_clausulas(
            (" AND classificacao_contabil = 'OPEX'", []),
            (where_periodo, params_periodo),
        )
        df_delta = calcular_delta(
            con, dims=["pacote_id"],
            filtro_orcado=(filtro_orc_opex, params_orc_opex),
            filtro_realizado=(where_periodo, params_periodo),
        )
        if pacotes is not None:
            df_delta = df_delta[df_delta["pacote_id"].isin(pacotes)]
        resultado = calcular_explicacao(
            df_delta, df_explicacao, dims=["pacote_id"], categorias_validas=categorias_validas
        )
        resultado = resultado.rename(columns={"delta_nao_explicado": "valor"})[["pacote_id", "valor"]]
    else:
        filtrado = df_explicacao[df_explicacao["categoria"] == categoria]
        resultado = (
            filtrado.groupby("pacote_id")["valor_explicado"]
            .sum()
            .reset_index()
            .rename(columns={"valor_explicado": "valor"})
        )

    resultado = resultado[resultado["valor"] != 0].copy()
    resultado["abs_valor"] = resultado["valor"].abs()
    return resultado.sort_values("abs_valor", ascending=False).drop(columns="abs_valor")


def _cor_valor(valor: float) -> str:
    cor = COR_ESTOURO if valor > 0 else COR_ECONOMIA if valor < 0 else "inherit"
    return f"color: {cor}; font-weight: 600"


def tabela_ranking(df_ranking: pd.DataFrame, nomes_pacote: dict[str, str]) -> pd.io.formats.style.Styler:
    """Tabela em vez de gráfico de barra — decisão de 2026-08-10 (a pedido
    do usuário): os valores variam demais de escala (um pacote em milhões,
    outro em poucos reais) pra caber num gráfico de barra linear sem que a
    maioria vire um traço ilegível. Tabela mantém todo valor legível,
    ordenado por impacto (já vem ordenado de `dados_ranking_pacotes`)."""
    tabela = pd.DataFrame({
        "Pacote": [fmt_pacote(p, nomes_pacote.get(p)) for p in df_ranking["pacote_id"]],
        "Valor": df_ranking["valor"],
    })
    return (
        tabela.style
        .map(_cor_valor, subset=["Valor"])
        .format({"Valor": fmt_reais_abrev})
    )


def render_nivel3(
    con: duckdb.DuckDBPyConnection,
    gg_id: str,
    categoria: str,
    caminho_explicacoes: str,
    categorias_validas: list[str],
) -> None:
    render_page_banner("📦", "Pacotes", f"Pacotes em '{categoria}' — maior para menor impacto.")
    df_ranking = dados_ranking_pacotes(con, gg_id, categoria, caminho_explicacoes, categorias_validas)
    if df_ranking.empty:
        st.info(f"Nenhum pacote com valor em '{categoria}' neste recorte.")
        return
    st.caption("🔴 vermelho = estouro (valor positivo) · 🟢 verde = economia (valor negativo).")
    st.dataframe(
        tabela_ranking(df_ranking, mapa_nomes_pacote(con)),
        hide_index=True, use_container_width=True,
        key=f"ranking-{gg_id}-{categoria}",
    )
