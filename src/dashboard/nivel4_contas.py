"""Nível 4 — Contas: árvore Família de Pacote → Pacote → Conta, no estilo
da "Visão acumulado" do Power BI de referência (imagem trazida pelo usuário
em 2026-08-06), com colapsar/expandir nativo do navegador (`<details>`).

**Unificado em 2026-08-10** (a pedido do usuário: "não separar em Contas
Orçamento Base Zero e Contas Realizado, colocar em uma única linha"). Antes,
a Conta abria em 2 subárvores porque `conta_orcamento_id` (Base Zero, ex.
"PM03010") e `conta_razao_id` (Razão SAP, ex. "4130110101") são sistemas de
código diferentes, sem De-Para. Agora existe De-Para real — o Catálogo de
Contas (`load_catalogo_contas`, ver build_star_schema.py) mapeia os dois pro
mesmo `conta_interna_id`/`conta_interna_nome` (ex.: os dois códigos acima
viram "PM03010 — SERVIÇOS DE SUPER ESTRUTURA DE VIA"), a mesma chave que
`fact_orcamento` e `fact_realizado` carregam. Por isso a Conta agora fecha
Orçado x Real x Delta numa linha só, igual o Nível 5 já faz pra Centro de
Custo — e nenhuma conta fica sem nome: sem o catálogo (ou código não
catalogado), cai no próprio código, nunca inventa nome.

O HTML/CSS da árvore (`<details>` colapsável) mora em arvore_html.py,
compartilhado com o Nível 5 — extraído daqui em 2026-08-06 pra não duplicar
entre os dois níveis (e reaproveitado também na Visão Manutenção via
`render_arvore_contas(con, familia="PM")`).
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.arvore_html import (
    CSS_ARVORE,
    NOME_FAMILIA,
    cabecalho_arvore,
    linha_resumo,
)
from src.dashboard.filtros import clausula_familia, clausula_periodo, clausula_where, combinar_clausulas
from src.dashboard.formatacao import escapar_cifrao_md, fmt_pacote, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO
from src.dashboard.tendencia import dados_tendencia, figura_tendencia
from src.engine.delta_calculator import calcular_delta


def _filtros_padrao(familia: str | None) -> tuple[tuple[str, list], tuple[str, list]]:
    """(filtro_orcado, filtro_realizado) — mesmo recorte de filtros da
    sidebar (Pacote/Centro de Custo/PEP/Classificação/Coordenação/
    Gerência/Período) usado por dados_familia/dados_pacote/dados_conta E
    pela Tendência do recorte (ver render_arvore_contas) — extraído em
    2026-08-10 pra não repetir a mesma lógica 4x.

    Gerência no lado do Orçado usa a coluna `gerencia_raw`, não
    `gerencia_nome` (fact_orcamento não tem essa coluna) — corrigido em
    2026-08-11: o filtro de Gerência filtrava só o Realizado, deixando o
    Orçado do OPEX de fora mesmo já tendo o mesmo texto disponível
    (`gerencia_raw` carrega o nome real da Consulta de Contas pro OPEX,
    ver `_reshape_consulta_contas_opex` em build_star_schema.py — bate
    com `gerencia_nome` do Realizado, mesma fonte/hierarquia). CAPEX
    (Base Zero) não tem Gerência real, então essas linhas nunca batem
    com nenhum valor selecionado — ficam de fora quando o filtro de
    Gerência está ativo, o que é o comportamento correto (não sabemos a
    Gerência do CAPEX, não dá pra incluir por suposição). Coordenação
    continua só no Realizado — Orçado não tem essa informação de jeito
    nenhum (nem indireto), ver `_derivar_coordenacao`.
    """
    extra_where, extra_params = clausula_familia(familia)
    where_orc, params_orc = combinar_clausulas(
        clausula_where({
            "pacote_id": "pacote_id", "centro_custo_id": "centro_custo_id",
            "pep_id": "pep_id", "classificacao_contabil": "classificacao_contabil",
            "gerencia_nome": "gerencia_raw",
        }),
        clausula_periodo(),
    )
    where_real, params_real = combinar_clausulas(
        clausula_where({
            "pacote_id": "pacote_id", "centro_custo_id": "centro_custo_id",
            "coordenacao": "coordenacao", "gerencia_nome": "gerencia_nome",
        }),
        clausula_periodo(),
    )
    return (where_orc + extra_where, params_orc + extra_params), (where_real + extra_where, params_real + extra_params)


def dados_familia(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> pd.DataFrame:
    filtro_orcado, filtro_realizado = _filtros_padrao(familia)
    return calcular_delta(
        con, dims=["familia_pacote"],
        filtro_orcado=filtro_orcado, filtro_realizado=filtro_realizado,
    )


def dados_pacote(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> pd.DataFrame:
    filtro_orcado, filtro_realizado = _filtros_padrao(familia)
    return calcular_delta(
        con, dims=["familia_pacote", "pacote_id"],
        filtro_orcado=filtro_orcado, filtro_realizado=filtro_realizado,
    )


def dados_conta(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> pd.DataFrame:
    """Orçado x Real x Delta por `conta_interna_id` — a chave unificada do
    Catálogo de Contas (ver docstring do módulo). 1 linha por conta, não
    mais 2 subárvores separadas."""
    filtro_orcado, filtro_realizado = _filtros_padrao(familia)
    df = calcular_delta(
        con, dims=["familia_pacote", "pacote_id", "conta_interna_id"],
        filtro_orcado=filtro_orcado, filtro_realizado=filtro_realizado,
    )
    # Nome pode vir de qualquer um dos 2 lados (o que tiver preenchido) —
    # uma conta que só existe no Realizado ainda tem nome do SAP; uma que
    # só existe no Orçado tem nome do catálogo.
    nomes = con.execute("""
        SELECT conta_interna_id, MAX(NULLIF(conta_interna_nome, '')) AS conta_interna_nome
        FROM (
            SELECT conta_interna_id, conta_interna_nome FROM fact_orcamento
            UNION ALL
            SELECT conta_interna_id, conta_interna_nome FROM fact_realizado
        )
        GROUP BY conta_interna_id
    """).df()
    df = df.merge(nomes, on="conta_interna_id", how="left")
    df["conta_interna_nome"] = df["conta_interna_nome"].fillna("")
    return df


def _rotulo_conta(conta_interna_id: str, conta_interna_nome: str) -> str:
    if conta_interna_nome:
        return f"{conta_interna_id} — {conta_interna_nome}"
    return conta_interna_id


def _montar_arvore(
    df_familia: pd.DataFrame, df_pacote: pd.DataFrame, df_conta: pd.DataFrame,
    nomes_pacote: dict[str, str],
) -> str:
    partes = [CSS_ARVORE, '<div class="pnl-arvore">']
    partes.append(cabecalho_arvore("Classif. Pacote / Pacote / Conta"))

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

            contas_pac = df_conta[df_conta["pacote_id"] == pacote_id]
            contas_pac = contas_pac.reindex(
                contas_pac["orcado"].add(contas_pac["realizado"]).sort_values(ascending=False).index
            )
            for _, cta in contas_pac.iterrows():
                rotulo_cta = _rotulo_conta(cta["conta_interna_id"], cta["conta_interna_nome"])
                partes.append(
                    linha_resumo(rotulo_cta, cta["orcado"], cta["realizado"], cta["delta_total"], classe_extra="pnl-folha")
                )

            partes.append("</details>")
        partes.append("</details>")
    partes.append("</div>")
    return "".join(partes)


def _grafico_top_contas(df_conta: pd.DataFrame, nomes_pacote: dict[str, str], top_n: int = 15) -> go.Figure | None:
    if df_conta.empty:
        return None
    top = df_conta.reindex(df_conta["delta_total"].abs().sort_values(ascending=False).index).head(top_n)
    top = top.iloc[::-1]
    rotulo = (
        top["pacote_id"].map(lambda p: fmt_pacote(p, nomes_pacote.get(p)))
        + " · " + top.apply(lambda r: _rotulo_conta(r["conta_interna_id"], r["conta_interna_nome"]), axis=1)
    )
    cores = [COR_ESTOURO if v > 0 else COR_ECONOMIA for v in top["delta_total"]]
    fig = go.Figure(go.Bar(
        x=top["delta_total"], y=rotulo, orientation="h", marker={"color": cores},
        text=[fmt_reais_abrev(v) for v in top["delta_total"]], textposition="auto", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Delta: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Contas com Maior Desvio — {top_n} Principais (Pacote · Conta)",
        margin={"t": 60, "b": 40, "r": 110}, height=max(320, 28 * len(top)),
    )
    return fig


def _render_card_nivel4(df_familia: pd.DataFrame, df_pacote: pd.DataFrame, df_conta: pd.DataFrame) -> None:
    orcado = df_familia["orcado"].sum()
    realizado = df_familia["realizado"].sum()
    delta = realizado - orcado
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"
    with st.container(border=True):
        st.markdown("**Contas — recorte filtrado**")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado | {fmt_reais_abrev(orcado)} |
            | Realizado | {fmt_reais_abrev(realizado)} |
            | Delta | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Pacotes | {df_pacote['pacote_id'].nunique()} |
            | Contas distintas | {df_conta['conta_interna_id'].nunique()} |
            """)
        )


