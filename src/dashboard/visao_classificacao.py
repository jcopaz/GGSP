"""Visão CAPEX / Visão OPEX — navegação separada por Classificação Contábil,
a pedido do usuário em 2026-08-10 ("separar o que é Capex e o que é OPEX").

Só filtra o Orçado: `classificacao_contabil` só existe em `fact_orcamento`
(vem direto da Base Zero, linha a linha). O Realizado (SAP) não carrega essa
coluna, e não dá pra herdar via Conta — `conta_orcamento_id` (Base Zero) e
`conta_razao_id` (Razão SAP) são vocabulários diferentes, sem De-Para nos
arquivos que temos (mesmo achado documentado em nivel4_contas.py). Por isso
Realizado/Delta aparecem aqui só como referência SP (não fatiado), nunca
como "Realizado CAPEX"/"Realizado OPEX" — inventar esse rateio violaria a
Regra de Ouro do projeto (não simular valor).

Escopo de domínio (atualizado em 2026-08-11, diagrama trazido pelo usuário
mostrando os 3 universos financeiros de DINFRA — ver capex_dados.py e
project_orcamento_dinfra_status.md): esta página só cobre a fatia **CAPEX
de Manutenção Corrente — Malha** (Base Zero, área "Malha Capex", pacote
PM03, materiais/serviços de renovação de via). **Infra** (Drenagem,
Saneamento Vegetal, pequenas obras — mesmo universo "Manutenção Corrente")
ainda não tem arquivo carregado, pendência com a Alice/PMO. **Obras**
(Projetos, metodologia FEL/Capex Control Center) tem seção própria agora
— "CAPEX Projetos (Obras)", sourced em CJI4/CJI3 — não é mais um domínio
"sem dado", só não é mostrado nesta página específica (universo
diferente).

**Sem gráfico de Tendência aqui** (removido em 2026-08-10, revisão de
duplicação): toda linha de Tendência do painel tem que mostrar Planejado x
Realizado (não só uma perna) — e essa página não tem como fazer isso de
verdade, porque Realizado não é fatiável por Classificação Contábil (ver
acima). Uma Tendência só-Orçado ficaria incompleta e ainda repetiria, de
forma pior, a Tendência completa (Planejado x Realizado) que já existe no
Painel Executivo. O caminho pra ver evolução no tempo com as duas pernas é
lá.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.formatacao import escapar_cifrao_md, fmt_pacote, fmt_pct, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.paleta import COR_CAPEX, COR_OPEX

_COR_CLASSIFICACAO = {"CAPEX": COR_CAPEX, "OPEX": COR_OPEX}
_TITULO = {"CAPEX": "CAPEX Manutenção — Malha", "OPEX": "Visão OPEX (Manutenção Malha)"}
_ICONE = {"CAPEX": "🏗️", "OPEX": "🛠️"}


def _badges_dominio() -> None:
    """3 domínios do universo "Manutenção Corrente" (ver diagrama do
    usuário, 2026-08-11) — "Obras" deixou de ser "sem dado carregado" (tem
    fonte própria agora, CJI4/CJI3, seção "CAPEX Projetos") mas continua
    fora desta página específica, que é só Manutenção Corrente."""
    c1, c2, c3 = st.columns(3)
    c1.success("✅ Malha — dado carregado")
    c2.markdown(":gray[⬜ Infra — sem dado carregado (pendência com a Alice/PMO)]")
    c3.markdown(":blue[↗️ Obras — carregado, ver seção **CAPEX Projetos (Obras)**]")


def resumo_classificacao(con: duckdb.DuckDBPyConnection, classificacao: str) -> dict:
    (orcado,) = con.execute(
        "SELECT SUM(valor_orcado) FROM fact_orcamento WHERE classificacao_contabil = ?",
        [classificacao],
    ).fetchone()
    (orcado_total,) = con.execute("SELECT SUM(valor_orcado) FROM fact_orcamento").fetchone()
    (fora_plano,) = con.execute(
        "SELECT SUM(valor_orcado) FROM fact_orcamento "
        "WHERE classificacao_contabil = ? AND area LIKE 'Fora Plano%'",
        [classificacao],
    ).fetchone()
    (realizado_total,) = con.execute("SELECT SUM(valor_realizado) FROM fact_realizado").fetchone()

    orcado = orcado or 0.0
    orcado_total = orcado_total or 0.0
    return {
        "orcado": orcado,
        "pct_do_total": (orcado / orcado_total) if orcado_total else None,
        "fora_plano": fora_plano or 0.0,
        "realizado_total_sp": realizado_total or 0.0,
    }


def _dados_por_pacote(con: duckdb.DuckDBPyConnection, classificacao: str) -> pd.DataFrame:
    return con.execute(
        "SELECT pacote_id, SUM(valor_orcado) AS orcado FROM fact_orcamento "
        "WHERE classificacao_contabil = ? GROUP BY pacote_id ORDER BY orcado DESC",
        [classificacao],
    ).df()


def _grafico_por_pacote(df: pd.DataFrame, cor: str, nomes_pacote: dict[str, str]) -> go.Figure | None:
    if df.empty:
        return None
    rotulos = [fmt_pacote(p, nomes_pacote.get(p)) for p in df["pacote_id"]]
    fig = go.Figure(go.Bar(
        x=rotulos, y=df["orcado"], marker_color=cor,
        text=[fmt_reais_abrev(v) for v in df["orcado"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Orçado: %{text}<extra></extra>",
    ))
    fig.update_layout(title="Orçado por Pacote", margin={"t": 60, "b": 80})
    return fig


def _dados_por_conta(con: duckdb.DuckDBPyConnection, classificacao: str, top_n: int = 10) -> pd.DataFrame:
    """`conta_interna_id`/`conta_interna_nome` — mesma chave unificada do
    Nível 4 (ver build_star_schema.py) — pra não mostrar código sem nome."""
    return con.execute(
        "SELECT conta_interna_id AS conta, MAX(NULLIF(conta_interna_nome, '')) AS nome, "
        "SUM(valor_orcado) AS orcado FROM fact_orcamento "
        "WHERE classificacao_contabil = ? GROUP BY conta_interna_id "
        "ORDER BY orcado DESC LIMIT ?",
        [classificacao, top_n],
    ).df()


def _grafico_por_conta(df: pd.DataFrame, cor: str, top_n: int) -> go.Figure | None:
    if df.empty:
        return None
    df = df.iloc[::-1].copy()
    df["rotulo"] = df.apply(lambda r: f'{r["conta"]} — {r["nome"]}' if r["nome"] else r["conta"], axis=1)
    fig = go.Figure(go.Bar(
        x=df["orcado"], y=df["rotulo"], orientation="h", marker_color=cor,
        text=[fmt_reais_abrev(v) for v in df["orcado"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Orçado: %{text}<extra></extra>",
    ))
    fig.update_layout(title=f"Orçado por Conta — {top_n} Principais", margin={"t": 60, "b": 40, "r": 110})
    return fig


def _render_card_classificacao(classificacao: str, resumo: dict) -> None:
    linhas_extra = ""
    if classificacao == "OPEX" and resumo["fora_plano"]:
        linhas_extra = f'| &nbsp;&nbsp;↳ Fora do Plano | {fmt_reais_abrev(resumo["fora_plano"])} |\n'
    with st.container(border=True):
        st.markdown(f"**{_ICONE[classificacao]} {classificacao}**")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado {classificacao} | {fmt_reais_abrev(resumo["orcado"])} |
            {linhas_extra}| % do Orçamento total (Malha) | {fmt_pct(resumo["pct_do_total"])} |
            | Realizado (ref. Malha, não fatiado) | {fmt_reais_abrev(resumo["realizado_total_sp"])} |
            """)
        )


