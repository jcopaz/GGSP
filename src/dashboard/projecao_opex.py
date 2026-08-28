"""Projeção OPEX por ritmo médio realizado, separada do Forecast PMO."""
from __future__ import annotations
import duckdb
import streamlit as st
from src.branding import render_page_banner
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.tendencia import dados_tendencia, figura_tendencia
from src.dashboard.formatacao import fmt_reais_abrev

FAMILIAS = {"PD": "Despesas Gerais", "PP": "Despesas Pessoais", "PM": "Manutenção"}

def render_projecao_opex(con: duckdb.DuckDBPyConnection, ano_fiscal: int) -> None:
    render_page_banner("📈", "Projeção OPEX", "Ritmo médio do Realizado versus Orçamento, sem substituir o Forecast PMO.")
    st.caption("A projeção mantém o Realizado acumulado até o último mês com dado e repete, nos meses futuros, a média mensal realizada. Assim ela mostra onde o ritmo atual tende a encerrar o ano.")
    abas = st.tabs(list(FAMILIAS.values()))
    for aba, (familia, rotulo) in zip(abas, FAMILIAS.items()):
        with aba:
            df = dados_tendencia(
                con, ano_fiscal, familia=familia,
                filtro_orcado=(" AND classificacao_contabil = 'OPEX'", []),
                filtro_realizado=(" AND classificacao_contabil = 'OPEX'", []),
            )
            anual_orcado = float(df["orcado"].sum())
            ultima = df["projecao_ritmo_acumulada"].dropna()
            fechamento = float(ultima.iloc[-1]) if not ultima.empty else 0.0
            delta = fechamento - anual_orcado
            c1, c2, c3 = st.columns(3)
            c1.metric("Orçamento anual", fmt_reais_abrev(anual_orcado))
            c2.metric("Fechamento projetado", fmt_reais_abrev(fechamento))
            c3.metric("Projeção x Orçamento", fmt_reais_abrev(delta), delta="Estouro" if delta > 0 else "Abaixo do orçamento")
            st.plotly_chart(figura_tendencia(df, f"{rotulo}: Orçado, Realizado, Forecast e projeção de ritmo"), use_container_width=True, key=f"projecao-opex-{familia}", config=CONFIG_PLOTLY)
