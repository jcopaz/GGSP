# 07 — Plano de migração para a Visão Ideal (sidebar compacta)

Pedido do usuário em 2026-09-01: reestruturar o Fin360 para bater com
`FIN360_VISAO_IDEAL.md` (raiz do projeto — a **versão compacta/corrigida**,
não `FIN360_VISAO_IDEAL_ANTES_DO_MARCO.md`, que apresenta o inventário de
funcionalidades como se fosse a sidebar).

**Objetivo declarado:** eliminar a redundância de abas/páginas e consolidar
de forma organizada. Nenhuma função pode ser perdida — a complexidade migra
para dentro de abas internas.

Este doc é o mapa da obra. Cada etapa é um incremento validável isolado
(`py_compile` + `AppTest` contra o `painel.duckdb` real + as 2 regressões
numéricas `fase4_fase5_check` e `validacao_rdg_julho_check`).

---

## 1. Regras de execução (dadas pelo usuário)

1. **`st.fragment` em tudo** — cada painel de aba é um `@st.fragment`
   isolado. Cada fragmento **abre a própria conexão DuckDB** (`_conectar()`
   + `finally: con.close()` dentro do próprio fragmento). Nunca capturar
   `con` do escopo externo: o `finally` do run completo fecha a conexão, e
   um rerun só-do-fragmento reusaria uma conexão fechada. Meta: interação
   dentro de uma aba não dispara consulta das outras.
2. **Paleta de gráfico intocada.** Não alterar cores, tipo de gráfico nem
   layout de nenhuma figura. Se uma consolidação exigir mexer em um
   gráfico, **parar e sinalizar antes** — ver
   `docs/04-licoes-aprendidas.md` e a memória de regras de gráfico.
3. **`CAPEX Obras - Especialistas`** (`pce_especialista.py`): conteúdo,
   filtros, colunas, gráficos, fórmulas e ordenação 100% congelados. Só
   pode mudar de lugar na sidebar. A label do documento é
   `CAPEX Obras - Especialistas` (plural, hífen) — hoje o código usa
   `CAPEX Obras — Especialista` (singular, travessão). Pendente de decisão
   do usuário: renomear para bater com o doc, ou o doc se ajusta.
4. Login (`src/auth/login.py`, `src/branding.py::render_logo_video`)
   intocado.

---

## 2. Estrutura atual x estrutura-alvo

### Hoje (v6.5.x) — ~17 itens de menu em 4 grupos

```
Plano de Manutenção
  Visão Resumo Executivo — GGSP   (resumo_executivo)   [default]
  Painel Executivo                (painel_executivo)
  OPEX / CAPEX — Manutenção Malha  (opex_capex_manutencao)
  Visão Manutenção (SP)           (visao_manutencao)
  Projeção OPEX                   (projecao_opex)
  Nível 4 — Contas                (contas)
  Nível 5 — Centro de Custo       (centro_custo)
  Nível 6 — Rastreabilidade SAP   (rastreabilidade_sap)
Plano de Obras
  Resumo Executivo               (capex_resumo)
  Painel Executivo               (capex_painel)
  Nível 4 — Contas               (capex_contas)
  Nível 6 — Rastreabilidade SAP  (capex_rastreabilidade)
  CAPEX Obras — Especialista     (pce_especialista)
Dados
  Upload de Dados                (upload)
Administração  [admin-only]
  Gestão e Auditoria             (administracao)
```

### Alvo — 8 itens em 3 grupos

```
PLANO DE MANUTENÇÃO
  Resumo                       abas: Visão Executiva | Desvios e Causas | Projeção
  Análise Financeira           abas: Pacotes | Contas e Centros de Custo | CAPEX Sustaining
  Pendências e Justificativas   abas: Fila de Pendências | Em elaboração | Consolidadas | Histórico
  Evidências SAP
CAPEX PLANO DE OBRAS
  Resumo                       abas: Visão Executiva | Desvios e Evolução
  CAPEX Obras - Especialistas   (página própria, intacta)
GESTÃO
  Dados e Qualidade
  Administração
```

### De/para detalhado

