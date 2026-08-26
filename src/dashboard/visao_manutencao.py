"""Visão Manutenção (SP) — réplica parcial da página "Visão Opex -
Manutenção MALHA E GIV" do Power BI de referência (PDF trazido pelo
usuário em 2026-08-06), recortada para os dados que realmente temos hoje:
só GG = SP, família de pacote PM (Manutenção Malha — PM01/PM02/PM03/PM05).

O que NÃO foi reproduzido, de propósito (não inventar dado/mapeamento):
- Quebra "Classificação" (Opex Via / Opex EE / Indiretos) por conta: no
  Power BI de referência isso vem de uma tabela Conta → Classificação que
  não temos aqui, e não é derivável de Grupo/Disciplina nem de Tipo.
- Comparação Orçado x Real por Escopo/Tipo: só a Base Zero (Orçamento) tem
  Grupo/Disciplina, Sub-Grupo/Escopo e Tipo — o Realizado (SAP) não carrega
  essas colunas, então os gráficos de Escopo/Tipo abaixo só têm Orçado.

Árvores de Contas (Nível 4) e Centro de Custo (Nível 5), recortadas em
familia_pacote="PM", adicionadas em 2026-08-06 a pedido do usuário ("Na
visão Manutenção Malha é importante ter tudo isso também dentro da aba") —
reaproveitam `render_arvore_contas`/`render_arvore_centro_custo` dos
próprios módulos de Nível 4/5, sem duplicar a consulta nem o HTML da
árvore. Os gráficos/queries que já existiam aqui passaram a respeitar
também o filtro global de Período (Ano/Trimestre/Mês) da sidebar, pela
mesma razão.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.filtros import clausula_periodo
from src.dashboard.formatacao import escapar_cifrao_md, fmt_pacote, fmt_pct, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.grafico_interativo import CONFIG_PLOTLY, com_alternancia_barra_linha
from src.dashboard.nivel4_contas import render_arvore_contas
from src.dashboard.nivel5_centro_custo import render_arvore_centro_custo
from src.dashboard.paleta import COR_ORCADO, COR_REALIZADO
from src.dashboard.tendencia import dados_tendencia, figura_tendencia

FAMILIA_MANUTENCAO = "PM"
_NOMES_MES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
              7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def resumo_manutencao(con: duckdb.DuckDBPyConnection) -> dict:
    where_periodo, params_periodo = clausula_periodo()
    (orcado,) = con.execute(
        f"SELECT SUM(valor_orcado) FROM fact_orcamento WHERE familia_pacote = ?{where_periodo}",
        [FAMILIA_MANUTENCAO, *params_periodo],
    ).fetchone()
    (realizado,) = con.execute(
        f"SELECT SUM(valor_realizado) FROM fact_realizado WHERE familia_pacote = ?{where_periodo}",
        [FAMILIA_MANUTENCAO, *params_periodo],
    ).fetchone()
    orcado = orcado or 0.0
    realizado = realizado or 0.0
    delta = realizado - orcado
    aderencia = (realizado / orcado) if orcado else None
    return {"orcado": orcado, "realizado": realizado, "delta": delta, "aderencia": aderencia}


def _dados_por_pacote(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    where_periodo, params_periodo = clausula_periodo()
    return con.execute(
        f"""
        WITH orc AS (
            SELECT pacote_id, SUM(valor_orcado) AS orcado FROM fact_orcamento
            WHERE familia_pacote = ?{where_periodo} GROUP BY pacote_id
        ), real AS (
            SELECT pacote_id, SUM(valor_realizado) AS realizado FROM fact_realizado
            WHERE familia_pacote = ?{where_periodo} GROUP BY pacote_id
        )
        SELECT COALESCE(orc.pacote_id, real.pacote_id) AS pacote_id,
               COALESCE(orcado, 0) AS orcado, COALESCE(realizado, 0) AS realizado
        FROM orc FULL OUTER JOIN real USING (pacote_id)
        ORDER BY pacote_id
        """,
        [FAMILIA_MANUTENCAO, *params_periodo, FAMILIA_MANUTENCAO, *params_periodo],
    ).df()


def _grafico_por_pacote(df: pd.DataFrame, nomes_pacote: dict[str, str]) -> go.Figure:
    rotulos = [fmt_pacote(p, nomes_pacote.get(p)) for p in df["pacote_id"]]
    fig = go.Figure()
    fig.add_bar(
        name="Orçado", x=rotulos, y=df["orcado"], marker_color=COR_ORCADO,
        text=[fmt_reais_abrev(v) for v in df["orcado"]],
        hovertemplate="<b>%{x}</b><br>Orçado: %{text}<extra></extra>",
    )
    fig.add_bar(
        name="Real", x=rotulos, y=df["realizado"], marker_color=COR_REALIZADO,
        text=[fmt_reais_abrev(v) for v in df["realizado"]],
        hovertemplate="<b>%{x}</b><br>Real: %{text}<extra></extra>",
    )
    fig.update_layout(
        title="Orçado x Real por Pacote", barmode="group", margin={"t": 60, "b": 80},
        hovermode="x unified",
    )
    return fig


def _dados_mensal(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    where_periodo, params_periodo = clausula_periodo()
    df = con.execute(
        f"""
        WITH orc AS (
            SELECT mes, SUM(valor_orcado) AS orcado FROM fact_orcamento
            WHERE familia_pacote = ?{where_periodo} GROUP BY mes
        ), real AS (
            SELECT mes, SUM(valor_realizado) AS realizado FROM fact_realizado
            WHERE familia_pacote = ?{where_periodo} GROUP BY mes
        )
        SELECT COALESCE(orc.mes, real.mes) AS mes,
               COALESCE(orcado, 0) AS orcado, COALESCE(realizado, 0) AS realizado
        FROM orc FULL OUTER JOIN real USING (mes)
        ORDER BY mes
        """,
        [FAMILIA_MANUTENCAO, *params_periodo, FAMILIA_MANUTENCAO, *params_periodo],
    ).df()
    df["aderencia"] = df.apply(
        lambda r: (r["realizado"] / r["orcado"]) if r["orcado"] else None, axis=1
    )
    df["mes_nome"] = df["mes"].map(_NOMES_MES)
    return df


def _grafico_mensal(df: pd.DataFrame) -> go.Figure:
    """Orçado/Real alternam Barra (padrão) x Linha via botões — eixo X é
    mês, sequencial, então a Linha é uma leitura válida (ver
    grafico_interativo.py). Aderência fica sempre como linha pontilhada no
    eixo secundário nos 2 modos — é uma taxa, não um valor monetário
    "empilhável" com Orçado/Real — entra como `traces_extras` do helper
    compartilhado (migrado em 2026-08-13, achado #6 da auditoria de UX:
    esta função e `tendencia.figura_tendencia` reimplementavam o mesmo
    padrão de `updatemenus` cada uma na sua)."""
    aderencia = go.Scatter(
        name="Aderência", x=df["mes_nome"], y=df["aderencia"], mode="lines+markers",
        yaxis="y2", line={"color": "steelblue", "dash": "dot"}, visible=True,
        hovertemplate="Aderência: %{y:.1%}<extra></extra>",
    )
    fig = com_alternancia_barra_linha(
        categorias=df["mes_nome"].tolist(),
        series=[("Orçado", df["orcado"], COR_ORCADO), ("Real", df["realizado"], COR_REALIZADO)],
        titulo="Visão Mensal",
        traces_extras=[aderencia],
        layout_extra={
            "yaxis2": {"overlaying": "y", "side": "right", "tickformat": ".0%", "title": "Aderência"},
            "margin": {"t": 70, "b": 40},
            "hovermode": "x unified",
        },
    )
    for indice in range(4):
        y = fig.data[indice].y
        fig.data[indice].text = [fmt_reais_abrev(v) for v in y]
        nome = fig.data[indice].name
        fig.data[indice].hovertemplate = f"{nome}: %{{text}}<extra></extra>"
    return fig


def _grafico_escopo(con: duckdb.DuckDBPyConnection, top_n: int = 10) -> go.Figure | None:
    """Só Orçado — Realizado (SAP) não carrega Grupo/Disciplina."""
    where_periodo, params_periodo = clausula_periodo()
    df = con.execute(
        f"""
        SELECT grupo_disciplina, SUM(valor_orcado) AS orcado
        FROM fact_orcamento
        WHERE familia_pacote = ? AND grupo_disciplina != ''{where_periodo}
        GROUP BY grupo_disciplina
        ORDER BY orcado DESC
        LIMIT ?
        """,
        [FAMILIA_MANUTENCAO, *params_periodo, top_n],
    ).df()
    if df.empty:
        return None
    df = df.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=df["orcado"], y=df["grupo_disciplina"], orientation="h", marker_color=COR_ORCADO,
        text=[fmt_reais_abrev(v) for v in df["orcado"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Orçado: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Orçado por Escopo (Grupo/Disciplina) — {top_n} Principais",
        margin={"t": 60, "b": 40, "r": 110},
    )
    return fig


def _grafico_tipo(con: duckdb.DuckDBPyConnection) -> go.Figure | None:
    """Só Orçado — Realizado (SAP) não carrega Tipo (Material/Serviço)."""
    where_periodo, params_periodo = clausula_periodo()
    df = con.execute(
        f"""
        SELECT tipo_item, SUM(valor_orcado) AS orcado
        FROM fact_orcamento WHERE familia_pacote = ? AND tipo_item != ''{where_periodo}
        GROUP BY tipo_item ORDER BY orcado DESC
        """,
        [FAMILIA_MANUTENCAO, *params_periodo],
    ).df()
    if df.empty:
        return None
    fig = go.Figure(go.Bar(
        x=df["tipo_item"], y=df["orcado"], marker_color=COR_ORCADO,
        text=[fmt_reais_abrev(v) for v in df["orcado"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Orçado: %{text}<extra></extra>",
    ))
    fig.update_layout(title="Orçado por Tipo", margin={"t": 60, "b": 40})
    return fig


def _render_card_manutencao(resumo: dict) -> None:
    delta = resumo["delta"]
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"
    with st.container(border=True):
        st.markdown("**🛠️ Manutenção (SP)**")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado | {fmt_reais_abrev(resumo["orcado"])} |
            | Real Contabilizado | {fmt_reais_abrev(resumo["realizado"])} |
            | Delta | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Aderência | {fmt_pct(resumo["aderencia"])} |
            """)
        )


