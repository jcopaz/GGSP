# Changelog — Fin360 (Painel Orçamento GGSP)

Versionamento SemVer (ver `src/versao.py`): MAJOR = tela nova/schema/
segurança/integridade de dado; MINOR = funcionalidade nova sem quebrar
nada; PATCH = correção de bug. Bump a cada commit relevante.

## 7.1.0 — 2026-09-02

**Fase RBAC-A.2 — 1ª página: Projeção OPEX.** O escopo por universo
(`docs/08`) passa a ser aplicado de verdade nesta tela. Sem mudança de
schema; nenhuma figura Plotly tocada.

- **`src/auth/permissions.py`**: `require_universo(universo)` — barra a
  página (`st.error` + `st.stop`) se o usuário não tem acesso ao universo.
  Admin / `ORCAMENTO_SKIP_LOGIN=1` passam.
- **`src/dashboard/filtros.py`**: `clausula_escopo(universo, coluna="gerencia_id")`
  — fragmento sempre-ligado no formato de `clausula_periodo`: `("",[])` se
  vê o universo inteiro, `(" AND gerencia_id IN (?,…)", alvos)` no recorte,
  `(" AND 1=0", [])` se sem acesso (defensivo — a página já barrou antes).
- **`src/dashboard/projecao_opex.py`**: `render_projecao_opex` chama
  `require_universo("opex_sustaining")`, mostra a faixa "🔒 Recorte do seu
  acesso: <Gerências>" quando não tem a GG inteira, e injeta
  `clausula_escopo` nos filtros passados a `dados_tendencia` (Orçado e
  Realizado). Analista escopado em GER MALHA (SP) vê só os números dele;
  quem tem `gg` vê a GG inteira, sem a faixa.
- **`tests/rbac_projecao_check.py`**: confere que o Orçado das 3 famílias
  no recorte bate exatamente com a soma SQL direta de `fact_orcamento`
  filtrado por `gerencia_id`, e que o recorte de PM é estritamente menor
  que o total (filtro não é no-op). Números reais: PM escopo GGE_0025 =
  R$ 17,24 MM x total R$ 40,90 MM; PD R$ 2,88 MM x R$ 6,71 MM; PP
  R$ 0,35 MM x R$ 0,68 MM.
- Validado: `py_compile`; `pytest` (`test_rbac_escopo` 9 + `test_projecao_ritmo`
  1); `tests.rbac_projecao_check`; `AppTest.from_function(render_projecao_opex)`
  nos 3 cenários (sem acesso → barrado, 0 métrica; recorte → faixa +
  R$ 17,2 MM; GG inteira → sem faixa + R$ 40,9 MM); `AppTest.from_file("app.py")`
  skip-login e admin sem exceção; regressões `fase4_fase5` e
  `validacao_rdg_julho` inalteradas.

## 7.0.0 — 2026-09-02

**Fase RBAC-A.1** do RBAC de escopo por universo (`docs/08`). MAJOR por
mudança de schema (coluna nova no Neon). **Nada muda no que as páginas do
painel mostram** — enforcement nas telas é a Fase RBAC-A.2, ainda não
ligado. Aqui: schema + camada de leitura + tela de delegação.

> **Ação de deploy:** rodar `config/schema_postgres.sql` de novo no SQL
> Editor do Neon (idempotente) — adiciona `universo` em
> `app.escopo_acesso`, o tipo `gg` e o índice único novo. Sem isso, a
> nova seção da Administração mostra erro (tratado, não quebra a página) e
> os helpers caem em fail-closed.

- **Schema** (`config/schema_postgres.sql`): `app.escopo_acesso` ganha
  `universo` (`opex_sustaining` / `capex_sustaining` / `capex_obras`, ou
  NULL = linha legada), o `tipo` `gg` (= universo inteiro), e o índice
  único passa a considerar `coalesce(universo,'')` (antes
  `unique(usuario_id,tipo,valor)` impedia o mesmo recorte em universos
  diferentes).
- **Leitura** (`src/auth/permissions.py`): `universos_permitidos(usuario)`
  (1ª camada) e `escopo_universo(universo, usuario) -> (tem_acesso, tudo,
  alvos)` (2ª camada), com cache 1x/sessão (`_escopos_cache`) igual ao de
  permissão de página. `admin` e `ORCAMENTO_SKIP_LOGIN=1` = bypass; papel
  `gg` **não** é bypass (decisão do usuário 2026-09-02). Fail closed em
  erro de banco. Lógica pura isolada em `_resolver_*` para teste sem
  Streamlit. Constante `_PAGINAS_ALLOW_EXPLICITO = {"pce_especialista"}`
  registrada (opção B do `docs/08` §10) mas **ainda não usada** por
  `can_acessar_pagina` — só na Fase RBAC-A.2.
