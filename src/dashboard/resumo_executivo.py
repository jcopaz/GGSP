"""Visão Resumo Executivo — GGSP, 1 tela só, gráfica e resumida, para a
GG Infraestrutura (SP) bater o olho: quanto é o desvio, CAPEX x OPEX,
quanto já está explicado e onde estão os principais desvios por Gerência Local.
Alvo direto do critério de sucesso do projeto (ver
docs/00-especificacao-consolidada.md, seção 10: "responder, sem apoio do
PMO, em menos de 2 minutos").

**Reconstruída em painéis em 2026-08-12**, pra replicar de verdade o
layout do painel "Plano de Manutenção" (PMO/Power BI) que o usuário
trouxe — a primeira tentativa só colou 2 gráficos na página antiga, o
usuário pediu pra reconstruir igual à imagem. Estrutura confirmada com o
usuário antes de codar (painel por painel):

1. **Financeiro** (card-resumo + Visão Anual/Forecast) — visão geral, sem
   waterfall aqui (foi pro painel "Financeiro OPEX" próprio, item 3,
   igual à referência — ajustado em 2026-08-12 a pedido do usuário).
2. **OPEX** — composição (Opex Malha x Opex Infra) + "Visão Gerências
   Locais" dentro da GGSP (as Gerências reais carregadas na fonte),
   com Aderência % colorida por linha, usando a mesma métrica do nível GG.
3. **Financeiro OPEX** — waterfall por causa, com subtítulo do período
   acumulado — igual à referência.
4. **CAPEX** — composição Via/EE + "Visão GG" por região (SP x VP, o
   único corte de Gerência que a Base Zero tem pro CAPEX — não são as 8
   Gerências reais, ver `_dados_visao_gg_capex`). Só Orçado — CAPEX
   Realizado não existe.
5. **Financeiro CAPEX** — marcado como indisponível, visível (não
   escondido): falta o Realizado de CAPEX Malha pra montar esse
   waterfall.

Forecast agora usa a fórmula real do PMO (saldo do desvio redistribuído
nos meses restantes — ver `tendencia.py`), não mais a extrapolação
run-rate — fecha o item 2 de docs/02-perguntas-em-aberto.md.

Fora de escopo, registrado e não escondido: "OPEX Infra (Drenagem)" (sem
arquivo carregado), "Real Físico" separado do Contabilizado (continuam
iguais, decisão já validada), quebra de causa por Gerência (exigiria
inventar rateio, viola a Regra de Ouro) — ver
docs/02-perguntas-em-aberto.md, item 22.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.auth.permissions import escopo_universo
from src.branding import render_page_banner
from src.dashboard.filtros import (
    clausula_escopo,
    clausula_periodo,
    guardar_e_faixa_universo,
    periodo_efetivo,
)
from src.dashboard.formatacao import (
    escapar_cifrao_md, fmt_pacote, fmt_pct, fmt_reais_abrev, fmt_semaforo, mapa_nomes_pacote,
)
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.layout import bloco_resumo_visual, legenda_semaforo, nota_forecast
from src.dashboard.nivel1_diretoria import GG_TOTAL
from src.dashboard.nivel2_gg import dados_gerencia_gg, dados_waterfall_gg, figura_waterfall
from src.dashboard.nivel3_pacotes import dados_ranking_pacotes
from src.dashboard.paleta import (
    COR_ADERENCIA_ATENCAO, COR_ADERENCIA_FORA, COR_ADERENCIA_OK,
    COR_CAPEX_EE, COR_CAPEX_VIA, COR_NEUTRO, COR_OPEX, COR_ORCADO, COR_REALIZADO,
    COR_REGIAO_SP, COR_REGIAO_VP,
)
from src.dashboard.tendencia import dados_tendencia, figura_tendencia
from src.engine.explanation_engine import CATEGORIA_CALCULADA
from src.engine.semaforo import classificar_semaforo

_COR_COMPOSICAO = {"CAPEX Via": COR_CAPEX_VIA, "CAPEX EE": COR_CAPEX_EE, "OPEX Malha": COR_OPEX}
_COR_REGIAO_CAPEX = {"SP": COR_REGIAO_SP, "VP": COR_REGIAO_VP}
_NOMES_MES_ABREV = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
                     7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def _subtitulo_periodo_acumulado() -> str:
    """"Detalhamento orçamento acumulado – Jan a Jun" (igual ao painel de
    referência do PMO) — deriva do filtro de Período da sidebar
    (`periodo_efetivo`, filtros.py). Sem filtro de Mês/Trimestre ativo,
    cai num texto genérico (não inventa um período que o usuário não
    escolheu)."""
    _, meses_efetivos = periodo_efetivo()
    if not meses_efetivos:
        return "Detalhamento orçamento acumulado no ano"
    primeiro, ultimo = min(meses_efetivos), max(meses_efetivos)
    if primeiro == ultimo:
        return f"Detalhamento orçamento acumulado – {_NOMES_MES_ABREV[primeiro]}"
    return f"Detalhamento orçamento acumulado – {_NOMES_MES_ABREV[primeiro]} a {_NOMES_MES_ABREV[ultimo]}"


def _where_recorte_opex() -> tuple[str, list]:
    """`clausula_periodo` + `clausula_escopo("opex_sustaining")` num
    fragmento só (RBAC de escopo — docs/08). No-op pra quem tem a GG
    inteira/admin; recorte por `gerencia_id` pra usuário escopado."""
    where_p, params_p = clausula_periodo()
    where_e, params_e = clausula_escopo("opex_sustaining")
    return where_p + where_e, [*params_p, *params_e]


def _resumo_geral(con: duckdb.DuckDBPyConnection) -> dict:
    """`delta`/`aderencia` comparam Realizado (só OPEX) contra Orçado
    OPEX, não o total (CAPEX+OPEX) — ver docstring do módulo. `orcado`
    (total) continua no retorno só pra exibição no card."""
    where_periodo, params_periodo = _where_recorte_opex()
    (orcado,) = con.execute(
        f"SELECT SUM(valor_orcado) FROM fact_orcamento WHERE 1=1{where_periodo}", params_periodo,
    ).fetchone()
    (orcado_opex,) = con.execute(
        f"SELECT SUM(valor_orcado) FROM fact_orcamento "
        f"WHERE classificacao_contabil = 'OPEX'{where_periodo}",
        params_periodo,
    ).fetchone()
    (realizado,) = con.execute(
        f"SELECT SUM(valor_realizado) FROM fact_realizado "
        f"WHERE classificacao_contabil = 'OPEX'{where_periodo}",
        params_periodo,
    ).fetchone()
    orcado = orcado or 0.0
    orcado_opex = orcado_opex or 0.0
    realizado = realizado or 0.0
    delta = realizado - orcado_opex
    aderencia = (realizado / orcado_opex) if orcado_opex else None
    return {
        "orcado": orcado, "orcado_opex": orcado_opex, "realizado": realizado,
        "delta": delta, "aderencia": aderencia,
    }


def _dados_capex_opex(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Orçado por Classificação Contábil — usado só pro card-resumo
    (`orcado_capex`/`orcado_opex`/`orcado_fora_plano`). `fora_do_plano`
    isola `area = 'Fora Plano - Malha'` (hoje classificado como OPEX): é
    orçamento fora do plano original aprovado, não é OPEX operacional
    comum — a Regra de Ouro do projeto pede que nada relevante fique
    escondido dentro de outra categoria."""
    where_periodo, params_periodo = clausula_periodo()
    return con.execute(
        f"""
        SELECT COALESCE(NULLIF(classificacao_contabil, ''), 'Não informado') AS classificacao,
               (area LIKE 'Fora Plano%') AS fora_do_plano,
               SUM(valor_orcado) AS orcado
        FROM fact_orcamento WHERE 1=1{where_periodo} GROUP BY 1, 2 ORDER BY orcado DESC
        """,
        params_periodo,
    ).df()


