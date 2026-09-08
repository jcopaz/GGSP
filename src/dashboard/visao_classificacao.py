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

from src.branding import render_page_banner
from src.dashboard.filtros import clausula_escopo, guardar_e_faixa_universo
from src.dashboard.formatacao import escapar_cifrao_md, fmt_pacote, fmt_pct, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.layout import bloco_resumo_visual
from src.dashboard.paleta import COR_CAPEX, COR_OPEX

# RBAC de escopo (docs/08): esta tela tem um lado OPEX e um lado CAPEX de
# Manutenção — cada um é um universo próprio.
UNIVERSO_POR_CLASSIFICACAO = {"OPEX": "opex_sustaining", "CAPEX": "capex_sustaining"}

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


def _escopo(classificacao: str) -> tuple[str, list]:
    """Fragmento de recorte por Gerência (RBAC de escopo — docs/08), no
    universo do lado escolhido (OPEX -> opex_sustaining, CAPEX ->
    capex_sustaining). `gerencia_id` está populado nos dois fatos, tanto
    pra linhas OPEX quanto CAPEX de `fact_orcamento`."""
    return clausula_escopo(UNIVERSO_POR_CLASSIFICACAO[classificacao])


def resumo_classificacao(con: duckdb.DuckDBPyConnection, classificacao: str) -> dict:
    esc, esc_p = _escopo(classificacao)
    (orcado,) = con.execute(
        f"SELECT SUM(valor_orcado) FROM fact_orcamento WHERE classificacao_contabil = ?{esc}",
        [classificacao, *esc_p],
    ).fetchone()
    (orcado_total,) = con.execute(
        f"SELECT SUM(valor_orcado) FROM fact_orcamento WHERE 1=1{esc}", esc_p
    ).fetchone()
    (fora_plano,) = con.execute(
        "SELECT SUM(valor_orcado) FROM fact_orcamento "
        f"WHERE classificacao_contabil = ? AND area LIKE 'Fora Plano%'{esc}",
        [classificacao, *esc_p],
    ).fetchone()
    (realizado_total,) = con.execute(
        f"SELECT SUM(valor_realizado) FROM fact_realizado WHERE 1=1{esc}", esc_p
    ).fetchone()

    orcado = orcado or 0.0
    orcado_total = orcado_total or 0.0
    return {
        "orcado": orcado,
        "pct_do_total": (orcado / orcado_total) if orcado_total else None,
        "fora_plano": fora_plano or 0.0,
        "realizado_total_sp": realizado_total or 0.0,
    }