def render_arvore_contas(
    con: duckdb.DuckDBPyConnection, familia: str | None = None, key_prefix: str = "n4",
    ano_fiscal: int | None = None, mostrar_resumo: bool = True,
) -> None:
    """Card-resumo | divisor | gráfico dos maiores desvios, Tendência do
    recorte filtrado embaixo (full-width), árvore completa por último —
    mesmo padrão do Painel Executivo. Usado pelo Nível 4 (sem filtro de
    família) e pela Visão Manutenção (`familia="PM"`).

    `mostrar_resumo=False` (Visão Manutenção, 2026-08-10): a página que
    chama já tem seu próprio card-resumo/Tendência pra essa mesma família —
    repetir aqui era informação idêntica 2x (mesmo Orçado/Realizado/Delta,
    mesma Tendência, já que não há filtro adicional). Nesse modo só entra o
    gráfico de maiores desvios (informação nova: quais Contas puxam o
    desvio) + a árvore."""
    df_familia = dados_familia(con, familia=familia)
    df_pacote = dados_pacote(con, familia=familia)
    df_conta = dados_conta(con, familia=familia)
    nomes_pacote = mapa_nomes_pacote(con)

    if df_familia.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        return

    if mostrar_resumo:
        col_card, col_linha, col_graf = st.columns([1, 0.04, 3], gap="medium")
        with col_card:
            _render_card_nivel4(df_familia, df_pacote, df_conta)
        with col_linha:
            st.markdown(
                "<div style='border-left: 1px solid #ccc; height: 100%; "
                "min-height: 420px; margin: 0 auto;'></div>",
                unsafe_allow_html=True,
            )
        with col_graf:
            fig = _grafico_top_contas(df_conta, nomes_pacote)
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}-top-contas", config=CONFIG_PLOTLY)
                st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
            else:
                st.info("Nenhuma conta com desvio no recorte selecionado.")

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
        fig = _grafico_top_contas(df_conta, nomes_pacote)
        if fig:
            st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}-top-contas", config=CONFIG_PLOTLY)
            st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
        else:
            st.info("Nenhuma conta com desvio no recorte selecionado.")

    st.divider()
    arvore_html = _montar_arvore(df_familia, df_pacote, df_conta, nomes_pacote)
    st.markdown(arvore_html, unsafe_allow_html=True)


def render_nivel4_contas(con: duckdb.DuckDBPyConnection, ano_fiscal: int) -> None:
    st.header("Nível 4 — Contas")
    st.caption(
        "Família de Pacote → Pacote → Conta, Orçado x Real x Delta numa "
        "linha só (unificado via Catálogo de Contas — antes abria em 2 "
        "subárvores separadas). Conta sem nome catalogado mostra só o "
        "código, nunca um nome inventado."
    )
    render_arvore_contas(con, key_prefix="n4", ano_fiscal=ano_fiscal)
