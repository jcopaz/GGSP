"""Fase 4 — Nível 2 (Gerência Geral): waterfall do Delta por categoria de
causa, para o GG selecionado no Nível 1 (ou total da GG Infraestrutura SP).

A soma das barras de categoria + "Não Justificado" tem que fechar
exatamente no Delta Total mostrado no Nível 1 para o mesmo recorte —
critério de pronto da Fase 4 (ver docs/01-plano-de-build-mvp.md).
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.filtros import clausula_periodo, filtrar_periodo_df
from src.dashboard.formatacao import fmt_pacote, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.nivel1_diretoria import GG_TOTAL
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO, COR_NEUTRO, COR_ORCADO
from src.dashboard.tendencia import dados_tendencia, figura_tendencia
from src.engine.delta_calculator import calcular_delta
from src.engine.explanation_engine import CATEGORIA_CALCULADA, carregar_explicacoes


def _pacotes_do_gg(con: duckdb.DuckDBPyConnection, gg_id: str) -> list[str] | None:
    """None = sem filtro (recorte total da GG Infraestrutura SP)."""
    if gg_id == GG_TOTAL:
        return None
    linhas = con.execute(
        "SELECT DISTINCT pacote_id FROM fact_orcamento WHERE gg_id = ? "
        "UNION SELECT DISTINCT pacote_id FROM fact_realizado WHERE gg_id = ?",
        [gg_id, gg_id],
    ).df()
    return linhas["pacote_id"].tolist()


def _nome_gg(con: duckdb.DuckDBPyConnection, gg_id: str) -> str:
    if gg_id == GG_TOTAL:
        # Rótulo evita "DINFRA" — pode ser lido como a Diretoria inteira
        # (que tem mais GGs além desta, ver docs/02-perguntas-em-aberto.md
        # item 5) quando o escopo real do painel é só a Gerência Geral
        # GGG_0054 — corrigido a pedido do usuário em 2026-08-12.
        return "GER. GERAL DE INFRAESTRUTURA (SP)"
    linha = con.execute(
        "SELECT gg_nome FROM fact_realizado WHERE gg_id = ? LIMIT 1", [gg_id]
    ).fetchone()
    return linha[0] if linha else gg_id


def dados_waterfall_gg(
    con: duckdb.DuckDBPyConnection,
    gg_id: str,
    caminho_explicacoes: str,
    categorias_validas: list[str],
) -> tuple[float, float, pd.DataFrame]:
    """Retorna (orcado, delta_total, df com 1 linha por categoria incl. Não
    Justificado). `orcado` vira a barra âncora inicial do waterfall (ver
    figura_waterfall) — pedido do usuário em 2026-08-10, pra caminhar
    Orçado → causas → Real Contabilizado com barras no mesmo nível, igual
    a referência do PMO/RDG, em vez de partir de zero.

    **`orcado`/`realizado` só OPEX — corrigido em 2026-08-11.** CAPEX
    Realizado não tem fonte carregada ainda (`fact_realizado` só tem
    OPEX, ver build_star_schema.py); comparar contra o Orçado total
    (CAPEX+OPEX) inflava o Delta sem ser um estouro/economia real, só a
    ausência de dado do lado do CAPEX.

    **Filtro de Período (Ano/Trimestre/Mês) aplicado desde 2026-08-11.**
    Diferente de Gerência/Coordenação/etc. (que continuam de fora, ver
    módulo `filtros.py`), Período não quebra o fechamento do waterfall:
    `explicacoes.csv` já tem `ano`/`mes` por linha, então dá pra filtrar
    o Delta (SQL) e a explicação de causa (`filtrar_periodo_df`) pelo
    mesmo recorte de tempo sem inventar rateio nenhum."""
    pacotes = _pacotes_do_gg(con, gg_id)
    where_periodo, params_periodo = clausula_periodo()

    if pacotes is None:
        (orcado,) = con.execute(
            f"SELECT SUM(valor_orcado) FROM fact_orcamento "
            f"WHERE classificacao_contabil = 'OPEX'{where_periodo}",
            params_periodo,
        ).fetchone()
        (realizado,) = con.execute(
            f"SELECT SUM(valor_realizado) FROM fact_realizado "
            f"WHERE classificacao_contabil = 'OPEX'{where_periodo}",
            params_periodo,
        ).fetchone()
    else:
        placeholders = ", ".join("?" * len(pacotes)) if pacotes else "NULL"
        (orcado,) = con.execute(
            f"SELECT SUM(valor_orcado) FROM fact_orcamento "
            f"WHERE classificacao_contabil = 'OPEX' AND pacote_id IN ({placeholders}){where_periodo}",
            pacotes + params_periodo,
        ).fetchone()
        (realizado,) = con.execute(
            f"SELECT SUM(valor_realizado) FROM fact_realizado "
            f"WHERE classificacao_contabil = 'OPEX' AND pacote_id IN ({placeholders}){where_periodo}",
            pacotes + params_periodo,
        ).fetchone()

    delta_total = (realizado or 0.0) - (orcado or 0.0)

    df_explicacao = carregar_explicacoes(caminho_explicacoes)
    if pacotes is not None:
        df_explicacao = df_explicacao[df_explicacao["pacote_id"].isin(pacotes)]
    df_explicacao = filtrar_periodo_df(df_explicacao)

    categorias_preenchiveis = [c for c in categorias_validas if c != CATEGORIA_CALCULADA]
    explicado_por_cat = (
        df_explicacao.groupby("categoria")["valor_explicado"].sum()
        if not df_explicacao.empty
        else pd.Series(dtype=float)
    )

    linhas = [
        {"categoria": cat, "valor": float(explicado_por_cat.get(cat, 0.0))}
        for cat in categorias_preenchiveis
    ]
    delta_explicado = sum(l["valor"] for l in linhas)
    linhas.append({"categoria": CATEGORIA_CALCULADA, "valor": delta_total - delta_explicado})

    return orcado or 0.0, delta_total, pd.DataFrame(linhas)


def figura_waterfall(titulo: str, orcado: float, delta_total: float, df_categorias: pd.DataFrame) -> go.Figure:
    """Orçado → causas → Real Contabilizado, com barra âncora no início e
    no fim (estilo de referência do PMO/RDG — ver docs/02-perguntas-em-
    aberto.md e captura trazida pelo usuário em 2026-08-10). Antes, o
    waterfall partia de zero e só mostrava as causas soltas + um total —
    sem âncora, as barras "despencavam" em vez de ficarem niveladas.
    """
    realizado = orcado + delta_total
    fig = go.Figure(go.Waterfall(
        orientation="v",
        x=["Orçado", *df_categorias["categoria"], "Real Contabilizado"],
        y=[orcado, *df_categorias["valor"], realizado],
        measure=["absolute"] + ["relative"] * len(df_categorias) + ["total"],
        text=[fmt_reais_abrev(orcado)] + [fmt_reais_abrev(v) for v in df_categorias["valor"]] + [fmt_reais_abrev(realizado)],
        textposition="outside",
        hovertemplate="%{x}<br>%{text}<extra></extra>",
        connector={"line": {"color": "rgb(180,180,180)"}},
        decreasing={"marker": {"color": COR_ECONOMIA}},
        increasing={"marker": {"color": COR_ESTOURO}},
        totals={"marker": {"color": COR_ORCADO}},
    ))
    fig.update_layout(
        title=f"Nível 2 — Orçado → Real Contabilizado (OPEX), por causa — {titulo}",
        showlegend=False,
        margin={"t": 60, "b": 40},
    )
    return fig


_SEM_SELECAO = "— selecione uma categoria —"


def render_nivel2(
    con: duckdb.DuckDBPyConnection,
    gg_id: str,
    caminho_explicacoes: str,
    categorias_validas: list[str],
    ano_fiscal: int,
) -> None:
    """Só o waterfall + seletor de categoria pro Nível 3. A Tendência saiu
    daqui em 2026-08-10 (a pedido do usuário) — vira `render_tendencia_gg`,
    renderizada full-width abaixo da linha Nível 1/Nível 2, não espremida
    dentro da coluna estreita do waterfall."""
    st.header("Nível 2 — Gerência Geral")
    nome_gg = _nome_gg(con, gg_id)
    orcado, delta_total, df_categorias = dados_waterfall_gg(con, gg_id, caminho_explicacoes, categorias_validas)
    fig = figura_waterfall(nome_gg, orcado, delta_total, df_categorias)
    st.plotly_chart(fig, use_container_width=True, key=f"waterfall-{gg_id}", config=CONFIG_PLOTLY)
    st.caption(
        "Orçado x Real aqui é só OPEX — CAPEX Realizado ainda não tem "
        "fonte carregada (aguardando outro arquivo). Ver CAPEX Orçado no "
        "card do Nível 1."
    )

    opcoes = [_SEM_SELECAO, *df_categorias["categoria"].tolist()]
    categoria_atual = st.session_state.get("categoria_selecionada")
    indice = opcoes.index(categoria_atual) if categoria_atual in opcoes else 0
    escolha = st.selectbox(
        "Ver Nível 3 (ranking de pacotes) da categoria:",
        opcoes,
        index=indice,
        key=f"seletor-categoria-{gg_id}",
    )
    st.session_state["categoria_selecionada"] = None if escolha == _SEM_SELECAO else escolha


def dados_gerencia_gg(con: duckdb.DuckDBPyConnection, gg_id: str) -> pd.DataFrame:
    """Orçado x Real x Delta por Gerência, dentro do recorte do GG (mesmo
    escopo de Pacotes de `_pacotes_do_gg`) — pedido do usuário em
    2026-08-11: "como executivo, onde está o problema e qual Gerência".

    CAPEX (Base Zero) só tem "SP"/"VP" num nível hierárquico diferente de
    Gerência — desde 2026-08-17, confirmado pelo usuário, "SP" mapeia pra
    GER MALHA (SP)/Jefferson Luders e "VP" pra GER IMPLANT DE OBRAS E
    MALHA VP/Vinicius Nascimento (ver `_GERENCIA_ID_POR_REGIAO_BASE_ZERO`
    em build_star_schema.py). CGG050 (despesa direta da GG, Marcelo
    Modolo — ver `_GERENCIA_ID_GG_DIRETO`) também ganhou linha própria,
    não é mais "Não atribuído". No Orçado (`fact_orcamento`), "Não
    atribuído" (`gerencia_id IS NULL`) está zerado desde então — só sobra
    no Realizado, pras poucas linhas sem Gerência na hierarquia SAP.

    Filtro de Período (Ano/Trimestre/Mês) aplicado desde 2026-08-11, mesmo
    motivo do waterfall — não depende de causa/explicacoes.csv aqui (é só
    soma de Orçado/Realizado), então nem precisava do cuidado extra do
    Nível 2/3 com `filtrar_periodo_df`.
    """
    pacotes = _pacotes_do_gg(con, gg_id)
    where_periodo, params_periodo = clausula_periodo()
    if pacotes is None:
        where_orc, params_orc = "WHERE 1=1", []
        where_real, params_real = "WHERE 1=1", []
    else:
        marcadores = ", ".join("?" * len(pacotes)) if pacotes else "NULL"
        where_orc, params_orc = f"WHERE pacote_id IN ({marcadores})", list(pacotes)
        where_real, params_real = f"WHERE pacote_id IN ({marcadores})", list(pacotes)
    where_orc += where_periodo
    params_orc += params_periodo
    where_real += where_periodo
    params_real += params_periodo

    df_orc = con.execute(
        f"SELECT COALESCE(gerencia_id, '') AS gerencia_id, SUM(valor_orcado) AS orcado "
        f"FROM fact_orcamento {where_orc} GROUP BY 1",
        params_orc,
    ).df()
    df_real = con.execute(
        f"SELECT COALESCE(gerencia_id, '') AS gerencia_id, "
        f"MAX(NULLIF(gerencia_nome, '')) AS gerencia_nome, SUM(valor_realizado) AS realizado "
        f"FROM fact_realizado {where_real} GROUP BY 1",
        params_real,
    ).df()

    df = df_orc.merge(df_real, on="gerencia_id", how="outer")
    df["orcado"] = df["orcado"].fillna(0.0)
    df["realizado"] = df["realizado"].fillna(0.0)
    # `gerencia_nome` acima só vem do Realizado — Gerências que só existem
    # no Orçado (ex.: CGG050/"GG direto", que não tem Realizado nenhum
    # ainda) ficam sem nome resolvido; completa via dim_gerencia.
    df_dim_gerencia = con.execute("SELECT gerencia_id, gerencia_nome AS nome_dim FROM dim_gerencia").df()
    df = df.merge(df_dim_gerencia, on="gerencia_id", how="left")
    df["gerencia_nome"] = df["gerencia_nome"].fillna(df["nome_dim"]).fillna("")
    df = df.drop(columns=["nome_dim"])
    df["delta_total"] = df["realizado"] - df["orcado"]
    df["rotulo"] = df.apply(
        lambda r: (r["gerencia_nome"] or r["gerencia_id"]) if r["gerencia_id"] else "Não atribuído",
        axis=1,
    )
    return df.reindex(df["delta_total"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def _cor_valor_gerencia(valor: float) -> str:
    cor = "crimson" if valor > 0 else "seagreen" if valor < 0 else "inherit"
    return f"color: {cor}; font-weight: 600"


def tabela_gerencia(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Tabela colorida — complementa o gráfico com o valor exato de Orçado/
    Realizado (o gráfico só mostra Delta, ver `_grafico_gerencia`)."""
    tabela = pd.DataFrame({
        "Gerência": df["rotulo"],
        "Orçado": df["orcado"],
        "Realizado": df["realizado"],
        "Delta": df["delta_total"],
    })
    return tabela.style.map(_cor_valor_gerencia, subset=["Delta"]).format(
        {"Orçado": fmt_reais_abrev, "Realizado": fmt_reais_abrev, "Delta": fmt_reais_abrev}
    )


