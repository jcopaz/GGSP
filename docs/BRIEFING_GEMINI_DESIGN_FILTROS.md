# Briefing — Fin360 (Painel Orçamento GGSP) · Problema de design nos filtros da sidebar

> **Para quem lê:** este documento é um pacote de contexto para pedir ajuda de
> design a outra IA (Gemini). O problema central está na **Seção 6**. As
> Seções 1–5 dão o contexto de arquitetura e o código relevante. As Seções 7–9
> trazem o histórico de tentativas, o que já foi feito e as perguntas abertas.

---

## 0. TL;DR do problema

O Fin360 é um dashboard **Streamlit** (Python) com uma sidebar de filtros feita
de `st.multiselect`. A engine de UI do Streamlit é o **BaseWeb** (do Uber). A
sidebar hoje é **clara** (cinza-azulado), mas o `primaryColor` do tema é
**navy escuro (`#1e3a5f`)** — e o BaseWeb usa `primaryColor` para pintar as
*tags* (chips) do multiselect. Resultado: **chips navy sólidos e pesados sobre
um fundo claro e leve** — "as cores não conversam". Além disso, os ícones
internos do BaseWeb (o "×" de cada chip, a seta de abrir, o "limpar tudo")
aparecem com um **contorno/retângulo quadrado feio**.

Já foram **6+ rodadas** tentando resolver isso via CSS por cima do BaseWeb (ver
Seção 7). A rodada atual (v6.4.0, Seção 8) mudou a estratégia: chip em **navy
translúcido** (não sólido) e **remoção da regra de CSS que vazava** nos ícones.
Queremos uma opinião de design independente sobre se essa é a direção certa e
como deixar a sidebar de filtros **limpa, consistente e à prova de tela**.

**Restrições rígidas (não mexer):** paleta de cores dos gráficos
(`src/dashboard/paleta.py`), tipos de gráfico já construídos, e a logomarca
animada (sidebar + tela de login).

---

## 1. Visão geral do produto e da stack

