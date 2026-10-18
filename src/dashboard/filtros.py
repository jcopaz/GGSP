"""Filtros globais da barra lateral, em 3 grupos hierárquicos (reorganizado
em 2026-08-10, a pedido do usuário — "precisamos de uma hierarquia
organizada"):

1. 🏢 Organização (quem) — Gerência → Coordenação → Centro de Custo → PEP.
2. 📦 Projeto / Classificação (o quê) — Classificação (CAPEX/OPEX) → Pacote.
3. 📅 Tempo (quando) — Período (Ano/Trimestre/Mês).

Ficam abaixo da navegação, a pedido do usuário em 2026-08-06.

Nem toda tabela tem todas essas colunas: fact_orcamento não tem
Coordenação nem Gerência no mesmo vocabulário do Realizado (só a
"Gerência" bruta SP/VP — ver GAP em build_star_schema.py), então cada
página aplica só os filtros que fazem sentido pra ela ("caso se aplique",
como pedido) — `clausula_where` só usa as chaves que a tabela chamando
realmente tem.

Filtro de PEP adicionado em 2026-08-10. O campo "Elemento PEP" do Realizado
continua 100% vazio no export (confirmado, 0/5253 linhas) — mas o PEP
existe do lado do Orçamento, escondido dentro do campo combinado "Centro de
Custo/PEP" da Base Zero. `_dividir_centro_custo_pep`
(src/ingestion/loaders.py) separa os dois por um critério confirmado contra
o dado real: código com "/" é PEP (sempre CAPEX), sem "/" é Centro de Custo
formato CCRxxx/CGExxx (sempre OPEX, bate 1:1 com o Realizado). Por isso o
filtro de PEP só filtra `fact_orcamento`, igual Classificação Contábil.

Filtro de Período (Ano/Trimestre/Mês) adicionado em 2026-08-06, a pedido do
usuário ("filtro que dê a possibilidade de escolher dentro de uma árvore o
Período"). Aplicado nos Níveis 4/5/6 e na Visão Manutenção via
`clausula_periodo` (mesmas páginas que já usam `clausula_where`).

**Desde 2026-08-11, Período também filtra Nível 1/2/3, Resumo Executivo,
"Ver por Gerência" e o Mapa de Calor** — diferente de
Gerência/Coordenação/Centro de Custo/PEP/Classificação (que continuam
fora dessas páginas, de propósito), Período não quebra o fechamento
matemático do waterfall: `explicacoes.csv` (motor de causa) já tem
`ano`/`mes` por linha, então dá pra filtrar o Delta (SQL, via
`clausula_periodo`) e a explicação de causa (em memória, via
`filtrar_periodo_df`) pelo mesmo recorte de tempo sem ratear nada.
Gerência/Coordenação/etc. não têm essa saída: a causa só é rastreada por
Pacote inteiro, não por sub-recorte de Gerência dentro do Pacote — filtrar
por Gerência ali exigiria inventar um rateio, e por isso continuam fora.

Em 2026-08-07, a pedido do usuário ("se eu quiser ver 2 trimestres quero
poder selecionar"), o Período deixou de ser árvore em cascata (Ano libera
Trimestre libera Mês, um valor por vez) e virou 3 `st.multiselect`
independentes — dá pra combinar, por exemplo, 2026+2027 ou T1+T3. Ano
filtra a coluna de ano; Mês e Trimestre disputam a coluna de mês (mesma
condição SQL), então quando os dois têm seleção, Mês manda e Trimestre é
ignorado, pra não gerar contradição tipo "T1 e Mar" com Mar já dentro de
T1 — ver `clausula_periodo`.

Filtro de Classificação Contábil (CAPEX/OPEX) adicionado em 2026-08-07, a
pedido do usuário. Só existe em `fact_orcamento` — o Realizado (SAP) não
carrega essa coluna por linha (ver GAP no topo de build_star_schema.py, o
mesmo motivo pelo qual não virou `dim_classificacao`). Por isso funciona
como o inverso de Coordenação/Gerência: aparece na sidebar pra todo mundo,
mas só entra no `clausula_where` das consultas que apontam pra
`fact_orcamento`.

**Multiseleção habilitada em 2026-08-11** (a pedido do usuário): os 6
filtros simples (Gerência/Coordenação/Centro de Custo/PEP/Classificação/
Pacote) eram `st.sidebar.selectbox` (1 valor + "Todos") — viraram
`st.sidebar.multiselect` (0+ valores; lista vazia = sem filtro, mesmo
efeito de "Todos" antes — o sentinel `TODOS` foi removido, não faz mais
sentido com multiselect). `clausula_where` monta `IN (...)` quando há 1+
valor selecionado, em vez de `= ?`. Período (Ano/Trimestre/Mês) já era
multiselect desde 2026-08-07, sem mudança.

**Cascata em Gerência → Coordenação → Centro de Custo (2026-08-29)**, a
pedido do usuário ("Centro de Custo é igual a Coordenação/Gerência?") —
conferido no dado real que é uma hierarquia estrita (0 exceção em
`fact_realizado`: nenhum Centro de Custo pertence a mais de 1
Coordenação/Gerência, nenhuma Coordenação pertence a mais de 1
Gerência). Diferente do Período (que teve a cascata REMOVIDA em
2026-08-07 pra permitir combinar valores não relacionados, ex. 2 anos):
aqui cada caixa continua multiseleção livre, só a LISTA DE SUGESTÕES
estreita (ver `_opcoes_filtradas`) — não é uma árvore de 1 valor por
vez. Não fica genuinamente "redundante" na prática porque a camada do
meio (Coordenação) só existe pra parte das Gerências (o resto tem
Centro de Custo direto, sem sub-agrupamento nomeado) — ver
`docs/04-licoes-aprendidas.md`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import duckdb
import streamlit as st

from src.auth.permissions import escopo_universo

_CHAVES_SESSAO = {
    "gerencia_nome": "filtro_gerencia",
    "coordenacao": "filtro_coordenacao",
    "centro_custo_id": "filtro_centro_custo",
    "pep_id": "filtro_pep",
    "classificacao_contabil": "filtro_classificacao",
    "pacote_id": "filtro_pacote",
}

# chave de sessão aplicada -> chave do widget de rascunho (usada só pelos
# botões Aplicar/Limpar, ver renderizar_filtros_sidebar).
_CHAVES_WIDGET = {
    "filtro_gerencia": "w_filtro_gerencia",
    "filtro_coordenacao": "w_filtro_coordenacao",
    "filtro_centro_custo": "w_filtro_centro_custo",
    "filtro_pep": "w_filtro_pep",
    "filtro_classificacao": "w_filtro_classificacao",
    "filtro_pacote": "w_filtro_pacote",
    "filtro_projeto_capex": "w_filtro_projeto_capex",
    "filtro_elemento_pep_capex": "w_filtro_elemento_pep_capex",
    "filtro_periodo_anos": "w_periodo_anos",
    "filtro_periodo_trimestres": "w_periodo_trimestres",
    "filtro_periodo_meses": "w_periodo_meses",
}

_NOMES_MES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
              7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def _grupo_filtro(texto: str, primeiro: bool = False) -> None:
    """Cabeçalho de grupo de filtro na sidebar — caixa-alta, hairline em
    cima, pros 3 grupos se lerem como grupos (classe `.f360-filtro-grupo`
    definida em branding.inject_shell_css, 6.4.0). Substitui o
    `st.sidebar.markdown("**Título**")` solto."""
    classe = "f360-filtro-grupo is-first" if primeiro else "f360-filtro-grupo"
    st.sidebar.markdown(f'<div class="{classe}">{texto}</div>', unsafe_allow_html=True)


def _opcoes(con: duckdb.DuckDBPyConnection, tabelas_colunas: list[tuple[str, str]]) -> list[str]:
    """União de valores distintos de uma coluna em 1+ tabelas — o mesmo
    filtro pode precisar casar com tabelas diferentes (ex.: pacote_id
    existe em fact_orcamento e fact_realizado, com códigos em comum)."""
    valores: set[str] = set()
    for tabela, coluna in tabelas_colunas:
        df = con.execute(
            f"SELECT DISTINCT {coluna} FROM {tabela} "
            f"WHERE {coluna} IS NOT NULL AND {coluna} != ''"
        ).df()
        valores.update(df[coluna].tolist())
    return sorted(valores)


def _opcoes_filtradas(
    con: duckdb.DuckDBPyConnection, tabela: str, coluna: str, filtros_pai: dict[str, list[str]],
) -> list[str]:
    """Cascata de Organização (2026-08-29, a pedido do usuário — conferido
    no dado real: Gerência ⊃ Coordenação ⊃ Centro de Custo é hierarquia
    estrita em `fact_realizado`, 0 exceção). Devolve só os valores de
    `coluna` que aparecem junto de pelo menos 1 valor de cada filtro pai
    já escolhido acima na sidebar (`filtros_pai`, ex.:
    `{"gerencia_nome": ["GER MALHA (SP)"]}`) — estreita a lista de
    sugestões da caixa de baixo em vez de deixá-la solta com o universo
    inteiro. `filtros_pai` só com listas vazias (nada escolhido ainda)
    devolve `[]` — quem chama decide o fallback (universo completo)."""
    condicoes, params = [], []
    for col_pai, valores in filtros_pai.items():
        if valores:
            marcadores = ", ".join(["?"] * len(valores))
            condicoes.append(f"{col_pai} IN ({marcadores})")
            params.extend(valores)
    if not condicoes:
        return []
    where_extra = " AND " + " AND ".join(condicoes)
    df = con.execute(
        f"SELECT DISTINCT {coluna} FROM {tabela} "
        f"WHERE {coluna} IS NOT NULL AND {coluna} != ''{where_extra}",
        params,
    ).df()
    return sorted(df[coluna].tolist())


def _tabela_existe(con: duckdb.DuckDBPyConnection, nome: str) -> bool:
    (n,) = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [nome],
    ).fetchone()
    return n > 0


def _renderizar_filtro_capex_obras(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    """Projeto (`e_pep_projeto`) e Elemento PEP (`elemento_pep`) do CAPEX de
    Projetos e Obras (`fact_cji4_capex_obras`/`fact_cji3_capex_obras`) —
    adicionado em 2026-08-11 (a pedido do usuário: "preciso ter um filtro
    no side bar com o projeto... os projetos também têm elemento pep, e
    não está aparecendo nos filtros"). Vocabulário próprio, diferente do
    "PEP" que já existe em Organização (esse é o PEP extraído da Base Zero/
    OPEX, outro código, outra fonte — ver docstring do módulo). Só aparece
    na sidebar se pelo menos 1 das 2 tabelas de CAPEX Obras existir
    (arquivos opcionais, ver build_star_schema.py)."""
    tem_cji4 = _tabela_existe(con, "fact_cji4_capex_obras")
    tem_cji3 = _tabela_existe(con, "fact_cji3_capex_obras")
    if not tem_cji4 and not tem_cji3:
        return [], []

    tabelas = []
    if tem_cji4:
        tabelas.append("fact_cji4_capex_obras")
    if tem_cji3:
        tabelas.append("fact_cji3_capex_obras")
    projetos = _opcoes(con, [(t, "e_pep_projeto") for t in tabelas])
    elementos_pep = _opcoes(con, [(t, "elemento_pep") for t in tabelas])

    _grupo_filtro("🏗️ CAPEX Obras (Projeto/PEP)")
    projeto_sel = st.sidebar.multiselect(
        "Projeto", projetos, key="w_filtro_projeto_capex",
        help="Só CAPEX de Projetos e Obras (CJI4/CJI3) — não filtra as páginas de OPEX.",
    )
    elemento_pep_sel = st.sidebar.multiselect(
        "Elemento PEP", elementos_pep, key="w_filtro_elemento_pep_capex",
        help="Subdivisão do Projeto (ex.: \"DM/21973C-06-02\"). Só CAPEX de Projetos e Obras.",
    )
    return projeto_sel, elemento_pep_sel


def renderizar_filtros_sidebar(con: duckdb.DuckDBPyConnection) -> None:
    """Widgets ficam em chaves `w_*` de rascunho — só viram filtro de
    verdade (chaves `filtro_*` lidas por `clausula_where`/`clausula_periodo`)
    quando o usuário clica "Aplicar filtros" (pedido do usuário em
    2026-08-07, pra poder ajustar vários filtros de uma vez sem disparar
    consulta a cada clique). "Limpar filtros" reseta rascunho e filtro
    aplicado juntos e força um rerender (`st.rerun()`) — sem isso os
    widgets já desenhados neste run não voltariam a mostrar "Todos".

    Organizado em grupos hierárquicos, a pedido do usuário em 2026-08-10:

    1. Organização (quem) — Gerência → Coordenação → Centro de Custo → PEP.
       Ordem espelha a hierarquia real confirmada nos dados: Coordenação é
       extraída do nome do Centro de Custo, que por sua vez é o mesmo eixo
       que PEP (um cobre OPEX, o outro CAPEX — ver
       `_dividir_centro_custo_pep` em src/ingestion/loaders.py). PEP fica
       abaixo de Centro de Custo (pedido explícito do usuário), não ao lado.
    2. Projeto / Classificação (o quê) — Classificação (CAPEX/OPEX) → Pacote.
    3. CAPEX Obras (Projeto/PEP) — Projeto (`e_pep_projeto`) → Elemento PEP,
       adicionado em 2026-08-11, vocabulário próprio do CJI4/CJI3 (ver
       `_renderizar_filtro_capex_obras`), diferente do "PEP" do grupo 1.
    4. Tempo (quando) — Período (Ano/Trimestre/Mês), estático (fora de
       expander desde 2026-08-28, a pedido do usuário).
    """
    # Reforço do estilo do chip do multiselect: LETRA BRANCA no chip navy.
    # branding.py::inject_shell_css já injeta isso, mas 3 tentativas não
    # pegaram no deploy (2026-09-08) — injetar aqui de novo, no fim da árvore
    # da sidebar, garante que este `<style>` é o ÚLTIMO do documento e ganha
    # qualquer empate de `!important` por ordem de cascata. `-webkit-text-
    # fill-color` porque o BaseWeb/emotion fixa essa prop e ela sobrepõe
    # `color` no Chromium.
    st.sidebar.markdown(
        """
        <style>
        [data-baseweb="tag"], [data-baseweb="tag"] *,
        [data-baseweb="select"] [data-baseweb="tag"] span {
            color: #ffffff !important;
            fill: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            opacity: 1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.divider()
    st.sidebar.caption("Ajuste os filtros e clique em **Aplicar filtros** no fim.")

    # P9 (2026-10-18): Gerências que só têm Orçado (ex.: "DIRETO GG (Marcelo
    # Modolo)", "OFF GER. DE PLANEJ...") também entram — desde que o filtro
    # passou a casar por `gerencia_id` (ver `clausulas_recorte_sidebar`),
    # elas filtram o Orçado de verdade.
    gerencias = _opcoes(con, [("fact_realizado", "gerencia_nome"), ("dim_gerencia", "gerencia_nome")])
    coordenacoes_todas = _opcoes(con, [("fact_realizado", "coordenacao")])
    centros_custo_todos = _opcoes(con, [("fact_orcamento", "centro_custo_id"), ("fact_realizado", "centro_custo_id")])
    peps = _opcoes(con, [("fact_orcamento", "pep_id")])
    classificacoes = _opcoes(con, [("fact_orcamento", "classificacao_contabil")])
    pacotes = _opcoes(con, [("fact_orcamento", "pacote_id"), ("fact_realizado", "pacote_id")])

    _grupo_filtro("🏢 Organização", primeiro=True)
    gerencia_sel = st.sidebar.multiselect(
        "Gerência", gerencias, key="w_filtro_gerencia",
        help="Só Realizado, na nomenclatura da hierarquia SAP.",
    )

    # Cascata Gerência → Coordenação → Centro de Custo (2026-08-29, a
    # pedido do usuário — conferido no dado real: 0 exceção na hierarquia
    # Gerência ⊃ Coordenação ⊃ Centro de Custo). Cada caixa só estreita a
    # LISTA DE SUGESTÕES a partir do que já foi escolhido acima; nunca
    # remove algo que a pessoa já tinha selecionado (união com o valor
    # atual da própria caixa) — evita a caixa quebrar com "valor fora da
    # lista" se a Gerência mudar depois de já ter Coordenação/Centro de
    # Custo escolhido, e deixa a pessoa perceber e ajustar manualmente em
    # vez de perder a seleção sem aviso.
    if gerencia_sel:
        coordenacoes = sorted(set(
            _opcoes_filtradas(con, "fact_realizado", "coordenacao", {"gerencia_nome": gerencia_sel})
        ) | set(st.session_state.get("w_filtro_coordenacao", [])))
    else:
        coordenacoes = coordenacoes_todas
    coordenacao_sel = st.sidebar.multiselect(
        "Coordenação", coordenacoes, key="w_filtro_coordenacao",
        help="Só Realizado — extraído do nome do Centro de Custo. Base Zero não tem essa informação. Lista estreita conforme a Gerência escolhida acima.",
    )

    filtros_cc_pai = {}
    if gerencia_sel:
        filtros_cc_pai["gerencia_nome"] = gerencia_sel
    if coordenacao_sel:
        filtros_cc_pai["coordenacao"] = coordenacao_sel
    if filtros_cc_pai:
        # Só fact_realizado carrega gerencia_nome/coordenacao (fact_orcamento
        # não tem essas colunas nesse vocabulário — ver docstring do
        # módulo) — 1 código de Centro de Custo (CGE053, confirmado no
        # dado real) existe só em fact_orcamento e por isso nunca aparece
        # aqui quando a cascata está ativa; continua selecionável
        # normalmente sem nenhum filtro de Gerência/Coordenação escolhido.
        centros_custo = sorted(set(
            _opcoes_filtradas(con, "fact_realizado", "centro_custo_id", filtros_cc_pai)
        ) | set(st.session_state.get("w_filtro_centro_custo", [])))
    else:
        centros_custo = centros_custo_todos
    centro_custo_sel = st.sidebar.multiselect(
        "Centro de Custo", centros_custo, key="w_filtro_centro_custo",
        help="Lista estreita conforme Gerência/Coordenação escolhidas acima.",
    )
    pep_sel = st.sidebar.multiselect(
        "PEP", peps, key="w_filtro_pep",
        help=(
            "Só Orçamento — o campo próprio de PEP no Realizado (SAP) vem "
            "vazio no export atual. Extraído do campo combinado "
            "'Centro de Custo/PEP' da Base Zero: código com '/' é PEP "
            "(sempre CAPEX); sem '/' é Centro de Custo (sempre OPEX)."
        ),
    )

    _grupo_filtro("📦 Projeto / Classificação")
    classificacao_sel = st.sidebar.multiselect(
        "Classificação (CAPEX/OPEX)", classificacoes, key="w_filtro_classificacao",
        help="Só Orçamento — Realizado (SAP) não carrega Classificação Contábil por linha.",
    )
    pacote_sel = st.sidebar.multiselect("Pacote", pacotes, key="w_filtro_pacote")

    projeto_capex_sel, elemento_pep_capex_sel = _renderizar_filtro_capex_obras(con)

    _grupo_filtro("📅 Tempo")
    anos_sel, trimestres_sel, meses_sel = _renderizar_filtro_periodo(con)

    col_aplicar, col_limpar = st.sidebar.columns(2)
    aplicar = col_aplicar.button("Aplicar filtros", type="primary", use_container_width=True)
    col_limpar.button("Limpar filtros", use_container_width=True, on_click=_limpar_filtros)

    if aplicar:
        st.session_state["filtro_gerencia"] = gerencia_sel
        st.session_state["filtro_coordenacao"] = coordenacao_sel
        st.session_state["filtro_centro_custo"] = centro_custo_sel
        st.session_state["filtro_pep"] = pep_sel
        st.session_state["filtro_classificacao"] = classificacao_sel
        st.session_state["filtro_pacote"] = pacote_sel
        st.session_state["filtro_projeto_capex"] = projeto_capex_sel
        st.session_state["filtro_elemento_pep_capex"] = elemento_pep_capex_sel
        st.session_state["filtro_periodo_anos"] = anos_sel
        st.session_state["filtro_periodo_trimestres"] = trimestres_sel
        st.session_state["filtro_periodo_meses"] = meses_sel


def _limpar_filtros() -> None:
    """Callback do botão "Limpar filtros" (F3 da validação de 2026-10-18).

    Antes o botão fazia `st.session_state.pop(chave_widget)` + `st.rerun()`
    depois dos widgets já desenhados: o filtro aplicado sumia, mas o
    frontend reenviava o valor antigo de cada multiselect no rerun e as
    tags continuavam lá — no próximo "Aplicar" os filtros velhos voltavam
    somados ao novo. Num `on_click` o Streamlit roda o callback ANTES de
    redesenhar os widgets, e aí é permitido gravar a chave do widget: zerar
    para `[]` limpa as tags de verdade."""
    for chave_filtro, chave_widget in _CHAVES_WIDGET.items():
        st.session_state[chave_widget] = []
        st.session_state.pop(chave_filtro, None)


def _anos_disponiveis(con: duckdb.DuckDBPyConnection) -> list[int]:
    df = con.execute("SELECT DISTINCT ano FROM dim_tempo ORDER BY ano").df()
    return df["ano"].astype(int).tolist()


def _trimestres_disponiveis(con: duckdb.DuckDBPyConnection) -> list[int]:
    df = con.execute("SELECT DISTINCT trimestre FROM dim_tempo ORDER BY trimestre").df()
    return df["trimestre"].astype(int).tolist()


def _meses_disponiveis(con: duckdb.DuckDBPyConnection) -> list[int]:
    df = con.execute("SELECT DISTINCT mes FROM dim_tempo ORDER BY mes").df()
    return df["mes"].astype(int).tolist()


def _renderizar_filtro_periodo(con: duckdb.DuckDBPyConnection) -> tuple[list[int], list[int], list[int]]:
    """3 multiselects independentes — Ano, Trimestre, Mês —, cada um
    listando só os valores que existem de fato em dim_tempo. Não há mais
    cascata (escolher Ano não restringe as opções de Trimestre/Mês): dá pra
    combinar livremente, ex. Ano=[2026, 2027] ou Trimestre=[T1, T3]. A
    prioridade entre Mês e Trimestre quando os dois estão preenchidos é
    resolvida em `clausula_periodo`, não aqui.

    Devolve (anos, trimestres, meses) escolhidos no rascunho — quem decide
    se isso vira filtro de verdade é `renderizar_filtros_sidebar`, via o
    botão Aplicar."""
    anos = _anos_disponiveis(con)
    trimestres = _trimestres_disponiveis(con)
    meses = _meses_disponiveis(con)
    nome_para_mes = {nome: numero for numero, nome in _NOMES_MES.items()}

    # Estático (fora de expander) desde 2026-08-28, a pedido do usuário —
    # antes ficava dentro de um st.sidebar.expander recolhido por padrão.
    anos_opt = st.sidebar.multiselect("Ano", anos, key="w_periodo_anos")
    trimestres_opt = st.sidebar.multiselect("Trimestre", [f"T{t}" for t in trimestres], key="w_periodo_trimestres")
    meses_opt = st.sidebar.multiselect(
        "Mês", [_NOMES_MES[m] for m in meses], key="w_periodo_meses",
        help="Se Mês e Trimestre estiverem preenchidos ao mesmo tempo, Mês manda.",
    )

    return (
        [int(a) for a in anos_opt],
        [int(t[1:]) for t in trimestres_opt],
        [nome_para_mes[m] for m in meses_opt],
    )


def periodo_efetivo() -> tuple[list[int], list[int]]:
    """(anos, meses) já resolvidos da sessão — mesma regra de prioridade
    de `clausula_periodo` (Mês manda sobre Trimestre quando os dois têm
    seleção), mas devolvido como listas Python em vez de fragmento SQL.
    Usado por `clausula_periodo` (fact_orcamento/fact_realizado, via SQL)
    e por `filtrar_periodo_explicacoes` (explicacoes.csv, um DataFrame em
    memória, sem tabela SQL) — extraído em 2026-08-11 pra não duplicar a
    regra Mês x Trimestre nos dois lugares."""
    anos: list[int] = st.session_state.get("filtro_periodo_anos") or []
    trimestres: list[int] = st.session_state.get("filtro_periodo_trimestres") or []
    meses: list[int] = st.session_state.get("filtro_periodo_meses") or []

    if meses:
        meses_efetivos = meses
    elif trimestres:
        meses_efetivos = sorted({
            m for t in trimestres for m in range((t - 1) * 3 + 1, (t - 1) * 3 + 4)
        })
    else:
        meses_efetivos = []
    return anos, meses_efetivos


def clausula_periodo(coluna_ano: str = "ano", coluna_mes: str = "mes") -> tuple[str, list]:
    """Filtro de sessão do Período (3 multiselects independentes da
    sidebar: Ano, Trimestre, Mês).

    Ano vira `IN (...)` direto na coluna de ano. Trimestre e Mês disputam a
    coluna de mês: se houver Mês selecionado, ele manda (Trimestre é
    ignorado nesse caso — evita contradição tipo "T1 e Mar" com Mar já
    dentro de T1); sem Mês selecionado, usa a união dos meses de todos os
    Trimestres marcados. `fact_orcamento`, `fact_realizado` e
    `fact_realizado_documento` têm `ano`/`mes` com o mesmo nome — por isso
    os parâmetros default já cobrem os três casos de uso atuais.
    """
    anos, meses_efetivos = periodo_efetivo()

    condicoes: list[str] = []
    params: list[int] = []
    if anos:
        condicoes.append(f"{coluna_ano} IN ({', '.join(['?'] * len(anos))})")
        params += anos
    if meses_efetivos:
        condicoes.append(f"{coluna_mes} IN ({', '.join(['?'] * len(meses_efetivos))})")
        params += meses_efetivos

    if not condicoes:
        return "", []
    return " AND " + " AND ".join(condicoes), params


def filtrar_periodo_df(df, coluna_ano: str = "ano", coluna_mes: str = "mes"):
    """Mesmo filtro de `clausula_periodo`, aplicado em memória a um
    DataFrame com colunas `ano`/`mes` — usado pra `explicacoes.csv`
    (motor de causa), que não é uma tabela SQL. Adicionado em 2026-08-11
    (a pedido do usuário: "Painel Executivo não responde a filtro de
    Período") — sem isso, filtrar T1/T2/T3 mudava o Orçado/Realizado mas
    não a quebra por categoria de causa, e o waterfall parava de fechar
    (soma das categorias ≠ Delta Total do recorte filtrado)."""
    anos, meses_efetivos = periodo_efetivo()
    if anos:
        df = df[df[coluna_ano].isin(anos)]
    if meses_efetivos:
        df = df[df[coluna_mes].isin(meses_efetivos)]
    return df


def clausula_projeto_capex(
    coluna_projeto: str = "e_pep_projeto", coluna_elemento_pep: str = "elemento_pep",
) -> tuple[str, list]:
    """Filtro de Projeto/Elemento PEP do CAPEX de Projetos e Obras (sessão
    `filtro_projeto_capex`/`filtro_elemento_pep_capex`, ver
    `_renderizar_filtro_capex_obras`) — mesmo formato de retorno de
    `clausula_periodo`/`clausula_where` (fragmento pronto pra colar depois
    de "WHERE 1=1" + params). Só as páginas de CAPEX (`capex_dados.py`)
    usam isso — `fact_orcamento`/`fact_realizado` (OPEX) não têm essas
    colunas."""
    condicoes: list[str] = []
    params: list = []

    projetos = st.session_state.get("filtro_projeto_capex") or []
    if projetos:
        condicoes.append(f"{coluna_projeto} IN ({', '.join(['?'] * len(projetos))})")
        params += projetos

    elementos_pep = st.session_state.get("filtro_elemento_pep_capex") or []
    if elementos_pep:
        condicoes.append(f"{coluna_elemento_pep} IN ({', '.join(['?'] * len(elementos_pep))})")
        params += elementos_pep

    if not condicoes:
        return "", []
    return " AND " + " AND ".join(condicoes), params


def _contar_no_recorte(con: duckdb.DuckDBPyConnection, universo: str) -> int | None:
    """Quantas linhas de fato o recorte do usuário alcança. None = não deu
    pra checar (tabela ausente etc.) — quem chama não barra nesse caso."""
    if universo == "capex_obras":
        clausula, params = clausula_escopo_obras()
        tabelas = ("fact_cji4_capex_obras", "fact_cji3_capex_obras")
    else:
        clausula, params = clausula_escopo(universo)
        tabelas = ("fact_orcamento", "fact_realizado")
    existentes = {
        r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    tabelas = [t for t in tabelas if t in existentes]
    if not tabelas:
        return None
    total = 0
    for t in tabelas:
        (n,) = con.execute(f"SELECT COUNT(*) FROM {t} WHERE 1=1{clausula}", params).fetchone()
        total += n
    return total


def _barrar_recorte_sem_dado(con: duckdb.DuckDBPyConnection, universo: str, alvos: list[str]) -> None:
    """Caso Sandra (2026-10-04): usuário com universo liberado, mas cujo
    recorte não casa com nenhuma linha da base (código de Gerência/PEP
    antigo, ou tipo de escopo que o filtro de CAPEX Obras não reconhece —
    ex. 'gerencia' em vez de 'gerencia_obras'). Antes, toda consulta voltava
    vazia e a tela ficava em branco, sem aviso nenhum — parecia app
    quebrado. Agora explica e para a página."""
    try:
        n = _contar_no_recorte(con, universo)
    except Exception:
        return
    if n is None or n > 0:
        return
    st.warning(
        "🔒 Seu acesso a esta área está liberado, mas o recorte cadastrado "
        f"para o seu usuário ({', '.join(alvos)}) não encontrou nenhum dado "
        "na base atual. Peça ao administrador para revisar seus escopos em "
        "**Administração → Permissões e escopos**."
    )
    st.stop()


def guardar_e_faixa_universo(con: duckdb.DuckDBPyConnection, universo: str) -> None:
    """`require_universo` (barra quem não tem acesso) + faixa "🔒 Recorte
    do seu acesso: <Gerências>" quando o usuário não tem a GG inteira.
    Chamar no topo da página/painel, logo depois do `render_page_banner`.
    Admin / `ORCAMENTO_SKIP_LOGIN=1` passam sem faixa (veem tudo).

    Sustaining (`opex_/capex_sustaining`): traduz `gerencia_id` → nome via
    `dim_gerencia`. `capex_obras` (quando a Fase RBAC-A.2 chegar nele):
    `alvos` já são nomes de `gerencia_obras` / códigos de PEP — mostra
    como está."""
    from src.auth.permissions import require_universo

    require_universo(universo)
    _tem, tudo, alvos = escopo_universo(universo)
    if tudo or not alvos:
        return
    _barrar_recorte_sem_dado(con, universo, alvos)
    if universo == "capex_obras":
        nomes = list(alvos)
    else:
        nomes = con.execute(
            "SELECT gerencia_nome FROM dim_gerencia "
            f"WHERE gerencia_id IN ({', '.join(['?'] * len(alvos))}) ORDER BY gerencia_nome",
            list(alvos),
        ).df()["gerencia_nome"].tolist() or list(alvos)
    st.caption(
        "🔒 Recorte do seu acesso: " + ", ".join(nomes)
        + " — os números abaixo são só desse recorte, não o total da GG."
    )


def clausula_escopo(universo: str, coluna: str = "gerencia_id") -> tuple[str, list]:
    """Filtro sempre-ligado do RBAC de escopo por universo (docs/08,
    Fase RBAC-A.2). Mesmo formato de `clausula_periodo`/`clausula_where`
    (fragmento pronto pra colar depois de "WHERE 1=1" + params):

      - vê o universo inteiro   -> ("", [])
      - recorte por Gerência    -> (" AND gerencia_id IN (?, ?)", [...])
      - sem acesso ao universo  -> (" AND 1=0", [])

    O último caso é defensivo: a página deve barrar antes com
    `permissions.require_universo`, mas se não barrou, a consulta não
    vaza dado nenhum. `coluna` troca pra `gerencia_obras` / `e_pep_projeto`
    nas telas de CAPEX Obras. Admin / `ORCAMENTO_SKIP_LOGIN=1` sempre caem
    no primeiro caso (`escopo_universo` devolve `tudo=True`)."""
    tem_acesso, tudo, alvos = escopo_universo(universo)
    if tudo:
        return "", []
    if not tem_acesso or not alvos:
        return " AND 1=0", []
    marcadores = ", ".join("?" * len(alvos))
    return f" AND {coluna} IN ({marcadores})", list(alvos)


def clausula_escopo_obras(
    coluna_gerencia: str = "gerencia_obras", coluna_projeto: str = "e_pep_projeto",
) -> tuple[str, list]:
    """Escopo sempre-ligado do universo `capex_obras` (docs/08). Os alvos
    podem ser de dois tipos ao mesmo tempo — Gerência de Obras e/ou Projeto
    (`e_pep_projeto`, gravado pela tela de delegação com `tipo='elemento_pep'`)
    — combinados com OR:
      - vê o universo inteiro   -> ("", [])
      - recorte                 -> " AND (gerencia_obras IN (...) OR e_pep_projeto IN (...))"
      - sem acesso              -> (" AND 1=0", [])
    """
    from src.auth.permissions import escopo_alvos_por_tipo

    alvos = escopo_alvos_por_tipo("capex_obras")
    if "gg" in alvos:
        return "", []
    partes: list[str] = []
    params: list = []
    gers = alvos.get("gerencia_obras") or []
    if gers:
        partes.append(f"{coluna_gerencia} IN ({', '.join(['?'] * len(gers))})")
        params += gers
    projs = alvos.get("elemento_pep") or []
    if projs:
        partes.append(f"{coluna_projeto} IN ({', '.join(['?'] * len(projs))})")
        params += projs
    if not partes:
        return " AND 1=0", []
    return " AND (" + " OR ".join(partes) + ")", params


def clausula_escopo_centro_custo(
    con: duckdb.DuckDBPyConnection, universo: str = "opex_sustaining",
    coluna: str = "centro_custo_id",
) -> tuple[str, list]:
    """Como `clausula_escopo`, mas pra tabela SEM `gerencia_id` (ex.:
    `fact_realizado_documento`, Nível 6). Traduz os alvos de Gerência do
    escopo → a lista de `centro_custo_id` daquelas Gerências (via
    `fact_realizado`, onde CC ⊂ Gerência é hierarquia estrita — 0 exceção,
    ver docs/04) e filtra por `centro_custo_id`."""
    tem_acesso, tudo, alvos = escopo_universo(universo)
    if tudo:
        return "", []
    if not tem_acesso or not alvos:
        return " AND 1=0", []
    marcadores = ", ".join("?" * len(alvos))
    ccs = con.execute(
        "SELECT DISTINCT centro_custo_id FROM fact_realizado "
        f"WHERE centro_custo_id IS NOT NULL AND gerencia_id IN ({marcadores})",
        list(alvos),
    ).df()["centro_custo_id"].tolist()
    if not ccs:
        return " AND 1=0", []
    marc_cc = ", ".join("?" * len(ccs))
    return f" AND {coluna} IN ({marc_cc})", list(ccs)


def clausula_familia(familia: str | None, coluna: str = "familia_pacote") -> tuple[str, list]:
    """Filtro explícito de Família de Pacote — diferente de
    `clausula_where`/`clausula_periodo`, não lê da sessão: quem decide o
    valor é o chamador (ex.: Visão Manutenção fixa `familia="PM"` pra
    reaproveitar as árvores do Nível 4/5 recortadas em Manutenção)."""
    if not familia:
        return "", []
    return f" AND {coluna} = ?", [familia]


def combinar_clausulas(*pares: tuple[str, list]) -> tuple[str, list]:
    """Concatena N pares (fragmento_sql, params) de clausula_where/
    clausula_periodo/clausula_familia num só, na ordem recebida."""
    where = "".join(fragmento for fragmento, _ in pares)
    params: list = []
    for _, params_par in pares:
        params += params_par
    return where, params


def clausula_where(colunas_disponiveis: dict[str, str]) -> tuple[str, list]:
    """`colunas_disponiveis`: {chave_do_filtro: nome_da_coluna_nesta_tabela}
    — só as chaves que a tabela chamando isso realmente tem. Retorna um
    fragmento SQL pronto pra colar depois de "WHERE 1=1" (começa com " AND
    " ou é string vazia) + a lista de params na mesma ordem."""
    condicoes = []
    params: list = []
    for chave_filtro, coluna_tabela in colunas_disponiveis.items():
        chave_sessao = _CHAVES_SESSAO.get(chave_filtro)
        valores = st.session_state.get(chave_sessao) if chave_sessao else None
        if valores:
            marcadores = ", ".join("?" * len(valores))
            condicoes.append(f"{coluna_tabela} IN ({marcadores})")
            params += valores
    if not condicoes:
        return "", []
    return " AND " + " AND ".join(condicoes), params


def _in(coluna: str, valores: list) -> tuple[str, list]:
    return f" AND {coluna} IN ({', '.join(['?'] * len(valores))})", list(valores)


def recorte_sidebar_ativo() -> bool:
    """True quando há filtro de Organização/Classificação/Pacote aplicado
    (não conta Período nem os filtros de CAPEX Obras)."""
    return any(st.session_state.get(chave) for chave in _CHAVES_SESSAO.values())


def clausulas_recorte_sidebar(incluir_periodo: bool = True) -> tuple[tuple[str, list], tuple[str, list]]:
    """Todos os filtros da sidebar (Organização + Classificação + Pacote +
    Período), com a MESMA regra de negócio nos dois fatos — devolve
    `((where_orcado, params), (where_realizado, params))`, fragmentos
    prontos pra colar depois de "WHERE 1=1" (ou de outra condição).

    Criado em 2026-10-18 (validação de filtros, F1/F4/D1) pra Visão
    Executiva responder aos filtros sem cada tela reinventar o mapeamento.
    Regras, por filtro:

    - Gerência (nome, vocabulário do Realizado): resolve pra `gerencia_id`
      via `dim_gerencia`/`fact_realizado` e filtra `gerencia_id` nos DOIS
      fatos. No Orçado isso inclui o CAPEX da Base Zero, que já tem
      `gerencia_id` por região (SP -> GER MALHA (SP), VP -> GER IMPLANT DE
      OBRAS E MALHA VP — `_GERENCIA_ID_POR_REGIAO_BASE_ZERO`).
    - Coordenação: Realizado direto; no Orçado vira a lista de Centros de
      Custo daquela Coordenação (hierarquia estrita CC ⊂ Coordenação,
      0 exceção — docs/04). CAPEX (PEP, sem CC) fica de fora, correto.
    - Centro de Custo, Classificação, Pacote: coluna própria nos dois fatos
      (`fact_realizado.classificacao_contabil` existe e é sempre 'OPEX').
    - PEP: só existe no Orçado (sempre CAPEX). O Realizado carregado é só
      OPEX e não tem PEP — com PEP selecionado, Realizado = 0 (`1=0`), em
      vez de ignorar o filtro e devolver o Realizado inteiro.
    - Período: `clausula_periodo` nos dois (`incluir_periodo=False` deixa
      de fora — usado pela curva anual da Tendência, que sempre mostra o
      ano inteiro).

    Não inclui o escopo de RBAC (`clausula_escopo`) — quem chama combina.
    """
    orc: list[tuple[str, list]] = []
    real: list[tuple[str, list]] = []
    ss = st.session_state

    gerencias = ss.get("filtro_gerencia") or []
    if gerencias:
        marc = ", ".join(["?"] * len(gerencias))
        sub = (
            f" AND gerencia_id IN (SELECT gerencia_id FROM dim_gerencia WHERE gerencia_nome IN ({marc}) "
            f"UNION SELECT gerencia_id FROM fact_realizado WHERE gerencia_nome IN ({marc}))"
        )
        orc.append((sub, [*gerencias, *gerencias]))
        real.append((sub, [*gerencias, *gerencias]))

    coordenacoes = ss.get("filtro_coordenacao") or []
    if coordenacoes:
        marc = ", ".join(["?"] * len(coordenacoes))
        orc.append((
            f" AND centro_custo_id IN (SELECT DISTINCT centro_custo_id FROM fact_realizado "
            f"WHERE coordenacao IN ({marc}))",
            list(coordenacoes),
        ))
        real.append(_in("coordenacao", coordenacoes))

    for chave_sessao, coluna in (
        ("filtro_centro_custo", "centro_custo_id"),
        ("filtro_classificacao", "classificacao_contabil"),
        ("filtro_pacote", "pacote_id"),
    ):
        valores = ss.get(chave_sessao) or []
        if valores:
            orc.append(_in(coluna, valores))
            real.append(_in(coluna, valores))

    peps = ss.get("filtro_pep") or []
    if peps:
        orc.append(_in("pep_id", peps))
        real.append((" AND 1=0", []))

    if incluir_periodo:
        periodo = clausula_periodo()
        orc.append(periodo)
        real.append(periodo)
    return combinar_clausulas(*orc), combinar_clausulas(*real)


# ===== Fechamento contábil: "a realizar" e mês em aberto (P7 + B4, 2026-10-18)
#
# P7 (decisão do Julio): Delta, Aderência e causa comparam Orçado e
# Realizado só ATÉ o último mês fechado; o Orçado dos meses seguintes
# aparece à parte, como "a realizar". Totais de Orçamento (o que foi
# aprovado) e as curvas anuais continuam mostrando o recorte inteiro.
#
# B4 (docs/12, 2026-10-18): "último mês com Realizado ≠ 0" não basta — a
# Consulta de Contas pode ser carregada a qualquer dia, e o mês da carga
# vem com Realizado PARCIAL (ex.: carga em 15/09 traz Set pela metade).
# Entrar no Delta derrubava a Aderência e jogava o resto do mês no "Não
# Justificado". A referência é a DATA DA CARGA do arquivo (tabela
# `meta_carga`, gravada pelo build), NUNCA a data de hoje, e nada de campo
# manual — o painel só centraliza o que veio do SAP. Regra (Calendário
# Integrado de Gestão Financeira da GGFC, jul/26): o fechamento contábil
# do mês M-1 sai no 5º dia útil de M.
#   - mês M da carga: sempre aberto ("em andamento");
#   - M-1: fechado se a carga foi no 5º dia útil de M ou depois; antes
#     disso continua aberto ("aguardando fechamento contábil");
#   - corte = min(último mês com Realizado ≠ 0, M-1 ou M-2).
# O Realizado dos meses abertos aparece à parte, como "Realizado parcial",
# e NUNCA entra em Real Contabilizado/Delta/Aderência/rankings.

_NOMES_MES_FECH = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
                   7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}

# Chave de `cfg["caminhos"]` cuja data de carga define o mês em aberto: o
# `fact_realizado` sai da Consulta de Contas (build_star_schema.py), não do
# Base Analítico.
TIPO_CARGA_REALIZADO = "consulta_contas"

# N-ésimo dia útil de M em que o mês M-1 fecha. None/0 desliga a regra e
# volta a "mês anterior ao da carga = fechado".
# GAP: dia útil = segunda a sexta, SEM feriados (nacionais/MRS ignorados).
# Regra vista no calendário da GGFC de jul/26 — falta confirmar com a GGFC
# se vale todo mês (o calendário varia a cada ciclo).
DIA_UTIL_FECHAMENTO_CONTABIL: int | None = 5


def _mes_anterior(aaaamm: int) -> int:
    ano, mes = divmod(aaaamm, 100)
    return (ano - 1) * 100 + 12 if mes == 1 else aaaamm - 1


def _mes_seguinte(aaaamm: int) -> int:
    ano, mes = divmod(aaaamm, 100)
    return (ano + 1) * 100 + 1 if mes == 12 else aaaamm + 1


def _como_data(valor: date | datetime) -> date:
    return valor.date() if isinstance(valor, datetime) else valor


def dia_util_fechamento(ano: int, mes: int, n: int | None = None) -> date:
    """N-ésimo dia útil (seg–sex, sem feriados — ver GAP em
    `DIA_UTIL_FECHAMENTO_CONTABIL`) do mês. Ex.: Out/2026 -> 07/10/2026."""
    n = n or DIA_UTIL_FECHAMENTO_CONTABIL or 1
    dia = date(ano, mes, 1)
    contados = 0
    while True:
        if dia.weekday() < 5:
            contados += 1
            if contados == n:
                return dia
        dia += timedelta(days=1)


def meses_abertos_na_carga(data_carga: date | datetime) -> list[tuple[int, str]]:
    """[(aaaamm, situação)] dos meses ainda abertos na data da carga, em
    ordem: M-1 ("aguardando fechamento contábil", só se a carga foi antes
    do 5º dia útil de M) e M ("em andamento"). Pura."""
    d = _como_data(data_carga)
    mes_carga = d.year * 100 + d.month
    abertos = [(mes_carga, "em andamento")]
    if DIA_UTIL_FECHAMENTO_CONTABIL and d < dia_util_fechamento(d.year, d.month):
        abertos.insert(0, (_mes_anterior(mes_carga), "aguardando fechamento contábil"))
    return abertos


def corte_fechamento(
    ultimo_com_realizado: int | None, data_carga: date | datetime | None,
) -> int | None:
    """Último (ano*100+mês) que entra no Delta. Pura (testada em
    tests/test_corte_fechamento.py): min(último mês com Realizado ≠ 0,
    mês anterior ao primeiro mês ainda aberto na carga). None = sem
    Realizado nenhum (aí não há corte)."""
    if ultimo_com_realizado is None:
        return None
    if data_carga is None:
        # GAP: base sem `meta_carga` (warehouse antigo ou teste) — sem a
        # data da carga não dá pra saber se o último mês está completo;
        # volta à regra antiga (último mês com Realizado), e a nota avisa.
        return ultimo_com_realizado
    primeiro_aberto = meses_abertos_na_carga(data_carga)[0][0]
    return min(ultimo_com_realizado, _mes_anterior(primeiro_aberto))


def data_carga_realizado(con: duckdb.DuckDBPyConnection) -> datetime | None:
    """Quando o arquivo do Realizado foi carregado (`meta_carga`, gravada
    pelo build — ver `build_star_schema._linhas_meta_carga`). None = tabela
    ausente (warehouse anterior a 2026-10-18) ou tipo sem registro."""
    try:
        (valor,) = con.execute(
            "SELECT MAX(carregado_em) FROM meta_carga WHERE tipo = ?", [TIPO_CARGA_REALIZADO],
        ).fetchone()
    except Exception:
        return None
    return valor or None


def _ultimo_mes_com_realizado(con: duckdb.DuckDBPyConnection) -> int | None:
    """Último (ano*100+mês) com Realizado diferente de zero em
    `fact_realizado` — ex.: 202609. `fact_realizado` vem pré-populado com
    zeros nos meses futuros (ver tendencia.py), por isso o `<> 0`."""
    try:
        (valor,) = con.execute(
            "SELECT MAX(ano * 100 + mes) FROM fact_realizado WHERE valor_realizado <> 0"
        ).fetchone()
    except Exception:
        return None
    return int(valor) if valor else None


def ultimo_periodo_fechado(con: duckdb.DuckDBPyConnection) -> int | None:
    """Último mês fechado (entra no Delta) — `corte_fechamento` sobre o
    dado e a data da carga. Nome mantido: todas as telas já usam."""
    return corte_fechamento(_ultimo_mes_com_realizado(con), data_carga_realizado(con))


def mes_em_andamento(con: duckdb.DuckDBPyConnection) -> int | None:
    """Mês da carga do Realizado (sempre aberto). None sem `meta_carga`."""
    data = data_carga_realizado(con)
    if data is None:
        return None
    return meses_abertos_na_carga(data)[-1][0]


def meses_em_aberto(con: duckdb.DuckDBPyConnection) -> list[tuple[int, str]]:
    """Meses abertos na carga que ficam DEPOIS do corte (1 ou 2). Vazio
    sem `meta_carga` ou sem Realizado."""
    data = data_carga_realizado(con)
    corte = ultimo_periodo_fechado(con)
    if data is None or corte is None:
        return []
    return [(m, s) for m, s in meses_abertos_na_carga(data) if m > corte]


def rotulo_periodo(aaaamm: int | None) -> str:
    if not aaaamm:
        return ""
    return f"{_NOMES_MES_FECH[aaaamm % 100]}/{aaaamm // 100}"


def rotulo_meses_em_aberto(meses: list[tuple[int, str]]) -> str:
    """"Out/2026 em andamento" ou "Set/2026 aguardando fechamento contábil
    e Out/2026 em andamento"."""
    return " e ".join(f"{rotulo_periodo(m)} {s}" for m, s in meses)


def clausula_ate_fechamento(con: duckdb.DuckDBPyConnection) -> tuple[str, list]:
    corte = ultimo_periodo_fechado(con)
    if corte is None:
        return "", []
    return " AND (ano * 100 + mes) <= ?", [corte]


def clausula_apos_fechamento(con: duckdb.DuckDBPyConnection) -> tuple[str, list]:
    corte = ultimo_periodo_fechado(con)
    if corte is None:
        return " AND 1=0", []
    return " AND (ano * 100 + mes) > ?", [corte]


def orcado_a_realizar(con: duckdb.DuckDBPyConnection, filtro_orcado_sem_corte: tuple[str, list]) -> float:
    """Orçado do recorte nos meses DEPOIS do último fechado — a parte que
    ainda não pode ser comparada com Realizado (desde B4 inclui o(s) mês(es)
    em aberto, cujo Realizado é parcial)."""
    frag, params = combinar_clausulas(filtro_orcado_sem_corte, clausula_apos_fechamento(con))
    (valor,) = con.execute(f"SELECT SUM(valor_orcado) FROM fact_orcamento WHERE 1=1{frag}", params).fetchone()
    return float(valor or 0.0)


def valores_em_andamento(
    con: duckdb.DuckDBPyConnection,
    filtro_orc_sem_corte: tuple[str, list],
    filtro_real_sem_corte: tuple[str, list],
) -> dict | None:
    """Orçado e Realizado PARCIAL do(s) mês(es) em aberto no recorte —
    `{"meses": [(aaaamm, situação)], "mes": mês da carga, "orcado",
    "realizado"}`. Só informativo: nunca entra no Delta. None sem mês em
    aberto ou com os dois lados zerados. Carga no dia 1–2 (Realizado 0,
    Orçado > 0) aparece — decisão do dono: o leitor precisa ver que o mês
    existe e ainda não tem lançamento."""
    meses = meses_em_aberto(con)
    if not meses:
        return None
    lista = [m for m, _ in meses]
    marc = ", ".join(["?"] * len(lista))
    frag_o, par_o = filtro_orc_sem_corte
    frag_r, par_r = filtro_real_sem_corte
    (orcado,) = con.execute(
        f"SELECT SUM(valor_orcado) FROM fact_orcamento WHERE (ano * 100 + mes) IN ({marc}){frag_o}",
        [*lista, *par_o],
    ).fetchone()
    (realizado,) = con.execute(
        f"SELECT SUM(valor_realizado) FROM fact_realizado WHERE (ano * 100 + mes) IN ({marc}){frag_r}",
        [*lista, *par_r],
    ).fetchone()
    orcado, realizado = float(orcado or 0.0), float(realizado or 0.0)
    if not orcado and not realizado:
        return None
    return {"meses": meses, "mes": lista[-1], "orcado": orcado, "realizado": realizado}


def realizado_apos_carga(con: duckdb.DuckDBPyConnection, filtro_real_sem_corte: tuple[str, list]) -> float:
    """Realizado do recorte com competência DEPOIS do mês da carga — não
    deveria existir (R7 da validação com o Copilot da MRS). Fica fora do
    Delta e do "parcial"; sem este número ele sumiria calado (Regra de
    Ouro). 0 sem `meta_carga`."""
    mes_carga = mes_em_andamento(con)
    if mes_carga is None:
        return 0.0
    frag, params = filtro_real_sem_corte
    (valor,) = con.execute(
        f"SELECT SUM(valor_realizado) FROM fact_realizado WHERE (ano * 100 + mes) > ?{frag}",
        [mes_carga, *params],
    ).fetchone()
    return float(valor or 0.0)


def nota_fechamento(
    con: duckdb.DuckDBPyConnection,
    a_realizar: float | None = None,
    em_andamento: dict | None = None,
    realizado_futuro: float = 0.0,
) -> None:
    """Legenda padrão embaixo dos cards com Delta: até onde vai o Delta,
    data da carga, mês(es) em aberto com o Realizado parcial, o "a
    realizar" e o alerta de Realizado com competência futura."""
    from src.dashboard.formatacao import escapar_cifrao_md, fmt_reais_abrev

    corte = ultimo_periodo_fechado(con)
    if corte is None:
        # Base sem nenhum Realizado ≠ 0 (ex.: carga no 1º dia do ano, ou
        # Consulta de Contas sem Realizado): não há corte, e o Delta compara
        # o Orçado com Realizado zero. Antes a nota simplesmente sumia (2ª
        # revisão do Astra, 2026-10-18) — agora avisa, sem mexer no cálculo.
        st.warning(
            "Não há Realizado contabilizado nesta base: o Delta e a Aderência abaixo "
            "comparam o Orçado com Realizado zero. Confira a carga da Consulta de Contas "
            "(Gestão › Dados e Qualidade)."
        )
        return

    data_carga = data_carga_realizado(con)
    texto = f"Delta e Aderência acumulados até {rotulo_periodo(corte)}"
    if data_carga is None:
        texto += (
            " (data da carga do Realizado não registrada nesta base — corte pelo último mês "
            "com Realizado)."
        )
    else:
        texto += f" (Realizado carregado em {_como_data(data_carga):%d/%m/%Y})."
    if em_andamento:
        texto += (
            f" {rotulo_meses_em_aberto(em_andamento['meses'])} — fora do Delta: Realizado "
            f"parcial {fmt_reais_abrev(em_andamento['realizado'])} x Orçado "
            f"{fmt_reais_abrev(em_andamento['orcado'])}."
        )
    if a_realizar:
        texto += (
            f" Orçado de {rotulo_periodo(_mes_seguinte(corte))} em diante no recorte: "
            f"{fmt_reais_abrev(a_realizar)} — a realizar."
        )
    if data_carga is not None and DIA_UTIL_FECHAMENTO_CONTABIL:
        texto += (
            f" Fechamento contábil: o mês fecha no {DIA_UTIL_FECHAMENTO_CONTABIL}º dia útil do "
            "mês seguinte (calendário da GGFC) — carga antes disso deixa o mês anterior em aberto."
        )
    st.caption(escapar_cifrao_md(texto))
    if realizado_futuro:
        st.warning(escapar_cifrao_md(
            f"Atenção: {fmt_reais_abrev(realizado_futuro)} de Realizado com competência após "
            f"{rotulo_periodo(mes_em_andamento(con))} — lançamento futuro, verificar a base."
        ))


def nota_fechamento_recorte(
    con: duckdb.DuckDBPyConnection,
    filtro_orc_sem_corte: tuple[str, list],
    filtro_real_sem_corte: tuple[str, list],
) -> None:
    """`nota_fechamento` completa a partir do par (Orçado, Realizado) SEM
    corte de um recorte — usada pelos cards de Contas, CC e Manutenção."""
    nota_fechamento(
        con,
        a_realizar=orcado_a_realizar(con, filtro_orc_sem_corte),
        em_andamento=valores_em_andamento(con, filtro_orc_sem_corte, filtro_real_sem_corte),
        realizado_futuro=realizado_apos_carga(con, filtro_real_sem_corte),
    )


def clausulas_recorte(
    universo: str = "opex_sustaining",
    incluir_periodo: bool = True,
    con: duckdb.DuckDBPyConnection | None = None,
    ate_fechamento: bool = False,
) -> tuple[tuple[str, list], tuple[str, list]]:
    """`clausulas_recorte_sidebar` + escopo de RBAC do `universo` (+ corte
    no último mês fechado, quando `ate_fechamento=True` e `con` é dado) —
    o par (Orçado, Realizado) que toda tela com Orçado x Realizado deve
    usar. Sem filtro, fora do RBAC e sem corte, os fragmentos são vazios."""
    (where_o, params_o), (where_r, params_r) = clausulas_recorte_sidebar(incluir_periodo=incluir_periodo)
    where_e, params_e = clausula_escopo(universo)
    orc = [(where_o, params_o), (where_e, params_e)]
    real = [(where_r, params_r), (where_e, list(params_e))]
    if ate_fechamento and con is not None:
        corte = clausula_ate_fechamento(con)
        orc.append(corte)
        real.append(corte)
    return combinar_clausulas(*orc), combinar_clausulas(*real)


def clausulas_gerencias_opex(con: duckdb.DuckDBPyConnection) -> tuple[tuple[str, list], tuple[str, list]]:
    """Recorte das visões "por Gerência" (Gerências Locais do Resumo, "Ver
    por Gerência" e mapa de calor de Desvios e Causas): sidebar + escopo,
    até o último mês fechado, Orçado só OPEX. Antes (até 2026-10-18) o
    Orçado por Gerência somava o CAPEX da Base Zero (SP -> GER MALHA,
    VP -> GER IMPLANT ... VP) contra um Realizado só OPEX."""
    (where_o, params_o), real = clausulas_recorte("opex_sustaining", con=con, ate_fechamento=True)
    return (" AND classificacao_contabil = 'OPEX'" + where_o, params_o), real


_FILTROS_INCOMPATIVEIS_COM_CAUSA = (
    "filtro_gerencia", "filtro_coordenacao", "filtro_centro_custo", "filtro_pep",
)


def causa_disponivel_no_recorte() -> bool:
    """O waterfall de causa (e % Explicado / Não Justificado) só fecha em
    recortes que a causa consegue acompanhar: Período (explicacoes.csv tem
    ano/mês), Pacote (a causa é rastreada por Pacote inteiro) e
    Classificação que inclua OPEX (o waterfall é OPEX x OPEX). Gerência/
    Coordenação/Centro de Custo/PEP cortam DENTRO do Pacote — atribuir a
    causa a esse sub-recorte exigiria inventar rateio (Regra de Ouro,
    docs/02 item 22)."""
    if any(st.session_state.get(k) for k in _FILTROS_INCOMPATIVEIS_COM_CAUSA):
        return False
    classificacao = st.session_state.get("filtro_classificacao") or []
    return not classificacao or "OPEX" in classificacao


def pacotes_filtro() -> list[str] | None:
    return list(st.session_state.get("filtro_pacote") or []) or None


AVISO_CAUSA_INDISPONIVEL = (
    "🔎 Decomposição por causa indisponível neste recorte. A causa "
    "(Físico, Efeito Preço, Carry Over…) é rastreada por Pacote "
    "inteiro — filtros de Gerência, Coordenação, Centro de Custo, "
    "PEP ou Classificação só CAPEX cortam dentro do Pacote, e "
    "atribuir a causa a esse pedaço exigiria inventar rateio. "
    "Orçado, Realizado, Delta e Aderência já estão filtrados. "
    "Para ver o waterfall, deixe só Período, Pacote ou Classificação OPEX."
)


def algum_filtro_ativo() -> bool:
    filtros_simples = any(
        st.session_state.get(chave) for chave in _CHAVES_SESSAO.values()
    )
    filtro_capex = bool(
        st.session_state.get("filtro_projeto_capex")
        or st.session_state.get("filtro_elemento_pep_capex")
    )
    filtro_periodo = bool(
        st.session_state.get("filtro_periodo_anos")
        or st.session_state.get("filtro_periodo_trimestres")
        or st.session_state.get("filtro_periodo_meses")
    )
    return filtros_simples or filtro_capex or filtro_periodo


# chave de sessão -> rótulo de exibição, na mesma ordem visual da sidebar
# (Organização -> Projeto/Classificação -> CAPEX Obras) — usado só pelo
# badge abaixo, achado #4 da auditoria de UX de 2026-08-13.
_ROTULOS_FILTRO_SIMPLES = {
    "filtro_gerencia": "Gerência",
    "filtro_coordenacao": "Coordenação",
    "filtro_centro_custo": "Centro de Custo",
    "filtro_pep": "PEP",
    "filtro_classificacao": "Classificação",
    "filtro_pacote": "Pacote",
    "filtro_projeto_capex": "Projeto (CAPEX Obras)",
    "filtro_elemento_pep_capex": "Elemento PEP (CAPEX Obras)",
}


# P3 (2026-10-18): quais filtros da sidebar cada universo de página respeita.
# A faixa "Filtros ativos" separa o que vale na página aberta do que não se
# aplica — antes ela listava tudo, inclusive filtros que a página ignorava.
_CHAVE_PERIODO = "__periodo__"
_FILTROS_MANUTENCAO = frozenset(_CHAVES_SESSAO.values()) | {_CHAVE_PERIODO}
FILTROS_APLICAVEIS: dict[str, frozenset[str]] = {
    "manutencao": _FILTROS_MANUTENCAO,
    "obras": frozenset({"filtro_projeto_capex", "filtro_elemento_pep_capex", _CHAVE_PERIODO}),
    "especialista": frozenset(),  # filtros próprios no topo da página
}


def _partes_filtros_ativos() -> list[tuple[str, str]]:
    """[(chave, "Rótulo: valores")] dos filtros aplicados agora (chaves
    `filtro_*`, não o rascunho `w_*`), na ordem visual da sidebar."""
    partes = [
        (chave, f"{rotulo}: {', '.join(str(v) for v in st.session_state[chave])}")
        for chave, rotulo in _ROTULOS_FILTRO_SIMPLES.items()
        if st.session_state.get(chave)
    ]
    anos = st.session_state.get("filtro_periodo_anos") or []
    trimestres = st.session_state.get("filtro_periodo_trimestres") or []
    meses = st.session_state.get("filtro_periodo_meses") or []
    periodo = []
    if meses:
        periodo.append(f"Mês: {', '.join(_NOMES_MES[m] for m in meses)}")
    elif trimestres:
        periodo.append(f"Trimestre: {', '.join(f'T{t}' for t in trimestres)}")
    if anos:
        periodo.append(f"Ano: {', '.join(str(a) for a in anos)}")
    if periodo:
        partes.append((_CHAVE_PERIODO, " · ".join(periodo)))
    return partes


def resumo_filtros_ativos(universo: str | None = None) -> str | None:
    """"Gerência: Malha SP · Período: Jan–Jun" com os filtros de fato
    aplicados agora — None quando nenhum filtro está ativo. Com `universo`,
    só os filtros que valem naquele universo (ver `FILTROS_APLICAVEIS`)."""
    aplicaveis = FILTROS_APLICAVEIS.get(universo) if universo else None
    partes = [
        texto for chave, texto in _partes_filtros_ativos()
        if aplicaveis is None or chave in aplicaveis
    ]
    return " · ".join(partes) if partes else None


def renderizar_badge_filtros_ativos(universo: str | None = None) -> None:
    """1 linha no topo de cada página com o recorte de filtro atual —
    chamado de `app.py`. Com `universo` ("manutencao", "obras",
    "especialista"), mostra à parte, em cinza, os filtros ativos que NÃO se
    aplicam à página aberta (P3, 2026-10-18)."""
    partes = _partes_filtros_ativos()
    if not partes:
        return
    aplicaveis = FILTROS_APLICAVEIS.get(universo) if universo else None
    validos = [t for c, t in partes if aplicaveis is None or c in aplicaveis]
    fora = [t for c, t in partes if aplicaveis is not None and c not in aplicaveis]
    html = []
    if validos:
        # Chip discreto (6.4.0) — classe `.f360-badge-filtros` em
        # branding.inject_shell_css.
        html.append(
            f'<div class="f360-badge-filtros">🔎 Filtros ativos &nbsp;·&nbsp; {_html_escape(" · ".join(validos))}</div>'
        )
    if fora:
        html.append(
            '<div class="f360-badge-filtros" style="opacity:0.6;">'
            f'⊘ Não se aplica nesta página &nbsp;·&nbsp; {_html_escape(" · ".join(fora))}</div>'
        )
    st.markdown("".join(html), unsafe_allow_html=True)


def _html_escape(texto: str) -> str:
    import html as _html

    return _html.escape(texto, quote=False)