def _grafico_gerencia(df: pd.DataFrame) -> go.Figure:
    """Barras horizontais só do Delta (não Orçado/Realizado juntos) — mesmo
    padrão já validado em `nivel4_contas._grafico_top_contas`/
    `nivel5_centro_custo._grafico_top_cc`: com só 1 dimensão de valor, a
    escala extrema entre Gerências (R$ dezenas de mil a R$ dezenas de
    milhão) continua legível, diferente de tentar plotar Orçado+Realizado
    lado a lado."""
    top = df.iloc[::-1]
    cores = [COR_ESTOURO if v > 0 else COR_ECONOMIA if v < 0 else COR_NEUTRO for v in top["delta_total"]]
    fig = go.Figure(go.Bar(
        x=top["delta_total"], y=top["rotulo"], orientation="h", marker={"color": cores},
        text=[fmt_reais_abrev(v) for v in top["delta_total"]], textposition="auto", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Delta: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title="Delta por Gerência", margin={"t": 60, "b": 40, "r": 110},
        height=max(320, 40 * len(top)),
    )
    return fig


def dados_pacotes_gerencia(
    con: duckdb.DuckDBPyConnection, gg_id: str, gerencia_id: str | None,
) -> pd.DataFrame:
    """Orçado x Real x Delta por Pacote, dentro de 1 Gerência — cascata
    Gerência → Pacote (pedido do usuário em 2026-08-11, "mais uma
    cascateada no nível de Pacote que cada Gerência está com Delta").
    `gerencia_id=None` = bucket "Não atribuído" (`gerencia_id IS NULL`)."""
    pacotes = _pacotes_do_gg(con, gg_id)

    condicoes_orc, params_orc = [], []
    condicoes_real, params_real = [], []
    if pacotes is not None:
        marcadores = ", ".join("?" * len(pacotes)) if pacotes else "NULL"
        condicoes_orc.append(f"pacote_id IN ({marcadores})")
        params_orc += pacotes
        condicoes_real.append(f"pacote_id IN ({marcadores})")
        params_real += pacotes
    if gerencia_id:
        condicoes_orc.append("gerencia_id = ?")
        params_orc.append(gerencia_id)
        condicoes_real.append("gerencia_id = ?")
        params_real.append(gerencia_id)
    else:
        condicoes_orc.append("gerencia_id IS NULL")
        condicoes_real.append("gerencia_id IS NULL")

    where_orc = "WHERE " + " AND ".join(condicoes_orc)
    where_real = "WHERE " + " AND ".join(condicoes_real)

    df_orc = con.execute(
        f"SELECT pacote_id, SUM(valor_orcado) AS orcado FROM fact_orcamento {where_orc} GROUP BY 1",
        params_orc,
    ).df()
    df_real = con.execute(
        f"SELECT pacote_id, SUM(valor_realizado) AS realizado FROM fact_realizado {where_real} GROUP BY 1",
        params_real,
    ).df()

    df = df_orc.merge(df_real, on="pacote_id", how="outer")
    df["orcado"] = df["orcado"].fillna(0.0)
    df["realizado"] = df["realizado"].fillna(0.0)
    df["delta_total"] = df["realizado"] - df["orcado"]
    return df.reindex(df["delta_total"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def tabela_pacotes_gerencia(df: pd.DataFrame, nomes_pacote: dict[str, str]) -> pd.io.formats.style.Styler:
    tabela = pd.DataFrame({
        "Pacote": [fmt_pacote(p, nomes_pacote.get(p)) for p in df["pacote_id"]],
        "Orçado": df["orcado"],
        "Realizado": df["realizado"],
        "Delta": df["delta_total"],
    })
    return tabela.style.map(_cor_valor_gerencia, subset=["Delta"]).format(
        {"Orçado": fmt_reais_abrev, "Realizado": fmt_reais_abrev, "Delta": fmt_reais_abrev}
    )


def render_gerencia_gg(con: duckdb.DuckDBPyConnection, gg_id: str) -> None:
    """Seção recolhível: gráfico + tabela de Orçado x Real x Delta por
    Gerência dentro da GG, e uma cascata pra ver os Pacotes de 1 Gerência
    escolhida — pra o GG ver rápido onde está o problema (qual Gerência) e
    o que compõe aquele Delta (quais Pacotes). Sem quebra por categoria de
    causa ainda: a causa hoje só é rastreada por Pacote (não por Gerência)
    e um mesmo Pacote pode pertencer a várias Gerências (confirmado nos
    dados reais) — não dá pra herdar a causa sem inventar rateio. Isso
    fica pra quando a captação Micro (Conta/Centro de Custo, que já
    carrega Gerência real no Realizado) existir de verdade — ver
    docs/03-processo-justificativas-causas.md."""
    df = dados_gerencia_gg(con, gg_id)
    if df.empty:
        return
    with st.expander("📊 Ver por Gerência (dentro desta GG)", expanded=False):
        st.caption(
            "Orçado x Real x Delta por Gerência dentro do organograma "
            "desta GG. Ainda sem quebra por categoria de causa (Físico/"
            "Efeito Preço/etc.) — a causa hoje só é rastreada por Pacote, "
            "que pode pertencer a várias Gerências ao mesmo tempo. "
            "\"Não atribuído\": OPEX sem Gerência na Consulta de Contas ou "
            "linha do Realizado sem Gerência na hierarquia SAP. CAPEX "
            "(Base Zero) já é atribuído por região SP/VP desde 2026-08-17."
        )
        st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
        st.plotly_chart(
            _grafico_gerencia(df), use_container_width=True,
            key=f"gerencia-grafico-{gg_id}", config=CONFIG_PLOTLY,
        )
        st.dataframe(
            tabela_gerencia(df), hide_index=True, use_container_width=True,
            key=f"gerencia-tabela-{gg_id}",
        )

        st.divider()
        st.markdown("**Cascata: Pacotes dentro de 1 Gerência**")
        opcoes = df["rotulo"].tolist()
        escolha = st.selectbox(
            "Ver Pacotes desta Gerência:", opcoes, key=f"gerencia-selecionada-{gg_id}",
        )
        gerencia_id_escolhida = df.loc[df["rotulo"] == escolha, "gerencia_id"].iloc[0] or None
        df_pacotes = dados_pacotes_gerencia(con, gg_id, gerencia_id_escolhida)
        if df_pacotes.empty:
            st.info("Nenhum Pacote com Orçado/Realizado nesta Gerência.")
        else:
            st.dataframe(
                tabela_pacotes_gerencia(df_pacotes, mapa_nomes_pacote(con)),
                hide_index=True, use_container_width=True,
                key=f"gerencia-pacotes-{gg_id}-{escolha}",
            )


def render_tendencia_gg(con: duckdb.DuckDBPyConnection, gg_id: str, ano_fiscal: int) -> None:
    """Gráfico de Tendência, separado do waterfall (ver render_nivel2) pra
    renderizar full-width, não espremido na coluna estreita ao lado do
    Nível 1."""
    nome_gg = _nome_gg(con, gg_id)
    df_tend = dados_tendencia(con, ano_fiscal, pacotes=_pacotes_do_gg(con, gg_id))
    st.plotly_chart(
        figura_tendencia(df_tend, f"Tendência do ano — {nome_gg}"),
        use_container_width=True, key=f"tendencia-{gg_id}", config=CONFIG_PLOTLY,
    )
    st.caption(
        "Orçado x Real aqui é só OPEX (CAPEX Realizado ainda sem fonte "
        "carregada). Linha pontilhada = Forecast (saldo do desvio até o "
        "mês de referência, redistribuído nos meses restantes — fecha "
        "exatamente no Orçado Anual em dezembro)."
    )
