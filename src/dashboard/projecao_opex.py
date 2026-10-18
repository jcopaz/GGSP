"""Projeção OPEX por ritmo médio realizado, separada do Forecast PMO."""
from __future__ import annotations
import duckdb
import streamlit as st
from src.branding import render_page_banner
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.filtros import (
    clausulas_recorte, guardar_e_faixa_universo, recorte_sidebar_ativo, rotulo_periodo, ultimo_periodo_fechado,
)
from src.dashboard.tendencia import dados_tendencia, figura_tendencia
from src.dashboard.formatacao import fmt_reais_abrev

FAMILIAS = {"PD": "Despesas Gerais", "PP": "Despesas Pessoais", "PM": "Manutenção"}


def render_projecao_opex(con: duckdb.DuckDBPyConnection, ano_fiscal: int) -> None:
    render_page_banner("📈", "Projeção OPEX", "Ritmo médio do Realizado versus Orçamento, sem substituir o Forecast PMO.")
    # RBAC de escopo (docs/08, Fase RBAC-A.2): universo opex_sustaining.
    guardar_e_faixa_universo(con, "opex_sustaining")
    # 2026-10-18 (validação de filtros, P5): recorte da sidebar (Gerência,
    # Coordenação, CC, PEP, Classificação, Pacote) + escopo. Período fica de
    # fora de propósito — a projeção é sempre o ano inteiro.
    (frag_o, par_o), (frag_r, par_r) = clausulas_recorte("opex_sustaining", incluir_periodo=False)
    filtro_opex = (" AND classificacao_contabil = 'OPEX'" + frag_o, list(par_o))
    filtro_real = (" AND classificacao_contabil = 'OPEX'" + frag_r, list(par_r))

    # B4 (2026-10-18): a média e o "Fechamento projetado" usam só os meses
    # fechados (ver `tendencia.dados_tendencia`) — o mês em aberto, com
    # Realizado parcial, entra como projetado em vez de puxar a média.
    corte = rotulo_periodo(ultimo_periodo_fechado(con))
    st.caption(
        f"A projeção mantém o Realizado acumulado até o último mês fechado{f' ({corte})' if corte else ''} "
        "e repete, nos meses seguintes, a média mensal realizada até ele. O mês em aberto, com "
        "Realizado parcial, entra como projetado. Assim ela mostra onde o ritmo atual tende a "
        "encerrar o ano."
    )
    if recorte_sidebar_ativo():
        st.caption("Projeção do recorte filtrado na barra lateral. O filtro de Período não se aplica aqui: a projeção é sempre do ano inteiro.")
    abas = st.tabs(list(FAMILIAS.values()))
    for aba, (familia, rotulo) in zip(abas, FAMILIAS.items()):
        with aba:
            df = dados_tendencia(
                con, ano_fiscal, familia=familia,
                filtro_orcado=filtro_opex,
                filtro_realizado=filtro_real,
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