- **Delegação** (`src/dashboard/administracao.py`, aba "Permissões e
  escopos"): nova seção "Acesso por universo financeiro" — por usuário, um
  bloco por universo (vê? → GG inteira | Gerências específicas →
  multiselect; CAPEX Obras ainda tem Projetos/Elemento PEP e o checkbox
  "vê a tela CAPEX Obras — Especialista", que grava `permissao_pagina`
  para `pce_especialista`). Grava via `substituir_escopo_universo`
  (delete+insert atômico por universo). A antiga seção "Escopos de dados"
  virou "Escopos avançados (legado)" — grava linhas sem `universo`, que o
  RBAC novo ignora; mantida para `pacote`/`centro_custo`/`pep_filho`.
- **`src/auth/admin_queries.py`**: `listar_escopos_universo` (resiliente a
  coluna ausente → `[]`), `substituir_escopo_universo` (transação via
  `conectar()`). `adicionar_escopo` (legado) reescrito para delete+insert
  — não dá mais para usar `on conflict(usuario_id,tipo,valor)` (índice
  mudou). `listar_escopos` passou a filtrar `universo is null`.
- **`tests/test_rbac_escopo.py`**: 9 casos da lógica pura de resolução
  (admin bypass, fail-closed sem grant, grant `gg` = tudo, recorte por
  Gerência = união, `gg` + Gerência → `gg` manda).
- Validado: `py_compile`; `python -m pytest -q tests/test_rbac_escopo.py`
  (9 passa); `AppTest.from_file("app.py")` skip-login e sessão admin sem
  exceção contra o `painel.duckdb` real; regressões `fase4_fase5` e
  `validacao_rdg_julho` inalteradas.

## 6.6.0 — 2026-09-02

Etapa 2 da migração para a **Visão Ideal** (`docs/07`). Reagrupamento da
sidebar — só rótulo/estrutura de menu, **nenhuma** mudança de permissão,
chave de página, consulta, dado ou gráfico.

- **Grupo `GESTÃO`** no lugar das duas seções soltas `Dados` e
  `Administração` (`app.py`):
  - `Dados` (1 página) + `Administração` (1 página) → um grupo só com as
    duas.
  - "Upload de Dados" renomeada para **"Dados e Qualidade"** (título de
    `st.Page` + `render_page_banner` da `pagina_upload`). Chave de
    permissão continua `upload`.
  - "Gestão e Auditoria" renomeada para **"Administração"** (título de
    `st.Page`) — o banner interno da página já dizia "Administração",
    agora bate. Continua admin-only por checagem direta de papel (não
    passa por `permissao_pagina`). Chave continua `administracao`.
  - Montagem do grupo movida para fora do literal `st.navigation({...})`
    (`_paginas_gestao` + `_secoes`); o grupo só entra no menu se sobrar
    ao menos 1 página visível — corrige de passagem o caso de cabeçalho
    de seção vazio para não-admin sem permissão de `upload`.
- Textos de apoio que apontavam "Dados → Upload de Dados" atualizados para
  "Gestão → Dados e Qualidade" (`app.py::_aviso_base_nao_processada`,
  `administracao.py`, `pce_especialista.py`).
- **Ainda não feito nesta etapa** (fica para uma etapa própria, é decisão
  de RBAC — quem pode restaurar): mover histórico de versões de upload /
  rollback da aba "Uploads e exportações" da Administração para dentro de
  "Dados e Qualidade". Hoje segue admin-only, o que já satisfaz o
  "restauração administrativa, quando autorizada" do `FIN360_VISAO_IDEAL`.
- Validado: `py_compile` em `app.py`/`versao.py`/`administracao.py`/
  `pce_especialista.py`; `AppTest.from_file("app.py")` (skip-login e login
  admin) sobe sem exceção contra o `painel.duckdb` real, grupo `GESTÃO`
  presente com as 2 páginas; as 2 regressões numéricas (`fase4_fase5`,
  `RDG julho`) inalteradas.

## 6.5.2 — 2026-09-01

Etapa 1 da migração para a **Visão Ideal** (sidebar compacta — ver
`docs/07-plano-migracao-visao-ideal.md`). Só documentação + 1 ajuste de CSS
isolado; nenhuma mudança de navegação, dado ou gráfico ainda.

- **`docs/07-plano-migracao-visao-ideal.md`** criado — de/para completo das
  ~17 páginas de hoje para os 8 itens em 3 grupos do `FIN360_VISAO_IDEAL.md`,
  7 etapas validáveis, 2 decisões em aberto (RBAC por aba; `st.tabs` nativo
  x render preguiçoso), padrão de código `@st.fragment` por painel (conexão
  DuckDB própria em cada fragmento).
- **Tag de filtro da sidebar: dourado sólido + texto branco**
  (`src/branding.py::inject_shell_css`) — o chip do multiselect passou de
  `--f360-gold-soft` (13%) + texto escuro para `--f360-gold` (`#c9932f`)
  cheio + texto e `×` brancos, a pedido do usuário. Hover do `×` e do
  botão interno do BaseWeb ajustados para branco translúcido. Nenhum outro
  seletor tocado; paleta de gráfico intocada.
- Validado: `py_compile` em `branding.py`/`versao.py`; `AppTest.from_file
  ("app.py")` (skip-login e login normal) sobe sem exceção contra o
  `painel.duckdb` real.

## 6.5.1 — 2026-09-01 (hotfix)

- **`app.py` movido pra raiz do repositório** (era `src/dashboard/app.py`,
  `git mv` — preserva histórico). Alinha com a arquitetura de publicação
  em Streamlit Cloud (entrada principal na raiz).
- **Corrige `ModuleNotFoundError: No module named 'src'` que essa mudança
  introduziria**: `_RAIZ_PROJETO` em `app.py` calculava 3 `.parent` (conta
  certa para quando o arquivo morava 3 níveis abaixo da raiz) — com o
  arquivo na raiz, isso aponta 2 pastas ACIMA da raiz real, e o
  `sys.path.insert` correspondente vira inofensivo/errado. Confirmado ao
  vivo com `AppTest.from_file("app.py")`, que quebra exatamente assim
  antes da correção. Trocado pra 1 único `.parent` (mesma conta que
  `src/config.py::RAIZ_PROJETO` já faz, 1 nível mais fundo). Sem essa
  correção, `st.logo()` da sidebar (mesma variável) também apontaria pro
  caminho errado do `fin360_logo.gif` e quebraria pra todo usuário logado.
- **Fallback técnico no vídeo do Login + cópia de `static/fin360.mp4` na
  raiz** (`src/branding.py`): o Streamlit só serve a URL `app/static/...`
  a partir de uma pasta `static/` ao lado do script principal — com
  `app.py` na raiz, isso deixou de ser `src/dashboard/static/` (onde o
  vídeo mora oficialmente, README.md) e passou a exigir `static/` também
  na raiz. Adicionada uma cópia idêntica de `fin360.mp4` em `static/`
  (raiz) só pra essa URL resolver; a cópia "oficial" continua em
  `src/dashboard/static/` (é dali que `st.logo()` lê, por caminho de
  arquivo, não por URL — não depende desse mecanismo). Se o arquivo não
  existir em nenhuma das duas (ex.: ambiente sem o binário), o Login cai
  sozinho pra `fin360_logo.png` embutida em base64, na mesma moldura
  circular — mesmo tamanho/sombra, sem mudar layout/cor/texto/fluxo.
- Validado: `py_compile`; `AppTest` (skip-login e login normal) sem
  exceção, inclusive contra o warehouse/dado real (renderizou a Visão
  Resumo Executivo de verdade); `tests/fase1_check.py` e
  `tests/fase4_fase5_check.py` batendo contra o dado real (waterfall
  fecha exatamente no Delta Total, Nível 3 bate com a categoria).
- Descoberto durante a correção, registrado como achado do diagnóstico
  (não corrigido agora, fora do escopo deste hotfix): o pacote que o
  Copilot devolveu ao reorganizar o projeto (`Fin360_projeto_completo_
  reenvio/`) tinha o mesmo código-fonte (100% idêntico em `app.py`,
  `settings.yaml`, `schema_postgres.sql`, `requirements.txt`), mas **não
  incluía os scripts reais de `tests/`** (só `__init__.py` vazio) nem o
  `fin360_logo.gif`/`fin360.mp4` originais (gif de qualidade bem inferior,
  vídeo ausente) — preservados aqui a partir da produção real, não do
  pacote do Copilot.

## 6.5.0 — 2026-08-30

Passada minuciosa na sidebar (`src/branding.py`). Só CSS — nenhuma
mudança de dado/lógica. Paleta de gráfico, tipos de gráfico e
`primaryColor` (`.streamlit/config.toml`, ainda navy) intocados; o
dourado é 100% CSS escopado em `[data-testid="stSidebar"]`.

- **Acento DOURADO de volta** (`--f360-gold: #c9932f`, o mesmo da
  6.2.0–6.2.2) — item de nav ativo (tint + barra dourada), anel de foco
  do multiselect, borda de hover dos botões, tag/chip. Voltou sem
  reabrir o problema do contorno da tag porque desde a 6.4.0 a tag e os
  ícones internos do BaseWeb são estilizados explicitamente.
- **Logo da sidebar quadrada — corrigido na raiz.** O `st.logo()` do
  Streamlit 1.57 embrulha o `<img>` num `<div>` só na página default e
  num `<button data-testid="stLogoLink">` nas demais — o seletor antigo
  (`stSidebarHeader > div`) só pegava o `<div>`, então a moldura circular
  sumia ao navegar pra fora da home. Agora div/a/button recebem a moldura
  e o `stSidebarCollapseButton` é excluído. Círculo com medida e sombra
  iguais aos da tela de login (112px, `rgba(15,23,42,.18)`).
- Botão "Aplicar filtros" com o mesmo gradiente navy do "Entrar" do login.
- Colunas da sidebar não quebram mais (Aplicar | Limpar lado a lado — a
  regra global de reflow da 6.4.0 agora é só do conteúdo principal);
  scrollbar fina; ritmo dos grupos de filtro revisto; hover no select.
- `--f360-accent*` viraram alias de `--f360-gold*` (compat).

## 6.4.0 — 2026-08-30

Passada de design UI/UX: filtro da sidebar + consistência de layout entre
telas e monitores. Nenhuma mudança de dado/schema/segurança — só casca
visual. Paleta de gráfico (`paleta.py`), tipos de gráfico e logomarca
(sidebar + login) **não foram tocados**, por pedido do usuário.

### Filtro da sidebar (`src/branding.py`)

CSS refinado a partir de uma segunda opinião de design (Gemini), sobre a
base do 6.4.0 — a lógica de `filtros.py` não mudou (mesmos widgets, mesma
cascata).

- **Chip ("tag") do multiselect em navy SUAVE** (`--f360-accent-soft`,
  navy translúcido ~8%) no lugar do navy sólido chapado que o
  `primaryColor` do BaseWeb pintava — o bloco escuro brigava com a
  sidebar clara ("as cores não conversam"). `primaryColor` continua navy
  (serve o resto do app). Chip ganha **borda sutil** + texto `#16283f`.
- **Contorno quadrado do "×"/seta resolvido na raiz**: a regra de botão
  da sidebar deixou de mirar `button` genérico (vazava nos botõezinhos
  internos do BaseWeb) e passou a mirar só `.stButton`/`stFormSubmitButton`.
  Removido o reset `[data-baseweb] * { color: initial }`. Somado a isso,
  um **reset explícito de fundo/borda/sombra** nos `[role="button"]`/
  `button`/`svg` internos do multiselect (× da tag, seta, limpar-tudo) —
  escopado só ao multiselect, `svg` a 12px muted, hover suave.
- Caixa do select ganha `:focus-within` (anel navy) e `::placeholder`
  estilizado; botão primário ("Aplicar filtros") com fill navy explícito.
- Grupos de filtro (Organização / Projeto / Tempo) viram cabeçalhos de
  seção de verdade (`.f360-filtro-grupo`) + caption curta no lugar do
  tooltip "?" escondido.

### Consistência entre telas/monitores

- **`max-width: 1500px` centralizado** no `.block-container` — sem isso
  cada monitor renderizava outra proporção (quadros-resumo e gráficos
  "distorcidos a depender do monitor").
- **Colunas com `flex-wrap` + `min-width`** — quando o espaço aperta
  (tela menor, sidebar aberto num notebook) empilham limpo em vez de
  esmagar/sobrepor.
- **`src/dashboard/layout.py` (novo)**: `bloco_resumo_visual()` — uma
  implementação só do "card-resumo | divisória | visual principal",
  substituindo o padrão `st.columns([1, 0.04, 3])` + `<div>` de altura
  fixa (a coluna-fantasma 0.04 virava um traço vertical solto no meio da
  tela quando as colunas quebravam). Aplicado em 8 páginas.
- Árvore colapsável (Nível 4/5, `arvore_html.py`) ganha wrapper de
  scroll horizontal — não força mais a página inteira a rolar em tela
  estreita.

### Labels / textos

- Títulos dos banners de página normalizados numa voz só.
- Legendas (`st.caption`) de 4–6 linhas enxutas pra 1–2 linhas + expander
  "Notas" com o restante (nenhum conteúdo removido).
- Badge "🔎 Filtros ativos" vira chip discreto (`.f360-badge-filtros`) no
  lugar do `st.info` full-width.

- Validado: `py_compile` em todos os módulos, AppTest por página sem
  exceção. Confirmação visual (sidebar aberto/fechado, notebook + monitor
  externo) pendente com o usuário.

## 6.3.0 — 2026-08-29

- **`primaryColor` trocado de dourado (#c9932f) pra azul-marinho
  (#1e3a5f)** — a pedido do usuário, depois que remover o CSS
  especulativo (6.2.2) NÃO resolveu o contorno do multiselect. Confirma a
  hipótese: BaseWeb usa `primaryColor` pra colorir a tag do multiselect,
  e dourado não tinha contraste natural suficiente pro "×"/seta que o
  próprio BaseWeb desenha por cima — o "contorno" era o BaseWeb tentando
  compensar. Valor idêntico ao do MRS Sentinel, por pedido explícito
  ("deixei os filtros iguais ao do Sentinel").
  - `.streamlit/config.toml`: `primaryColor = "#1e3a5f"`.
  - `src/branding.py`: `--f360-gold` renomeado pra `--f360-accent` (mesmo
    valor de `primaryColor`) — usado no indicador do item ativo de
    navegação e no hover do botão secundário. Texto do botão primário
    (ex. "Aplicar filtros") vira branco (não mais `#16283f` escuro) —
    dark-on-dark ficaria ilegível agora que o fundo do botão é navy, não
    mais dourado.
  - Dourado continua existindo só na imagem estática do logo (marca) —
    não mais como cor de widget "selecionado/ativo". Paleta de gráfico
    (`paleta.py`, `#ffc000`) não é tocada — sistema visual separado,
    decisão de 2026-08-13, sem relação com este problema.
- Validado: `py_compile`, sintaxe TOML, `AppTest` completo sem exceção.
  Confirmação visual pendente.

## 6.2.2 — 2026-08-29

- **Logo do sidebar: centralizada de verdade** — `stSidebarHeader` ficava
  lado a lado com o botão de colapsar (irmãos no mesmo flex row) e só
  ocupava a largura do próprio conteúdo (110px), início da linha. Agora
  cresce (`flex:1; width:100%`) pra tomar o espaço que sobra, e
  `justify-content:center` passa a centralizar em relação à sidebar
  inteira, não só dentro da própria moldura.
- **Filtros — removidas as regras de CSS que forçavam cor/fundo/borda/
  formato nos ícones internos do multiselect (seta, x)**, depois de
  comparar com o código-fonte do MRS Sentinel: mesmo `st.multiselect`,
  mesma engine BaseWeb, **zero CSS mirando esses elementos** — funciona
  liso lá porque o `primaryColor` de lá é azul-marinho escuro (alto
  contraste natural com "×" branco). O Fin360 usa `primaryColor` dourado;
  as regras removidas foram criadas quando a sidebar ainda era navy
  escuro (precisava mesmo forçar ícone claro) e provavelmente estavam
  brigando com o comportamento nativo do BaseWeb agora que a sidebar já
  é clara (6.2.0). Se o contorno persistir depois disso, a causa real é
  o dourado do tema, não CSS — decisão de trocar `primaryColor` fica pro
  usuário.
- Validado: `py_compile`, `AppTest` completo sem exceção. Confirmação
  visual pendente (logo + filtros).

## 6.2.1 — 2026-08-29

- **Logo da sidebar: mesmo loop da tela de login, finalmente**. Print do
  usuário mostrou que o tamanho/posição já estava certo (rodada 5.x), mas
  o "loop" continuava diferente do login. Investigação com frames reais
  (não tentativa): 2 causas raiz.
  1. `fin360_logo.gif` tinha só 38 frames amostrados esparsamente (a cada
     ~11,8 dos 450 frames do `fin360.mp4`) — a animação passa por fases
     bem distintas (marca oculta → cor → cinza → dourado, não só um anel
     girando), então a amostragem esparsa pulava fases inteiras.
  2. O CSS ainda aplicava `transform:scale(1.7)` no `<img>`, mas o GIF já
     tinha esse recorte pré-aplicado em cada frame — zoom duplicado,
     mostrando o centro morto de cada frame (círculo preto sólido).
  - Corrigido: `fin360_logo.gif` regenerado do zero a partir do
    `fin360.mp4` (75 frames, crop+zoom aplicado 1x só na geração,
    ~2,6 MB — era 1,4 MB); CSS não aplica mais `transform:scale`.
  - Lição registrada em `docs/04-licoes-aprendidas.md` item 23.
- **Filtros — seta quadrada + contorno restante**: a correção anterior
  (6.1.4) só cobria `<button>`; ampliado pra também pegar
  `[role="button"]` (comum no BaseWeb pra ícones clicáveis) e força
  `border-radius:50%` em qualquer um dos dois — resolve tanto o
  contorno quanto o formato quadrado da seta, independente do que o
  BaseWeb aplicar por padrão.
- Validado: `py_compile`, `AppTest` completo sem exceção. Confirmação
  visual pendente.

## 6.2.0 — 2026-08-29

- **Sidebar vira clara** (cinza-azulado, não mais navy sólido) —
  decisão do usuário depois de 2 rodadas de correção cirúrgica sem
  sucesso no contraste do ícone de seta/x do multiselect contra o navy.
  Substitui a versão navy aprovada em 2026-08-27.
  - `src/branding.py`: variáveis `--f360-sidebar-*` invertidas pra tons
    claros (mesma função de cada uma, valor oposto); botão secundário
    (Sair/Limpar filtros) troca véu branco translúcido por véu escuro
    (só faz sentido contra fundo claro agora); ícone dourado/accent
    (`--f360-gold`) sem mudança.
  - `src/dashboard/app.py`: rodapé da sidebar (versão + assinatura) tinha
    cor/borda fixas em hex, não em variável — atualizado manualmente pro
    mesmo par de tons claros.
  - Efeito colateral esperado (e desejado): ícone de seta/x do
    multiselect, que já tinha cor clara reforçada numa versão anterior,
    passa a ficar contra um fundo geral também claro — elimina o choque
    "caixa clara ilha no meio do navy" que gerava o contorno feio
    reportado, sem precisar achar o seletor exato do BaseWeb.
- Validado: `py_compile`, `AppTest` completo sem exceção. Confirmação
  visual ainda pendente (logo + filtros, junto com a 6.1.5).

## 6.1.5 — 2026-08-29

- **Logo do sidebar: círculo elegante igual ao da tela de login**,
  finalmente. Print do usuário mostrou o logo quadrado e descentralizado
  depois do ajuste anterior — causa raiz: as 2 tentativas anteriores
  tentavam fazer o `<img>` sozinho ser "moldura" (tamanho/corte) E
  "conteúdo com zoom" (`transform:scale`) ao mesmo tempo, o que não
  funciona (transform escala o recorte inteiro junto). Reestruturado
  pra replicar a mesma técnica de 2 nós que já funciona em
  `render_logo_video()` (tela de login): o `<div>` que o próprio
  `st.logo()` já gera em volta do `<img>` vira a MOLDURA (110px,
  círculo, `overflow:hidden`); o `<img>` em si vira o CONTEÚDO (100% da
  moldura + `transform:scale(1.7)`, mesmo fator do vídeo do login).
- Validado: `py_compile`, `AppTest` completo sem exceção. Confirmação
  visual ainda pendente.
- **Filtros (seta/x do multiselect) — ainda não resolvido**: o ajuste da
  6.1.4 não mudou nada visualmente, segundo o usuário. Investigação
  segue separada (não é a mesma causa da logo) — ver conversa/próximo
  commit.

## 6.1.4 — 2026-08-29

- **"Contorno preto" feio na seta/x do multiselect, corrigido**: a regra
  "Botão comum" (`button:not([kind="primary"])`, pensada pra botões
  inteiros tipo "Sair"/"Aplicar filtros") também pintava fundo + borda
  nos ícones internos de multiselect/selectbox (seta de abrir opções, x
  de remover tag/limpar tudo) — tecnicamente também são `<button>`,
  então herdavam a mesma caixinha visível. Neutralizado fundo/borda
  especificamente dentro de `[data-baseweb]`; a cor clara do ícone (já
  corrigida em versão anterior) não muda.
- Validado: `py_compile`, `AppTest` completo sem exceção. Ainda pendente
  confirmação visual do usuário (junto com o logo do item 6.1.3).

## 6.1.3 — 2026-08-29

- **Logo do sidebar aparecendo cortado nas bordas, corrigido**: print do
  usuário mostrou o logo maior porém cortado ("M"/"S" cortados nas
  pontas) depois do ajuste pra 165px — diagnóstico: `stSidebarHeader` e o
  `<div>` que envolve o `<img>` mantinham altura fixa/`overflow` do
  tamanho pequeno original, cortando a imagem maior. Liberado
  `height: auto` + `overflow: visible` nos dois containers, e
  `object-fit: contain` no próprio `<img>`.
- Validado: `py_compile`, `AppTest` completo sem exceção. **Ainda não
  confirmado visualmente** (sem navegador neste ambiente) — pendente
  print do usuário depois do reboot.

## 6.1.2 — 2026-08-29

- **Logo do sidebar reduzido pela metade** (330px → 165px) — ficou
  grande demais colado na navegação, a pedido do usuário depois de ver
  o resultado publicado.
- **Quebra visual entre logo e menu de navegação**: `stSidebarHeader`
  (container real do `st.logo()`, confirmado via DevTools) ganhou
  margem/borda inferior — antes "Plano de Manutenção" ficava colado
  embaixo do logo sem respiro.
- Validado: `py_compile`, `AppTest` completo sem exceção.

## 6.1.1 — 2026-08-29

- **Keep-awake ajustado**: conferido na API de execuções do GitHub
  (`workflows/keep-awake.yml/runs`) que o intervalo REAL entre execuções
  estava em 3h–7h, não os 30 min configurados — `schedule` do GitHub
  Actions é "melhor esforço" e atrasa mais em horário de pico, que é
  justamente `:00`/`:30` (o minuto que o cron usava). Deslocado pra
  `:07`/`:37`, mitigação oficialmente recomendada pelo GitHub pra esse
  atraso. Sem mudança de custo (mesma contagem de execuções/mês).
- Validado: sintaxe YAML.

## 6.1.0 — 2026-08-29

- **Filtros de Organização cascateiam** (Gerência → Coordenação → Centro
  de Custo): conferido no dado real que é hierarquia estrita (0 Centro de
  Custo em mais de 1 Coordenação/Gerência, 0 Coordenação em mais de 1
  Gerência). Cada caixa continua multiseleção livre, só a lista de
  sugestões estreita a partir do que já foi escolhido acima
  (`src/dashboard/filtros.py::_opcoes_filtradas`) — nunca remove um valor
  já selecionado, pra nunca quebrar o widget se a Gerência mudar depois.
- **"Visão OPEX" e "CAPEX Manutenção — Malha" viram 1 tela só**
  (`pagina_opex_capex_manutencao`, `src/dashboard/app.py`): as duas eram
  literalmente a mesma função (`render_visao_classificacao`), só
  trocando o parâmetro `classificacao` — confirmado em código antes de
  unificar. Toggle `st.segmented_control` (OPEX/CAPEX, padrão OPEX) no
  lugar de 2 itens de menu. **Consequência de RBAC**: as chaves de
  permissão antigas ("visao_opex"/"capex_manutencao") viram uma só
  ("opex_capex_manutencao") — não é mais possível liberar só um dos dois
  lados por permissão granular; quem acessa a tela escolhe livremente no
  toggle. Sem migração de banco (linha antiga em `app.permissao_pagina`
  fica órfã, inofensiva).
- Validado: `py_compile`; `AppTest` completo sem exceção; `AppTest`
  isolado da tela unificada nos 3 estados do toggle (OPEX/CAPEX/
  deselecionado); cascata de filtros testada direto contra o warehouse
  real (Gerência="GER MALHA (SP)" → 3 Coordenações → 4 Centro de Custo,
  batendo com o esperado); reconciliação Fase 4/5 inalterada (mudança é
  só UI/navegação, não toca cálculo).

## 6.0.0 — 2026-08-29

- **Escopos de dados do CAPEX Obras (PEP/PEP Filho) viram catálogo real**:
  `dim_catalogo_capex_obras` (nova, `build_star_schema.py`) materializa o
  Catálogo CAPEX Obras com granularidade completa (95 Elemento PEP, 2795
  PEP Filho) — antes só existia deduplicado 1 linha/projeto, transiente,
  nunca virava tabela. Corrige suposição errada de 2026-08-28 ("pep_filho
  não é campo que a fonte tem"), ver docs/04-licoes-aprendidas.md item 22.
- **Novo tipo de escopo `gerencia_obras`**, separado de `gerencia`:
  conferido no dado real que são duas taxonomias sem código em comum
  (Gerência SAP de Manutenção/OPEX × recorte regional do CAPEX Obras —
  Baixada Santista, Corredor São Paulo, Expansão, Mobilidade Urbana,
  Obras Ferroviárias). Migração de CHECK em `app.escopo_acesso.tipo`
  (**precisa rodar `config/schema_postgres.sql` de novo no Neon**).
- **`coordenacao` sai da lista selecionável** (Centro de Custo já cobre a
  mesma granularidade) — continua aceito no banco, só não aparece mais
  na tela.
- Rótulos amigáveis no seletor "Tipo" (ex. "PEP (Elemento PEP)" em vez de
  `elemento_pep` cru).
- Validado: `py_compile`, reprocessamento real da base (confirma 95/2795/5
  valores esperados por tipo, batendo com o exemplo dado pelo usuário —
  `DM/21973 — Pátio Regulador Jurubatuba`, `DM/21973C-04 — Projeto
  básico`), reconciliação Fase 4/5 inalterada (mudança é aditiva, não
  toca `fact_orcamento`/`fact_realizado`/`fact_pce_realizado`).
- Bump MAJOR: mudança de schema (Postgres + nova dimensão no warehouse).

## 5.0.1 — 2026-08-28

- **Logo do sidebar corrigido de verdade** (achado via DevTools real do
  usuário, não mais tentativa às cegas): o seletor `[data-testid="stLogo"]`
  usado nas duas tentativas anteriores (140px, 330px) nunca existiu —
  o Streamlit expõe `data-testid="stSidebarLogo"` no wrapper e usa
  `stLogo` como classe do `<img>`, não como data-testid. Corrigido pra
  `[data-testid="stSidebarLogo"], img.stLogo` — mesmo tamanho pedido
  (330px), agora realmente aplicado.
- **Ícone do botão de abrir/fechar "Filtros" (sidebar) corrigido**: o
  mesmo print mostrou um `<button>` com ícone `fill="currentColor"`
  quase invisível — causado pela regra `[data-baseweb] * { color:
  initial }` (2026-08-28, feita pra devolver contraste normal às caixas
  de multiselect/selectbox) que também zerava a cor desse botão/ícone,
  que fica dentro de um bloco `[data-baseweb]`. Reforça cor clara
  especificamente pra `button`/`svg` nesse contexto, sem tocar no reset
  das caixas de input.

## 5.0.0 — 2026-08-28 (correção de segurança)

- **Remove senha padrão fixa (achado HIGH de revisão de segurança)**: a
  4.1.0 (abaixo) introduziu `SENHA_PADRAO = "Fin360@123"` — um literal no
  código-fonte, igual pra todo usuário novo criado pela Administração.
  Revisão automática de segurança classificou como HIGH: "Hardcoded
  Credentials / Shared Default Password" (uma senha compartilhada e
  visível no código expõe toda conta ainda não trocada). Substituído por
  senha temporária **única e aleatória por usuário**
  (`src/auth/senha.py::gerar_senha_temporaria()`, mesma função do reset
  autoatendido), exibida uma única vez pra quem cria (`st.code`, nunca
  gravada em texto plano) — a pessoa continua obrigada a trocar no
  primeiro login. Sem migração de schema nova (reaproveita a coluna
  `app.usuario.precisa_trocar_senha` já criada na 4.1.0). Bump MAJOR por
  ser correção de segurança, não PATCH (regra do projeto).

## 4.1.0 — 2026-08-28

- **Senha padrão obrigatória**: usuário criado pela Administração sempre
  entra com `Fin360@123` e é travado numa tela de troca de senha
  obrigatória no primeiro login (nova coluna
  `app.usuario.precisa_trocar_senha`, migração idempotente em
  `config/schema_postgres.sql` — precisa rodar de novo no Neon).
  **Corrigido na 5.0.0 acima — senha fixa removida no mesmo dia.**
- **Gerência/Pacote/Centro de Custo/Coordenação selecionáveis**: criar
  usuário e Escopos de dados agora usam dropdown/multiseleção com valor
  real do warehouse local (dim_gerencia/dim_pacote/fact_realizado), não
  texto livre — dá pra escolher um, vários ou todos de uma vez.
  Projeto/Elemento PEP/PEP Filho continuam texto livre (sem lista
  fechada confiável na fonte ainda).
- **Auditoria em horário de Brasília**: toda data/hora da Administração
  (auditoria, upload, exportação) converte de UTC pra
  America/São_Paulo antes de exibir.
- Validado: `compileall`, reconciliação Fase 4/5, `AppTest` completo
  (`app.py` como admin e com `ORCAMENTO_SKIP_LOGIN`,
  `render_administracao()` com conexão real do warehouse local — passou
  por toda a lógica nova, só parou no ponto esperado de conexão com o
  Neon).

## 4.0.3 — 2026-08-28 (hotfix urgente)

- **Corrige possível causa de "trocar de página derruba pra tela de
  login"**: `can_acessar_pagina()` era chamada 1x por página da
  navegação (~15 páginas) em **todo rerun** do Streamlit — sem cache,
  cada clique podia abrir até ~15 conexões novas ao Neon em sequência
  (`conectar()` não usa pool). Lento o bastante pra estourar timeout de
  infraestrutura no meio do caminho. Agora `app.permissao_pagina` é
  buscada 1x por sessão (`st.session_state`), não repetida a cada
  página/clique. Admin não é afetado (já não tocava o banco pra isso).
  Cache não invalida sozinho durante a sessão — permissão alterada por
  um admin só pega efeito no próximo login da pessoa (trade-off
  aceito, não bug).

## 4.0.2 — 2026-08-28

- Ícone de ajuda ("?") escondido na sidebar — print do usuário mostrou
  renderizando quebrado (posição e contraste ruins) contra o fundo em
  gradiente; mais seguro esconder do que continuar ajustando cor às
  cegas sem conseguir ver o resultado ao vivo.
- Corrige botão "Aplicar filtros" (primário) quase invisível — a regra
  de botão fantasma da sidebar não distinguia primário de secundário e
  achatava os dois pro mesmo estilo sutil; agora só o secundário
  ("Sair"/"Limpar filtros") fica sutil, o primário usa o dourado do
  tema com texto reforçado.

## 4.0.1 — 2026-08-28

- Corrige ícones de filtro ilegíveis na sidebar (seta de dropdown,
  "?" de ajuda): a regra genérica `[data-testid="stSidebar"] *
  { color: claro }` também forçava o texto/ícone de DENTRO dos widgets
  (multiselect, selectbox, tooltip de ajuda) pra claro — e a caixa
  desses widgets é clara por padrão (tema global), então virava claro
  sobre claro. Trocado por regra cirúrgica: só label/texto solto vira
  claro; interior de widget (`[data-baseweb]`, ícone de tooltip) volta
  pro padrão do tema. Não verificado visualmente (sem navegador neste
  ambiente).
- Deploy no Streamlit Cloud ficou (3ª vez hoje) com cache desatualizado
  mesmo com o repositório remoto correto (`ImportError` de
  `restaurar_versao_arquivo`, já existia certinho no commit anterior) —
  Reboot manual resolve, ver lição atualizada em
  `docs/04-licoes-aprendidas.md`, item 21.

## 4.0.0 — 2026-08-28

Integração do pacote de melhorias v3.4.0 (trazido pelo usuário, cópia em
`fin360_melhorias_v3_4_0/`, fora do git) — arquivo por arquivo, não
substituição em bloco. Detalhe completo em
`docs/06-administracao-auditoria-e-projecao.md`.

- **Nova página "Administração"** (`src/dashboard/administracao.py`),
  exclusiva de admin: usuários (criar/editar/ativar, papel, permissões
  operacionais), permissões por página, escopos de dado (cadastro/
  consulta, ainda não aplicados em filtro — pendência documentada),
  auditoria, histórico versionado de upload com reversão, cópias
  auditadas de exportação.
- **RBAC de navegação**: `can_acessar_pagina()` esconde página do menu
  E revalida dentro dela (`_pagina_se_permitida`/`_com_guard_pagina` em
  `app.py`) — não confia só em esconder. Usuário sem override continua
  vendo tudo (compatibilidade). Administração nunca passa pelo override
  genérico, é sempre `is_admin()` direto.
- **Upload versionado**: `app.arquivo_bruto_versao` (nova) guarda todo o
  histórico; `app.arquivo_bruto` (já existia) continua só com a última
  versão pro auto-restore de reboot — as duas ficam em sincronia.
- **4 tabelas novas no Neon** (`permissao_pagina`, `escopo_acesso`,
  `artefato_exportado`, `arquivo_bruto_versao`) — **não 5**: o pacote
  propunha `log_atividade`, redundante com `log_auditoria` já existente
  (reaproveitada, não duplicada). SQL em `config/schema_postgres.sql`,
  idempotente — **precisa ser rodado no Neon antes da Administração
  funcionar**.
- **2 correções de segurança/robustez sobre o design recebido**: (1)
  `can_acessar_pagina` falhava aberto se o Postgres caísse (todo mundo
  via tudo) — corrigido pra fail closed; (2) `src/auth/db.py::conectar()`
  não tinha timeout de conexão — numa rede que bloqueia a porta em
  silêncio, a auditoria (agora chamada a cada página) travava a UI
  inteira esperando o timeout padrão do SO; corrigido com
  `connect_timeout=8`.
- `ORCAMENTO_SKIP_LOGIN=1` (bypass local) também libera o RBAC novo —
  sem isso o próprio flag de teste local ficava inútil.
- Achado durante a integração: `projecao_opex.py` e `administracao.py`
  já tinham sido copiados pro repositório antes desta integração, mas
  dependiam de peças que nunca tinham sido implementadas (coluna de
  projeção em `tendencia.py`; `restaurar_versao_arquivo` em
  `arquivo_bruto.py`) — as duas telas quebrariam ao abrir. Implementado
  nesta rodada.
- Limpeza: `devcontainer.json` solto na raiz (cópia idêntica do que já
  existe em `.devcontainer/`) e `LEIA-ME-ENTREGA.md` removidos —
  redundantes com este CHANGELOG e com `docs/06`.
- Validado: `python -m compileall src tests` sem erro; testes de
  reconciliação existentes (Fase 4/5) continuam batendo; `AppTest` do
  `app.py` inteiro sem exceção como admin simulado e com
  `ORCAMENTO_SKIP_LOGIN`; `render_administracao()` testado até o ponto
  de conexão real com o Neon (falha esperada aqui — rede local não
  alcança o Neon — não é bug de código).
- **Não executado**: qualquer teste que dependa de dado real no Neon
  (listar usuários/atividades/versões de verdade) — precisa do schema
  aplicado e de acesso de rede que este ambiente não tem. Fica como
  próximo passo do usuário: rodar o SQL, depois confirmar ao vivo.

## 3.4.0 — 2026-08-28

- **Nova página "Projeção OPEX"** (Plano de Manutenção): 3 abas —
  Despesas Gerais (PD), Despesas Pessoais (PP), Manutenção (PM). Mostra
  Orçamento Anual, Fechamento Projetado e a diferença entre os dois.
- **Nova curva "Projeção pelo ritmo realizado"** em `tendencia.py`
  (`dados_tendencia`/`figura_tendencia`) — **diferente do Forecast
  PMO**, que continua com a fórmula original intocada (redistribui o
  saldo pra fechar exatamente no Orçado). A nova curva não força
  convergência nenhuma: identifica o último mês com Realizado, calcula
  a média mensal sobre os meses efetivamente considerados, e projeta
  essa média pros meses restantes — pode fechar acima (vermelho) ou
  abaixo (verde) do Orçado, cor semântica igual aos chips de status.
  Sem nenhum mês com Realizado, a coluna fica vazia (nunca projeta em
  cima de nada).
- Encontrado durante a integração: um pacote de melhorias trazido pelo
  usuário já tinha copiado `src/dashboard/projecao_opex.py` pro
  repositório, mas dependia de uma coluna (`projecao_ritmo_acumulada`)
  que nunca foi implementada em `tendencia.py` — a página quebraria com
  `KeyError` assim que alguém a abrisse. Implementado agora.
- Validado: testes de reconciliação existentes (Fase 4/5 — Delta Total,
  fechamento do waterfall, Não Justificado) continuam batendo depois da
  mudança; fórmula da nova curva conferida manualmente contra o dado
  real das 3 famílias (PD/PP/PM). Fase 1/2/3 rodaram sem exceção
  (divergências que aparecem ali contra baseline antigo são anteriores
  a esta mudança, não relacionadas).

## 3.3.1 — 2026-08-28 (hotfix urgente, durante reunião)

- **Corrige `NameError: name 'render_page_banner' is not defined`** na
  página de Upload — import esquecido em `app.py` (todos os outros 12
  arquivos que passaram a usar `render_page_banner` na v3.3.0 já
  importavam certo; só `app.py` tinha uma linha de import existente que
  eu deveria ter estendido, não criei nova). Confirmado via AppTest
  antes e depois do fix.
- Logo do `st.logo()` em **330px** (3x o tamanho anterior). GIF
  regerado em resolução maior (280x280, 38 frames, ~1.4 MB) pra não
  ficar borrado esticado.
- Conflito registrado (não decidido sozinho): pedido novo pede usar
  `fin360.mp4` direto em vez de GIF — mantive o GIF de propósito,
  porque é a única forma que resolve posição (acima do menu) E
  animação ao mesmo tempo (`st.logo()` não aceita vídeo). Ver docstring
  de `_renderizar_usuario_logado` em `app.py`.

## 3.3.0 — 2026-08-28

- **Card em gradiente em todas as páginas** (`render_page_banner`) — as
  13 páginas que ainda tinham `st.header()` + parágrafo de legenda
  longo passaram pro banner navy/dourado, subtítulo reduzido a 1 linha
  essencial. Upload de Dados manteve o texto completo, mas movido pra
  dentro de um expander ("Como funciona o upload") em vez de aberto.
- **Logo animada de volta**: `st.logo()` agora usa um GIF (75 frames,
  110×110, ~600 KB) gerado do próprio `fin360.mp4`, não mais PNG
  estático — mantém o loop pedido, só troca vídeo por GIF (`st.logo()`
  não aceita vídeo, mas aceita GIF animado). `icon_image` (PNG) cobre
  só o estado colapsado da sidebar.
- Logo maior via CSS (`width: 140px`) — não confirmado visualmente.
- Testado via AppTest: as 12 páginas principais + a página default
  rodaram sem exceção contra o warehouse local real antes de publicar.

## 3.2.0 — 2026-08-28

- **Logo da sidebar via `st.logo()`** — substitui a tentativa de CSS
  (que não funcionava: o menu de `st.navigation()` fixa a própria
  posição, independente da ordem de chamada no script). Frame estático
  extraído de `fin360.mp4` (`src/dashboard/static/fin360_logo.png`) —
  `st.logo()` só aceita imagem, não vídeo.
- **Tema próprio no `config.toml`** (`primaryColor` dourado): corrige o
  vermelho de fábrica do Streamlit em widgets nativos (tags de
  multiselect, botão "Aplicar filtros") que ficava ilegível contra a
  sidebar navy. Fundo do conteúdo principal voltou a branco
  (`backgroundColor`), revertendo o cinza-azulado testado antes.
- Filtro de Período (Ano/Trimestre/Mês) não fica mais dentro de um
  expander recolhido — estático, sempre visível.
- **Novo `render_page_banner()`** (`src/branding.py`): card em gradiente
  navy/dourado pro cabeçalho de página (ícone + título + subtítulo
  curto), substituindo `st.header()` + parágrafo longo de legenda.
  Aplicado em "CAPEX Obras — Especialista" e "Contas" (CAPEX) nesta
  rodada — mesmo padrão de banner usado em outros apps do usuário,
  personalizado pra identidade do Fin360.
- Testado via AppTest (app.py inteiro + os 2 banners novos contra o
  warehouse local real) antes de publicar.

## 3.1.2 — 2026-08-28

- Removido o `st.title` redundante do topo de toda página (pedido do
  usuário: "reduza o texto, deixe só o essencial") — a marca já fica
  fixa na sidebar, cada página já tem seu próprio `st.header` curto.
- "Nível 4 — Contas (CAPEX)" encurtado pra "Contas", legenda longa
  reduzida a uma linha.
- Sidebar reestruturada: bloco de marca (logo/Fin360/usuário/Sair) no
  topo, rodapé fixo (só "v{versão}" + "Desenvolvido por Julio Paz")
  depois de toda a navegação — chamado depois de `pg.run()` de propósito.
- Tentativa de reordenar a logo pra cima do menu de navegação via CSS
  (`order` em flexbox) — **não verificado visualmente** (sem navegador
  neste ambiente), pode precisar de ajuste depois de olhar ao vivo.
- Testado via `AppTest` rodando `app.py` inteiro de ponta a ponta antes
  de publicar (sem exceção).

## 3.1.1 — 2026-08-28

- Keep-awake do fin360.streamlit.app via GitHub Actions (ping a cada 30
  min, `.github/workflows/keep-awake.yml`) — evita o app dormir por
  inatividade no plano free do Streamlit Community Cloud.
- Registrado: o "Reboot app" manual às vezes é necessário mesmo com push
  novo — o redeploy automático pode ficar com arquivo desatualizado em
  cache (visto em produção 2026-08-28, `ImportError` de `inject_shell_css`
  mesmo com o repositório remoto 100% consistente).

## 3.1.0 — 2026-08-27

- **Casca visual nova** (aprovada pelo usuário): sidebar navy sólido com
  indicador dourado só no item de navegação ativo (marca vira parte da
  navegação, não só do login); fundo do conteúdo em cinza-azulado; tipografia
  `Fraunces` (títulos) + `IBM Plex Sans` (interface) + `IBM Plex Mono`
  (número) em todo o painel — `src/branding.py::inject_shell_css()`.
- **Card de GG (Nível 1) redesenhado**: hierarquia rótulo → Delta grande
  em monoespaçada → chip de status, em vez da tabela markdown antiga.
  Chip reaproveita as cores reais do semáforo (`paleta.py`:
  `COR_ADERENCIA_OK/ATENCAO/FORA`, novo `COR_ROXO`) — nova função
  `fmt_semaforo_chip()` em `formatacao.py`. Paleta de gráfico intocada.
- Testado via `AppTest` (render sem exceção, inclusive caso limite sem
  orçamento/aderência indefinida) antes de publicar.

## 3.0.1 — 2026-08-27

- Tela de login: "Fin360" e "Acesso Restrito" (removida a menção à GG,
  pedido do usuário) centralizados abaixo da logo, versão centralizada
  abaixo disso. Assinatura "Desenvolvimento: Julio Paz" no rodapé.
- Sidebar: logo + "Fin360" + versão centralizados no topo (acima do
  bloco "Plano de Manutenção"), separados por divisor do bloco de
  identidade/logout do usuário logado.

## 3.0.0 — 2026-08-27

- **`fact_pce_realizado` deixa de depender de "PCE Base Luiz.xlsx"**
  (planilha curada manualmente) — agora derivada em código do CJI3 +
  Catálogo CAPEX Obras (nova tabela De/Para `Objeto → Classificação`,
  `config/catalogo_objeto_classificacao.csv`, achado empírico: 100%
  determinístico no dado real). Zona de upload `pce_realizado` removida
  — menos uma planilha manual na rotina. Validado contra dado real: mesmo
  total exato do CJI3, sem duplicar/perder valor. Ver
  `docs/04-licoes-aprendidas.md`, item 20. Mudança de integridade de
  dado (como um número central é calculado) — bump MAJOR pela própria
  regra de versionamento do projeto.

## 2.0.2 — 2026-08-27

- Corrige `duckdb.CatalogException` na página "CAPEX Obras — Especialista":
  `fact_pce_realizado` (fonte "PCE Base Luiz.xlsx") não tinha zona de
  upload própria — nova zona "Sob demanda" em `TIPOS_ARQUIVO`, mais guard
  defensivo em `pce_especialista.py` (devolve 0/vazio se a tabela ainda
  não existir, em vez de quebrar). Ver `docs/04-licoes-aprendidas.md`,
  item 19.

## 2.0.1 — 2026-08-27

- Redesenho da tela de login: card branco centralizado sobre fundo neutro,
  logo em moldura circular (recorta a margem escura do vídeo fonte via
  `transform: scale`), tipografia e botão com a cor da marca (azul-marinho
  Fin360). Mesma moldura circular aplicada ao logo da sidebar.

## 2.0.0 — 2026-08-27

- Tela de login centralizada (CSS) e vídeo de logo corrigido — `static/`
  precisa estar em `src/dashboard/static/` (mesma pasta do script
  principal), não na raiz do repositório; movido de lugar.
- **Nova tabela no schema Postgres**: `app.arquivo_bruto` — guarda o
  último arquivo bruto de cada tipo enviado no Upload de Dados. O painel
  agora se restaura sozinho depois de um reboot do Streamlit Cloud (disco
  efêmero apagado): `_garantir_base_pronta()` restaura os arquivos do
  Neon e reprocessa a base automaticamente, sem precisar reenviar arquivo
  que não mudou. Upload manual só é necessário quando há arquivo novo de
  verdade. **Requer rodar de novo `config/schema_postgres.sql` no Neon**
  (idempotente — só cria a tabela nova, não afeta as existentes).

## 1.0.0 — 2026-08-27

Primeira versão publicada online (antes só rodava local, sem controle
de versão).

- Login próprio (bcrypt + Neon Postgres), gate de sessão obrigatório em
  todas as páginas.
- Fundação de RBAC (papéis, permissões granulares — `src/auth/`).
- Schema de justificativas/delegação/auditoria preparado no Postgres
  (`config/schema_postgres.sql`), pronto para a Camada 4 (captura de
  justificativas).
- Deploy no Streamlit Community Cloud (`fin360.streamlit.app`).
- Identidade visual "Fin360": logo em vídeo (login + sidebar), nome
  padrão em toda a interface.
- Correções de "dia zero" encontradas no primeiro deploy real (ver
  `docs/04-licoes-aprendidas.md`, itens 16-18): sys.path na raiz do
  projeto, aviso claro quando faltam arquivos obrigatórios no upload,
  CSV de explicações ausente tratado como "sem justificativa ainda".
