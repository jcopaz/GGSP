"""Fase 4 — Nível 1 (Diretoria): cards de Orçamento, Real Físico, Real
Contabilizado, Delta e Aderência, por GG.

Real Físico = Real Contabilizado: confirmado pelo usuário em 2026-08-06 que
a fonte de Real Físico é a mesma Base Analítico SAP já carregada, não uma
fonte separada (ver docs/02-perguntas-em-aberto.md, item 1 — resolvido).

Forecast continua "—": fonte do PMO ainda não recebida (item 2, em aberto).

**Card "DINFRA (total)" removido em 2026-08-10** (a pedido do usuário):
desde que o escopo do painel ficou restrito a 1 GG (`gg_escopo_dinfra` em
settings.yaml — ver item 5 de docs/02-perguntas-em-aberto.md), o card
sintético de total e o card do único GG real sempre mostravam exatamente
os mesmos números — card duplicado, sem valor. `GG_TOTAL` continua
existindo como conceito interno ("sem filtro, escopo inteiro") — é o que
a Visão Resumida Executiva usa, e o que `gg_padrao()` devolve de volta se
o escopo crescer para mais de 1 GG no futuro.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from src.branding import render_page_banner
from src.dashboard.filtros import clausula_periodo
from src.dashboard.formatacao import fmt_pct, fmt_reais_abrev, fmt_semaforo_chip
from src.engine.semaforo import classificar_semaforo

GG_TOTAL = "DINFRA"


def gg_padrao(con: duckdb.DuckDBPyConnection) -> str:
    """GG selecionado por padrão ao abrir o Painel Executivo, antes de
    qualquer clique em card. Com exatamente 1 GG em escopo (caso de hoje),
    aponta direto pra ele — não faz sentido abrir o Nível 2 num "total"
    sintético quando só existe 1 card real no Nível 1. Com 0 ou mais de 1
    GG, volta pro agregado `GG_TOTAL` (comportamento antigo)."""
    linhas = con.execute(
        "SELECT DISTINCT gg_id FROM fact_realizado WHERE gg_id IS NOT NULL"
    ).df()
    if len(linhas) == 1:
        return linhas["gg_id"].iloc[0]
    return GG_TOTAL


def resumo_nivel1(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """1 linha por GG presente na base — sem card de total sintético (ver
    decisão de 2026-08-10 no topo do módulo).

    Aderência = Realizado / Orçamento — confirmado batendo os números contra
    o Power BI de referência ("Visão Opex - DINFRA", pág. 1: 22.667.988 /
    39.320.140 = 57,65% = "Adr fin" mostrado; pág. 3: 21.666.621,90 /
    23.918.464,63 = 90,59%, também bate). Não é mais suposição.

    **Delta/Aderência usam `orcado_opex`, não `orcado` (total) — corrigido
    em 2026-08-11.** Desde que `fact_realizado` passou a vir só da
    Consulta de Contas (OPEX — ver build_star_schema.py), comparar
    Realizado contra o Orçado total (CAPEX+OPEX) misturava escopos: CAPEX
    Realizado não tem fonte ainda, então "Delta" contra o Orçado total
    aparecia gigante e enganoso (parecia estouro/economia de CAPEX, mas
    era só a ausência de dado). Orçado total (CAPEX+OPEX) continua exibido
    no card, só não entra mais na conta de Delta/Aderência.

    orcado_capex/orcado_opex: quebra de `classificacao_contabil`, coluna
    100% preenchida e sem conta com classificação mista (confirmado contra
    o dado real em 2026-08-10) — por isso vira eixo principal do card. Só
    existe do lado do Orçado: Realizado (SAP) não carrega essa coluna por
    linha, então não tem "realizado_capex"/"realizado_opex" aqui (ver
    docs/02-perguntas-em-aberto.md, item 11).

    Orçado CAPEX por GG individual só existe quando aquele `gg_id` aparece
    de fato em linha de CAPEX (na prática, hoje, só quando há exatamente 1
    GG no escopo — Base Zero não tem coluna própria de GG, ver GAP em
    `_atribuir_gg_orcamento`, build_star_schema.py). Por isso a consulta de
    CAPEX por GG usa `LEFT JOIN`, não fillna: um GG sem CAPEX atribuído
    fica `NaN` (não 0 — 0 sugeriria "esse GG não tem CAPEX", quando na
    verdade é "não sabemos"). Todas as consultas por GG filtram `WHERE
    gg_id IS NOT NULL` — sem isso, sobraria um card "fantasma" sem nome
    juntando tudo que não tem GG atribuído.

    Orçado OPEX por GG já é real desde 2026-08-10 (Consulta de Contas
    carrega `gg_id` por linha, ver decisão em build_star_schema.py).

    `CAST(... AS VARCHAR)` evita erro de merge float64 x str quando a
    coluna nula do DuckDB volta como float64 pro pandas.
    """
    where_periodo, params_periodo = clausula_periodo()
    orcado_gg = con.execute(
        f"SELECT CAST(gg_id AS VARCHAR) AS gg_id, gg_nome, SUM(valor_orcado) AS orcado "
        f"FROM fact_orcamento WHERE gg_id IS NOT NULL{where_periodo} GROUP BY gg_id, gg_nome",
        params_periodo,
    ).df()
    orcado_capex_gg = con.execute(
        f"SELECT CAST(gg_id AS VARCHAR) AS gg_id, SUM(valor_orcado) AS orcado_capex "
        f"FROM fact_orcamento WHERE gg_id IS NOT NULL AND classificacao_contabil = 'CAPEX'{where_periodo} "
        f"GROUP BY gg_id",
        params_periodo,
    ).df()
    orcado_opex_gg = con.execute(
        f"SELECT CAST(gg_id AS VARCHAR) AS gg_id, SUM(valor_orcado) AS orcado_opex "
        f"FROM fact_orcamento WHERE gg_id IS NOT NULL AND classificacao_contabil = 'OPEX'{where_periodo} "
        f"GROUP BY gg_id",
        params_periodo,
    ).df()
    realizado_gg = con.execute(
        f"SELECT CAST(gg_id AS VARCHAR) AS gg_id, gg_nome, SUM(valor_realizado) AS realizado "
        f"FROM fact_realizado WHERE gg_id IS NOT NULL{where_periodo} GROUP BY gg_id, gg_nome",
        params_periodo,
    ).df()

    orcado_por_gg_disponivel = not orcado_gg.empty

    if orcado_por_gg_disponivel:
        por_gg = orcado_gg.merge(realizado_gg, on=["gg_id", "gg_nome"], how="outer")
        por_gg = por_gg.merge(orcado_capex_gg, on="gg_id", how="left")
        por_gg = por_gg.merge(orcado_opex_gg, on="gg_id", how="left")
        por_gg["orcado"] = por_gg["orcado"].fillna(0.0)
        por_gg["orcado_opex"] = por_gg["orcado_opex"].fillna(0.0)
        # orcado_capex fica sem fillna de propósito — ver docstring.
    else:
        # float("nan"), não pd.NA: pd.NA quebra em comparação booleana
        # direta (`delta > 0` com delta = realizado - pd.NA vira pd.NA, e
        # `if pd.NA` levanta TypeError) — NaN float participa de `>`/`<`
        # normalmente (sempre False), sem exceção.
        por_gg = realizado_gg.copy()
        por_gg["orcado"] = float("nan")
        por_gg["orcado_capex"] = float("nan")
        por_gg["orcado_opex"] = float("nan")
    por_gg["realizado"] = por_gg["realizado"].fillna(0.0)

    resultado = por_gg.sort_values("gg_id").reset_index(drop=True)
    resultado["delta_total"] = resultado["realizado"] - resultado["orcado_opex"]
    resultado["aderencia"] = resultado.apply(
        lambda r: (r["realizado"] / r["orcado_opex"]) if pd.notna(r["orcado_opex"]) and r["orcado_opex"] else None,
        axis=1,
    )
    return resultado


def _render_card_gg(linha: pd.Series) -> None:
    """Card redesenhado em 2026-08-27 (casca visual aprovada pelo usuário
    — ver artefato de proposta na mesma sessão): hierarquia rótulo →
    número grande → chip de status, em vez da tabela markdown antiga.
    HTML próprio (não `st.container(border=True)`) porque o container
    nativo não aceita CSS livre — mesma limitação que motivou a troca.

    Real Físico não aparece separado de Real Contabilizado: são o mesmo
    valor por definição (ver docstring do módulo, confirmado 2026-08-06)
    — mostrar os dois rótulos com o mesmo número era redundante.
    """
    delta = linha["delta_total"]
    rotulo = linha["gg_nome"] or linha["gg_id"]
    # Só por Aderência aqui — sem a checagem de Roxo (delta sem
    # justificativa), que exige o cálculo de causa feito no Nível 2/Resumo
    # Executivo, não disponível neste card (ver src/engine/semaforo.py).
    status_semaforo = classificar_semaforo(linha["aderencia"])

    orcado = linha["orcado"] or 0
    pct_capex = (linha["orcado_capex"] / orcado * 100) if orcado else 0
    pct_opex = (linha["orcado_opex"] / orcado * 100) if orcado else 0
    cor_delta = "#a8071a" if delta > 0 else "#237804" if delta < 0 else "#5b6b85"
    sinal = "+" if delta > 0 else ""

    st.markdown(
        f"""
        <div style="background:#fff;border:1px solid #dfe5ef;border-radius:12px;
            padding:1.15rem 1.25rem 1.05rem;box-shadow:0 1px 2px rgba(15,34,64,0.06);
            margin-bottom:0.9rem;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.7rem;">
            <div>
              <div style="font-weight:600;font-size:0.92rem;color:#16213a;">{rotulo}</div>
              <div style="font-size:0.72rem;color:#8697b3;margin-top:0.1rem;">OPEX × OPEX</div>
            </div>
            {fmt_semaforo_chip(status_semaforo)}
          </div>
          <div style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:1.5rem;
              font-weight:500;color:{cor_delta};margin-bottom:0.65rem;">
            {sinal}{fmt_reais_abrev(delta)}
            <span style="font-family:'IBM Plex Sans',sans-serif;font-size:0.72rem;color:#8697b3;font-weight:400;">
                · {fmt_pct(linha["aderencia"])} aderência
            </span>
          </div>
          <div style="display:flex;gap:0.7rem;font-size:0.72rem;margin-bottom:0.6rem;">
            <div style="flex:1;">
              <div style="display:flex;justify-content:space-between;color:#8697b3;margin-bottom:0.28rem;">
                CAPEX <b style="color:#16213a;font-family:'IBM Plex Mono',monospace;font-weight:500;">{fmt_reais_abrev(linha["orcado_capex"])}</b>
              </div>
              <div style="height:4px;border-radius:2px;background:#f5f7fb;overflow:hidden;">
                <div style="height:100%;width:{pct_capex:.0f}%;background:#1f3864;"></div>
              </div>
            </div>
            <div style="flex:1;">
              <div style="display:flex;justify-content:space-between;color:#8697b3;margin-bottom:0.28rem;">
                OPEX <b style="color:#16213a;font-family:'IBM Plex Mono',monospace;font-weight:500;">{fmt_reais_abrev(linha["orcado_opex"])}</b>
              </div>
              <div style="height:4px;border-radius:2px;background:#f5f7fb;overflow:hidden;">
                <div style="height:100%;width:{pct_opex:.0f}%;background:#1f3864;"></div>
              </div>
            </div>
          </div>
          <div style="font-size:0.76rem;color:#5b6b85;border-top:1px solid #eef1f6;padding-top:0.5rem;">
            Orçamento {fmt_reais_abrev(orcado)} &nbsp;·&nbsp; Realizado {fmt_reais_abrev(linha["realizado"])} &nbsp;·&nbsp; Forecast —
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_nivel1(con: duckdb.DuckDBPyConnection) -> None:
    render_page_banner("🧭", "Diretoria", "Real/Delta/Aderência comparam só OPEX x OPEX — waterfall por causa (Nível 2) logo abaixo.")
    resumo = resumo_nivel1(con)
    colunas = st.columns(len(resumo))
    for coluna, (_, linha) in zip(colunas, resumo.iterrows()):
        with coluna:
            _render_card_gg(linha)