def _dados_composicao_capex(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Orçado CAPEX por componente (Via / EE) — inspirado no painel
    "Plano de Manutenção" do PMO (imagem trazida em 2026-08-12).

    Não vem separado na fonte (Base Zero) como uma coluna própria —
    classificado pelo nome da conta interna: contém "ELETRO" =
    Eletro-Eletrônica, resto = Via. Confirmado contra as 6 contas reais do
    CAPEX Malha (PM03001/002/003/007/010/015): soma das duas partes bate
    exato com o total (R$43,07 MM), sem sobra nem furo.
    """
    where_periodo, params_periodo = clausula_periodo()
    df_capex = con.execute(
        f"""
        SELECT conta_interna_id, MAX(conta_interna_nome) AS nome, SUM(valor_orcado) AS orcado
        FROM fact_orcamento
        WHERE classificacao_contabil = 'CAPEX'{where_periodo}
        GROUP BY conta_interna_id
        """,
        params_periodo,
    ).df()
    if df_capex.empty:
        return pd.DataFrame({"componente": ["CAPEX Via", "CAPEX EE"], "orcado": [0.0, 0.0]})
    eh_ee = df_capex["nome"].fillna("").str.contains("ELETRO", case=False)
    return pd.DataFrame({
        "componente": ["CAPEX Via", "CAPEX EE"],
        "orcado": [df_capex.loc[~eh_ee, "orcado"].sum(), df_capex.loc[eh_ee, "orcado"].sum()],
    })


def _grafico_composicao_capex(df: pd.DataFrame) -> go.Figure:
    top = df.sort_values("orcado").reset_index(drop=True)
    cores = [_COR_COMPOSICAO.get(c, COR_NEUTRO) for c in top["componente"]]
    fig = go.Figure(go.Bar(
        x=top["orcado"], y=top["componente"], orientation="h", marker={"color": cores},
        text=[fmt_reais_abrev(v) for v in top["orcado"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Orçado: %{text}<extra></extra>",
    ))
    fig.update_layout(title="CAPEX Orçado — Via x EE", margin={"t": 50, "b": 20, "r": 90}, height=220)
    return fig


def _dados_composicao_opex(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Composição Orçado x Real Contabilizado (Opex Malha + Opex Infra
    Drenagem — esse último sempre 0 por enquanto, sem fonte carregada,
    ver docs/02-perguntas-em-aberto.md item 22) — os 2 únicos "estágios"
    que temos dado real pra comparar (Forecast/Real Físico/Real 1T+2T do
    painel de referência do PMO não têm fonte separada aqui, ou já são
    idênticos ao Real Contabilizado — decisão já validada com o
    usuário)."""
    where_periodo, params_periodo = _where_recorte_opex()
    (orcado,) = con.execute(
        f"SELECT COALESCE(SUM(valor_orcado), 0) FROM fact_orcamento "
        f"WHERE classificacao_contabil = 'OPEX'{where_periodo}",
        params_periodo,
    ).fetchone()
    (realizado,) = con.execute(
        f"SELECT COALESCE(SUM(valor_realizado), 0) FROM fact_realizado "
        f"WHERE classificacao_contabil = 'OPEX'{where_periodo}",
        params_periodo,
    ).fetchone()
    return pd.DataFrame({
        "estagio": ["Orçado", "Orçado", "Real Contabilizado", "Real Contabilizado"],
        "componente": ["Opex Malha", "Opex Infra (Drenagem)", "Opex Malha", "Opex Infra (Drenagem)"],
        "valor": [orcado, 0.0, realizado, 0.0],
    })


def _grafico_composicao_opex(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    cores = {"Opex Malha": COR_OPEX, "Opex Infra (Drenagem)": "#ffe699"}
    for componente in ("Opex Malha", "Opex Infra (Drenagem)"):
        sub = df[df["componente"] == componente]
        fig.add_bar(
            name=componente, x=sub["estagio"], y=sub["valor"], marker_color=cores[componente],
            text=[fmt_reais_abrev(v) for v in sub["valor"]],
            hovertemplate=f"%{{x}}<br>{componente}: %{{text}}<extra></extra>",
        )

    orcado_total = df.loc[df["estagio"] == "Orçado", "valor"].sum()
    real_total = df.loc[df["estagio"] == "Real Contabilizado", "valor"].sum()
    delta = real_total - orcado_total
    pct = (delta / orcado_total) if orcado_total else None
    cor_delta = "crimson" if delta > 0 else "seagreen" if delta < 0 else "gray"
    y_topo = max(orcado_total, real_total, 1.0) * 1.14

    # Bracket entre as 2 barras (aproximação em coordenadas de "paper" —
    # com só 2 categorias no eixo X, ficam nas posições ~0,25/0,75 por
    # padrão do Plotly), igual ao estilo do painel de referência do PMO.
    fig.add_shape(type="line", x0=0.24, x1=0.24, y0=orcado_total, y1=y_topo, xref="paper", yref="y", line={"color": "#888", "width": 1})
    fig.add_shape(type="line", x0=0.76, x1=0.76, y0=real_total, y1=y_topo, xref="paper", yref="y", line={"color": "#888", "width": 1})
    fig.add_shape(type="line", x0=0.24, x1=0.76, y0=y_topo, y1=y_topo, xref="paper", yref="y", line={"color": "#888", "width": 1})
    fig.add_annotation(
        x=0.5, y=y_topo, xref="paper", yref="y", yanchor="bottom",
        text=f"<b>{fmt_reais_abrev(delta)}</b> ({fmt_pct(pct) if pct is not None else '—'})",
        showarrow=False, font={"color": cor_delta, "size": 12},
    )

    fig.update_layout(
        title="OPEX — Orçado x Real Contabilizado", barmode="stack",
        margin={"t": 60, "b": 20}, height=300, showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        yaxis={"range": [0, y_topo * 1.08]},
    )
    return fig


def _dados_visao_gg_capex(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """CAPEX Orçado por região (SP x VP) — o único corte de "Gerência" que
    a fonte do CAPEX (Base Zero) tem: um campo bruto `gerencia_raw` só com
    "SP"/"VP" (achado em 2026-08-12, respondendo pergunta do usuário) —
    não são as 8 Gerências reais (essas só existem no lado OPEX, via
    Consulta de Contas). Só Orçado: CAPEX Realizado não existe, então não
    dá pra calcular Aderência aqui — diferente da Visão GG do OPEX."""
    where_periodo, params_periodo = clausula_periodo()
    return con.execute(
        f"""
        SELECT gerencia_raw AS regiao, SUM(valor_orcado) AS orcado
        FROM fact_orcamento
        WHERE classificacao_contabil = 'CAPEX'{where_periodo}
        GROUP BY gerencia_raw ORDER BY orcado DESC
        """,
        params_periodo,
    ).df()


def _grafico_visao_gg_capex(df: pd.DataFrame) -> go.Figure | None:
    if df.empty:
        return None
    top = df.iloc[::-1]
    cores = [_COR_REGIAO_CAPEX.get(r, COR_NEUTRO) for r in top["regiao"]]
    fig = go.Figure(go.Bar(
        x=top["orcado"], y=top["regiao"], orientation="h", marker={"color": cores},
        text=[fmt_reais_abrev(v) for v in top["orcado"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Orçado: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title="CAPEX Orçado por Região (SP x VP)",
        margin={"t": 50, "b": 20, "r": 90}, height=max(180, 60 * len(top)),
    )
    return fig


def _cor_aderencia(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "color: #999"
    if 0.95 <= valor <= 1.05:
        return f"color: {COR_ADERENCIA_OK}; font-weight: 700"
    if (0.90 <= valor < 0.95) or (1.05 < valor <= 1.10):
        return f"color: {COR_ADERENCIA_ATENCAO}; font-weight: 700"
    return f"color: {COR_ADERENCIA_FORA}; font-weight: 700"


def _cor_aderencia_md(valor: float | None) -> str:
    """Cor no vocabulário restrito do `st.markdown(":cor[texto]")` (mesma
    limitação já documentada em formatacao.py/fmt_semaforo)."""
    if valor is None or pd.isna(valor):
        return "gray"
    if 0.95 <= valor <= 1.05:
        return "green"
    if (0.90 <= valor < 0.95) or (1.05 < valor <= 1.10):
        return "orange"
    return "red"


def _dados_visao_gg_ordenado(df: pd.DataFrame) -> pd.DataFrame:
    """Ordena por Orçado (maior primeiro) e calcula Aderência — ordem
    compartilhada entre a legenda de texto e o gráfico, pra alinhar linha
    a linha (ver `_render_visao_gg_opex`)."""
    df = df.copy()
    df["aderencia"] = df.apply(lambda r: (r["realizado"] / r["orcado"]) if r["orcado"] else None, axis=1)
    return df.sort_values("orcado", ascending=False).reset_index(drop=True)


def _separar_nao_atribuido(df_ordenado: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series | None]:
    """Isola a linha "Não atribuído" (CAPEX sem Gerência real na Base Zero
    + Realizado sem Gerência na hierarquia SAP) do ranking pareado de
    Gerências Locais — não é uma Gerência de verdade, e no recorte típico
    seu Orçado é maior que o de qualquer Gerência real, o que esmagava a
    escala do gráfico Orçado x Real (2026-08-13, usuário reportou "meio
    bagunçado": 9 das 10 barras viravam fiapo do lado de uma barra 2-5x
    maior). Continua visível — Regra de Ouro, nada some: sai só do
    gráfico/legenda pareados, mas segue num aviso à parte e na tabela
    completa (`_tabela_visao_gg_opex`, que recebe o df sem filtrar)."""
    mascara = df_ordenado["rotulo"] == "Não atribuído"
    linha = df_ordenado.loc[mascara].iloc[0] if mascara.any() else None
    return df_ordenado.loc[~mascara].reset_index(drop=True), linha


def _tabela_visao_gg_opex(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Versão em tabela da "Visão GG" (valores exatos, complementa o
    gráfico — que é só pra bater o olho)."""
    df = df.copy()
    df["aderencia"] = df.apply(lambda r: (r["realizado"] / r["orcado"]) if r["orcado"] else None, axis=1)
    tabela = pd.DataFrame({
        "Gerência Local": df["rotulo"], "Orçado": df["orcado"],
        "Realizado": df["realizado"], "Aderência": df["aderencia"],
    })
    return tabela.style.map(_cor_aderencia, subset=["Aderência"]).format(
        {"Orçado": fmt_reais_abrev, "Realizado": fmt_reais_abrev, "Aderência": fmt_pct}
    )


def _grafico_visao_gg_opex(df_ordenado: pd.DataFrame) -> go.Figure:
    """Barras pareadas Orçado x Real Contabilizado por Gerência — sem
    rótulo no eixo Y (`showticklabels=False`): o nome da Gerência e a
    Aderência % colorida já aparecem na legenda de texto ao lado
    (`_render_legenda_visao_gg`), renderizada pelo Streamlit, não pelo
    Plotly. Tentei colocar a % como anotação dentro do próprio gráfico
    antes (`xref="paper"`) e o texto colidiu com o rótulo comprido de
    Gerência (achado real, usuário reportou em 2026-08-12: "GER MAL40,1%"
    — nomes de Gerência grudando na porcentagem) — essa versão evita o
    problema de vez, sem depender de posição aproximada. Sem `title=`
    (2026-08-13, achado #9 da auditoria de UX): o subheader Streamlit
    "**Visão Gerências Locais**" logo acima já diz a mesma coisa — 2
    títulos empilhados era redundância visual."""
    top = df_ordenado.iloc[::-1].reset_index(drop=True)

    fig = go.Figure()
    fig.add_bar(
        name="Orçado", y=top["rotulo"], x=top["orcado"], orientation="h",
        marker_color=COR_ORCADO, text=[fmt_reais_abrev(v) for v in top["orcado"]],
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Orçado: %{text}<extra></extra>",
    )
    fig.add_bar(
        name="Real Contabilizado", y=top["rotulo"], x=top["realizado"], orientation="h",
        marker_color=COR_REALIZADO, text=[fmt_reais_abrev(v) for v in top["realizado"]],
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Real Contabilizado: %{text}<extra></extra>",
    )
    fig.update_layout(
        barmode="group", hovermode="y unified",
        margin={"t": 20, "b": 55, "l": 10, "r": 90}, height=max(240, 68 * len(top)) + 30,
        legend={"orientation": "h", "yanchor": "top", "y": -0.08, "xanchor": "center", "x": 0.5},
        xaxis_title=None, yaxis={"showticklabels": False},
    )
    return fig


def _render_legenda_visao_gg(df_ordenado: pd.DataFrame) -> None:
    """Nome da Gerência + Aderência % colorida, em texto (Streamlit, não
    Plotly) — 1 linha por Gerência, mesma ordem de cima pra baixo do
    gráfico ao lado (`_grafico_visao_gg_opex`), pra alinhar visualmente
    sem depender de posicionamento aproximado dentro da figura."""
    st.caption("_Aderência Financeira_")
    for _, r in df_ordenado.iterrows():
        cor = _cor_aderencia_md(r["aderencia"])
        st.markdown(f":{cor}[**{fmt_pct(r['aderencia'])}**] &nbsp; {r['rotulo']}")


def _render_card_resumo(
    resumo: dict, orcado_capex: float, orcado_opex: float, orcado_fora_plano: float,
    pct_explicado: float | None, delta_nao_justificado: float, status_semaforo: str,
) -> None:
    """Card no mesmo estilo do Nível 1 (ver nivel1_diretoria._render_card_gg),
    estendido com % Explicado/Não Justificado — pedido do usuário em
    2026-08-10, pra padronizar resumo | divisor | visualização principal
    em todas as abas."""
    delta = resumo["delta"]
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"
    with st.container(border=True):
        st.markdown(f"**GER. GERAL DE INFRAESTRUTURA (SP)** &nbsp; {fmt_semaforo(status_semaforo)}")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçamento (CAPEX+OPEX) | {fmt_reais_abrev(resumo["orcado"])} |
            | &nbsp;&nbsp;↳ CAPEX | {fmt_reais_abrev(orcado_capex)} |
            | &nbsp;&nbsp;↳ OPEX | {fmt_reais_abrev(orcado_opex)} |
            | &nbsp;&nbsp;&nbsp;&nbsp;↳ Fora do Plano | {fmt_reais_abrev(orcado_fora_plano)} |
            | Real Contabilizado (OPEX) | {fmt_reais_abrev(resumo["realizado"])} |
            | Delta (OPEX x OPEX) | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Aderência (OPEX x OPEX) | {fmt_pct(resumo["aderencia"])} |
            | % Explicado | {fmt_pct(pct_explicado)} |
            | Não Justificado | {fmt_reais_abrev(delta_nao_justificado)} |
            """)
        )


def _render_resumo_recorte(con: duckdb.DuckDBPyConnection, ano_fiscal: int) -> None:
    """Resumo Executivo para usuário SEM a GG inteira (RBAC de escopo —
    docs/08, Opção B). Mostra Orçado/Realizado/Delta/Aderência, Visão por
    Gerência, Composição OPEX, Tendência e o ranking de Pacotes ofensores
    — tudo recortado nas Gerências do grant. NÃO mostra o waterfall de
    causa: a causa é rastreada por Pacote (Macro) e cruza Gerências, então
    não dá pra atribuí-la corretamente a um sub-recorte de Gerência
    (ratear seria inventar dado). O waterfall fica no acesso à GG inteira
    (Analista que apura a GG)."""
    from src.engine.delta_calculator import calcular_delta

    frag, params = clausula_escopo("opex_sustaining")
    filtro_opex = (" AND classificacao_contabil = 'OPEX'" + frag, list(params))
    filtro_real = (frag, list(params)) if frag else None

    resumo = _resumo_geral(con)
    delta = resumo["delta"]
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"

    def _card() -> None:
        with st.container(border=True):
            st.markdown("**Recorte do seu acesso — OPEX**")
            st.markdown(escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado OPEX | {fmt_reais_abrev(resumo["orcado_opex"])} |
            | Real Contabilizado | {fmt_reais_abrev(resumo["realizado"])} |
            | Delta | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Aderência | {fmt_pct(resumo["aderencia"])} |
            """))
            st.caption(
                "🔒 A decomposição de causa (waterfall) é Macro por Pacote e "
                "cruza Gerências — disponível só no acesso à GG inteira "
                "(Analista que apura a GG). Aqui você tem Orçado/Realizado/"
                "Delta e os ofensores da(s) sua(s) Gerência(s)."
            )

    def _visual() -> None:
        st.plotly_chart(
            figura_tendencia(
                dados_tendencia(con, ano_fiscal, filtro_orcado=filtro_opex, filtro_realizado=filtro_real),
                "Visão Anual — Orçado x Real x Forecast (OPEX, seu recorte)",
            ),
            use_container_width=True, key="resumo-recorte-tendencia", config=CONFIG_PLOTLY,
        )
        nota_forecast(com_recorte=True)

    st.subheader("📊 Financeiro")
    bloco_resumo_visual(_card, _visual, key="resumo-recorte-financeiro")

    st.divider()
    st.subheader("🛠️ OPEX — Composição e Gerências (seu recorte)")
    st.plotly_chart(
        _grafico_composicao_opex(_dados_composicao_opex(con)), use_container_width=True,
        key="resumo-recorte-composicao", config=CONFIG_PLOTLY,
    )

    df_gerencia = dados_gerencia_gg(con, GG_TOTAL)
    df_ordenado = _dados_visao_gg_ordenado(df_gerencia) if not df_gerencia.empty else df_gerencia
    df_reais, linha_na = (
        _separar_nao_atribuido(df_ordenado) if not df_ordenado.empty else (df_ordenado, None)
    )
    if df_reais.empty:
        st.caption("Nenhuma Gerência com dado no recorte selecionado.")
    else:
        col_l, col_g = st.columns([1.2, 2.8], gap="medium")
        with col_l:
            _render_legenda_visao_gg(df_reais)
        with col_g:
            st.plotly_chart(
                _grafico_visao_gg_opex(df_reais), use_container_width=True,
                key="resumo-recorte-visao-gg", config=CONFIG_PLOTLY,
            )
    if not df_ordenado.empty:
        st.dataframe(_tabela_visao_gg_opex(df_ordenado), hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Pacotes com Maior Desvio (seu recorte)")
    ranking = calcular_delta(
        con, dims=["pacote_id"], filtro_orcado=filtro_opex, filtro_realizado=(filtro_real or ("", [])),
    )
    if ranking.empty:
        st.caption("Nenhum Pacote com desvio neste recorte.")
    else:
        ranking = ranking.reindex(ranking["delta_total"].abs().sort_values(ascending=False).index).head(5)
        nomes_pacote = mapa_nomes_pacote(con)
        tabela = ranking.assign(
            pacote_id=ranking["pacote_id"].map(lambda p: fmt_pacote(p, nomes_pacote.get(p))),
            delta_total=ranking["delta_total"].map(fmt_reais_abrev),
        ).rename(columns={"pacote_id": "Pacote", "orcado": "Orçado", "realizado": "Realizado", "delta_total": "Delta"})
        for col in ("Orçado", "Realizado"):
            tabela[col] = tabela[col].map(fmt_reais_abrev)
        st.dataframe(tabela[["Pacote", "Orçado", "Realizado", "Delta"]], hide_index=True, use_container_width=True)


def render_resumo_executivo(
    con: duckdb.DuckDBPyConnection,
    caminho_explicacoes: str,
    categorias_validas: list[str],
    simulado: bool,
    ano_fiscal: int,
) -> None:
    render_page_banner("🧭", "Resumo Executivo", "Quanto é o desvio, CAPEX x OPEX, e como se distribui nas Gerências Locais.")
    # RBAC de escopo (docs/08, Fase RBAC-A.2, Opção B): quem não tem a GG
    # inteira em opex_sustaining vê um resumo recortado, sem waterfall de
    # causa (a causa é Macro por Pacote, cruza Gerências).
    guardar_e_faixa_universo(con, "opex_sustaining")
    if not escopo_universo("opex_sustaining")[1]:
        _render_resumo_recorte(con, ano_fiscal)
        return
    if simulado:
        st.warning(
            "🎲 Modo simulação ativo — os valores de causa/justificativa "
            "abaixo são sintéticos, gerados só para demonstração. "
            "Orçamento e Realizado continuam sendo os dados reais "
            "carregados."
        )

    resumo = _resumo_geral(con)
    orcado_rdg, delta_total, df_categorias = dados_waterfall_gg(con, GG_TOTAL, caminho_explicacoes, categorias_validas)
    delta_explicado = df_categorias.loc[df_categorias["categoria"] != CATEGORIA_CALCULADA, "valor"].sum()
    delta_nao_justificado = df_categorias.loc[df_categorias["categoria"] == CATEGORIA_CALCULADA, "valor"].sum()
    pct_explicado = (delta_explicado / delta_total) if delta_total else None
    status_semaforo = classificar_semaforo(
        resumo["aderencia"], delta_nao_justificado=delta_nao_justificado, delta_total=delta_total,
    )

    df_capex_opex = _dados_capex_opex(con)
    orcado_capex = df_capex_opex.loc[df_capex_opex["classificacao"] == "CAPEX", "orcado"].sum()
    orcado_opex = df_capex_opex.loc[df_capex_opex["classificacao"] == "OPEX", "orcado"].sum()
    orcado_fora_plano = df_capex_opex.loc[df_capex_opex["fora_do_plano"], "orcado"].sum()

    # ===== Painel "Financeiro" (card-resumo + Visão Anual) =====
    st.subheader("📊 Financeiro")

    def _resumo_financeiro() -> None:
        _render_card_resumo(
            resumo, orcado_capex, orcado_opex, orcado_fora_plano,
            pct_explicado, delta_nao_justificado, status_semaforo,
        )
        legenda_semaforo()

    def _visual_financeiro() -> None:
        st.plotly_chart(
            figura_tendencia(dados_tendencia(con, ano_fiscal), "Visão Anual — Orçado x Real x Forecast (OPEX)"),
            use_container_width=True, key="resumo-tendencia", config=CONFIG_PLOTLY,
        )
        st.caption("Orçado x Real aqui é só OPEX — CAPEX Realizado ainda sem fonte carregada.")
        nota_forecast()

    bloco_resumo_visual(_resumo_financeiro, _visual_financeiro, key="resumo-financeiro")

    st.divider()

    # ===== Painel "OPEX" (composição + Visão GG) =====
    df_gerencia = dados_gerencia_gg(con, GG_TOTAL)
    df_gg_ordenado = _dados_visao_gg_ordenado(df_gerencia) if not df_gerencia.empty else df_gerencia
    df_gg_reais, linha_nao_atribuido = (
        _separar_nao_atribuido(df_gg_ordenado) if not df_gg_ordenado.empty else (df_gg_ordenado, None)
    )
    with st.container(border=True):
        st.subheader("🛠️ OPEX — Gerências Locais GGSP")
        st.caption(
            "Esta visão substitui o conceito de \"outras GGs\" da referência do PMO "
            "pelas Gerências Locais da GGSP, mantendo a mesma mensuração: "
            "Orçado x Real Contabilizado, Delta e Aderência Financeira."
        )

        # ---- Parte 1: Composição OPEX (linha própria, largura cheia) ----
        st.markdown("**Composição OPEX**")
        st.plotly_chart(
            _grafico_composicao_opex(_dados_composicao_opex(con)), use_container_width=True,
            key="resumo-opex-composicao", config=CONFIG_PLOTLY,
        )

        st.divider()

        # ---- Parte 2: Visão Gerências Locais (legenda + gráfico pareado) ----
        st.markdown("**Visão Gerências Locais**")
        if linha_nao_atribuido is not None:
            st.caption(escapar_cifrao_md(
                "⚠️ \"Não atribuído\" fica fora do gráfico pareado abaixo "
                f"(Orçado {fmt_reais_abrev(linha_nao_atribuido['orcado'])} · "
                f"Realizado {fmt_reais_abrev(linha_nao_atribuido['realizado'])} · "
                f"Aderência {fmt_pct(linha_nao_atribuido['aderencia'])}) — sozinho ele "
                "era maior que qualquer Gerência real e esmagava a escala das outras "
                "9 barras. Segue na tabela completa, abaixo."
            ))
        if df_gg_reais.empty:
            st.caption("Nenhuma Gerência Local com dado no recorte selecionado.")
        else:
            col_legenda, col_grafico = st.columns([1.2, 2.8], gap="medium")
            with col_legenda:
                _render_legenda_visao_gg(df_gg_reais)
            with col_grafico:
                st.plotly_chart(
                    _grafico_visao_gg_opex(df_gg_reais), use_container_width=True,
                    key="resumo-opex-visao-gg", config=CONFIG_PLOTLY,
                )
        if not df_gg_ordenado.empty:
            st.dataframe(
                _tabela_visao_gg_opex(df_gg_ordenado), hide_index=True, use_container_width=True,
                key="resumo-opex-tabela",
            )
        st.caption(
            "Orçado x Real x Delta x Aderência por Gerência Local dentro do "
            "organograma da GG Infraestrutura (SP), gráfico e tabela."
        )
        with st.expander("Notas"):
            st.caption(
                "\"Opex Infra (Drenagem)\" sempre 0 — sem arquivo carregado "
                "ainda. \"Não atribuído\" (fora do gráfico, ver aviso acima e "
                "tabela completa): linha sem Gerência na hierarquia SAP/"
                "Consulta de Contas (ex.: CGG050, Centro de Custo da própria "
                "GG — ver Nível 5 pra esse detalhe, confirmação formal ainda "
                "pendente com a Laís Machado)."
            )

    # ===== Painel "Financeiro OPEX" (waterfall) =====
    with st.container(border=True):
        st.subheader("📈 Financeiro OPEX")
        st.caption(f"_{_subtitulo_periodo_acumulado()}_")
        fig_wf = figura_waterfall("GER. GERAL DE INFRAESTRUTURA (SP)", orcado_rdg, delta_total, df_categorias)
        st.plotly_chart(fig_wf, use_container_width=True, key="resumo-waterfall", config=CONFIG_PLOTLY)
        st.caption("Waterfall e Delta/Aderência do card acima comparam só OPEX x OPEX.")
        with st.expander("Notas"):
            st.caption(
                "CAPEX Realizado ainda não tem fonte carregada. Quebra por "
                "Gerência Local de cada categoria (Físico/Efeito Preço/etc, "
                "como no painel de referência do PMO) não está aqui: causa "
                "hoje só é rastreada por Pacote inteiro, quebrar por Gerência "
                "Local exigiria inventar rateio."
            )

    # ===== Painel "CAPEX" (composição Via/EE + Visão GG SP/VP) =====
    with st.container(border=True):
        st.subheader("🏗️ CAPEX")
        col_a, col_b = st.columns(2, gap="medium")
        with col_a:
            st.plotly_chart(
                _grafico_composicao_capex(_dados_composicao_capex(con)), use_container_width=True,
                key="resumo-capex-composicao", config=CONFIG_PLOTLY,
            )
        with col_b:
            fig_capex_gg = _grafico_visao_gg_capex(_dados_visao_gg_capex(con))
            if fig_capex_gg:
                st.plotly_chart(
                    fig_capex_gg, use_container_width=True,
                    key="resumo-capex-visao-gg", config=CONFIG_PLOTLY,
                )
            else:
                st.info("Nenhum CAPEX no recorte selecionado.")
        st.caption("Só Orçado — CAPEX Realizado ainda não tem fonte carregada.")
        with st.expander("Notas"):
            st.caption(
                "Sem Realizado não dá pra calcular Aderência nem Delta aqui. "
                "\"SP x VP\" é o único corte de região que a Base Zero (fonte "
                "do CAPEX) tem — não são as 8 Gerências reais do organograma "
                "(essas só existem no lado OPEX)."
            )

    # ===== Painel "Financeiro CAPEX" — indisponível, visível de propósito =====
    with st.container(border=True):
        st.subheader("📊 Financeiro CAPEX")
        st.warning(
            "Sem dado suficiente pra montar este painel: o CAPEX Malha "
            "(Base Zero) não tem Realizado carregado — sem Realizado não "
            "dá pra calcular Delta nem decompor por causa (Físico/Taxa "
            "Bom-Mix/Efeito Preço/etc.), como o waterfall OPEX acima faz. "
            "Orçado por componente já aparece no painel CAPEX, acima."
        )

    st.divider()
    st.subheader("Pacotes com Maior Desvio Não Explicado")
    ranking = dados_ranking_pacotes(con, GG_TOTAL, CATEGORIA_CALCULADA, caminho_explicacoes, categorias_validas)
    top5 = ranking.head(5)
    if top5.empty:
        st.caption("Nenhum pacote com Delta Não Explicado neste recorte.")
    else:
        nomes_pacote = mapa_nomes_pacote(con)
        tabela = top5.assign(
            pacote_id=top5["pacote_id"].map(lambda p: fmt_pacote(p, nomes_pacote.get(p))),
            valor=top5["valor"].map(fmt_reais_abrev),
        ).rename(columns={"pacote_id": "Pacote", "valor": "Não Justificado"})
        st.dataframe(tabela, hide_index=True, use_container_width=True)
