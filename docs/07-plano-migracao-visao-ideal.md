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
| `visao_manutencao` | Manutenção › Análise Financeira › aba **Pacotes** (sub-abas PM/PD/PP desde v11.0.0) | + "Orçado por Conta" (veio do lado OPEX Sustaining) |
| `opex_capex_manutencao` (lado CAPEX) | Análise Financeira › aba **CAPEX Sustaining** | lado OPEX **resolvido em v11.0.0**: distribuído nas sub-abas PM/PD/PP de "Pacotes"; a aba virou só CAPEX, fatiada por Elemento PEP |
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
| **3** ✅ | Página **Resumo** (Manutenção) = `segmented_control` Visão Executiva / Desvios e Causas / Projeção, cada painel `@st.fragment` com conexão própria. `pagina_resumo_executivo`/`pagina_painel`/`pagina_projecao_opex` → `pagina_manutencao_resumo` + 3 fragments. Chave `manutencao_resumo`; `_JORNADA_HERDA_DENY` pra herdar deny das 3 antigas. Corrigido de latente: `is_admin()` agora vem antes da consulta ao Neon em `universos_permitidos`/`escopo_universo`/`escopo_alvos_por_tipo`. v8.0.0 | médio | MAJOR (8.0.0) | D1 |
| **4** ✅ | Página **Resumo** (Obras) = `segmented_control` Visão Executiva / Desvios e Evolução. `pagina_capex_resumo`/`pagina_capex_painel` → `pagina_obras_resumo` + 2 fragments. Chave `obras_resumo`. Corrigido bug latente `KeyError projecao_ritmo_acumulada` em `figura_tendencia` (docs/04 lição 25). v8.1.0 | médio | MINOR (8.1.0) | Etapa 3 |
| **5** ✅ | Página **Análise Financeira** = `segmented_control` Pacotes / Contas e Centros de Custo / CAPEX Sustaining (toggle Conta\|CC interno; toggle OPEX\|CAPEX interno na 3ª). Funde `visao_manutencao`+`contas`+`centro_custo`+`opex_capex_manutencao` → `pagina_manutencao_analise_financeira` + 3 fragments. Chave `manutencao_analise_financeira`. Seções filtradas por universo. Painel renomeado **"OPEX / CAPEX Sustaining"** (v8.3.1, decisão do usuário 2026-09-06) — mantém os dois lados via toggle interno. "Plano de Manutenção" → 3 itens. v8.2.0 | médio-alto | MINOR (8.2.0) | Etapa 3 |
| **5b** ✅ | **Reestruturação da "Análise Financeira"** (pedido do usuário 2026-09-08). "Pacotes" ganhou `segmented_control` interno **PM \| PD \| PP** (`render_visao_manutencao(familia=...)` generalizada) + "Orçado por Conta" (macro→micro). A aba "OPEX / CAPEX Sustaining" virou **"CAPEX Sustaining"**: o lado OPEX foi distribuído nas 3 sub-abas; o CAPEX passou a ser fatiado por **Elemento PEP** (tudo PM03), nomeado pelo novo `dim_pep_sustaining` (ingest de `Catalago CAPEX Sustaining.xlsx`). **Sem Realizado/Projeção de CAPEX Sustaining** — não existe a fonte (SAP não fatia por classificação contábil), inventar violaria a Regra de Ouro. Fix latente: `settings.yaml::consulta_contas` apontava pra arquivo renomeado (`Consulta de Contas.xlsx` → `Orçado x Realizado.xlsx`) — sem o fix o rebuild zerava o OPEX. **Achado não corrigido** (mantido "excelente" a pedido): a sub-aba **PM** soma OPEX+CAPEX no card/gráficos (Orçado R$83,97 MM, Aderência ~23%); PD/PP são OPEX puro (não têm CAPEX). **Deploy: reprocessar o warehouse.** v11.0.0 | alto | MAJOR (11.0.0) | Etapa 5 |
| **6a** ✅ | Renomear `Nível 6` → **"Evidências SAP"** (Manutenção) e → **"Rastreabilidade CJI3"** (Obras). Só label; chaves `rastreabilidade_sap`/`capex_rastreabilidade` mantidas. v8.2.1 | baixo | PATCH (8.2.1) | Etapa 5 |
| **6b** ✅ | Links contextuais Análise Financeira ⇄ Evidências SAP. Árvore N4/N5 é HTML estático → link a nível de painel (`st.page_link`), não por linha. Recorte preservado pelos filtros globais da sidebar (não injeta estado). `_link_para` + `_PG_EVIDENCIAS_SAP`/`_PG_ANALISE_FIN`. v8.3.0 | baixo | MINOR (8.3.0) | Etapa 6a |
| **7** | **Pendências e Justificativas** (4 abas) — fase própria. Desenho consolidado em **`docs/09`** (Sustaining: Conta × Gerência, dono = ponto focal da Gerência; Obras: Projeto/PEP). Sub-fases **7a** (schema + motor da Fila, sem UI), **7b** (página + form Micro), **7c** (Macro + hover + consolidação mensal), **7d** (import do legado). Validações de negócio com a MRS: **respondidas** (docs/09 §6) — 7a desbloqueada. | alto | MAJOR | negócio |
| **7a.1** ✅ | Schema + config, sem UI. `config/schema_postgres.sql`: bloco idempotente em `fact_explicacao_log` (`universo`/`gerencia_id`/`e_pep_projeto`/`elemento_pep`/`escopo_temporal`, `pacote_id` nullable, `chk_nivel_campos` reescrito p/ 3 universos, índice `idx_explicacao_gerencia_escopo`). `config/settings.yaml`: `threshold_justificativa` (Micro sem threshold). docs/09 §3/§4.2 finalizados. **Deploy: rodar `schema_postgres.sql` no Neon.** v9.0.0 | médio | MAJOR (9.0.0) | negócio |
| **7a.2** ✅ | Motor da Fila de Pendências — `src/engine/fila_pendencias.py` (`calcular_fila_pendencias`) + `carregar_justificativas_vigentes` (Neon, falha-soft). Cruza Delta (DuckDB) × justificativas vigentes por universo/`escopo_temporal`, recorte por escopo injetado. Micro mensal+acumulado sem threshold, Macro só acum ≥ threshold, Obras só acum \|Δ\| ≥ threshold. `tests/fase7a_fila_pendencias_check.py` (8 checagens vs SQL direto). Hoje: OPEX 654 pendências / CAPEX Sust. 0 (sem Realizado) / Obras 35. **Ponto aberto**: Obras usa \|Δ\| → inclui underspend (25/35) — confirmar com a MRS. v9.1.0 | médio | MINOR (9.1.0) | 7a.1 |
| **7b** | Página "Pendências e Justificativas" (`segmented_control`: Fila \| Em elaboração \| Consolidadas \| Histórico) + formulário Micro (Conta/Projeto, mês/acumulado) gravando em `fact_explicacao_log`. Recorte por escopo. Depende de `permissao_justificativa_micro`. | alto | MAJOR | 7a.2 |

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
