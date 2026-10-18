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

from src.branding import render_page_banner
from src.dashboard.arvore_html import (
    CSS_ARVORE,
    NOME_FAMILIA,
    cabecalho_arvore,
    linha_resumo,
)
from src.dashboard.filtros import (
    clausula_familia,
    clausulas_recorte,
    guardar_e_faixa_universo,
    nota_fechamento_recorte,
    rotulo_periodo,
    ultimo_periodo_fechado,
)
from src.dashboard.formatacao import escapar_cifrao_md, fmt_pacote, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.grafico_interativo import CONFIG_PLOTLY
from src.dashboard.layout import bloco_resumo_visual, nota_forecast
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO
from src.dashboard.tendencia import dados_tendencia, figura_tendencia
from src.engine.delta_calculator import calcular_delta


def _filtros_padrao(
    familia: str | None,
    con: duckdb.DuckDBPyConnection | None = None,
    ate_fechamento: bool = False,
    incluir_periodo: bool = True,
) -> tuple[tuple[str, list], tuple[str, list]]:
    """(filtro_orcado, filtro_realizado) do recorte da sidebar, usado por
    dados_familia/dados_pacote/dados_conta, pelo Nível 5 e pela Visão
    Manutenção (que reusam este helper) e pela Tendência do recorte.

    **Reescrito em 2026-10-18 (validação de filtros, P1/P2):**
    - Usa `filtros.clausulas_recorte` — a MESMA regra do Resumo nos dois
      fatos. Antes o lado Realizado ignorava Classificação e PEP: com
      Classificação = CAPEX o Orçado zerava e o Realizado OPEX continuava
      inteiro (Delta de +R$ 20,9 MM na PM). Gerência no Orçado passa de
      `gerencia_raw` para `gerencia_id`.
    - Orçado SEMPRE só OPEX (B1, decisão do Julio em 2026-10-18, opção
      b): o Realizado carregado é 100% OPEX, e comparar o Orçado
      CAPEX+OPEX contra ele inflava o Delta (Contas e CC mostravam
      -R$ 66,2 MM contra -R$ 23,1 MM do Resumo). Até a rodada anterior,
      escolher Classificação = CAPEX trazia o CAPEX pra árvore com
      Realizado zero — um Delta = -Orçado que não é desvio, é falta de
      fonte. Agora Contas, CC e Tendência são OPEX x OPEX sempre; a
      Classificação continua nos dois lados (via `clausulas_recorte`):
      CAPEX → 0/0, CAPEX+OPEX → OPEX x OPEX. O CAPEX Sustaining do recorte
      aparece só como informação, sem Delta (`aviso_capex_sustaining`).
    - `ate_fechamento=True` (com `con`): Orçado e Realizado só até o último
      mês fechado (P7, "a realizar"). As Tendências chamam sem corte, pra
      desenhar o ano inteiro; `incluir_periodo=False` idem.
    """
    (where_orc, params_orc), (where_real, params_real) = clausulas_recorte(
        "opex_sustaining", incluir_periodo=incluir_periodo, con=con, ate_fechamento=ate_fechamento,
    )
    where_orc += " AND classificacao_contabil = 'OPEX'"
    extra_where, extra_params = clausula_familia(familia)
    return (
        (where_orc + extra_where, params_orc + extra_params),
        (where_real + extra_where, params_real + extra_params),
    )