def render_visao_classificacao(con: duckdb.DuckDBPyConnection, classificacao: str) -> None:
    cor = _COR_CLASSIFICACAO[classificacao]
    st.header(f"{_ICONE[classificacao]} {_TITULO[classificacao]}")
    _badges_dominio()
    st.caption(
        "Só o Orçado é fatiado por Classificação Contábil — Realizado (SAP) "
        "não carrega essa coluna por linha, e não dá pra herdar via Conta "
        "sem o de/para (ver docs/02-perguntas-em-aberto.md, item 11). Por "
        "isso Realizado aqui aparece só como referência de Malha (SP) "
        "inteira, não fatiado — e por isso essa aba não tem gráfico de "
        "Tendência (não daria pra mostrar Planejado x Realizado de "
        "verdade); a evolução no tempo está no Painel Executivo."
    )

    resumo = resumo_classificacao(con, classificacao)
    nomes_pacote = mapa_nomes_pacote(con)

    # Card-resumo | divisor | gráfico por Pacote — mesmo padrão do Painel
    # Executivo (Nível 1 | Nível 2), pedido do usuário em 2026-08-10.
    col_card, col_linha, col_graf = st.columns([1, 0.04, 3], gap="medium")
    with col_card:
        _render_card_classificacao(classificacao, resumo)
    with col_linha:
        st.markdown(
            "<div style='border-left: 1px solid #ccc; height: 100%; "
            "min-height: 420px; margin: 0 auto;'></div>",
            unsafe_allow_html=True,
        )
    with col_graf:
        fig_pacote = _grafico_por_pacote(_dados_por_pacote(con, classificacao), cor, nomes_pacote)
        if fig_pacote:
            st.plotly_chart(fig_pacote, use_container_width=True, key=f"vc-{classificacao}-pacote", config=CONFIG_PLOTLY)

    st.divider()
    fig_conta = _grafico_por_conta(_dados_por_conta(con, classificacao), cor, top_n=10)
    if fig_conta:
        st.plotly_chart(fig_conta, use_container_width=True, key=f"vc-{classificacao}-conta", config=CONFIG_PLOTLY)