def render_visao_manutencao(con: duckdb.DuckDBPyConnection, ano_fiscal: int) -> None:
    st.header("Visão Manutenção (SP)")
    st.caption(
        "Recorte da família de pacote PM (Manutenção Malha), réplica parcial "
        "da página 'Visão Opex - Manutenção MALHA E GIV' do Power BI de "
        "referência trazido em 2026-08-06. Só cobre SP porque é o único GG "
        "com dado real carregado hoje."
    )

    resumo = resumo_manutencao(con)
    nomes_pacote = mapa_nomes_pacote(con)

    # Card-resumo | divisor | gráfico por Pacote — mesmo padrão das demais
    # abas, replicado em 2026-08-10.
    col_card, col_linha, col_graf = st.columns([1, 0.04, 3], gap="medium")
    with col_card:
        _render_card_manutencao(resumo)
    with col_linha:
        st.markdown(
            "<div style='border-left: 1px solid #ccc; height: 100%; "
            "min-height: 420px; margin: 0 auto;'></div>",
            unsafe_allow_html=True,
        )
    with col_graf:
        st.plotly_chart(
            _grafico_por_pacote(_dados_por_pacote(con), nomes_pacote),
            use_container_width=True, key="manut-por-pacote", config=CONFIG_PLOTLY,
        )

    st.divider()
    df_tend = dados_tendencia(con, ano_fiscal, familia=FAMILIA_MANUTENCAO)
    st.plotly_chart(
        figura_tendencia(df_tend, "Tendência do ano — Manutenção (SP)"),
        use_container_width=True, key="manut-tendencia", config=CONFIG_PLOTLY,
    )
    st.caption(
        "Linha pontilhada = Forecast (saldo do desvio até o mês de "
        "referência, redistribuído nos meses restantes — fecha "
        "exatamente no Orçado Anual em dezembro)."
    )

    st.plotly_chart(_grafico_mensal(_dados_mensal(con)), use_container_width=True, key="manut-mensal", config=CONFIG_PLOTLY)

    col_esc, col_tipo = st.columns(2)
    with col_esc:
        fig_escopo = _grafico_escopo(con)
        if fig_escopo:
            st.plotly_chart(fig_escopo, use_container_width=True, key="manut-escopo", config=CONFIG_PLOTLY)
    with col_tipo:
        fig_tipo = _grafico_tipo(con)
        if fig_tipo:
            st.plotly_chart(fig_tipo, use_container_width=True, key="manut-tipo", config=CONFIG_PLOTLY)

    st.divider()
    st.subheader("Nível 4 — Contas (Manutenção)")
    st.caption(
        "Orçado/Realizado/Delta e Tendência da família PM já estão no "
        "resumo acima — aqui só o detalhe novo: quais Contas puxam o desvio."
    )
    render_arvore_contas(con, familia=FAMILIA_MANUTENCAO, key_prefix="manut-n4", mostrar_resumo=False)

    st.divider()
    st.subheader("Nível 5 — Centro de Custo (Manutenção)")
    st.caption(
        "Mesmo raciocínio: resumo já está acima, aqui só o detalhe de "
        "quais Centros de Custo puxam o desvio."
    )
    render_arvore_centro_custo(con, familia=FAMILIA_MANUTENCAO, key_prefix="manut-n5", mostrar_resumo=False)

    st.info(
        "Não reproduzido aqui: quebra por 'Classificação' (Opex Via / Opex "
        "EE / Indiretos) do Power BI de referência — exigiria uma tabela "
        "Conta → Classificação que não temos, e eu não ia inventar esse "
        "mapeamento. E os gráficos de Escopo/Tipo acima só têm barra de "
        "Orçado porque o Realizado (SAP) não carrega essas colunas."
    )
