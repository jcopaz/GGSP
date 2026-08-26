"""Nível 5 — Centro de Custo: árvore Família de Pacote → Pacote → Centro de
Custo, no mesmo estilo visual do Nível 4 (Contas) — a pedido do usuário em
2026-08-06 ("ficou muito bom o Nível 4, faça a mesma coisa no Nível 5").

Diferente do Nível 4 (Conta) — aqui existe sobreposição real de código
entre Orçamento e Realizado (ex.: CCR063, CCR097, CCR098 aparecem nos dois
lados, confirmado nos dados), então o Centro de Custo fecha um Delta de
verdade e vira uma 3ª linha-folha na árvore (não duas subárvores
separadas, como a Conta do Nível 4).

Os níveis de Família de Pacote e Pacote reaproveitam `dados_familia`/
`dados_pacote` de nivel4_contas.py — mesma consulta, mesmo recorte de
filtro — pra não duplicar; só o nível de Centro de Custo é específico
daqui.

Campos "PEP" e "Coordenação" citados na spec original (Conceito/#
Complemento da Especificação.txt, seção "Nível 5") não existem como
colunas distintas nos exports atuais: Base Zero só tem "Centro de
Custo/PEP" combinado numa coluna só, e "Elemento PEP" do Realizado está
100% vazio nesta base (confirmado, 0/5253 linhas) — mas o PEP do lado do
Orçamento não estava perdido, só escondido: `_dividir_centro_custo_pep`
(src/ingestion/loaders.py, 2026-08-10) separa o campo combinado em
`centro_custo_id` (formato CCRxxx/CGExxx) e `pep_id` (contém "/"), e vira
filtro global de sidebar — mas continua só do lado do Orçamento.
"Coordenação" agora existe como filtro global (derivado do nome do Centro
de Custo — ver build_star_schema.py), mas não é mostrada como coluna
própria aqui porque não veio assim da fonte.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.arvore_html import CSS_ARVORE, NOME_FAMILIA, cabecalho_arvore, linha_resumo
from src.dashboard.formatacao import escapar_cifrao_md, fmt_pacote, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.nivel4_contas import _filtros_padrao, dados_familia, dados_pacote
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO
from src.dashboard.tendencia import dados_tendencia, figura_tendencia
from src.engine.delta_calculator import calcular_delta

# Centro de Custo da própria GGG_0054 (não de nenhuma das 8 Gerências de
# campo — ver "Relação de Centro de Custo - DINFRA" trazida pelo usuário
# em 2026-08-12), domínio "Indireto Manutenção". Card abaixo mostra o
# recorte filtrado COM e SEM essa linha, pra reproduzir o número que o
# PMO mostra pra Diretoria (que aparenta excluir esse CC) sem precisar
# subtrair na mão. Se algum dia esse código de CC mudar/for confirmado
# como desabilitado pela Laís Machado (pendente, ela está de férias —
# ver docs/02-perguntas-em-aberto.md), ajustar aqui.
CENTRO_CUSTO_INDIRETO_GG = "CGG050"


def dados_centro_custo(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> pd.DataFrame:
    filtro_orcado, filtro_realizado = _filtros_padrao(familia)
    df = calcular_delta(
        con, dims=["familia_pacote", "pacote_id", "centro_custo_id"],
        filtro_orcado=filtro_orcado, filtro_realizado=filtro_realizado,
    )
    nomes = con.execute(
        "SELECT DISTINCT centro_custo_id, centro_custo_nome FROM fact_realizado "
        "WHERE centro_custo_nome IS NOT NULL"
    ).df()
    df = df.merge(nomes, on="centro_custo_id", how="left")
    df["centro_custo_nome"] = df["centro_custo_nome"].fillna("")
    return df


def _montar_arvore(
    df_familia: pd.DataFrame, df_pacote: pd.DataFrame, df_cc: pd.DataFrame, nomes_pacote: dict[str, str],
) -> str:
    partes = [CSS_ARVORE, '<div class="pnl-arvore">']
    partes.append(cabecalho_arvore("Família de Pacote / Pacote / Centro de Custo"))

    df_familia = df_familia.reindex(df_familia["orcado"].add(df_familia["realizado"]).sort_values(ascending=False).index)
    for _, fam in df_familia.iterrows():
        familia_id = fam["familia_pacote"]
        nome_familia = NOME_FAMILIA.get(familia_id, familia_id)
        partes.append('<details class="pnl-nivel1" open>')
        partes.append(f'<summary>{linha_resumo(nome_familia, fam["orcado"], fam["realizado"], fam["delta_total"])}</summary>')

        pacotes_fam = df_pacote[df_pacote["familia_pacote"] == familia_id]
        pacotes_fam = pacotes_fam.reindex(
            pacotes_fam["orcado"].add(pacotes_fam["realizado"]).sort_values(ascending=False).index
        )
        for _, pac in pacotes_fam.iterrows():
            pacote_id = pac["pacote_id"]
            rotulo_pacote = fmt_pacote(pacote_id, nomes_pacote.get(pacote_id))
            partes.append('<details class="pnl-nivel2">')
            partes.append(f'<summary>{linha_resumo(rotulo_pacote, pac["orcado"], pac["realizado"], pac["delta_total"])}</summary>')

            ccs = df_cc[df_cc["pacote_id"] == pacote_id]
            ccs = ccs.reindex(ccs["orcado"].add(ccs["realizado"]).sort_values(ascending=False).index)
            for _, cc in ccs.iterrows():
                nome_cc = cc["centro_custo_nome"] or ""
                rotulo_cc = f'{cc["centro_custo_id"]} — {nome_cc}' if nome_cc else cc["centro_custo_id"]
                partes.append(linha_resumo(rotulo_cc, cc["orcado"], cc["realizado"], cc["delta_total"], classe_extra="pnl-folha"))

            partes.append("</details>")
        partes.append("</details>")
    partes.append("</div>")
    return "".join(partes)


def _grafico_top_cc(df: pd.DataFrame, nomes_pacote: dict[str, str], top_n: int = 12) -> go.Figure | None:
    if df.empty:
        return None
    top = df.reindex(df["delta_total"].abs().sort_values(ascending=False).index).head(top_n)
    top = top.iloc[::-1]
    rotulo = top["pacote_id"].map(lambda p: fmt_pacote(p, nomes_pacote.get(p))) + " · " + top["centro_custo_id"]
    cores = [COR_ESTOURO if v > 0 else COR_ECONOMIA for v in top["delta_total"]]
    fig = go.Figure(go.Bar(
        x=top["delta_total"], y=rotulo, orientation="h", marker={"color": cores},
        text=[fmt_reais_abrev(v) for v in top["delta_total"]], textposition="auto", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Delta: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Maiores Desvios — {top_n} Principais (Pacote · Centro de Custo)",
        margin={"t": 60, "b": 40, "r": 110}, height=max(320, 30 * len(top)),
    )
    return fig


def _render_card_nivel5(df_familia: pd.DataFrame, df_cc: pd.DataFrame) -> None:
    orcado = df_familia["orcado"].sum()
    realizado = df_familia["realizado"].sum()
    delta = realizado - orcado
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"

    linha_indireto = ""
    cc_indireto = df_cc[df_cc["centro_custo_id"] == CENTRO_CUSTO_INDIRETO_GG]
    if not cc_indireto.empty:
        orcado_indireto = cc_indireto["orcado"].sum()
        realizado_indireto = cc_indireto["realizado"].sum()
        orcado_sem = orcado - orcado_indireto
        realizado_sem = realizado - realizado_indireto
        delta_sem = realizado_sem - orcado_sem
        cor_delta_sem = "red" if delta_sem > 0 else "green" if delta_sem < 0 else "gray"
        linha_indireto = f"""
            | &nbsp; | &nbsp; |
            | Orçado sem Indireto GG ({CENTRO_CUSTO_INDIRETO_GG}) | {fmt_reais_abrev(orcado_sem)} |
            | Realizado sem Indireto GG | {fmt_reais_abrev(realizado_sem)} |
            | Delta sem Indireto GG | :{cor_delta_sem}[**{fmt_reais_abrev(delta_sem)}**] |
            """

    with st.container(border=True):
        st.markdown("**Centro de Custo — recorte filtrado**")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado | {fmt_reais_abrev(orcado)} |
            | Realizado | {fmt_reais_abrev(realizado)} |
            | Delta | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Centros de Custo | {df_cc['centro_custo_id'].nunique()} |
            {linha_indireto}""")
        )
        if linha_indireto:
            st.caption(
                f"\"Sem Indireto GG\" tira o Centro de Custo "
                f"{CENTRO_CUSTO_INDIRETO_GG} (da própria GGG_0054, não de "
                f"nenhuma Gerência de campo) do total acima — é o número "
                f"que costuma bater com a visão que o PMO mostra pra "
                f"Diretoria. Confirmação formal desse tratamento ainda "
                f"pendente com a Laís Machado (de férias)."
            )