| Página hoje (`chave`) | Destino | Observação |
|---|---|---|
| `resumo_executivo` | Manutenção › Resumo › aba **Visão Executiva** | `render_resumo_executivo` já é função limpa |
| `painel_executivo` | Manutenção › Resumo › aba **Desvios e Causas** | hoje é orquestração inline em `app.py::pagina_painel` (~55 linhas) — extrair para `render_*` |
| `projecao_opex` | Manutenção › Resumo › aba **Projeção** | `projecao_opex.py` já usa `st.tabs` interno (PM/PD/PP) → aba dentro de aba, revisar visual |
| `visao_manutencao` | Manutenção › Análise Financeira › aba **Pacotes** | + componentes de ranking |
| `opex_capex_manutencao` (lado CAPEX) | Análise Financeira › aba **CAPEX Sustaining** | lado OPEX (`render_visao_classificacao("OPEX")`) precisa de destino explícito — ver item aberto |
| `contas` | Análise Financeira › aba **Contas e Centros de Custo** | toggle interno Conta \| Centro de Custo |
| `centro_custo` | mesma aba, lado "Centro de Custo" do toggle | |
| `rastreabilidade_sap` | página **Evidências SAP** (4ª do grupo) | + acesso por link contextual do Pacote/Conta/CC |
| — não existe — | Manutenção › **Pendências e Justificativas** | **feature nova**, ver `docs/03` |
| `capex_resumo` | Obras › Resumo › aba **Visão Executiva** | |
| `capex_painel` | Obras › Resumo › aba **Desvios e Evolução** | fusão real (hoje repete card+waterfall de propósito) |
| `capex_contas` | componente/aba dentro do Resumo de Obras | perde item de menu (doc aceita) |
| `capex_rastreabilidade` | rastreabilidade CJI3 via link contextual | perde item de menu (doc aceita) |
| `pce_especialista` | Obras › **CAPEX Obras - Especialistas** | só reposiciona |
| `upload` | GESTÃO › **Dados e Qualidade** | + alertas de qualidade / versões / rollback (parte já em `administracao.py` aba "Uploads") |
| `administracao` | GESTÃO › **Administração** | só reagrupa |

---

## 3. Decisões em aberto (bloqueiam as etapas estruturais)

### D1 — RBAC nas páginas consolidadas — **SUPERADO por `docs/08` (2026-09-01)**

O usuário detalhou o requisito: não é "1 chave por página", é **RBAC de
escopo em 2 camadas aplicado no dado** (1ª camada = universo
OPEX Sustaining / CAPEX Sustaining / CAPEX Obras; 2ª camada = quais
Gerências / Projetos dentro do universo). Modelo completo, exemplos e
perguntas em aberto em **`docs/08-rbac-escopo-por-universo.md`** (DRAFT).
Vira pré-requisito das Etapas 3–6. O texto abaixo (opção A/B/C) fica só
como registro do que foi descartado.

<!-- registro histórico -->
**(descartado) recomendação anterior: opção A**

Hoje cada página tem `chave` própria em `app.permissao_pagina` +
`can_acessar_pagina` + `registrar_visualizacao_pagina`.
`can_acessar_pagina` libera por padrão quem **não tem linha** pra aquela
página (`permissoes.get(pagina, True)`) — a negação fina é um mecanismo de
exceção por usuário/página, não a regra. `st.segmented_control` (D2) **não
tem permissão por opção**. Já colapsamos chaves assim antes (fusão
`visao_opex` + `capex_manutencao` → `opex_capex_manutencao`).

- **A) 1 chave por página-jornada (recomendado).** `manutencao_resumo`,
  `manutencao_analise_financeira`, `evidencias_sap`, `obras_resumo` (+
  `pce_especialista`, `gestao_dados`, `administracao` inalteradas).
  Alinhado ao doc, que só exige validação **na página e na consulta** —
  e a autorização substantiva (escopo de Gerência, `can_ver_gerencia`,
  export/justificativa) é **por linha de dado**, não por página, e fica
  100% intocada. Salvaguarda: mapa de migração — linha `permitido=false`
  numa das sub-páginas antigas passa a **negar a página-jornada inteira**
  (conservador); o Editor de Permissões da Administração mostra a chave
  nova. Se um dia precisar de controle por opção do `segmented_control`,
  é barato adicionar depois (basta filtrar a lista de `options` por
  `can_acessar_pagina(subchave)`) — a escolha do D2 deixa isso fácil.
- **B) Guarda por opção.** Cada opção do `segmented_control` revalida a
  própria chave e some da lista se negada. Mantém a granularidade atual,
  mas espalha lógica de permissão rara por toda página consolidada.
- **C) Híbrido.** A + esconder opções só onde já existe deny fino
  cadastrado. Pior relação complexidade/benefício.

### D2 — Mecanismo de aba x peso — **DECIDIDO (2026-09-01): `st.segmented_control` + render só do painel aberto**

