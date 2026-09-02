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
    st.sidebar.divider()
    st.sidebar.caption("Ajuste os filtros e clique em **Aplicar filtros** no fim.")

    gerencias = _opcoes(con, [("fact_realizado", "gerencia_nome")])
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
    limpar = col_limpar.button("Limpar filtros", use_container_width=True)

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

    if limpar:
        for chave_filtro, chave_widget in _CHAVES_WIDGET.items():
            st.session_state.pop(chave_widget, None)
            st.session_state.pop(chave_filtro, None)
        st.rerun()


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


def resumo_filtros_ativos() -> str | None:
    """"Gerência: Malha SP · Período: Jan–Jun" com os filtros de fato
    aplicados agora (chaves `filtro_*`, não o rascunho `w_*`) — None
    quando nenhum filtro está ativo. `algum_filtro_ativo()` já existia
    (booleano puro) mas não alimentava nada visível na tela — o painel
    tem 4 grupos de filtro que só valem depois de "Aplicar filtros", sem
    esse indicador fora da sidebar (que pode estar colapsada) não tinha
    como saber, voltando numa aba depois, se o número era um recorte ou
    o total."""
    partes = [
        f"{rotulo}: {', '.join(str(v) for v in st.session_state[chave])}"
        for chave, rotulo in _ROTULOS_FILTRO_SIMPLES.items()
        if st.session_state.get(chave)
    ]

    anos = st.session_state.get("filtro_periodo_anos") or []
    trimestres = st.session_state.get("filtro_periodo_trimestres") or []
    meses = st.session_state.get("filtro_periodo_meses") or []
    if meses:
        partes.append(f"Mês: {', '.join(_NOMES_MES[m] for m in meses)}")
    elif trimestres:
        partes.append(f"Trimestre: {', '.join(f'T{t}' for t in trimestres)}")
    if anos:
        partes.append(f"Ano: {', '.join(str(a) for a in anos)}")

    return " · ".join(partes) if partes else None


def renderizar_badge_filtros_ativos() -> None:
    """1 linha no topo de cada página com o recorte de filtro atual —
    chamado de `app.py`, logo depois da checagem de base pronta, pra
    valer em toda página navegável de uma vez (ver docstring de
    `resumo_filtros_ativos`)."""
    resumo = resumo_filtros_ativos()
    if resumo:
        # Chip discreto (6.4.0) no lugar do st.info full-width, que
        # gritava em toda página — classe `.f360-badge-filtros` em
        # branding.inject_shell_css.
        st.markdown(
            f'<div class="f360-badge-filtros">🔎 Filtros ativos &nbsp;·&nbsp; {resumo}</div>',
            unsafe_allow_html=True,
        )