def _dados_por_pacote(con: duckdb.DuckDBPyConnection, classificacao: str) -> pd.DataFrame:
    esc, esc_p = _escopo(classificacao)
    return con.execute(
        "SELECT pacote_id, SUM(valor_orcado) AS orcado FROM fact_orcamento "
        f"WHERE classificacao_contabil = ?{esc} GROUP BY pacote_id ORDER BY orcado DESC",
        [classificacao, *esc_p],
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
    esc, esc_p = _escopo(classificacao)
    return con.execute(
        "SELECT conta_interna_id AS conta, MAX(NULLIF(conta_interna_nome, '')) AS nome, "
        "SUM(valor_orcado) AS orcado FROM fact_orcamento "
        f"WHERE classificacao_contabil = ?{esc} GROUP BY conta_interna_id "
        "ORDER BY orcado DESC LIMIT ?",
        [classificacao, *esc_p, top_n],
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


# --------------------------------------------------------------------------- #
# Lado CAPEX: quebra por Elemento PEP / Disciplina / Tipo (2026-09-08).
# A aba "OPEX / CAPEX Sustaining" virou só "CAPEX Sustaining" — o lado OPEX
# foi distribuído nas sub-abas PM/PD/PP da aba "Pacotes" (ver docs/07 §3.2 e
# visao_manutencao.py). Aqui o CAPEX passa a ser fatiado por Elemento PEP
# (não por Pacote — é tudo PM03), nomeado pelo catálogo `dim_pep_sustaining`.
# NÃO tem Realizado nem Projeção: não existe execução de CAPEX Sustaining em
# fonte nenhuma (SAP não carrega classificação contábil) — inventar violaria
# a Regra de Ouro. `grupo_disciplina`/`tipo_item` só existem nas linhas de
# CAPEX da Base Zero, por isso essas quebras vivem aqui, não na aba Pacotes.
# --------------------------------------------------------------------------- #
def _catalogo_pep_disponivel(con: duckdb.DuckDBPyConnection) -> bool:
    try:
        con.execute("SELECT 1 FROM dim_pep_sustaining LIMIT 1")
        return True
    except Exception:
        return False


def _dados_por_pep(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Orçado CAPEX por Elemento PEP, com nome/disciplina do catálogo quando
    houver (o item coarse `ME/22001`, ~86% do total, não tem linha no
    catálogo — fica sem disciplina, mostrado como '(sem catálogo)')."""
    esc, esc_p = _escopo("CAPEX")
    if _catalogo_pep_disponivel(con):
        sql = (
            "SELECT f.pep_id AS pep, "
            "COALESCE(NULLIF(d.projeto_nome, ''), NULLIF(f.pep_nome, ''), '') AS nome, "
            "COALESCE(NULLIF(d.disciplina, ''), '(sem catálogo)') AS disciplina, "
            "SUM(f.valor_orcado) AS orcado "
            "FROM fact_orcamento f LEFT JOIN dim_pep_sustaining d ON f.pep_id = d.elemento_pep "
            f"WHERE f.classificacao_contabil = 'CAPEX'{esc} GROUP BY f.pep_id, nome, disciplina "
            "ORDER BY orcado DESC"
        )
    else:
        sql = (
            "SELECT pep_id AS pep, NULLIF(pep_nome, '') AS nome, "
            "'(sem catálogo)' AS disciplina, SUM(valor_orcado) AS orcado "
            f"FROM fact_orcamento WHERE classificacao_contabil = 'CAPEX'{esc} "
            "GROUP BY pep_id, nome ORDER BY orcado DESC"
        )
    return con.execute(sql, esc_p).df()


def _grafico_por_pep(df: pd.DataFrame, cor: str, top_n: int = 15) -> go.Figure | None:
    if df.empty:
        return None
    df = df.head(top_n).iloc[::-1].copy()
    df["rotulo"] = df.apply(lambda r: f'{r["pep"]} — {r["nome"]}' if r["nome"] else r["pep"], axis=1)
    fig = go.Figure(go.Bar(
        x=df["orcado"], y=df["rotulo"], orientation="h", marker_color=cor,
        text=[fmt_reais_abrev(v) for v in df["orcado"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Orçado: %{text}<extra></extra>",
    ))
    fig.update_layout(title="Orçado por Elemento PEP", margin={"t": 60, "b": 40, "r": 140})
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
    eh_capex = classificacao == "CAPEX"
    render_page_banner(
        _ICONE[classificacao], _TITULO[classificacao],
        "Só o Orçado é fatiado por Classificação Contábil — Realizado aparece como referência de Malha (SP) inteira.",
    )
    guardar_e_faixa_universo(con, UNIVERSO_POR_CLASSIFICACAO[classificacao])  # RBAC de escopo (docs/08)
    _badges_dominio()

    if eh_capex:
        st.info(
            "**Só Orçado.** Não existe Realizado de CAPEX Sustaining em fonte "
            "nenhuma — o SAP não carrega classificação contábil e cai 100% "
            "como OPEX (ver docs/07 §3.2). Por isso não há Orçado × Realizado "
            "nem Projeção aqui; o Realizado abaixo é a referência de Malha "
            "inteira (não fatiada), como no card."
        )

    resumo = resumo_classificacao(con, classificacao)
    nomes_pacote = mapa_nomes_pacote(con)

    # Card-resumo | divisória | gráfico macro. CAPEX -> por Elemento PEP
    # (tudo PM03, nomeado pelo catálogo); OPEX -> por Pacote (legado).
    def _visual_macro() -> None:
        if eh_capex:
            fig = _grafico_por_pep(_dados_por_pep(con), cor)
            chave = f"vc-{classificacao}-pep"
        else:
            fig = _grafico_por_pacote(_dados_por_pacote(con, classificacao), cor, nomes_pacote)
            chave = f"vc-{classificacao}-pacote"
        if fig:
            st.plotly_chart(fig, use_container_width=True, key=chave, config=CONFIG_PLOTLY)

    bloco_resumo_visual(
        lambda: _render_card_classificacao(classificacao, resumo),
        _visual_macro,
        key=f"vc-{classificacao}",
    )

    st.divider()
    fig_conta = _grafico_por_conta(_dados_por_conta(con, classificacao), cor, top_n=10)
    if fig_conta:
        st.plotly_chart(fig_conta, use_container_width=True, key=f"vc-{classificacao}-conta", config=CONFIG_PLOTLY)
