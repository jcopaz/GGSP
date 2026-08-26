"""Resumo Executivo CAPEX — mesma ideia da Visão Resumida Executiva do
OPEX (1 tela, gráfica, "bater o olho"), mas pro CAPEX de Projetos e Obras
(CJI4 Orçado x CJI3 Realizado), trazido em 2026-08-11.

Sem motor de causa aqui: `explicacoes.csv` (Físico/Efeito Preço/etc.) só
existe pro recorte OPEX/Malha — não há captação de justificativa pra
Projetos e Obras ainda. Por isso não há waterfall por categoria nem
"% Explicado" — só Orçado x Real x Delta x Aderência, igual ao card do
Nível 1 antes do motor de causa existir.

Escopo de Gerência (Expansão, Obras Ferroviárias, Baixada Santista,
Mobilidade Urbana, Corredor São Paulo) confirmado como GG Infraestrutura
(SP) em 2026-08-12 — ver capex_dados.py e docs/02-perguntas-em-aberto.md,
item 21.
"""
from __future__ import annotations

import duckdb
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.capex_dados import (
    dados_gerencia_obras,
    dados_projetos,
    resumo_geral_capex,
    rotulo_projeto,
    tabelas_disponiveis,
)
from src.dashboard.formatacao import escapar_cifrao_md, fmt_pct, fmt_reais_abrev, fmt_semaforo
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.paleta import COR_ORCADO, COR_REALIZADO
from src.engine.semaforo import classificar_semaforo


def _render_card_resumo(resumo: dict, status_semaforo: str) -> None:
    delta = resumo["delta"]
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"
    with st.container(border=True):
        st.markdown(f"**CAPEX — Projetos e Obras** &nbsp; {fmt_semaforo(status_semaforo)}")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado (CJI4) | {fmt_reais_abrev(resumo["orcado"])} |
            | Realizado (CJI3) | {fmt_reais_abrev(resumo["realizado"])} |
            | Delta | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Aderência | {fmt_pct(resumo["aderencia"])} |
            """)
        )


def _grafico_gerencia_obras(df) -> go.Figure:
    top = df.iloc[::-1]
    fig = go.Figure()
    fig.add_bar(
        name="Orçado (CJI4)", x=top["orcado"], y=top["rotulo"], orientation="h", marker_color=COR_ORCADO,
        text=[fmt_reais_abrev(v) for v in top["orcado"]],
        hovertemplate="<b>%{y}</b><br>Orçado (CJI4): %{text}<extra></extra>",
    )
    fig.add_bar(
        name="Realizado (CJI3)", x=top["realizado"], y=top["rotulo"], orientation="h", marker_color=COR_REALIZADO,
        text=[fmt_reais_abrev(v) for v in top["realizado"]],
        hovertemplate="<b>%{y}</b><br>Realizado (CJI3): %{text}<extra></extra>",
    )
    fig.update_layout(
        title="Orçado x Realizado por Gerência de Obras", barmode="group",
        margin={"t": 60, "b": 40, "r": 40}, height=max(320, 50 * len(top)),
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        hovermode="y unified",
    )
    return fig


def render_resumo_executivo_capex(con: duckdb.DuckDBPyConnection) -> None:
    st.header("Resumo Executivo — CAPEX")
    st.caption(
        "CAPEX de Projetos e Obras (fora da Malha SP) — Orçado vem do CJI4, "
        "Realizado do CJI3, ambos trazidos em 2026-08-11. Escopo de "
        "Gerência confirmado como GG Infraestrutura (SP) em 2026-08-12 "
        "(Expansão, Obras Ferroviárias, Baixada Santista, Mobilidade "
        "Urbana, Corredor São Paulo) — esta aba fica separada do total "
        "Orçamento (CAPEX+OPEX) "
        "mostrado no Painel OPEX porque é outro universo (Projetos, não "
        "Manutenção Corrente), não por dúvida de escopo. Sem motor de "
        "causa ainda: não há captação de justificativa pra Projetos e "
        "Obras."
    )

    tem_orc, tem_real = tabelas_disponiveis(con)
    if not tem_orc and not tem_real:
        st.warning(
            "Nenhum arquivo de CAPEX de Projetos e Obras carregado ainda "
            "(CJI4/CJI3 em data/raw/)."
        )
        return

    resumo = resumo_geral_capex(con)
    status_semaforo = classificar_semaforo(resumo["aderencia"])

    df_gerencia = dados_gerencia_obras(con)

    col_card, col_linha, col_graf = st.columns([1, 0.04, 3], gap="medium")
    with col_card:
        _render_card_resumo(resumo, status_semaforo)
        if not tem_orc:
            st.caption("⚠️ CJI4 (Orçado) não carregado — Orçado fica zerado.")
        if not tem_real:
            st.caption("⚠️ CJI3 (Realizado) não carregado — Realizado fica zerado.")
        st.caption("🟢 95–105% · 🟡 90–95%/105–110% · 🔴 fora da faixa · ⚪ sem dado.")
    with col_linha:
        st.markdown(
            "<div style='border-left: 1px solid #ccc; height: 100%; "
            "min-height: 320px; margin: 0 auto;'></div>",
            unsafe_allow_html=True,
        )
    with col_graf:
        if df_gerencia.empty:
            st.info("Nenhum dado por Gerência de Obras no recorte selecionado.")
        else:
            st.plotly_chart(
                _grafico_gerencia_obras(df_gerencia), use_container_width=True,
                key="capex-resumo-gerencia", config=CONFIG_PLOTLY,
            )

    st.divider()
    st.subheader("Projetos com Maior Desvio")
    ranking = dados_projetos(con)
    top10 = ranking.head(10)
    if top10.empty:
        st.caption("Nenhum projeto com Orçado/Realizado no recorte selecionado.")
    else:
        tabela = top10.assign(
            projeto=top10.apply(lambda r: rotulo_projeto(r["e_pep_projeto"], r["nome_empreendimento"]), axis=1),
            orcado=top10["orcado"].map(fmt_reais_abrev),
            realizado=top10["realizado"].map(fmt_reais_abrev),
            delta_total=top10["delta_total"].map(fmt_reais_abrev),
        )[["projeto", "gerencia_obras", "orcado", "realizado", "delta_total"]].rename(columns={
            "projeto": "Projeto", "gerencia_obras": "Gerência de Obras",
            "orcado": "Orçado", "realizado": "Realizado", "delta_total": "Delta",
        })
        st.dataframe(tabela, hide_index=True, use_container_width=True)
