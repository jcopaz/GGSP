"""Painel Executivo CAPEX — equivalente ao Painel Executivo OPEX (Nível 1 →
Nível 2), mas pro CAPEX de Projetos e Obras (CJI4 Orçado x CJI3 Realizado),
trazido em 2026-08-11.

Sem waterfall por categoria de causa (ver capex_resumo.py: não existe
captação de justificativa pra Projetos e Obras ainda) — o Nível 2 aqui é o
ranking de Projetos dentro da Gerência de Obras selecionada no Nível 1,
mesmo padrão do "Ver por Gerência" que o Painel OPEX já tem
(nivel2_gg.render_gerencia_gg), só que como fluxo principal (não expander),
porque aqui não tem waterfall pra competir por espaço.

Mapa de Calor Gerência de Obras x Projeto reaproveita o mesmo CSS/lógica de
cor do lado OPEX (`mapa_calor_gerencia_pacote.CSS_MAPA_CALOR`/`_cor_celula`)
— só a fonte de dados e o rótulo de coluna mudam.
"""
from __future__ import annotations

import html as _html

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.capex_dados import (
    dados_gerencia_obras,
    dados_projetos,
    dados_heatmap_gerencia_projeto,
    dados_tendencia_capex,
    rotulo_projeto,
    tabelas_disponiveis,
)
from src.dashboard.formatacao import escapar_cifrao_md, fmt_pct, fmt_reais_abrev, fmt_semaforo
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.mapa_calor_gerencia_pacote import CSS_MAPA_CALOR, LIMIAR_PULSO, _cor_celula, sombra_texto
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO, COR_NEUTRO
from src.dashboard.tendencia import figura_tendencia
from src.engine.semaforo import classificar_semaforo

CAPEX_GERENCIA_SELECIONADA = "capex_gerencia_selecionada"