def orcado_capex_fora_da_arvore(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> float:
    """Orçado CAPEX Sustaining do recorte, que NÃO entra na árvore (ver
    `_filtros_padrao`: Contas/CC são sempre OPEX x OPEX). Mostrado à parte
    por `aviso_capex_sustaining` — Regra de Ouro, nada some calado.

    B1 (2026-10-18): usa o recorte do universo `capex_sustaining` —
    respeita todos os filtros (Classificação = OPEX zera; Gerência pega o
    PEP da região) e o RBAC desse universo: quem não tem acesso ao CAPEX
    Sustaining recebe `1=0` → 0 (antes o valor vazava pra quem só tinha
    OPEX, e com qualquer filtro de Classificação voltava 0 calado). Sem
    corte de fechamento: não há Delta aqui, é o Orçado do recorte inteiro."""
    (where_orc, params_orc), _ = clausulas_recorte("capex_sustaining")
    extra_where, extra_params = clausula_familia(familia)
    (valor,) = con.execute(
        f"SELECT SUM(valor_orcado) FROM fact_orcamento WHERE classificacao_contabil = 'CAPEX'"
        f"{where_orc}{extra_where}",
        params_orc + extra_params,
    ).fetchone()
    return float(valor or 0.0)


# B1 (2026-10-18): não citar a fonte — a fonte do Realizado CAPEX ainda vai
# ser decidida (correção do Julio).
TEXTO_REALIZADO_CAPEX_AUSENTE = (
    "O Realizado do CAPEX Sustaining ainda não está carregado no painel — por isso esse "
    "Orçado fica fora do Delta e da Aderência. Ver a aba CAPEX Sustaining."
)


def aviso_capex_sustaining(
    con: duckdb.DuckDBPyConnection, familia: str | None = None, destaque: bool = False,
) -> None:
    """Linha informativa do CAPEX Sustaining do recorte (B1, 2026-10-18):
    "Orçado ... R$ X · Realizado: — (não carregado)". Nunca "R$ 0" no
    Realizado (seria afirmar que não houve gasto) e nunca Delta/Aderência.
    `st.info` quando o recorte não tem OPEX (filtro de Classificação sem
    OPEX, ou `destaque=True` — árvore vazia); senão `st.caption` embaixo
    do card. Só aparece com valor ≠ 0."""
    capex = orcado_capex_fora_da_arvore(con, familia)
    if not capex:
        return
    texto = escapar_cifrao_md(
        f"Orçado CAPEX Sustaining do recorte: {fmt_reais_abrev(capex)} · Realizado: — (não carregado). "
        + TEXTO_REALIZADO_CAPEX_AUSENTE
    )
    classificacao = st.session_state.get("filtro_classificacao") or []
    if destaque or (classificacao and "OPEX" not in classificacao):
        st.info(texto)
    else:
        st.caption(texto)


def nota_recorte_arvore(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> None:
    """Legenda comum dos cards de Contas / Centro de Custo: corte no último
    mês fechado, mês(es) em aberto com o Realizado parcial (B4), a realizar
    + CAPEX Sustaining que ficou fora da comparação (B1)."""
    filtro_orc_sem_corte, filtro_real_sem_corte = _filtros_padrao(familia)
    nota_fechamento_recorte(con, filtro_orc_sem_corte, filtro_real_sem_corte)
    aviso_capex_sustaining(con, familia)


def dados_familia(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> pd.DataFrame:
    filtro_orcado, filtro_realizado = _filtros_padrao(familia, con=con, ate_fechamento=True)
    return calcular_delta(
        con, dims=["familia_pacote"],
        filtro_orcado=filtro_orcado, filtro_realizado=filtro_realizado,
    )


def dados_pacote(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> pd.DataFrame:
    filtro_orcado, filtro_realizado = _filtros_padrao(familia, con=con, ate_fechamento=True)
    return calcular_delta(
        con, dims=["familia_pacote", "pacote_id"],
        filtro_orcado=filtro_orcado, filtro_realizado=filtro_realizado,
    )


def dados_conta(con: duckdb.DuckDBPyConnection, familia: str | None = None) -> pd.DataFrame:
    """Orçado x Real x Delta por `conta_interna_id` — a chave unificada do
    Catálogo de Contas (ver docstring do módulo). 1 linha por conta, não
    mais 2 subárvores separadas."""
    filtro_orcado, filtro_realizado = _filtros_padrao(familia, con=con, ate_fechamento=True)
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


def rotulo_ate_corte(con: duckdb.DuckDBPyConnection) -> str:
    """"até Ago/2026" (último mês fechado) ou "" sem corte — rótulo das
    linhas Orçado/Realizado dos cards de Contas, CC e Manutenção (N4,
    2026-10-18: o card dizia só "Orçado" e parecia o ano inteiro)."""
    corte = rotulo_periodo(ultimo_periodo_fechado(con))
    return f" até {corte}" if corte else ""


def _render_card_nivel4(
    df_familia: pd.DataFrame, df_pacote: pd.DataFrame, df_conta: pd.DataFrame, ate: str = "",
) -> None:
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
            | Orçado{ate} | {fmt_reais_abrev(orcado)} |
            | Realizado{ate} | {fmt_reais_abrev(realizado)} |
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
        # B1 (2026-10-18): a árvore é sempre OPEX — com Classificação =
        # CAPEX ela fica vazia, e o CAPEX do recorte sumia calado. Aviso
        # com o valor ANTES do return. Sem resumo (Visão Manutenção), o
        # card da própria página já mostra o aviso — não repete.
        st.info("Nenhum OPEX no recorte selecionado.")
        if mostrar_resumo:
            aviso_capex_sustaining(con, familia, destaque=True)
        return

    if mostrar_resumo:
        def _visual_top_contas() -> None:
            fig = _grafico_top_contas(df_conta, nomes_pacote)
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}-top-contas", config=CONFIG_PLOTLY)
                st.caption("🔴 vermelho = estouro (Delta positivo) · 🟢 verde = economia (Delta negativo).")
            else:
                st.info("Nenhuma conta com desvio no recorte selecionado.")

        bloco_resumo_visual(
            lambda: (
                _render_card_nivel4(df_familia, df_pacote, df_conta, rotulo_ate_corte(con)),
                nota_recorte_arvore(con, familia),
            ),
            _visual_top_contas,
            key=f"{key_prefix}-resumo",
        )

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
            nota_forecast(com_recorte=True)
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
    render_page_banner("🧾", "Contas", "Conta sem nome catalogado mostra só o código, nunca um nome inventado.")
    guardar_e_faixa_universo(con, "opex_sustaining")  # RBAC de escopo (docs/08)
    render_arvore_contas(con, key_prefix="n4", ano_fiscal=ano_fiscal)
