"""Label do Especialista — CAPEX Obras, fonte `fact_pce_consolidado`
(Consolidado.xlsx, trazida em 2026-08-19 à tarde — substitui "PCE Base
Luiz.xlsx" como padrão de rotina pra essa Label e demais análises CAPEX,
pedido do usuário) e `fact_pce_realizado` (desde 2026-08-27, derivada em
código do CJI3 + Catálogo CAPEX Obras — ver
`build_star_schema._derivar_pce_realizado` — não depende mais de nenhum
arquivo separado; "PCE Base Luiz.xlsx" foi removido do pipeline).

Filtros próprios da página (Gerência / Classificação Atualizada / Grupo /
Versão), não os globais da sidebar (`filtros.py`) — essa base não
compartilha `pacote_id`/`gerencia_id` com `fact_orcamento`/`fact_realizado`,
é um universo à parte (mesmo padrão de isolamento do CJI4/CJI3).

**Duas granularidades de categoria de custo — não confundir (correção de
2026-08-19, 2 rodadas)**:
- `grupo` (`fact_pce_consolidado.grupo`/`fact_pce_realizado.grupo`) —
  categoria **grossa**, 9-10 valores (Custos do Proprietário, Obra/
  Pré-Obra, Owner's Engineering, Viagem, Escalation, Contingência,
  Capitalização, Rateios, Desafio, e às vezes Saving) — confirmada pelo
  usuário como a certa pro **filtro "Grupo" do topo da página** e pra
  tabela/gráfico "Por Grupo". Primeira tentativa (mesmo dia) tinha usado
  `descricao` aqui por engano, o que inflava o filtro pra 15-16 opções.
- `descricao` (`fact_pce_consolidado.descricao`, vinda da coluna
  `Descrição`; equivalente exato do lado Realizado é
  `fact_pce_realizado.descricao`, vinda da coluna `Classificação` — não
  `Classificação atualizada`, achado separado, ver `load_pce_realizado`)
  — categoria **fina** (SERVIÇOS, MATERIAIS, ENGENHARIA...), usada **só**
  pelos 8 blocos da seção "Análise por Grupo" mais abaixo (que precisam
  desse nível de detalhe pra isolar "Serviços sozinho", "SMA sozinho"
  etc.) — nunca pelo filtro do topo.

**Regra de agrupamento "Obra e Pré-Obra"/"Rateios" (2026-08-19, definida
pelo usuário a partir do de-para real Versão×Grupo×Descrição — a
classificação bruta é inconsistente entre versões, então isso é uma
normalização própria, não um filtro em cima da coluna `grupo`)**:
- **Obra e Pré-Obra** = Desafio + Engenharia + Equipamentos +
  Fundiário_RI_Regulatório + Indiretos MRS + Materiais + Rateios +
  Serviços + SMA.
- **Rateios** = Desafio + Engenharia + Fundiário_RI_Regulatório + Rateios
  (repara: 4 dessas Descrições também entram em "Obra e Pré-Obra" — os
  dois grupos propositalmente se sobrepõem, "Rateios" é um recorte
  transversal, não uma partição exclusiva).

**Versão — Orçado x Forecast (2026-08-19, confirmado com o usuário)**:
"Orçado" nos 8 blocos de análise é sempre `Orçamento 2026` (fixo); o
filtro de Versão no topo da página escolhe qual vira "Forecast" — se o
usuário escolher o próprio `Orçamento 2026` como Versão, Forecast e
Orçado saem iguais (caso degenerado, não é erro).

Não mistura Versão (pedido explícito do usuário: "não misture versões,
analise separadamente por coluna Versão").

**Paleta MRS pro par Orçado x Forecast (2026-08-19)**: Azul (`COR_ORCADO`)
= Orçado, Amarelo (`COR_CAPEX_FORECAST`) = Forecast — padrão definido
pelo usuário pra todo gráfico CAPEX Obras, não só esta página. Ver
docstring de `COR_CAPEX_FORECAST` em `paleta.py` pra por que não é o
mesmo símbolo que `COR_FORECAST` (cinza, convenção do universo OPEX).

**Análise Individual é opt-in (2026-08-19, pedido do usuário)**: os 8
blocos de `_BLOCOS_ANALISE` não renderizam mais todos de uma vez — um
`st.selectbox` deixa a pessoa escolher 1 análise por vez (ex.: "Obra e
Pré-Obra"), só então os gráficos/tabela são calculados e mostrados. Cada
análise mostra 2 gráficos no mesmo formato (barras do período + linhas
Acumulado no eixo Y secundário): **Mensal** (eixo X = mês 1-12,
`_serie_mensal` soma todo Exercício/ano que cair no recorte pra dentro
do mesmo mês — é o perfil sazonal do projeto inteiro, não só de 1 ano)
e **Plurianual** (eixo X = Exercício/ano, todo o intervalo que existe em
`fact_pce_consolidado` — ver `_anos_disponiveis` — é o mesmo total
quebrado pelo outro eixo), mais a tabela por Empreendimento já existente.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.branding import render_page_banner
from src.dashboard.formatacao import fmt_pct, fmt_reais_abrev
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.paleta import (
    COR_ADERENCIA_ATENCAO, COR_CAPEX_FORECAST, COR_ECONOMIA, COR_ESTOURO,
    COR_NEUTRO, COR_ORCADO, COR_REGIAO_VP,
)

_VERSAO_ORCADO = "Orçamento 2026"
# Ano-âncora da tabela/gráfico Mensal da seção "Visão — Mensal e
# Plurianual" (2026-08-19) — mesmo ano de `_VERSAO_ORCADO`. Confirmado
# batendo com o print de referência do usuário: a soma dos 12 meses da
# tabela "2026" fecha exato com a coluna "2026" da tabela "Pluri" ao
# lado — só faz sentido se o Mensal for filtrado nesse 1 ano, diferente
# do Mensal dos 8 blocos de Análise Individual (`_serie_mensal` sem
# `ano`), que soma todo Exercício no mesmo mês de propósito (perfil
# sazonal do projeto inteiro).
_ANO_MENSAL_PADRAO = 2026
_GRUPOS_DESTAQUE = ["CONTINGÊNCIA", "ESCALATION", "CAPITALIZAÇÃO"]

# Paleta da "Análise Comparativa" (2026-08-19, pedido do usuário: comparar
# N Versões, não só o par Orçado x Forecast) — a Versão base escolhida
# sempre usa `COR_ORCADO` (azul, mesma regra MRS); as demais Versões
# selecionadas pra comparação ciclam por aqui, 1 cor cada, na ordem em
# que foram escolhidas. Primeira cor é `COR_CAPEX_FORECAST` (amarelo) de
# propósito — quando só 1 Versão é comparada contra a base, o resultado
# visual é idêntico ao par Orçado/Forecast já usado no resto da página.
_PALETA_COMPARACAO = [
    COR_CAPEX_FORECAST, COR_ESTOURO, COR_ECONOMIA, COR_REGIAO_VP,
    COR_ADERENCIA_ATENCAO, COR_NEUTRO,
]

_GRUPO_OBRA_PRE_OBRA = [
    "DESAFIO", "ENGENHARIA", "EQUIPAMENTOS", "FUNDIÁRIO_RI_REGULATÓRIO",
    "INDIRETOS MRS", "MATERIAIS", "RATEIOS", "SERVIÇOS", "SMA",
]
_GRUPO_RATEIOS = ["DESAFIO", "ENGENHARIA", "FUNDIÁRIO_RI_REGULATÓRIO", "RATEIOS"]

# Os 8 blocos da seção "Análise" — 2 agrupados (definição acima) + 6
# individuais (pedido do usuário: "somente ele"). Ordem = ordem pedida.
_BLOCOS_ANALISE: list[tuple[str, list[str]]] = [
    ("Obra e Pré-Obra", _GRUPO_OBRA_PRE_OBRA),
    ("Rateios", _GRUPO_RATEIOS),
    ("Serviços", ["SERVIÇOS"]),
    ("SMA", ["SMA"]),
    ("Contingência", ["CONTINGÊNCIA"]),
    ("Custo do Proprietário", ["CUSTOS DO PROPRIETÁRIO"]),
    ("Escalation", ["ESCALATION"]),
    ("Owner's Engineering", ["OWNER'S ENGINEERING"]),
]

_NOMES_MES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
              7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def _opcoes(con: duckdb.DuckDBPyConnection, coluna: str, versao: str | None = None) -> list[str]:
    """`versao` opcional filtra as opções pra só o que existe naquela
    Versão (usado pelo filtro Grupo — 2026-08-19, a pedido do usuário:
    trocar de Versão não deve deixar Grupo mostrando opção que não existe
    ali)."""
    where = f"WHERE {coluna} IS NOT NULL AND {coluna} != ''"
    params: list = []
    if versao is not None:
        where += " AND versao = ?"
        params.append(versao)
    df = con.execute(
        f"SELECT DISTINCT {coluna} FROM fact_pce_consolidado {where} ORDER BY 1",
        params,
    ).df()
    return df[coluna].tolist()


def _clausula_lista(coluna: str, valores: list[str]) -> tuple[str, list[str]]:
    if not valores:
        return "", []
    marcadores = ", ".join("?" * len(valores))
    return f" AND {coluna} IN ({marcadores})", list(valores)


def _filtros_extra(
    gerencias: list[str], classificacoes: list[str], valores: list[str] | None = None,
    coluna: str = "descricao",
) -> tuple[str, list]:
    """`coluna` decide se o 3º filtro cai na coluna fina (`descricao`,
    usada pelos 8 blocos de "Análise por Grupo") ou na coluna grossa
    (`grupo`, usada pelo filtro "Grupo" do topo da página — corrigido em
    2026-08-19, o filtro do topo tinha ficado errado usando `descricao`,
    virando 15-16 opções em vez das 9-10 que o usuário confirmou como
    corretas: Custos do Proprietário, Obra/Pré-Obra, Owner's Engineering,
    Viagem, Escalation, Contingência, Capitalização, Rateios, Desafio)."""
    where = ""
    params: list = []
    pares = [("gerencia_obras", gerencias), ("classificacao_atualizada", classificacoes)]
    if valores is not None:
        pares.append((coluna, valores))
    for col, vals in pares:
        frag, p = _clausula_lista(col, vals)
        where += frag
        params += p
    return where, params


def dados_pce_grupo(
    con: duckdb.DuckDBPyConnection, versao: str,
    gerencias: list[str], classificacoes: list[str], grupos: list[str],
) -> pd.DataFrame:
    """Orçado/Forecast por Grupo (categoria grossa, `grupo` — Obra/Pré-
    Obra, Custos do Proprietário, Escalation etc.), 1 linha por Grupo,
    dentro dos filtros escolhidos."""
    frag, params_extra = _filtros_extra(gerencias, classificacoes, grupos, coluna="grupo")
    where = " WHERE versao = ?" + frag
    params = [versao] + params_extra
    return con.execute(
        f"SELECT grupo, SUM(valor) AS valor "
        f"FROM fact_pce_consolidado{where} GROUP BY 1 ORDER BY 2 DESC",
        params,
    ).df()


def _tabela_pce_realizado_existe(con: duckdb.DuckDBPyConnection) -> bool:
    """`fact_pce_realizado` é derivada do CJI3 (ver
    `build_star_schema._derivar_pce_realizado`) — só existe se o CJI3
    também tiver sido carregado. Sem isso, a query direto na tabela
    quebra com duckdb.CatalogException (visto em produção 2026-08-27, ver
    docs/04-licoes-aprendidas.md). Checar antes de consultar em vez de
    deixar quebrar."""
    (n,) = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fact_pce_realizado'"
    ).fetchone()
    return n > 0


def dados_pce_realizado_total(
    con: duckdb.DuckDBPyConnection, gerencias: list[str], classificacoes: list[str],
    valores: list[str] | None = None, coluna: str = "descricao",
) -> float:
    """Total Realizado dentro do recorte — `valores`/`coluna` opcionais
    (`fact_pce_realizado` tem tanto `grupo` quanto `descricao`, mesmos
    nomes de coluna que `fact_pce_consolidado` — ver docstring do módulo).
    Devolve 0.0 se `fact_pce_realizado` ainda não existir (arquivo PCE
    Base Luiz.xlsx ainda não enviado)."""
    if not _tabela_pce_realizado_existe(con):
        return 0.0
    frag, params = _filtros_extra(gerencias, classificacoes, valores, coluna=coluna)
    where = " WHERE 1=1" + frag
    (valor,) = con.execute(
        f"SELECT COALESCE(SUM(valor_realizado), 0) FROM fact_pce_realizado{where}",
        params,
    ).fetchone()
    return float(valor)


def _serie_mensal(
    con: duckdb.DuckDBPyConnection, versao: str, valores: list[str],
    gerencias: list[str], classificacoes: list[str],
    coluna: str = "descricao", ano: int | None = None,
) -> pd.DataFrame:
    """1 linha por mês (1-12), valor do mês + acumulado — meses sem linha
    na base entram como 0, não ficam faltando (pra Acumulado ficar
    contínuo). Sem `ano`, soma todo Exercício que cair no recorte pra
    dentro do mesmo mês (perfil sazonal do projeto inteiro — uso dos 8
    blocos de Análise Individual, por `descricao`). Com `ano` (usado pela
    seção "Visão por Gerência" — filtro do topo, por `grupo` — 2026-08-19,
    pedido do usuário: a tabela Mensal ali é só do ano corrente, pra bater
    exato com a coluna do ano equivalente na tabela Plurianual ao lado),
    filtra pra só aquele Exercício."""
    frag, params_extra = _filtros_extra(gerencias, classificacoes, valores, coluna=coluna)
    where = " WHERE versao = ?" + frag
    params = [versao] + params_extra
    if ano is not None:
        where += " AND ano = ?"
        params.append(ano)
    df = con.execute(
        f"SELECT mes, SUM(valor) AS valor FROM fact_pce_consolidado{where} "
        f"GROUP BY 1", params,
    ).df()
    completo = pd.DataFrame({"mes": range(1, 13)}).merge(df, on="mes", how="left")
    completo["valor"] = completo["valor"].fillna(0.0)
    completo["acumulado"] = completo["valor"].cumsum()
    completo["mes_nome"] = completo["mes"].map(_NOMES_MES)
    return completo


def _anos_disponiveis(con: duckdb.DuckDBPyConnection) -> list[int]:
    """Todo `ano` (Exercício) que existe em `fact_pce_consolidado`, sem
    filtro nenhum — eixo fixo do gráfico Plurianual (mesmo papel do 1-12
    fixo do Mensal), pra Acumulado ficar contínuo mesmo em recorte com
    ano vazio no meio ("os exercícios anteriores ou posteriores que tem
    na coluna exercício da base consolidada", pedido do usuário)."""
    df = con.execute(
        "SELECT DISTINCT ano FROM fact_pce_consolidado WHERE ano IS NOT NULL ORDER BY 1"
    ).df()
    return df["ano"].dropna().astype(int).tolist()


def _serie_anual(
    con: duckdb.DuckDBPyConnection, versao: str, valores: list[str],
    gerencias: list[str], classificacoes: list[str], anos: list[int],
    coluna: str = "descricao",
) -> pd.DataFrame:
    """Equivalente a `_serie_mensal`, mas por Exercício (ano) — pro
    gráfico Plurianual."""
    frag, params_extra = _filtros_extra(gerencias, classificacoes, valores, coluna=coluna)
    where = " WHERE versao = ?" + frag
    params = [versao] + params_extra
    df = con.execute(
        f"SELECT ano, SUM(valor) AS valor FROM fact_pce_consolidado{where} "
        f"GROUP BY 1", params,
    ).df()
    completo = pd.DataFrame({"ano": anos}).merge(df, on="ano", how="left")
    completo["valor"] = completo["valor"].fillna(0.0)
    completo["acumulado"] = completo["valor"].cumsum()
    completo["ano_nome"] = completo["ano"].astype(int).astype(str)
    return completo


def _dados_empreendimento_bloco(
    con: duckdb.DuckDBPyConnection, versao_forecast: str, descricoes: list[str],
    gerencias: list[str], classificacoes: list[str],
) -> pd.DataFrame:
    """Orçado (Orçamento 2026 fixo) x Forecast (versão escolhida) x
    Realizado, por Empreendimento, pro recorte de Descrição do bloco."""
    frag, params_extra = _filtros_extra(gerencias, classificacoes, descricoes)

    orc = con.execute(
        f"SELECT e_pep_projeto, nome_empreendimento, SUM(valor) AS orcado "
        f"FROM fact_pce_consolidado WHERE versao = ?{frag} GROUP BY 1,2",
        [_VERSAO_ORCADO] + params_extra,
    ).df()
    fc = con.execute(
        f"SELECT e_pep_projeto, SUM(valor) AS forecast "
        f"FROM fact_pce_consolidado WHERE versao = ?{frag} GROUP BY 1",
        [versao_forecast] + params_extra,
    ).df()
    if _tabela_pce_realizado_existe(con):
        real = con.execute(
            f"SELECT e_pep_projeto, SUM(valor_realizado) AS realizado "
            f"FROM fact_pce_realizado WHERE 1=1{frag} GROUP BY 1",
            params_extra,
        ).df()
    else:
        real = pd.DataFrame(columns=["e_pep_projeto", "realizado"])

    df = orc.merge(fc, on="e_pep_projeto", how="outer").merge(real, on="e_pep_projeto", how="outer")
    df[["orcado", "forecast", "realizado"]] = df[["orcado", "forecast", "realizado"]].fillna(0.0)
    df["nome_empreendimento"] = df["nome_empreendimento"].fillna("")
    df["aderencia"] = df.apply(lambda r: (r["realizado"] / r["orcado"]) if r["orcado"] else None, axis=1)
    return df.sort_values("orcado", ascending=False)


def _grafico_combo(
    df_orcado: pd.DataFrame, df_forecast: pd.DataFrame, titulo: str,
    coluna_x: str = "mes_nome", rotulo_periodo: str = "Mensal",
) -> go.Figure:
    """Barras (Orçado x Forecast do período) + linhas (Orçado x Forecast
    Acumulado, eixo Y secundário) — mesmo formato pro bloco Mensal
    (`coluna_x="mes_nome"`) e pro bloco Plurianual (`coluna_x="ano_nome"`,
    `rotulo_periodo="Anual"`), só troca o eixo X/rótulo. Paleta MRS
    (2026-08-19, padrão pro universo CAPEX Obras): Orçado sempre azul
    (`COR_ORCADO`), Forecast sempre amarelo (`COR_CAPEX_FORECAST`)."""
    fig = go.Figure()
    fig.add_bar(
        name=f"Orçado {rotulo_periodo}", x=df_orcado[coluna_x], y=df_orcado["valor"],
        marker_color=COR_ORCADO, offsetgroup=0,
        hovertemplate="Orçado %{x}: %{customdata}<extra></extra>",
        customdata=[fmt_reais_abrev(v) for v in df_orcado["valor"]],
    )
    fig.add_bar(
        name=f"Forecast {rotulo_periodo}", x=df_forecast[coluna_x], y=df_forecast["valor"],
        marker_color=COR_CAPEX_FORECAST, offsetgroup=1,
        hovertemplate="Forecast %{x}: %{customdata}<extra></extra>",
        customdata=[fmt_reais_abrev(v) for v in df_forecast["valor"]],
    )
    fig.add_trace(go.Scatter(
        name="Orçado Acumulado", x=df_orcado[coluna_x], y=df_orcado["acumulado"],
        mode="lines+markers", yaxis="y2", line={"color": COR_ORCADO, "width": 2.5},
        hovertemplate="Orçado acum. %{x}: %{customdata}<extra></extra>",
        customdata=[fmt_reais_abrev(v) for v in df_orcado["acumulado"]],
    ))
    fig.add_trace(go.Scatter(
        name="Forecast Acumulado", x=df_forecast[coluna_x], y=df_forecast["acumulado"],
        mode="lines+markers", yaxis="y2", line={"color": COR_CAPEX_FORECAST, "width": 2.5, "dash": "dot"},
        hovertemplate="Forecast acum. %{x}: %{customdata}<extra></extra>",
        customdata=[fmt_reais_abrev(v) for v in df_forecast["acumulado"]],
    ))
    fig.update_layout(
        title=titulo, barmode="group", margin={"t": 60, "b": 40},
        yaxis={"title": rotulo_periodo},
        yaxis2={"title": "Acumulado", "overlaying": "y", "side": "right", "showgrid": False},
        legend={"orientation": "h", "y": -0.18},
        hovermode="x unified",
    )
    return fig


def _grafico_combo_multi(
    series: list[tuple[str, pd.DataFrame, str]], titulo: str,
    coluna_x: str = "mes_nome", rotulo_periodo: str = "Mensal",
) -> go.Figure:
    """Generalização de `_grafico_combo` pra N Versões em vez de só o par
    Orçado x Forecast — usada pela "Análise Comparativa" (2026-08-19,
    pedido do usuário: comparar 2 ou mais Versões, inclusive todas as
    Forecast/FC* de uma vez, contra 1 Versão base). Cada item de `series`
    já vem com sua própria cor (ver `_PALETA_COMPARACAO` — a base sempre
    `COR_ORCADO`, comparações cicladas nas demais cores)."""
    fig = go.Figure()
    for i, (nome, df, cor) in enumerate(series):
        fig.add_bar(
            name=f"{nome} {rotulo_periodo}", x=df[coluna_x], y=df["valor"],
            marker_color=cor, offsetgroup=i,
            hovertemplate=f"{nome} %{{x}}: %{{customdata}}<extra></extra>",
            customdata=[fmt_reais_abrev(v) for v in df["valor"]],
        )
        fig.add_trace(go.Scatter(
            name=f"{nome} Acumulado", x=df[coluna_x], y=df["acumulado"],
            mode="lines+markers", yaxis="y2", line={"color": cor, "width": 2.5, "dash": "dot"},
            hovertemplate=f"{nome} acum. %{{x}}: %{{customdata}}<extra></extra>",
            customdata=[fmt_reais_abrev(v) for v in df["acumulado"]],
        ))
    fig.update_layout(
        title=titulo, barmode="group", margin={"t": 60, "b": 40},
        yaxis={"title": rotulo_periodo},
        yaxis2={"title": "Acumulado", "overlaying": "y", "side": "right", "showgrid": False},
        legend={"orientation": "h", "y": -0.25},
        hovermode="x unified",
    )
    return fig


def _fmt_num_tabela(valor: float | None) -> str:
    """Número pt-BR sem "R$" e com precisão cheia (centavos) — a tabela
    "padrão" (print de referência do usuário, 2026-08-19) mostra o valor
    exato, não abreviado (`fmt_reais_abrev` é pra card/gráfico, não pra
    essa tabela). Zero/None vira "-", igual ao print."""
    if valor is None or pd.isna(valor) or valor == 0:
        return "-"
    texto = f"{abs(valor):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}{texto}"


def _tabela_periodo_html(rotulo_periodo: str, colunas: list[str], linhas: dict[str, list[str]]) -> str:
    """Tabela HTML no "padrão" que o usuário trouxe como print de
    referência (2026-08-19): barra azul no topo com o rótulo do período
    (mês ou ano) + coluna de rótulo das 4 linhas destacada em dourado —
    mesma paleta MRS (`COR_ORCADO`/`COR_CAPEX_FORECAST`) do resto da
    página. `st.dataframe` não dá esse controle de estilo por célula sem
    reimplementar em `pandas.Styler` (suporte parcial no Streamlit); HTML
    direto é mais previsível aqui, mesmo padrão já usado em
    `mapa_calor_gerencia_pacote.py`/`arvore_html.py` pro mesmo motivo.
    `linhas` já vem formatada (`_fmt_num_tabela`) — função só monta o
    HTML, não formata número."""
    cabecalho = "".join(
        f'<th style="background:{COR_ORCADO};color:#fff;padding:6px 10px;'
        f'text-align:right;white-space:nowrap;font-size:0.85rem;">{c}</th>'
        for c in colunas
    )
    linhas_html = ""
    for rotulo, valores in linhas.items():
        celulas = "".join(
            f'<td style="padding:6px 10px;text-align:right;white-space:nowrap;'
            f'font-size:0.85rem;border-bottom:1px solid #e6e6e6;">{v}</td>'
            for v in valores
        )
        linhas_html += (
            f'<tr><td style="background:{COR_CAPEX_FORECAST};color:#1f1f1f;'
            f'font-weight:600;padding:6px 10px;white-space:nowrap;'
            f'font-size:0.85rem;border-bottom:1px solid #e6e6e6;">{rotulo}</td>{celulas}</tr>'
        )
    return (
        '<div style="overflow-x:auto;margin-bottom:1rem;">'
        '<table style="border-collapse:collapse;width:100%;">'
        f'<tr><th style="background:{COR_ORCADO};color:#fff;padding:6px 10px;'
        f'text-align:left;white-space:nowrap;font-size:0.85rem;">{rotulo_periodo}</th>{cabecalho}</tr>'
        f"{linhas_html}"
        "</table></div>"
    )


def _render_visao_mensal_plurianual(
    con: duckdb.DuckDBPyConnection, versao_forecast: str,
    gerencias: list[str], classificacoes: list[str], grupos: list[str], anos: list[int],
) -> None:
    """Seção "Visão — Mensal e Plurianual" (2026-08-19, pedido do
    usuário): tabelas + gráficos no recorte dos filtros do TOPO da
    página (Gerência/Classificação Atualizada/Grupo — coluna `grupo`,
    igual à seção "Por Grupo" ao redor) — diferente dos 8 blocos de
    "Análise Individual" mais abaixo, que filtram por
    `descricao` e exigem escolher 1 análise por vez. Objetivo do usuário:
    "quando filtrar a Gerência lá em cima, ter a mesma visão por Gerência
    do realizado mês a mês e o plurianual" sem precisar entrar em nenhuma
    Análise Individual específica."""
    df_orc_mes = _serie_mensal(
        con, _VERSAO_ORCADO, grupos, gerencias, classificacoes,
        coluna="grupo", ano=_ANO_MENSAL_PADRAO,
    )
    df_fc_mes = _serie_mensal(
        con, versao_forecast, grupos, gerencias, classificacoes,
        coluna="grupo", ano=_ANO_MENSAL_PADRAO,
    )
    df_orc_ano = _serie_anual(con, _VERSAO_ORCADO, grupos, gerencias, classificacoes, anos, coluna="grupo")
    df_fc_ano = _serie_anual(con, versao_forecast, grupos, gerencias, classificacoes, anos, coluna="grupo")

    rotulo_forecast = f"Forecast ({versao_forecast})"
    st.markdown(
        _tabela_periodo_html(
            str(_ANO_MENSAL_PADRAO), list(_NOMES_MES.values()),
            {
                f"Orçado {_ANO_MENSAL_PADRAO}": [_fmt_num_tabela(v) for v in df_orc_mes["valor"]],
                f"Orçado {_ANO_MENSAL_PADRAO} Acumulado": [_fmt_num_tabela(v) for v in df_orc_mes["acumulado"]],
                rotulo_forecast: [_fmt_num_tabela(v) for v in df_fc_mes["valor"]],
                "Forecast Acumulado": [_fmt_num_tabela(v) for v in df_fc_mes["acumulado"]],
            },
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        _tabela_periodo_html(
            "Pluri", [str(a) for a in anos],
            {
                f"Orçado {_ANO_MENSAL_PADRAO}": [_fmt_num_tabela(v) for v in df_orc_ano["valor"]],
                f"Orçado {_ANO_MENSAL_PADRAO} Acumulado": [_fmt_num_tabela(v) for v in df_orc_ano["acumulado"]],
                rotulo_forecast: [_fmt_num_tabela(v) for v in df_fc_ano["valor"]],
                "Forecast Acumulado": [_fmt_num_tabela(v) for v in df_fc_ano["acumulado"]],
            },
        ),
        unsafe_allow_html=True,
    )

    col_mes, col_ano = st.columns(2)
    with col_mes:
        st.plotly_chart(
            _grafico_combo(df_orc_mes, df_fc_mes, f"Distribuição Mensal ({_ANO_MENSAL_PADRAO})"),
            use_container_width=True, config=CONFIG_PLOTLY, key="pce-visao-combo-mensal",
        )
    with col_ano:
        st.plotly_chart(
            _grafico_combo(
                df_orc_ano, df_fc_ano, "Distribuição Plurianual",
                coluna_x="ano_nome", rotulo_periodo="Anual",
            ),
            use_container_width=True, config=CONFIG_PLOTLY, key="pce-visao-combo-anual",
        )


def _render_analise_comparativa(
    con: duckdb.DuckDBPyConnection, versoes_disponiveis: list[str],
    gerencias: list[str], classificacoes: list[str], grupos: list[str], anos: list[int],
) -> None:
    """Seção "Análise Comparativa — Versões" (2026-08-19, pedido do
    usuário): mesmo molde da "Visão — Mensal e Plurianual" (tabela Mensal
    do ano `_ANO_MENSAL_PADRAO` + tabela Plurianual + os 2 gráficos), mas
    generalizada pra N Versões escolhidas livremente (não só Orçado x 1
    Forecast fixo) — "quero comparar 2 versões, ou até mesmo todas as
    versões do Forecast em relação ao orçamento atual". `versao_base`
    (qualquer Versão, não só "Orçamento 2026" — o usuário citou
    "Orçamento 26, PN 26" como bases possíveis) sempre em `COR_ORCADO`
    azul; cada Versão de comparação recebe 1 cor própria de
    `_PALETA_COMPARACAO`, mesma cor nas tabelas e nos 2 gráficos.
    Opt-in: sem nenhuma Versão de comparação escolhida, não calcula nada."""
    st.divider()
    st.subheader("Análise Comparativa — Versões")
    st.caption(
        "Compare quantas Versões quiser (ex.: Orçamento 2026 x PN26, ou "
        "Orçamento 2026 x todas as Forecast FC*) — mesmo recorte dos "
        f"filtros do topo (Gerência/Classificação Atualizada/Grupo) e "
        f"mesmo molde da \"Visão — Mensal e Plurianual\" acima (Mensal só "
        f"o ano {_ANO_MENSAL_PADRAO}, Plurianual cobre todo Exercício da "
        "base)."
    )
    col_base, col_comp = st.columns([1, 2])
    versao_padrao = _VERSAO_ORCADO if _VERSAO_ORCADO in versoes_disponiveis else versoes_disponiveis[0]
    with col_base:
        versao_base = st.selectbox(
            "Versão base", versoes_disponiveis,
            index=versoes_disponiveis.index(versao_padrao),
            key="pce-comparativa-base",
        )
    with col_comp:
        # key inclui a Versão base de propósito, mesmo padrão já usado no
        # filtro Grupo do topo — trocar a base muda as opções disponíveis
        # (a base não pode aparecer nas comparações), Streamlit quebraria
        # se a seleção antiga tivesse a Versão que virou a base nova.
        versoes_comparacao = st.multiselect(
            "Versões para comparar com a base",
            [v for v in versoes_disponiveis if v != versao_base],
            key=f"pce-comparativa-versoes-{versao_base}",
            help="Escolha 1 ou mais — inclusive todas as Forecast (FC*) de uma vez.",
        )
    if not versoes_comparacao:
        st.info("Selecione ao menos 1 Versão pra comparar com a base.")
        return

    versoes_selecionadas = [versao_base] + versoes_comparacao
    cores = {versao_base: COR_ORCADO}
    for i, v in enumerate(versoes_comparacao):
        cores[v] = _PALETA_COMPARACAO[i % len(_PALETA_COMPARACAO)]

    series_mes = {
        v: _serie_mensal(con, v, grupos, gerencias, classificacoes, coluna="grupo", ano=_ANO_MENSAL_PADRAO)
        for v in versoes_selecionadas
    }
    series_ano = {
        v: _serie_anual(con, v, grupos, gerencias, classificacoes, anos, coluna="grupo")
        for v in versoes_selecionadas
    }

    linhas_mes: dict[str, list[str]] = {}
    linhas_ano: dict[str, list[str]] = {}
    for v in versoes_selecionadas:
        linhas_mes[v] = [_fmt_num_tabela(x) for x in series_mes[v]["valor"]]
        linhas_mes[f"{v} Acumulado"] = [_fmt_num_tabela(x) for x in series_mes[v]["acumulado"]]
        linhas_ano[v] = [_fmt_num_tabela(x) for x in series_ano[v]["valor"]]
        linhas_ano[f"{v} Acumulado"] = [_fmt_num_tabela(x) for x in series_ano[v]["acumulado"]]

    st.markdown(
        _tabela_periodo_html(str(_ANO_MENSAL_PADRAO), list(_NOMES_MES.values()), linhas_mes),
        unsafe_allow_html=True,
    )
    st.markdown(
        _tabela_periodo_html("Pluri", [str(a) for a in anos], linhas_ano),
        unsafe_allow_html=True,
    )

    col_mes, col_ano = st.columns(2)
    with col_mes:
        st.plotly_chart(
            _grafico_combo_multi(
                [(v, series_mes[v], cores[v]) for v in versoes_selecionadas],
                f"Distribuição Mensal ({_ANO_MENSAL_PADRAO}) — Comparativo",
            ),
            use_container_width=True, config=CONFIG_PLOTLY, key="pce-comparativa-combo-mensal",
        )
    with col_ano:
        st.plotly_chart(
            _grafico_combo_multi(
                [(v, series_ano[v], cores[v]) for v in versoes_selecionadas],
                "Distribuição Plurianual — Comparativo",
                coluna_x="ano_nome", rotulo_periodo="Anual",
            ),
            use_container_width=True, config=CONFIG_PLOTLY, key="pce-comparativa-combo-anual",
        )


def _render_bloco(
    con: duckdb.DuckDBPyConnection, titulo: str, descricoes: list[str],
    versao_forecast: str, gerencias: list[str], classificacoes: list[str],
    anos: list[int], key_prefix: str,
) -> None:
    """Renderiza direto na página (sem `st.expander`) — a partir de
    2026-08-19 a exibição em si já é opt-in (usuário escolhe a Análise
    Individual num seletor antes de chegar aqui), não precisa de mais uma
    camada de recolher/expandir por cima."""
    df_orc_mes = _serie_mensal(con, _VERSAO_ORCADO, descricoes, gerencias, classificacoes)
    df_fc_mes = _serie_mensal(con, versao_forecast, descricoes, gerencias, classificacoes)
    total_orcado = float(df_orc_mes["valor"].sum())
    total_realizado = dados_pce_realizado_total(con, gerencias, classificacoes, descricoes)
    aderencia = (total_realizado / total_orcado) if total_orcado else None

    st.subheader(titulo)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Orçado (Orçamento 2026)", fmt_reais_abrev(total_orcado))
    c2.metric(f"Forecast ({versao_forecast})", fmt_reais_abrev(float(df_fc_mes['valor'].sum())))
    c3.metric("Realizado", fmt_reais_abrev(total_realizado))
    c4.metric("Aderência %", fmt_pct(aderencia) if aderencia is not None else "—")

    if total_orcado == 0 and float(df_fc_mes["valor"].sum()) == 0:
        st.info("Sem valor pra esse recorte.")
        return

    st.plotly_chart(
        _grafico_combo(df_orc_mes, df_fc_mes, f"{titulo} — Mensal x Acumulado"),
        use_container_width=True, config=CONFIG_PLOTLY, key=f"pce-combo-mensal-{key_prefix}",
    )

    df_orc_ano = _serie_anual(con, _VERSAO_ORCADO, descricoes, gerencias, classificacoes, anos)
    df_fc_ano = _serie_anual(con, versao_forecast, descricoes, gerencias, classificacoes, anos)
    st.plotly_chart(
        _grafico_combo(
            df_orc_ano, df_fc_ano, f"{titulo} — Plurianual x Acumulado",
            coluna_x="ano_nome", rotulo_periodo="Anual",
        ),
        use_container_width=True, config=CONFIG_PLOTLY, key=f"pce-combo-anual-{key_prefix}",
    )

    st.markdown("**Por Empreendimento**")
    df_emp = _dados_empreendimento_bloco(con, versao_forecast, descricoes, gerencias, classificacoes)
    if df_emp.empty:
        st.caption("Nenhum empreendimento pra esse recorte.")
        return
    tabela = df_emp.copy()
    tabela["aderencia"] = tabela["aderencia"].map(lambda v: fmt_pct(v) if v is not None else "—")
    for col in ("orcado", "forecast", "realizado"):
        tabela[col] = tabela[col].map(fmt_reais_abrev)
    tabela = tabela.rename(columns={
        "e_pep_projeto": "PEP", "nome_empreendimento": "Empreendimento",
        "orcado": "Orçado", "forecast": "Forecast", "realizado": "Realizado",
        "aderencia": "Aderência %",
    })
    st.dataframe(tabela, hide_index=True, use_container_width=True)


def _grafico_grupo(df: pd.DataFrame) -> go.Figure:
    df = df.iloc[::-1]
    cores = [COR_ESTOURO if g in _GRUPOS_DESTAQUE else COR_ORCADO for g in df["grupo"]]
    fig = go.Figure(go.Bar(
        x=df["valor"], y=df["grupo"], orientation="h", marker_color=cores,
        text=[fmt_reais_abrev(v) for v in df["valor"]], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title="Orçado/Forecast por Grupo", margin={"t": 60, "b": 40, "r": 110},
        height=max(320, 28 * len(df)),
    )
    return fig


def render_pce_especialista(con: duckdb.DuckDBPyConnection) -> None:
    render_page_banner(
        "📐", "CAPEX Obras — Especialista",
        "Orçado: Consolidado.xlsx · Realizado: CJI3 + Catálogo CAPEX Obras · Filtros próprios, não usam a sidebar global.",
    )

    tabelas = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fact_pce_consolidado'"
    ).fetchone()[0]
    if not tabelas:
        st.info(
            "Base PCE ainda não carregada — suba \"Consolidado.xlsx\" em "
            "Gestão → Dados e Qualidade e reprocesse."
        )
        return

    versoes = con.execute(
        "SELECT DISTINCT versao FROM fact_pce_consolidado ORDER BY 1"
    ).df()["versao"].tolist()
    versao_padrao = _VERSAO_ORCADO if _VERSAO_ORCADO in versoes else versoes[0]

    col_v, col_g, col_c, col_gr = st.columns([1.2, 1.4, 1.4, 1.6])
    with col_v:
        versao = st.selectbox(
            "Versão (usada como Forecast nos blocos de análise)", versoes,
            index=versoes.index(versao_padrao),
            help=f"O Orçado dos blocos de análise é sempre \"{_VERSAO_ORCADO}\" fixo — essa Versão só decide o Forecast.",
        )
    with col_g:
        gerencias = st.multiselect("Gerência", _opcoes(con, "gerencia_obras"))
    with col_c:
        classificacoes = st.multiselect("Classificação Atualizada", _opcoes(con, "classificacao_atualizada"))
    with col_gr:
        # key inclui a Versão de propósito: trocar de Versão precisa
        # remontar o widget do zero (opções mudam), senão o Streamlit
        # quebra se a seleção antiga tiver um Grupo que não existe na
        # Versão nova — mesmo padrão já usado no filtro de Período
        # (filtros.py) antes dele virar multiselect livre.
        grupos = st.multiselect(
            "Grupo (categoria de custo)", _opcoes(con, "grupo", versao),
            key=f"pce-grupo-{versao}",
            help="Mostra só os Grupos que existem na Versão selecionada ao lado.",
        )

    df_grupo = dados_pce_grupo(con, versao, gerencias, classificacoes, grupos)
    if df_grupo.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        return
    total_orcado = float(df_grupo["valor"].sum())
    total_realizado = dados_pce_realizado_total(con, gerencias, classificacoes, grupos, coluna="grupo")

    c1, c2, c3 = st.columns(3)
    c1.metric("Orçado/Forecast (versão selecionada)", fmt_reais_abrev(total_orcado))
    c2.metric("Realizado", fmt_reais_abrev(total_realizado))
    aderencia = (total_realizado / total_orcado) if total_orcado else None
    c3.metric("Aderência", fmt_pct(aderencia) if aderencia is not None else "—")

    st.divider()
    st.subheader("% de Contingência / Escalation / Capitalização sobre o total")
    mapa_grupo = dict(zip(df_grupo["grupo"], df_grupo["valor"]))
    col_pct1, col_pct2, col_pct3 = st.columns(3)
    for coluna, grupo_destaque in zip((col_pct1, col_pct2, col_pct3), _GRUPOS_DESTAQUE):
        valor_destaque = mapa_grupo.get(grupo_destaque, 0.0)
        pct = (valor_destaque / total_orcado) if total_orcado else None
        coluna.metric(
            grupo_destaque.title(), fmt_pct(pct) if pct is not None else "—",
            help=f"{fmt_reais_abrev(valor_destaque)} sobre {fmt_reais_abrev(total_orcado)} do total filtrado",
        )

    st.divider()
    col_graf, col_tab = st.columns([1.3, 1])
    with col_graf:
        st.plotly_chart(_grafico_grupo(df_grupo), use_container_width=True, config=CONFIG_PLOTLY, key="pce-grafico-grupo")
    with col_tab:
        st.subheader("Por Grupo")
        tabela = df_grupo.copy()
        tabela["% do total"] = (tabela["valor"] / total_orcado * 100).round(2)
        tabela["valor"] = tabela["valor"].map(fmt_reais_abrev)
        st.dataframe(tabela.rename(columns={"grupo": "Grupo", "valor": "Valor"}), hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Visão — Mensal e Plurianual")
    st.caption(
        f"Recorte dos filtros do topo (Gerência/Classificação Atualizada/"
        f"Grupo). Orçado = sempre \"{_VERSAO_ORCADO}\" (fixo). Forecast = "
        f"versão escolhida acima. Mensal é só o ano {_ANO_MENSAL_PADRAO} "
        f"(a soma dos 12 meses bate com a coluna \"{_ANO_MENSAL_PADRAO}\" "
        f"da tabela Pluri ao lado); Plurianual cobre todo Exercício que "
        f"existe na base."
    )
    anos_disponiveis = _anos_disponiveis(con)
    _render_visao_mensal_plurianual(con, versao, gerencias, classificacoes, grupos, anos_disponiveis)

    _render_analise_comparativa(con, versoes, gerencias, classificacoes, grupos, anos_disponiveis)

    st.divider()
    st.subheader("Análise Individual — Mensal, Plurianual e Aderência")
    st.caption(
        "Escolha uma Análise abaixo pra gerar os gráficos e tabelas — "
        "opt-in (2026-08-19, pedido do usuário), nada é calculado até "
        "escolher. Orçado = sempre \"Orçamento 2026\" (fixo). Forecast = "
        "versão escolhida no filtro do topo. Cada Análise usa a "
        "definição de Grupo descrita no topo do módulo (\"Obra e "
        "Pré-Obra\"/\"Rateios\" são recortes definidos por lista de "
        "Descrição, não pela coluna Grupo bruta) — filtro de Gerência/"
        "Classificação Atualizada do topo continua valendo aqui; o "
        "filtro de Grupo do topo não se aplica (cada Análise já define "
        "o seu)."
    )
    _SEM_ESCOLHA = "Selecione uma análise..."
    escolha = st.selectbox(
        "Análise individual", [_SEM_ESCOLHA] + [titulo for titulo, _ in _BLOCOS_ANALISE],
        key="pce-analise-escolha",
    )
    if escolha != _SEM_ESCOLHA:
        descricoes_escolha = dict(_BLOCOS_ANALISE)[escolha]
        _render_bloco(
            con, escolha, descricoes_escolha, versao, gerencias, classificacoes,
            anos_disponiveis, key_prefix=escolha,
        )