def _render_card_gerencia(linha: pd.Series) -> None:
    delta = linha["delta_total"]
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"
    status_semaforo = classificar_semaforo(linha["aderencia"])
    with st.container(border=True):
        st.markdown(f"**{linha['rotulo']}** &nbsp; {fmt_semaforo(status_semaforo)}")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado (CJI4) | {fmt_reais_abrev(linha["orcado"])} |
            | Realizado (CJI3) | {fmt_reais_abrev(linha["realizado"])} |
            | Delta | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Aderência | {fmt_pct(linha["aderencia"])} |
            """)
        )


def render_nivel1_capex(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    st.subheader("Nível 1 — Gerência de Obras")
    st.caption(
        "🟢 95–105% · 🟡 90–95%/105–110% · 🔴 fora da faixa · ⚪ sem dado. "
        "\"Não catalogado\": projeto sem casar com o Catálogo CAPEX Obras "
        "(fica sem nome/Gerência)."
    )
    df = dados_gerencia_obras(con)
    if df.empty:
        st.info("Nenhum dado por Gerência de Obras no recorte selecionado.")
        return df
    colunas = st.columns(len(df))
    for coluna, (_, linha) in zip(colunas, df.iterrows()):
        with coluna:
            _render_card_gerencia(linha)
    return df


def _grafico_projetos(df: pd.DataFrame, top_n: int = 15) -> go.Figure | None:
    if df.empty:
        return None
    top = df.head(top_n).iloc[::-1]
    cores = [COR_ESTOURO if v > 0 else COR_ECONOMIA if v < 0 else COR_NEUTRO for v in top["delta_total"]]
    rotulos = [rotulo_projeto(r["e_pep_projeto"], r["nome_empreendimento"]) for _, r in top.iterrows()]
    fig = go.Figure(go.Bar(
        x=top["delta_total"], y=rotulos, orientation="h", marker={"color": cores},
        text=[fmt_reais_abrev(v) for v in top["delta_total"]], textposition="auto", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Delta: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Projetos com Maior Desvio — {top_n} Principais",
        margin={"t": 60, "b": 40, "r": 110}, height=max(320, 30 * len(top)),
    )
    return fig


def _cor_valor(valor: float) -> str:
    cor = COR_ESTOURO if valor > 0 else COR_ECONOMIA if valor < 0 else "inherit"
    return f"color: {cor}; font-weight: 600"


def _tabela_projetos(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    tabela = pd.DataFrame({
        "Projeto": [rotulo_projeto(r["e_pep_projeto"], r["nome_empreendimento"]) for _, r in df.iterrows()],
        "Orçado": df["orcado"], "Realizado": df["realizado"], "Delta": df["delta_total"],
    })
    return tabela.style.map(_cor_valor, subset=["Delta"]).format(
        {"Orçado": fmt_reais_abrev, "Realizado": fmt_reais_abrev, "Delta": fmt_reais_abrev}
    )


def render_nivel2_capex(con: duckdb.DuckDBPyConnection, df_gerencia: pd.DataFrame) -> None:
    st.subheader("Nível 2 — Projetos dentro da Gerência de Obras")
    if df_gerencia.empty:
        return
    opcoes = df_gerencia["rotulo"].tolist()
    atual = st.session_state.get(CAPEX_GERENCIA_SELECIONADA)
    indice = opcoes.index(atual) if atual in opcoes else 0
    escolha = st.selectbox("Ver Projetos desta Gerência de Obras:", opcoes, index=indice, key="capex-seletor-gerencia")
    st.session_state[CAPEX_GERENCIA_SELECIONADA] = escolha

    gerencia_obras = df_gerencia.loc[df_gerencia["rotulo"] == escolha, "gerencia_obras"].iloc[0] or None
    df_projetos = dados_projetos(con, gerencia_obras=gerencia_obras)
    if df_projetos.empty:
        st.info("Nenhum projeto com Orçado/Realizado nesta Gerência de Obras.")
        return

    fig = _grafico_projetos(df_projetos)
    if fig:
        st.plotly_chart(fig, use_container_width=True, key="capex-projetos-grafico", config=CONFIG_PLOTLY)
        st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
    st.dataframe(_tabela_projetos(df_projetos), hide_index=True, use_container_width=True)
    return gerencia_obras


def _html_mapa_calor_capex(df: pd.DataFrame) -> str:
    gerencias = (
        df.groupby("gerencia_rotulo")["delta_total"].apply(lambda s: s.abs().sum())
        .sort_values(ascending=False).index.tolist()
    )
    projetos = sorted(df["e_pep_projeto"].unique().tolist())
    matriz = df.set_index(["gerencia_rotulo", "e_pep_projeto"])
    max_abs = df["delta_total"].abs().max() or 0.0

    partes = [CSS_MAPA_CALOR, '<div class="pnl-heatmap-wrap"><table class="pnl-heatmap">']
    partes.append("<tr><th class='pnl-hm-rotulo'>Gerência \\ Projeto</th>")
    for proj in projetos:
        partes.append(f"<th>{_html.escape(proj)}</th>")
    partes.append("</tr>")

    for ger in gerencias:
        partes.append(f"<tr><td class='pnl-hm-rotulo'>{_html.escape(ger)}</td>")
        for proj in projetos:
            if (ger, proj) not in matriz.index:
                partes.append("<td class='pnl-hm-vazio'>·</td>")
                continue
            linha = matriz.loc[(ger, proj)]
            delta = float(linha["delta_total"])
            orcado, realizado = float(linha["orcado"]), float(linha["realizado"])
            if orcado == 0.0 and realizado == 0.0:
                partes.append("<td class='pnl-hm-vazio'>·</td>")
                continue
            cor_fundo, cor_texto = _cor_celula(delta, max_abs)
            pulsa = " pnl-hm-pulsa" if delta > LIMIAR_PULSO else ""
            titulo = (
                f"{ger} · {proj}\n"
                f"Orçado: {fmt_reais_abrev(orcado)} | Realizado: {fmt_reais_abrev(realizado)} | "
                f"Delta: {fmt_reais_abrev(delta)}"
            )
            partes.append(
                f"<td class='pnl-hm-valor{pulsa}' title='{_html.escape(titulo)}' "
                f"style='background:{cor_fundo}; color:{cor_texto}; text-shadow:{sombra_texto(cor_texto)};'>"
                f"{_html.escape(fmt_reais_abrev(delta))}</td>"
            )
        partes.append("</tr>")

    partes.append("</table></div>")
    return "".join(partes)


def render_mapa_calor_capex(con: duckdb.DuckDBPyConnection) -> None:
    df = dados_heatmap_gerencia_projeto(con)
    if df.empty:
        return
    with st.expander("🔥 Mapa de Calor: Gerência de Obras x Projeto", expanded=False):
        st.caption(
            f"Delta (Realizado − Orçado) cruzando Gerência de Obras x "
            f"Projeto. Vermelho = estouro, verde = economia. Célula "
            f"pulsando = estouro acima de {fmt_reais_abrev(LIMIAR_PULSO)} "
            f"(mesmo threshold do lado OPEX). Passe o cursor numa célula "
            f"pra ver Orçado/Realizado/Delta exatos."
        )
        st.markdown(_html_mapa_calor_capex(df), unsafe_allow_html=True)


def render_painel_executivo_capex(con: duckdb.DuckDBPyConnection, ano_fiscal: int) -> None:
    st.header("Painel Executivo — CAPEX")
    st.caption(
        "CAPEX de Projetos e Obras — Orçado (CJI4) x Realizado (CJI3), "
        "trazidos em 2026-08-11. Escopo de Gerência confirmado como GG "
        "Infraestrutura (SP) (2026-08-12 — ver docs/02-perguntas-em-"
        "aberto.md, item 21). Sem motor de causa: não há waterfall por "
        "categoria (Físico/Efeito Preço/etc.) aqui — só Orçado x Real x "
        "Delta."
    )

    tem_orc, tem_real = tabelas_disponiveis(con)
    if not tem_orc and not tem_real:
        st.warning(
            "Nenhum arquivo de CAPEX de Projetos e Obras carregado ainda "
            "(CJI4/CJI3 em data/raw/)."
        )
        return

    df_gerencia = render_nivel1_capex(con)
    st.divider()
    if not df_gerencia.empty:
        gerencia_obras = render_nivel2_capex(con, df_gerencia)

        st.divider()
        rotulo_atual = st.session_state.get(CAPEX_GERENCIA_SELECIONADA) or "Todas as Gerências"
        df_tend = dados_tendencia_capex(con, ano_fiscal, gerencia_obras=gerencia_obras)
        st.plotly_chart(
            figura_tendencia(df_tend, f"Tendência do ano — {rotulo_atual}"),
            use_container_width=True, key="capex-tendencia", config=CONFIG_PLOTLY,
        )
        st.caption(
            "Linha pontilhada = Forecast (saldo do desvio até o mês de "
            "referência, redistribuído nos meses restantes — fórmula do "
            "PMO, fecha exatamente no Orçado Anual em dezembro)."
        )

        render_mapa_calor_capex(con)