**Fin360** ("Painel Orçamento GGSP" / "Painel Executivo de Explicação de Delta —
DINFRA / MRS") é um painel financeiro interno da MRS (ferrovia). Ele não mostra
só "Orçado x Realizado": **explica o desvio (Delta)** por categoria de causa
(taxonomia do PMO: Físico, Efeito Preço, Não Previsto, Carry Over, etc.).
Público: um Gerente Geral que precisa responder "qual o desvio, onde está, por
quê" em menos de 2 minutos.

| Camada | Tecnologia |
|---|---|
| ETL | Python + `pandas` (lê planilhas SAP/Base Zero) |
| Armazenamento analítico | **DuckDB** (arquivo local `data/warehouse/painel.duckdb`, star schema, sem servidor) |
| Apresentação | **Streamlit** 1.57 (`st.navigation` multipágina) |
| Gráficos | **Plotly** (`st.plotly_chart`, `plotly.graph_objects`) |
| Auth | própria (bcrypt) contra Postgres/Neon; sessão via `st.session_state` |
| Deploy | **Streamlit Community Cloud** (disco efêmero; backup dos brutos no Neon) |

Não há frontend JS próprio: **todo o "design" é CSS injetado via
`st.markdown("<style>…</style>", unsafe_allow_html=True)`**, e a estrutura de
DOM é a que o Streamlit/BaseWeb gera. Não dá para trocar de componente de
multiselect — é o `st.multiselect` nativo ou nada.

---

## 2. Árvore de diretórios e papel de cada camada

```
Orçamento/
├── .streamlit/
│   ├── config.toml            # TEMA do Streamlit (primaryColor, cores base) — Seção 4
│   └── secrets.toml            # credenciais (fora deste briefing)
├── data/
│   ├── raw/                    # planilhas SAP / Base Zero (entrada do ETL)
│   └── warehouse/painel.duckdb # star schema pronto (saída do ETL)
├── src/
│   ├── versao.py               # APP_VERSION = "6.4.0"
│   ├── config.py               # carrega settings.yaml (caminhos, categorias de causa)
│   ├── branding.py             # ★ CASCA VISUAL: inject_shell_css() + render_page_banner()  — Seção 5
│   ├── auth/
│   │   ├── login.py            # ★ tela de login TEM CSS PRÓPRIO (_inject_login_css) — Seção 5
│   │   ├── session.py          # init_session / is_logged_in / get_nome / get_papel
│   │   └── permissions.py      # RBAC por página
│   ├── ingestion/              # loaders de planilha → DataFrame
│   ├── model/build_star_schema.py  # monta o DuckDB
│   ├── engine/                 # delta_calculator, explanation_engine, semaforo, simulador
│   └── dashboard/
│       ├── app.py              # ★ ENTRYPOINT: gate de login, monta sidebar (logo→nav→filtros→rodapé), st.navigation — Seção 5
│       ├── filtros.py          # ★ renderizar_filtros_sidebar(): TODOS os st.multiselect da sidebar — Seção 5
│       ├── layout.py           # ★ NOVO (6.4.0): bloco_resumo_visual(), legenda_semaforo(), nota_forecast() — Seção 5
│       ├── paleta.py           # 🔒 NÃO MEXER — cores dos GRÁFICOS (sistema visual separado)
│       ├── tema_plotly.py      # 🔒 template Plotly (fonte, grid) — não é o problema
│       ├── grafico_interativo.py  # helpers Plotly (alternância barra/linha)
│       ├── formatacao.py       # fmt_reais_abrev, fmt_pct, fmt_semaforo_chip (pt-BR)
│       ├── arvore_html.py      # árvore colapsável <details> em HTML/CSS puro (Nível 4/5)
│       ├── mapa_calor_gerencia_pacote.py  # heatmap HTML/CSS puro
│       ├── resumo_executivo.py # página "Resumo Executivo" (OPEX)
│       ├── nivel1_diretoria.py … nivel6_sap.py   # páginas do "Painel Executivo" (OPEX)
│       ├── visao_classificacao.py, visao_manutencao.py, projecao_opex.py
│       ├── capex_*.py          # páginas do universo "Plano de Obras" (CAPEX)
│       ├── pce_especialista.py # página "CAPEX Obras — Especialista"
│       └── administracao.py    # tela de admin (usuários/permissões/auditoria)
├── docs/                       # especificação, plano de build, lições aprendidas
└── CHANGELOG.md                # SemVer, bump a cada commit — Seção 7
```

**Fluxo de uma requisição (do ponto de vista da UI):**

```
streamlit run src/dashboard/app.py
  → init_session(); se não logado → render_login() (CSS PRÓPRIO) + st.stop()
  → inject_shell_css()                     # injeta o <style> global (Seção 5)
  → _renderizar_usuario_logado()           # st.logo(gif) + "👤 nome · papel" + botão Sair
  → _preparar_modo_simulacao()             # checkbox "Simular causas" na sidebar
  → _preparar_filtros_globais()            # → renderizar_filtros_sidebar(con)  ★ OS FILTROS
  → st.navigation({secão: [st.Page,...]})  # menu de páginas na sidebar
  → pg.run()                               # roda a página escolhida
  → _renderizar_rodape_sidebar()           # "v6.4.0 · Desenvolvido por Julio Paz"
```

---

## 3. Contratos de interface (o que uma camada expõe para a outra)

### 3.1 Estado dos filtros (`st.session_state`)

Cada `st.multiselect` da sidebar escreve num **rascunho** `w_*`. Só quando o
usuário clica **"Aplicar filtros"** o rascunho é copiado para as chaves
"aplicadas" `filtro_*`, que as páginas leem para montar o `WHERE` do SQL.
"Limpar filtros" apaga rascunho + aplicado e faz `st.rerun()`.

| Filtro (label visível) | key do widget (rascunho) | key aplicada | Coluna no DuckDB |
|---|---|---|---|
| Gerência | `w_filtro_gerencia` | `filtro_gerencia` | `fact_realizado.gerencia_nome` |
| Coordenação | `w_filtro_coordenacao` | `filtro_coordenacao` | `fact_realizado.coordenacao` |
| Centro de Custo | `w_filtro_centro_custo` | `filtro_centro_custo` | `fact_*.centro_custo_id` |
| PEP | `w_filtro_pep` | `filtro_pep` | `fact_orcamento.pep_id` |
| Classificação (CAPEX/OPEX) | `w_filtro_classificacao` | `filtro_classificacao` | `fact_orcamento.classificacao_contabil` |
| Pacote | `w_filtro_pacote` | `filtro_pacote` | `fact_*.pacote_id` |
| Projeto / Elemento PEP (CAPEX Obras) | `w_filtro_projeto_capex` / `w_filtro_elemento_pep_capex` | idem sem `w_` | tabelas CJI4/CJI3 |
| Ano / Trimestre / Mês | `w_periodo_anos` etc. | `filtro_periodo_anos` etc. | `dim_tempo` / `fact_*.ano,mes` |

Os filtros são agrupados em **3 grupos visuais** (+ 1 condicional):
`🏢 Organização` · `📦 Projeto / Classificação` · `🏗️ CAPEX Obras (Projeto/PEP)`
(só aparece se houver CJI3/CJI4 carregado) · `📅 Tempo`.

### 3.2 Sistema de tokens de CSS (definido em `inject_shell_css`)

```css
--f360-sidebar-bg: #eef1f6;        /* fundo da sidebar (claro) */
--f360-sidebar-bg-2: #f8f9fc;
--f360-sidebar-ink: #16283f;       /* texto na sidebar */
--f360-sidebar-ink-muted: #5b6b85;
--f360-sidebar-line: #d8dfea;      /* bordas / hairlines */
--f360-accent: #1e3a5f;            /* = primaryColor do tema (navy) */
--f360-accent-soft: rgba(30,58,95,.10);        /* NOVO 6.4.0 — fundo do chip */
--f360-accent-soft-hover: rgba(30,58,95,.17);
--f360-banner-from / --to / --title / --sub    /* banner de cabeçalho de página */
--f360-content-max: 1500px;        /* NOVO 6.4.0 — max-width do conteúdo */
```

### 3.3 Tema do Streamlit (`.streamlit/config.toml`) — ver Seção 4

`primaryColor = "#1e3a5f"` é o que o BaseWeb usa para colorir **a tag do
multiselect** e o botão `type="primary"`. Mudá-lo afeta o app inteiro.

### 3.4 Seletores de DOM relevantes (Streamlit 1.57 + BaseWeb)

| O que é | Seletor CSS |
|---|---|
| A sidebar inteira | `[data-testid="stSidebar"]` |
| Header da sidebar (onde vai o `st.logo`) | `[data-testid="stSidebarHeader"]` |
| Label de um widget | `[data-testid="stWidgetLabel"]` |
| Caixa do (multi)select | `[data-baseweb="select"] > div` |
| **Chip / tag selecionada** | `[data-baseweb="tag"]` (texto em `span`, "×" em `svg` dentro de um `[role="button"]`) |
| Botão Streamlit real | `.stButton button`, `[data-testid="stFormSubmitButton"] button` |
| Ícone "?" de `help=` | `[data-testid="stTooltipIcon"]` (hoje escondido na sidebar) |
| Container principal | `[data-testid="stMainBlockContainer"]` |
| Linha de colunas | `[data-testid="stHorizontalBlock"]` / coluna: `[data-testid="stColumn"]` |
| Classe de `st.container(key="x")` | `.st-key-x` |

O menu de opções do multiselect (o dropdown que abre) é renderizado num
**portal fora do `stSidebar`**, então regras com escopo `[data-testid="stSidebar"] …`
não o alcançam.

---

## 4. `.streamlit/config.toml` (tema do Streamlit)

```toml
# .streamlit/config.toml
[server]
enableStaticServing = true      # serve o vídeo/gif da logo

[theme]
# primaryColor é usado pelo BaseWeb para colorir a TAG do multiselect,
# o botão type="primary", ícones de foco. Mudar aqui muda o app inteiro.
# Já foi dourado (#c9932f) e virou navy em 2026-08-29 justamente por causa
# do contraste do "×"/seta contra a tag — ver Seção 7.
primaryColor = "#1e3a5f"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f5f7fb"
textColor = "#16213a"
```

---

## 5. Código relevante (com caminho no topo)

### 5.1 `src/branding.py` → `inject_shell_css()` — a casca visual global (estado atual, v6.4.0)

```python
# src/branding.py

def inject_shell_css() -> None:
    """Casca visual do painel inteiro (fundo, sidebar, tipografia).
    Chamar 1x, logo após o gate de login, antes de qualquer conteúdo.
    A tela de LOGIN tem CSS próprio (_inject_login_css) e nunca coexiste
    com este.
    """
    st.markdown(
        """
        <style>
        :root {
            --f360-sidebar-bg: #eef1f6;
            --f360-sidebar-bg-2: #f8f9fc;
            --f360-sidebar-ink: #16283f;
            --f360-sidebar-ink-muted: #5b6b85;
            --f360-sidebar-line: #d8dfea;
            --f360-accent: #1e3a5f;
            /* Navy translúcido — cor de "selecionado/ativo" dos widgets da
               sidebar (chip do multiselect, hover de botão). Suave de
               propósito: o navy chapado do primaryColor brigava com a
               sidebar clara (6.4.0). */
            --f360-accent-soft: rgba(30, 58, 95, 0.10);
            --f360-accent-soft-hover: rgba(30, 58, 95, 0.17);
            --f360-banner-from: #1c3250;
            --f360-banner-to: #16283f;
            --f360-banner-title: #e0ac52;
            --f360-banner-sub: #c3d0e6;
            --f360-content-max: 1500px;
        }

        html, body, [class*="css"] {
            font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
        }
        h1, h2, h3 {
            font-family: "Fraunces", Georgia, "Times New Roman", serif !important;
            letter-spacing: -0.01em;
        }

        /* ---- Largura e reflow do conteúdo (6.4.0) ----
           Sem max-width, cada monitor renderizava outra proporção. Não usa
           !important pra não brigar com o CSS da tela de login. */
        [data-testid="stMainBlockContainer"] {
            max-width: var(--f360-content-max);
            margin-inline: auto;
            padding-inline: clamp(1rem, 3vw, 3rem);
        }
        /* Colunas quebram em vez de esmagar/sobrepor quando o espaço aperta. */
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; align-items: stretch; }
        [data-testid="stColumn"], [data-testid="column"] { min-width: min(100%, 260px); }
        [data-testid="stColumn"] > div { min-width: 0; }
        [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] * { overflow-wrap: anywhere; }
        [data-testid="stMainBlockContainer"] img { max-width: 100%; height: auto; }
        [data-testid="stMainBlockContainer"] table { max-width: 100%; }

        /* Divisória do bloco "card-resumo | visual" (src/dashboard/layout.py).
           Alvo = a classe st-key-... que o st.container(key=) gera. Some < 900px. */
        [class*="st-key-f360-visualcol-"] {
            border-left: 1px solid var(--f360-sidebar-line);
            padding-left: 1.2rem;
        }
        @media (max-width: 900px) {
            [class*="st-key-f360-visualcol-"] { border-left: none; padding-left: 0; }
        }

        /* Cabeçalho de grupo de filtro na sidebar (Organização/Projeto/Tempo). */
        .f360-filtro-grupo {
            font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
            text-transform: uppercase; color: var(--f360-sidebar-ink-muted);
            margin: 1.2rem 0 0.15rem; padding-top: 0.75rem;
            border-top: 1px solid var(--f360-sidebar-line);
        }
        .f360-filtro-grupo.is-first { border-top: none; padding-top: 0; margin-top: 0.3rem; }

        /* Chip discreto de "filtros ativos" no topo das páginas. */
        .f360-badge-filtros {
            display: inline-block; font-size: 0.78rem; line-height: 1.5;
            color: var(--f360-sidebar-ink-muted);
            background: var(--f360-accent-soft); border: 1px solid var(--f360-sidebar-line);
            border-radius: 999px; padding: 0.15rem 0.7rem; margin-bottom: 0.9rem;
        }

        /* ---- Sidebar: cinza-azulado claro ---- */
        [data-testid="stSidebar"] {
            background: linear-gradient(175deg, var(--f360-sidebar-bg-2) 0%, var(--f360-sidebar-bg) 55%) !important;
        }
        /* Recolore o que fica DIRETO sobre o fundo (texto solto, label).
           span:not([data-baseweb] *) preserva o interior dos widgets. */
        [data-testid="stSidebar"] > div > div,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span:not([data-baseweb] *),
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
            color: var(--f360-sidebar-ink);
        }
        /* "?" de help= renderiza mal contra o gradiente → escondido na sidebar. */
        [data-testid="stSidebar"] [data-testid="stTooltipIcon"] { display: none !important; }
        [data-testid="stSidebar"] hr { border-color: var(--f360-sidebar-line) !important; }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--f360-sidebar-ink-muted) !important; }

        /* ---- Botões Streamlit REAIS da sidebar (Sair / Aplicar / Limpar) — e SÓ eles ----
           Até 6.3.0 a regra mirava `button` genérico e VAZAVA nos botõezinhos
           internos do multiselect (o "×", a seta, o limpar-tudo), desenhando
           o contorno quadrado. Escopar em .stButton/stFormSubmitButton resolve. */
        [data-testid="stSidebar"] .stButton button,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
            background: var(--f360-accent-soft) !important;
            border: 1px solid var(--f360-sidebar-line) !important;
            color: var(--f360-sidebar-ink) !important;
        }
        [data-testid="stSidebar"] .stButton button:hover,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:hover {
            background: var(--f360-accent-soft-hover) !important;
            border-color: var(--f360-accent) !important;
        }
        [data-testid="stSidebar"] .stButton button[kind="primary"] {
            color: #ffffff !important; font-weight: 600 !important;
        }
        [data-testid="stSidebar"] [data-testid="stCheckbox"] label span {
            border-color: var(--f360-sidebar-line) !important;
        }

        /* ---- Multiselect / selectbox da sidebar (6.4.0) ----
           Chip ("tag") em NAVY SUAVE (translúcido), não o navy sólido que o
           primaryColor do BaseWeb pinta por padrão. Sem forçar cor/fundo/borda
           nos ícones internos: só garante tinta navy no "×"/seta e remove o
           retângulo de fundo do botão de remover. */
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #ffffff;
            border-radius: 8px;
            border-color: var(--f360-sidebar-line);
        }
        [data-testid="stSidebar"] [data-baseweb="select"] input { color: var(--f360-sidebar-ink); }
        [data-testid="stSidebar"] [data-baseweb="tag"] {
            background: var(--f360-accent-soft) !important;
            border-radius: 7px !important;
            color: var(--f360-accent) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] span { color: var(--f360-accent) !important; }
        [data-testid="stSidebar"] [data-baseweb="tag"] svg {
            fill: var(--f360-accent) !important; color: var(--f360-accent) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] [role="button"] {
            background: transparent !important; border: none !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] [role="button"]:hover {
            background: var(--f360-accent-soft-hover) !important;
        }

        /* ---- Logo do st.logo() na sidebar — 🔒 NÃO MEXER ----
           Moldura circular de 110px, gif animado com crop/zoom pré-aplicado.
           Custou ~8 rodadas pra acertar tamanho + loop + centralização. */
        [data-testid="stSidebarHeader"] {
            height: auto !important; min-height: 0 !important; overflow: visible !important;
            margin-bottom: 1.1rem !important; padding-bottom: 0.6rem !important;
            border-bottom: 1px solid var(--f360-sidebar-line);
            flex: 1 1 auto !important; width: 100% !important;
            display: flex !important; justify-content: center !important;
        }
        [data-testid="stSidebarHeader"] > div {
            width: 110px !important; height: 110px !important; margin: 0 auto !important;
            border-radius: 50% !important; overflow: hidden !important;
            display: flex !important; align-items: center !important; justify-content: center !important;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.28) !important;
        }
        [data-testid="stSidebarLogo"], img.stLogo {
            width: 100% !important; height: 100% !important;
            max-width: none !important; object-fit: cover !important;
        }

        /* Item de navegação ativo (st.navigation). */
        [data-testid="stSidebar"] a[aria-current="page"] {
            background: rgba(30, 58, 95, 0.12) !important;
            border-radius: 8px; font-weight: 600 !important;
        }
        [data-testid="stSidebar"] a[aria-current="page"]::before {
            content: ""; position: absolute;
            left: -0.4rem; top: 15%; bottom: 15%; width: 3px;
            background: var(--f360-accent); border-radius: 0 3px 3px 0;
        }
        [data-testid="stSidebar"] a { position: relative; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # Fontes Google (única exceção de host externo permitida)
    st.markdown(
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Fraunces:opsz,wght@9..144,500;9..144,600&'
        'family=IBM+Plex+Sans:wght@400;500;600;700&'
        'family=IBM+Plex+Mono:wght@400;500;600&display=swap">',
        unsafe_allow_html=True,
    )
```

### 5.2 `src/dashboard/filtros.py` → montagem dos filtros na sidebar

```python
# src/dashboard/filtros.py  (trecho: helper de grupo + renderização)

def _grupo_filtro(texto: str, primeiro: bool = False) -> None:
    """Cabeçalho de grupo de filtro na sidebar (classe .f360-filtro-grupo)."""
    classe = "f360-filtro-grupo is-first" if primeiro else "f360-filtro-grupo"
    st.sidebar.markdown(f'<div class="{classe}">{texto}</div>', unsafe_allow_html=True)


def renderizar_filtros_sidebar(con) -> None:
    st.sidebar.divider()
    st.sidebar.caption("Ajuste os filtros e clique em **Aplicar filtros** no fim.")

    # ... consultas _opcoes(con, ...) que trazem as listas de valores ...

    _grupo_filtro("🏢 Organização", primeiro=True)
    gerencia_sel = st.sidebar.multiselect(
        "Gerência", gerencias, key="w_filtro_gerencia",
        help="Só Realizado, na nomenclatura da hierarquia SAP.",
    )
    # cascata: a lista de Coordenação estreita conforme a Gerência escolhida
    coordenacao_sel = st.sidebar.multiselect(
        "Coordenação", coordenacoes, key="w_filtro_coordenacao",
        help="Só Realizado — extraído do nome do Centro de Custo. Lista estreita conforme a Gerência acima.",
    )
    centro_custo_sel = st.sidebar.multiselect(
        "Centro de Custo", centros_custo, key="w_filtro_centro_custo",
        help="Lista estreita conforme Gerência/Coordenação escolhidas acima.",
    )
    pep_sel = st.sidebar.multiselect(
        "PEP", peps, key="w_filtro_pep",
        help="Só Orçamento — extraído do campo combinado 'Centro de Custo/PEP' da Base Zero.",
    )

    _grupo_filtro("📦 Projeto / Classificação")
    classificacao_sel = st.sidebar.multiselect(
        "Classificação (CAPEX/OPEX)", classificacoes, key="w_filtro_classificacao",
        help="Só Orçamento — Realizado (SAP) não carrega Classificação Contábil por linha.",
    )
    pacote_sel = st.sidebar.multiselect("Pacote", pacotes, key="w_filtro_pacote")

    projeto_capex_sel, elemento_pep_capex_sel = _renderizar_filtro_capex_obras(con)
    # → dentro dela: _grupo_filtro("🏗️ CAPEX Obras (Projeto/PEP)") + 2 multiselects
    #   ("Projeto", "Elemento PEP"), só se houver CJI3/CJI4 carregado.

    _grupo_filtro("📅 Tempo")
    anos_sel, trimestres_sel, meses_sel = _renderizar_filtro_periodo(con)
    # → 3 multiselects: "Ano", "Trimestre", "Mês" (independentes, não cascata)

    col_aplicar, col_limpar = st.sidebar.columns(2)
    aplicar = col_aplicar.button("Aplicar filtros", type="primary", use_container_width=True)
    limpar  = col_limpar.button("Limpar filtros", use_container_width=True)

    if aplicar:
        st.session_state["filtro_gerencia"] = gerencia_sel
        # ... copia todos os w_* → filtro_* ...
    if limpar:
        # apaga w_* e filtro_*, depois st.rerun()
        ...
```

Ou seja: a sidebar de filtros é **1 `st.caption` + 4 cabeçalhos de grupo (`<div class="f360-filtro-grupo">`) + ~11 `st.multiselect` + 2 `st.button` numa linha de 2 colunas**. Nenhum HTML custom além dos cabeçalhos de grupo.

### 5.3 `src/dashboard/app.py` → ordem de montagem da sidebar

```python
# src/dashboard/app.py  (trecho)

st.set_page_config(page_title="Fin360 — GG Infraestrutura (SP)", layout="wide")
init_session()
if not is_logged_in() and os.environ.get("ORCAMENTO_SKIP_LOGIN") != "1":
    render_login()          # tela de login — CSS PRÓPRIO, sidebar escondida
    st.stop()

inject_shell_css()          # ← injeta o <style> da Seção 5.1

def _renderizar_usuario_logado() -> None:
    st.logo(caminho_gif, icon_image=caminho_png, size="large")   # logo animada no topo da sidebar
    with st.sidebar:
        st.caption(f"👤 {get_nome()} · {get_papel()}")
        if st.button("Sair", use_container_width=True):
            clear_session(); st.rerun()
        st.divider()

_renderizar_usuario_logado()
_preparar_modo_simulacao()      # st.sidebar: checkbox "🎲 Simular causas/justificativas"
_preparar_filtros_globais()     # → renderizar_filtros_sidebar(con)   ★ OS FILTROS
pg = st.navigation({ "Plano de Manutenção": [...], "Plano de Obras": [...], "Dados": [...] })
pg.run()
_renderizar_rodape_sidebar()    # <div> centralizado: "v6.4.0 · Desenvolvido por Julio Paz"
```

**Ordem visual final da sidebar (de cima pra baixo):**
logo circular → `👤 nome · papel` → botão **Sair** → divisor → checkbox "Simular
causas" → divisor → caption "Ajuste os filtros…" → **grupos de filtro** →
**Aplicar / Limpar** → **menu de navegação** (`st.navigation`) → rodapé de versão.

> Nota: o `st.navigation` renderiza o menu **abaixo** dos filtros na ordem do
> código, mas o Streamlit pode reposicionar; hoje na prática o menu de páginas
> aparece **depois** do bloco de filtros.

### 5.4 `src/auth/login.py` → `_inject_login_css()` (CSS separado da tela de login)

```python
# src/auth/login.py

def _inject_login_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }   /* sem sidebar no login */
        [data-testid="stAppViewContainer"], .stApp { background: #eef1f6 !important; }
        .main .block-container, [data-testid="stMainBlockContainer"] {
            max-width: 420px !important; margin: 6vh auto !important;
            background: #ffffff; border-radius: 20px;
            padding: 2.75rem 2.5rem 2rem !important;
            box-shadow: 0 12px 34px rgba(15,23,42,0.10); text-align: center;
        }
        div[data-testid="stForm"] .stFormSubmitButton button,
        div[data-testid="stForm"] .stButton button {
            width: 100%;
            background: linear-gradient(135deg, #0f2f52 0%, #1d5488 100%) !important;
            color: #fff !important; border: none !important; border-radius: 10px !important;
            padding: 0.7rem !important; font-weight: 600 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
```

A tela de login **nunca coexiste** com `inject_shell_css()` (uma roda antes do
gate, a outra depois). A logo animada da tela de login é um `<video>` circular
(`render_logo_video()`), 🔒 não mexer.

### 5.5 `src/dashboard/layout.py` (novo em 6.4.0 — não é o problema, mas contextualiza os helpers de layout)

```python
# src/dashboard/layout.py

def bloco_resumo_visual(render_resumo, render_visual, *, key, proporcao=(1.0, 3.0), gap="medium"):
    """"Card-resumo | divisória | visual principal" — layout padrão do topo
    de quase toda página. Substitui o antigo st.columns([1, 0.04, 3]) +
    <div> de altura fixa (que virava um traço solto quando as colunas
    quebravam). Divisória = borda-esquerda do st.container(key=) da direita,
    via CSS [class*="st-key-f360-visualcol-"]. Some < 900px."""
    col_resumo, col_visual = st.columns(list(proporcao), gap=gap)
    with col_resumo:
        render_resumo()
    with col_visual:
        with st.container(key=f"f360-visualcol-{key}"):
            render_visual()

LEGENDA_SEMAFORO = "🟢 95–105% · 🟡 90–95%/105–110% · 🔴 fora da faixa · ⚪ sem dado · 🟣 delta relevante sem justificativa"
# + legenda_semaforo(), nota_forecast()  — só dedup de st.caption repetida
```

---

## 6. ★ O problema de design (o foco do pedido a você, Gemini)

### 6.1 Sintomas (o que se vê na tela)

1. **Chips navy sólidos e pesados numa sidebar clara e leve.** Um filtro com 1–2
   valores selecionados vira um "bloco de tinta" escuro; um filtro vazio
   ("Choose options") é claro e discreto. A sidebar fica com um contraste
   irregular e "sujo" — **as cores não conversam entre si**.
2. **Ícones do BaseWeb com aparência quebrada.** O "×" dentro de cada chip e os
   controles do select (limpar-tudo `⊗`, seta `⌄`) aparecem com um
   **contorno/caixa quadrada** em volta, de baixo contraste, parecendo bug.
3. **Grupos de filtro sem hierarquia visual clara** (parcialmente resolvido na
   6.4.0 com os cabeçalhos `.f360-filtro-grupo`, mas vale revisar o ritmo/
   espaçamento — hoje são ~11 multiselects empilhados).
4. **Sem "sensação de sistema"**: a sidebar de filtros, o menu de navegação, o
   botão "Sair", o checkbox de simulação e o rodapé de versão parecem 5 blocos
   de origens diferentes.

### 6.2 Por que é difícil (restrições técnicas)

- **Não dá para trocar o componente.** É o `st.multiselect` do Streamlit, cuja
  UI é o **BaseWeb**. Só se pode: (a) mexer no `primaryColor` do tema (afeta o
  app todo), e/ou (b) escrever CSS por cima de um DOM que não controlamos e que
  pode mudar a cada release do Streamlit.
- **`primaryColor` é global.** Ele pinta a tag do multiselect **e** o botão
  `type="primary"` ("Aplicar filtros") **e** ícones de foco. Um valor que fica
  ótimo na tag pode ficar ruim no botão, e vice-versa.
- **O BaseWeb "compensa contraste" sozinho.** Quando a cor da tag não dá
  contraste suficiente com o "×" branco que ele desenha, o BaseWeb parece
  adicionar um fundo/borda no ícone — que foi lido como o "contorno quadrado".
- **O dropdown de opções abre num portal** fora do `stSidebar` (CSS com escopo
  de sidebar não o alcança).
- **CSS-only.** Não há build de JS, não há como interceptar o render do BaseWeb.
- **Comparação:** o app-irmão **MRS Sentinel** usa o MESMO `st.multiselect`,
  MESMO BaseWeb, `primaryColor = #1e3a5f`, **zero CSS na tag/ícone**, e funciona
  liso — mas lá a **sidebar é escura (navy)**, então a tag navy sólida "combina"
  com o fundo. No Fin360 a sidebar é **clara**, então a tag navy sólida destoa.

### 6.3 Como seria o "bom" (critérios de aceite)

- Chips que **pertencem** à sidebar clara: leves, legíveis, sem "peso" de tinta.
- "×" / seta / limpar-tudo **limpos**, sem contorno/caixa, contraste ok.
- Estado vazio × estado com seleção com **transição visual suave** (não um salto
  de claro pra bloco escuro).
- Os 3–4 grupos de filtro **lidos como grupos** de imediato.
- A sidebar inteira parecendo **um sistema só** (filtros + navegação + ações).
- **Idêntico com a sidebar aberta ou fechada** e em qualquer monitor
  (1366 → 2560). Sem distorção/sobreposição. (Já tratado no conteúdo principal
  com `max-width: 1500px` + `flex-wrap`; a sidebar tem largura fixa do Streamlit.)
- **Sem regressão** na logo, na tela de login, nas cores dos gráficos.

---

## 7. Histórico das tentativas (extraído do CHANGELOG)

| Versão | O que se tentou no filtro | Resultado |
|---|---|---|
| 6.1.2–6.1.4 | Regras de CSS forçando cor/tamanho/`border-radius` no "×" e na seta do multiselect (sidebar ainda era **navy escuro**) | Não resolveu; a seta ficava quadrada, sobrava contorno |
| 6.1.5 | Mais CSS mirando `[role="button"]` dos ícones | "Não mudou nada visualmente" (usuário) |
| **6.2.0** | **Sidebar vira clara** (era navy sólido) — pra acabar com o choque "caixa clara ilha no meio do navy" | Melhorou o fundo, mas o contorno do ícone persistiu |
| 6.2.1 | Ampliou o CSS pra `[role="button"]` + `border-radius:50%` forçado | Persistiu |
| 6.2.2 | **Removeu todo o CSS especulativo** nos ícones, comparando com o MRS Sentinel (que não tem nenhum) | Contorno persistiu → conclusão: a causa é a **cor** |
| **6.3.0** | **`primaryColor` dourado → navy `#1e3a5f`** (igual ao Sentinel), pra dar contraste natural ao "×" branco | Chip virou navy sólido; melhora o ícone mas o **chip destoa da sidebar clara** |
| **6.4.0** | **Chip → navy translúcido** (`--f360-accent-soft`); **removeu a regra global de `button`** que vazava nos ícones internos (agora escopada em `.stButton`/`stFormSubmitButton`); removeu `[data-baseweb] * { color: initial }`; cabeçalhos de grupo `.f360-filtro-grupo`; badge "filtros ativos" virou chip | **Aguardando validação visual** — é a direção que queremos revisar com você |

---

## 8. O que já foi feito na v6.4.0 (aguardando validação)

**Filtro (`src/branding.py`):**
- Chip `[data-baseweb="tag"]` → `background: rgba(30,58,95,.10)`, texto/`svg`
  em `--f360-accent`, `border-radius: 7px`.
- Botão de remover (`[data-baseweb="tag"] [role="button"]`) → fundo/borda
  transparentes, hover suave.
- Regra de botão da sidebar **escopada** em `.stButton button` /
  `[data-testid="stFormSubmitButton"] button` (não mais `button` genérico).
- Removido `[data-testid="stSidebar"] [data-baseweb] * { color: initial }`.
- `[data-baseweb="select"] > div` → fundo branco, borda `--f360-sidebar-line`,
  `border-radius: 8px`.
- Cabeçalhos de grupo `.f360-filtro-grupo` (caixa-alta, hairline).

**Consistência entre telas (não é o filtro, mas foi na mesma passada):**
- `[data-testid="stMainBlockContainer"] { max-width: 1500px; margin-inline: auto }`.
- `[data-testid="stHorizontalBlock"] { flex-wrap: wrap }` + colunas com `min-width`.
- Novo `src/dashboard/layout.py` (`bloco_resumo_visual`) unifica o layout
  "card | divisória | gráfico" que estava copiado (com bug de layout) em 8 páginas.
- Árvore HTML (Nível 4/5) ganhou scroll-x interno.

**Validação feita:** `py_compile`, `compileall src`, `AppTest` renderizando as 10
páginas + `app.py` inteiro sem exceção, checks de reconciliação de números OK.
**Falta:** validação visual real (navegador) com sidebar aberta/fechada em
notebook + monitor externo.

---

## 9. Perguntas para você, Gemini

1. **Direção do chip.** Navy translúcido (`rgba(30,58,95,.10)` + texto navy) é a
   melhor escolha para uma sidebar clara `#eef1f6`? Ou um chip **branco com
   borda navy**? Ou **outline** (fundo transparente + borda)? Ou um cinza-azulado
   mais neutro (sem depender do `--f360-accent`)? Dê valores concretos
   (background, color, border, radius) e justifique em termos de hierarquia e
   contraste (WCAG).
2. **`primaryColor`.** Faz sentido manter `#1e3a5f` no tema e "neutralizar" a tag
   só por CSS (abordagem atual)? Ou existe um valor de `primaryColor` que fica
   bom **tanto** na tag **quanto** no botão "Aplicar filtros"? Lembre que ele
   também colore ícones de foco no app inteiro.
3. **Ícones do BaseWeb.** Como garantir "×"/seta/limpar-tudo limpos (sem
   contorno) de forma **robusta** a mudanças de versão do Streamlit? Que
   seletores são estáveis? Vale usar `:where()` pra baixar especificidade e
   deixar o BaseWeb "respirar", em vez de `!important`?
4. **Ritmo da sidebar.** Com ~11 multiselects + 4 grupos + 2 botões + checkbox +
   navegação + rodapé numa coluna estreita: qual densidade/espaçamento/tipografia
   recomenda? Faz sentido **colapsar** grupos (`<details>` ou `st.expander`)?
   Mover "Aplicar/Limpar" pra uma **barra fixa** no rodapé da sidebar?
5. **Coerência de sistema.** Como fazer filtros + `st.navigation` + "Sair" +
   checkbox de simulação + rodapé parecerem um sistema só? (bordas, fundos,
   espaçamento, um "cartão" por bloco?)
6. **Estado vazio vs. preenchido.** Ideias para suavizar a transição
   "placeholder claro → chips" (ex.: contador "(2)" ao lado do label, resumo
   textual em vez de chips quando há muitos valores, altura estável da caixa).
7. **Riscos.** Algum efeito colateral provável das regras da Seção 5.1 —
   sobretudo `[data-testid="stMarkdownContainer"] * { overflow-wrap: anywhere }`,
   `flex-wrap: wrap` nas colunas, e o seletor `[class*="st-key-…"]`?

---

## 10. Como rodar / ver

```bash
pip install -r requirements.txt
python -m src.model.build_star_schema        # ETL: planilhas → DuckDB (precisa dos brutos em data/raw/)
streamlit run src/dashboard/app.py           # sobe o painel (login obrigatório)
# bypass de login p/ dev local: ORCAMENTO_SKIP_LOGIN=1
```

Deploy: **Streamlit Community Cloud** (branch `master`). Versão atual **6.4.0**.
Stack fixada: `streamlit==1.57`, `duckdb`, `plotly`, `pandas`.

---

## 11. Anexo — estrutura de DOM de um `st.multiselect` (Streamlit 1.57 / BaseWeb, aproximada)

```html
<div data-testid="stMultiSelect" ...>
  <label data-testid="stWidgetLabel"><div data-testid="stMarkdownContainer">Gerência</div></label>
  <div data-baseweb="select" ...>
    <div ...>                                   <!-- a "caixa" (borda, fundo, radius) -->
      <div ...>                                 <!-- área de valores -->
        <span data-baseweb="tag" ...>           <!-- 1 chip por valor selecionado -->
          <span ...>GER MALHA (SP)</span>       <!-- texto do chip -->
          <span role="button" ...>              <!-- botão remover -->
            <svg ...>×</svg>
          </span>
        </span>
        <input ... />                           <!-- campo de busca -->
      </div>
      <div ...>                                 <!-- controles à direita -->
        <div role="button" ...><svg>⊗</svg></div>   <!-- limpar tudo -->
        <div ...><svg>⌄</svg></div>                  <!-- seta abrir -->
      </div>
    </div>
  </div>
  <!-- o menu de opções abre num PORTAL fora daqui, no fim do <body> -->
</div>
```

> Os nomes de classe reais do BaseWeb são hashes instáveis (ex.:
> `.st-emotion-cache-xxxxx`) — por isso o CSS mira `[data-baseweb="…"]` e
> `[data-testid="…"]`, que são mais estáveis, mas **não são contrato público**
> do Streamlit.
