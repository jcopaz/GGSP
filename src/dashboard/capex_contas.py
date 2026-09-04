"""Nível 4 CAPEX — árvore Gerência de Obras → Projeto → Conta, mesmo
estilo colapsável do Nível 4 OPEX (nivel4_contas.py), reaproveitando o
HTML/CSS compartilhado de arvore_html.py. Fonte: CJI4 (Orçado) x CJI3
(Realizado), trazidos em 2026-08-11.
"""
from __future__ import annotations

import duckdb
import plotly.graph_objects as go
import streamlit as st

from src.branding import render_page_banner
from src.dashboard.arvore_html import CSS_ARVORE, cabecalho_arvore, linha_resumo
from src.dashboard.capex_dados import dados_contas, dados_gerencia_obras, rotulo_projeto, tabelas_disponiveis
from src.dashboard.filtros import guardar_e_faixa_universo
from src.dashboard.formatacao import escapar_cifrao_md, fmt_reais_abrev
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.layout import bloco_resumo_visual
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO


def _rotulo_conta(conta_interna_id: str, conta_interna_nome: str) -> str:
    if conta_interna_nome:
        return f"{conta_interna_id} — {conta_interna_nome}"
    return conta_interna_id


def _montar_arvore(df_conta) -> str:
    partes = [CSS_ARVORE, '<div class="pnl-arvore">']
    partes.append(cabecalho_arvore("Gerência de Obras / Projeto / Conta"))

    df_gerencia = df_conta.groupby("gerencia_obras", dropna=False, as_index=False)[
        ["orcado", "realizado"]
    ].sum()
    df_gerencia["delta_total"] = df_gerencia["realizado"] - df_gerencia["orcado"]
    df_gerencia = df_gerencia.reindex(
        df_gerencia["orcado"].add(df_gerencia["realizado"]).sort_values(ascending=False).index
    )

    for _, ger in df_gerencia.iterrows():
        gerencia_obras = ger["gerencia_obras"]
        rotulo_ger = gerencia_obras or "Não catalogado"
        partes.append('<details class="pnl-nivel1" open>')
        partes.append(
            f'<summary>{linha_resumo(rotulo_ger, ger["orcado"], ger["realizado"], ger["delta_total"])}</summary>'
        )

        projetos_ger = df_conta[df_conta["gerencia_obras"] == gerencia_obras].groupby(
            ["e_pep_projeto", "nome_empreendimento"], dropna=False, as_index=False
        )[["orcado", "realizado"]].sum()
        projetos_ger["delta_total"] = projetos_ger["realizado"] - projetos_ger["orcado"]
        projetos_ger = projetos_ger.reindex(
            projetos_ger["orcado"].add(projetos_ger["realizado"]).sort_values(ascending=False).index
        )

        for _, proj in projetos_ger.iterrows():
            e_pep_projeto = proj["e_pep_projeto"]
            rotulo_proj = rotulo_projeto(e_pep_projeto, proj["nome_empreendimento"])
            partes.append('<details class="pnl-nivel2">')
            partes.append(
                f'<summary>{linha_resumo(rotulo_proj, proj["orcado"], proj["realizado"], proj["delta_total"])}</summary>'
            )

            contas_proj = df_conta[
                (df_conta["gerencia_obras"] == gerencia_obras) & (df_conta["e_pep_projeto"] == e_pep_projeto)
            ]
            contas_proj = contas_proj.reindex(
                contas_proj["orcado"].add(contas_proj["realizado"]).sort_values(ascending=False).index
            )
            for _, cta in contas_proj.iterrows():
                rotulo_cta = _rotulo_conta(cta["conta_interna_id"], cta["conta_interna_nome"])
                partes.append(
                    linha_resumo(rotulo_cta, cta["orcado"], cta["realizado"], cta["delta_total"], classe_extra="pnl-folha")
                )

            partes.append("</details>")
        partes.append("</details>")
    partes.append("</div>")
    return "".join(partes)


def _grafico_top_contas(df_conta, top_n: int = 15) -> go.Figure | None:
    if df_conta.empty:
        return None
    top = df_conta.reindex(df_conta["delta_total"].abs().sort_values(ascending=False).index).head(top_n)
    top = top.iloc[::-1]
    rotulo = (
        top.apply(lambda r: rotulo_projeto(r["e_pep_projeto"], r["nome_empreendimento"]), axis=1)
        + " · " + top.apply(lambda r: _rotulo_conta(r["conta_interna_id"], r["conta_interna_nome"]), axis=1)
    )
    cores = [COR_ESTOURO if v > 0 else COR_ECONOMIA for v in top["delta_total"]]
    fig = go.Figure(go.Bar(
        x=top["delta_total"], y=rotulo, orientation="h", marker={"color": cores},
        text=[fmt_reais_abrev(v) for v in top["delta_total"]], textposition="auto", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Delta: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Contas com Maior Desvio — {top_n} Principais (Projeto · Conta)",
        margin={"t": 60, "b": 40, "r": 110}, height=max(320, 28 * len(top)),
    )
    return fig


def _render_card_nivel4(df_gerencia, df_conta) -> None:
    orcado = df_gerencia["orcado"].sum()
    realizado = df_gerencia["realizado"].sum()
    delta = realizado - orcado
    cor_delta = "red" if delta > 0 else "green" if delta < 0 else "gray"
    with st.container(border=True):
        st.markdown("**Contas CAPEX — recorte filtrado**")
        st.markdown(
            escapar_cifrao_md(f"""
            | | |
            |---|---|
            | Orçado | {fmt_reais_abrev(orcado)} |
            | Realizado | {fmt_reais_abrev(realizado)} |
            | Delta | :{cor_delta}[**{fmt_reais_abrev(delta)}**] |
            | Projetos | {df_conta['e_pep_projeto'].nunique()} |
            | Contas distintas | {df_conta['conta_interna_id'].nunique()} |
            """)
        )


def render_nivel4_contas_capex(con: duckdb.DuckDBPyConnection) -> None:
    render_page_banner("🧾", "Contas", "Conta sem nome catalogado mostra só o código, nunca um nome inventado.")
    guardar_e_faixa_universo(con, "capex_obras")  # RBAC de escopo (docs/08)

    tem_orc, tem_real = tabelas_disponiveis(con)
    if not tem_orc and not tem_real:
        st.warning(
            "Nenhum arquivo de CAPEX de Projetos e Obras carregado ainda "
            "(CJI4/CJI3 em data/raw/)."
        )
        return

    df_conta = dados_contas(con)
    df_gerencia = dados_gerencia_obras(con)
    if df_conta.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        return

    def _visual_top_contas() -> None:
        fig = _grafico_top_contas(df_conta)
        if fig:
            st.plotly_chart(fig, use_container_width=True, key="capex-n4-top-contas", config=CONFIG_PLOTLY)
            st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
        else:
            st.info("Nenhuma conta com desvio no recorte selecionado.")

    bloco_resumo_visual(
        lambda: _render_card_nivel4(df_gerencia, df_conta),
        _visual_top_contas,
        key="capex-n4",
    )

    st.divider()
    arvore_html = _montar_arvore(df_conta)
    st.markdown(arvore_html, unsafe_allow_html=True)