def render_arvore_centro_custo(
    con: duckdb.DuckDBPyConnection, familia: str | None = None, key_prefix: str = "n5",
    ano_fiscal: int | None = None, mostrar_resumo: bool = True,
) -> None:
    """Card-resumo | divisor | gráfico dos maiores desvios, Tendência do
    recorte filtrado embaixo (full-width), árvore completa por último —
    mesmo padrão do Nível 4. Usado pelo Nível 5 (sem filtro de família) e
    pela Visão Manutenção (`familia="PM"`).

    `mostrar_resumo=False` (Visão Manutenção, 2026-08-10): mesma razão do
    Nível 4 — a página já mostra seu próprio card-resumo/Tendência pra essa
    família, repetir aqui era número idêntico 2x. Nesse modo só entra o
    gráfico de maiores desvios (Pacote · Centro de Custo) + a árvore."""
    df_familia = dados_familia(con, familia=familia)
    df_pacote = dados_pacote(con, familia=familia)
    df_cc = dados_centro_custo(con, familia=familia)
    nomes_pacote = mapa_nomes_pacote(con)

    if df_familia.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        return

    if mostrar_resumo:
        col_card, col_linha, col_graf = st.columns([1, 0.04, 3], gap="medium")
        with col_card:
            _render_card_nivel5(df_familia, df_cc)
        with col_linha:
            st.markdown(
                "<div style='border-left: 1px solid #ccc; height: 100%; "
                "min-height: 420px; margin: 0 auto;'></div>",
                unsafe_allow_html=True,
            )
        with col_graf:
            fig = _grafico_top_cc(df_cc, nomes_pacote)
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}-top-cc", config=CONFIG_PLOTLY)
                st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
            else:
                st.info("Nenhum Centro de Custo com desvio no recorte selecionado.")

        if ano_fiscal is not None:
            st.divider()
            filtro_orcado, filtro_realizado = _filtros_padrao(familia)
            df_tend = dados_tendencia(
                con, ano_fiscal, filtro_orcado=filtro_orcado, filtro_realizado=filtro_realizado,
            )
            st.plotly_chart(
                figura_tendencia(df_tend, "Tendência do ano — recorte filtrado"),
                use_container_width=True, key=f"{key_prefix}-tendencia", config=CONFIG_PLOTLY,
            )
            st.caption(
                "Linha pontilhada = Forecast (saldo do desvio até o mês de "
                "referência, redistribuído nos meses restantes — fecha "
                "exatamente no Orçado Anual em dezembro). Segue o mesmo "
                "recorte de filtros aplicado acima (Pacote/Centro de "
                "Custo/PEP/Classificação/Coordenação/Gerência/Período)."
            )
    else:
        fig = _grafico_top_cc(df_cc, nomes_pacote)
        if fig:
            st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}-top-cc", config=CONFIG_PLOTLY)
            st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
        else:
            st.info("Nenhum Centro de Custo com desvio no recorte selecionado.")

    st.divider()
    arvore_html = _montar_arvore(df_familia, df_pacote, df_cc, nomes_pacote)
    st.markdown(arvore_html, unsafe_allow_html=True)


def render_nivel5_centro_custo(con: duckdb.DuckDBPyConnection, ano_fiscal: int) -> None:
    st.header("Nível 5 — Centro de Custo")
    st.caption(
        "Família de Pacote → Pacote → Centro de Custo, no mesmo estilo do "
        "Nível 4. Diferente do Nível 4 (Conta), o código de Centro de "
        "Custo é compartilhado entre Orçamento e Realizado, então aqui "
        "fecha um Delta de verdade até a linha-folha."
    )
    render_arvore_centro_custo(con, key_prefix="n5", ano_fiscal=ano_fiscal)