`st.tabs` nativo executa **todos** os painéis a cada rerun completo (é
show/hide em CSS). O usuário priorizou "aplicação leve" e escolheu o
`st.segmented_control` (barra de opções no lugar da aba nativa): só o
painel selecionado consulta o banco. Cada painel continua sendo um
`@st.fragment` com conexão DuckDB própria — o `segmented_control` fica no
escopo da página, e um `if escolha == "...": _frag_x()` renderiza só o
painel ativo. Nas telas com sub-abas próprias hoje (`projecao_opex.py`,
PM/PD/PP) isso também evita `st.tabs` dentro de `st.tabs`.

---

## 4. Etapas

| Etapa | Escopo | Risco | SemVer | Depende de |
|---|---|---|---|---|
| **1** ✅ | Plano + memória + `docs/07`; CSS das tags de filtro → dourado sólido + texto branco (`branding.py`) | baixo | PATCH (6.5.2) | — |
| **2** ✅ | Grupo `GESTÃO` = `Dados e Qualidade` (era "Upload de Dados") + `Administração` (era "Gestão e Auditoria"). Só rótulo/menu; chaves `upload`/`administracao` e lógica intactas. Mover histórico/rollback de upload pra dentro de "Dados e Qualidade" ficou para etapa própria (é decisão de RBAC — quem restaura) | baixo | MINOR (6.6.0) | — |
| **3** | Página **Resumo** (Manutenção) = `segmented_control` Visão Executiva / Desvios e Causas / Projeção, cada painel `@st.fragment` com conexão própria. Extrair `pagina_painel` para `render_*` | médio | MAJOR (7.0.0) | D1 |
| **4** | Página **Resumo** (Obras) = Visão Executiva / Desvios e Evolução | médio | MINOR | Etapa 3 |
| **5** | Página **Análise Financeira** = Pacotes / Contas e Centros de Custo / CAPEX Sustaining (toggle Conta\|CC interno) | médio-alto | MINOR | Etapa 3 |
| **6** | Renomear `Nível 6` → **Evidências SAP**; links contextuais Pacote/Conta/CC → Evidências (preservando recorte) | médio | MINOR | Etapa 5 |
| **7** | **Pendências e Justificativas** (4 abas) — fase própria, precisa de schema novo + validação MRS. Ver `docs/03` | alto | MAJOR | negócio |

Ordem pode ser revista. D2 decidido (`segmented_control`). Etapas 3–6 só
começam depois de D1 confirmado. Etapa 2 é independente e pode ir antes.

---

## 5. Padrão de código para as abas (Etapas 3+) — `segmented_control` + fragment

```python
_ABAS_MANUT_RESUMO = ["Visão Executiva", "Desvios e Causas", "Projeção"]

def pagina_manutencao_resumo() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada(); return
    con = _conectar()                      # conexão curta só pra checagem
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada(); return
    finally:
        con.close()

    renderizar_badge_filtros_ativos()
    escolha = st.segmented_control(
        "Seção", _ABAS_MANUT_RESUMO, default=_ABAS_MANUT_RESUMO[0],
        key="w_seg_manut_resumo", label_visibility="collapsed",
    ) or _ABAS_MANUT_RESUMO[0]

    if escolha == "Visão Executiva":
        _frag_resumo_visao_executiva()
    elif escolha == "Desvios e Causas":
        _frag_resumo_desvios_causas()
    else:
        _frag_resumo_projecao()


@st.fragment
def _frag_resumo_projecao() -> None:
    con = _conectar()
    try:
        render_projecao_opex(con, ano_fiscal=CFG["ano_fiscal_orcamento"])
    finally:
        con.close()
```

Regras:
- **só o painel escolhido roda** — as consultas dos outros nem disparam;
- **um `@st.fragment` por painel**, conexão DuckDB aberta e fechada dentro
  do próprio fragmento (nunca capturar `con` do escopo externo);
- nenhuma figura Plotly é tocada — as `render_*` existentes são chamadas
  como estão hoje;
- o `segmented_control` é estilizado só por CSS já existente/novo em
  `branding.py` para parecer uma faixa de abas; sem novo tipo de gráfico.

---

## 6. O que NÃO muda

Motor financeiro (`src/engine/`), loaders (`src/ingestion/`), star schema
(`src/model/build_star_schema.py`), fórmulas de Delta / Não Justificado /
waterfall, `explicacoes.csv`, taxonomia de causa, paleta e temas de gráfico,
Login. A migração é 100% camada de apresentação (`app.py` + `src/dashboard/`
+ `src/branding.py`).
