# 09 — Etapa 7 da Visão Ideal: Pendências e Justificativas

**Status: proposta para revisão. NÃO implementado.** Consolida o desenho
fechado de `docs/03` + as decisões de negócio de 2026-09-06 + o
mapeamento pro estado atual do código (RBAC de escopo do `docs/08`,
schema já criado). Não repete `docs/03` — leia os dois juntos.

Alvo: a 3ª página do grupo "PLANO DE MANUTENÇÃO" da Visão Ideal
(`FIN360_VISAO_IDEAL.md` §3.3) — **"Pendências e Justificativas"**, abas
Fila de Pendências | Em elaboração | Consolidadas | Histórico.

---

## 1. O que já existe (não é greenfield)

| Peça | Onde | Estado |
|---|---|---|
| Tabela `app.fact_explicacao_log` (append-only, versionada, `nivel` macro/micro, `categoria`, `valor_explicado`, autor, `status_ciclo` rascunho/consolidado) | `config/schema_postgres.sql` | **criada**, sem UI e sem escrita pelo app |
| `app.delegacao_justificativa` (Gerente → Especialista, escopo Pacote/Conta/CC) | idem | **criada**, sem UI |
| Flags `usuario.permissao_justificativa_macro` / `_micro` + `usuario.gerencia_id` | idem | **existem**, editáveis na Administração |
| Motor `calcular_explicacao` (Delta − soma causas vigentes = Não Justificado) | `src/engine/explanation_engine.py` | funciona, hoje só chamado com `dims=["pacote_id"]` (Nível 3) |
| RBAC de escopo por universo + Gerência | `docs/08` (v7.0–8.3) | **pronto** — dá o "qual Gerência este usuário responde" |
| CSV de apoio `data/staging/explicacoes.csv` | — | preenchido à mão hoje; vira "versão 1, origem=importacao_legado" na migração |

Ou seja: falta a **UI** (Fila + formulários + histórico), o **motor da
Fila de Pendências** (query que reabre sozinha), e a extensão de schema
pro universo de **Obras**.

---

## 2. Decisões de negócio de 2026-09-06 (novas, sobre `docs/03`)

`docs/03` desenhou só OPEX. O usuário agora trouxe:

### 2.1 CAPEX / OPEX Sustaining — coleta por **Conta, por Gerência**

- A justificativa **no nível de Conta** é agrupada **por Gerência**.
- Responsável = **o ponto focal de cada Gerência** — não uma Analista
  central. Cada Gerência cuida das próprias Contas.
- Vale para **OPEX Sustaining e CAPEX Sustaining** (Malha) — os dois
  universos, mesmo modelo Conta × Gerência.
- No código: "ponto focal da Gerência X" = usuário com grant de escopo
  `(universo, gerencia, X)` (docs/08) **e** `permissao_justificativa_micro`.
  A Fila de Pendências desse usuário mostra só as Contas das Gerências do
  grant dele — o RBAC de escopo já faz esse recorte.
- O **Macro (Pacote)**, quando existir, continua como em `docs/03` §2.3
  (consumo GG/PMO, soma o Micro + resíduo). Mas a **entrada primária**
  agora é o Micro (Conta), descentralizada por Gerência.

### 2.2 CAPEX Plano de Obras — coleta por **Projeto / Elemento PEP**

- "Concentrar inicialmente a justificativa por **Projeto / Elemento PEP**"
  — a unidade de coleta é o Projeto (`e_pep_projeto`), com detalhe
  opcional por `elemento_pep`.
- Responsável = ponto focal / especialista do Projeto (usuário com grant
  `(capex_obras, gerencia_obras | projeto, …)`).
- **Não** desce a Conta/Classe de Custo nesta primeira fase.
- Universo à parte: fonte CJI4 (Orçado) x CJI3 (Realizado), não
  `fact_orcamento`/`fact_realizado`.

### 2.3 Resumo da matriz de coleta

| Universo | Unidade de coleta (fase 1) | Chave no schema | Responsável | Threshold |
|---|---|---|---|---|
| OPEX Sustaining | **Conta** (por Gerência) | `conta_interna_id` + `gerencia_id` | ponto focal da Gerência | 100% (Micro sem threshold, `docs/03` §3.3) |
| CAPEX Sustaining | **Conta** (por Gerência) | `conta_interna_id` + `gerencia_id` | ponto focal da Gerência | **[A CONFIRMAR]** — provável 100% também |
| CAPEX Obras | **Projeto / Elemento PEP** | `e_pep_projeto` (+ `elemento_pep`) | ponto focal do Projeto | **[A CONFIRMAR]** — `docs/03` cita R$500 mil |

---

## 3. Extensão de schema necessária

`app.fact_explicacao_log` hoje é `pacote_id`-cêntrica (`pacote_id NOT
NULL`) + `conta_interna_id`/`centro_custo_id` pro Micro. Para o modelo
acima:

1. **`gerencia_id`** (texto, nullable) — a Gerência responsável pela linha
   Micro de Sustaining. Redundante com a Conta mas explícito pra filtrar a
   Fila por ponto focal sem join.
2. **Universo de Obras**: `pacote_id` deixa de ser obrigatório; novas
   colunas `e_pep_projeto` (texto, nullable) e `elemento_pep` (texto,
   nullable). O `CHECK` de "nível macro/micro" ganha um 3º caso:
   `universo = 'capex_obras'` exige `e_pep_projeto`, proíbe `pacote_id`.
3. **`universo`** (texto: `opex_sustaining` / `capex_sustaining` /
   `capex_obras`) — mesma taxonomia do `docs/08`, pra a Fila e o motor
   saberem em qual conjunto de fatos calcular o Delta.
4. **`escopo_temporal`** (texto: `mensal` / `acumulado`) — decisão do
   usuário 2026-09-06. Onde cada um se aplica:

   | Nível / universo | `mensal` | `acumulado` |
   |---|---|---|
   | **Sustaining Micro** (Conta × Gerência) | sim | sim |
   | **Sustaining Macro** (Pacote) | — | **só acumulado** |
   | **Obras** (Projeto / Elemento PEP) | — | **só acumulado** |

   `(ano, mes)` numa linha `mensal` = a competência do estouro; numa linha
   `acumulado` = o mês de fechamento "até o qual" ela vale (a última
   `versao` carrega o mês mais recente confirmado).
5. `status_ciclo` (já existe: `rascunho` / `consolidado`) alimenta as abas
   "Em elaboração" (rascunho) e "Consolidadas".

**Justificativa acumulada é "carregada" ao longo do tempo** (regra de
negócio do usuário): a partir do 1º mês em que o acumulado estoura, o
gestor já sabe e já acionou a hierarquia (compensar com outra conta/
pacote, pedir forecast). Logo, a justificativa acumulada de uma
(Conta, ano) é **um único `explicacao_id`** que ganha uma `versao` nova a
cada fechamento em que o acumulado continua estourado — não é recriada do
zero todo mês. A narrativa evolui ("desde março estamos +X; ação: …");
quando o acumulado volta a ≤ 0 (compensado), a pendência acumulada some e
a última versão vira histórico.

Migração idempotente, mesmo padrão dos ALTERs de `docs/08`.

---

## 4. Motor da Fila de Pendências (query, não tabela)

Recalculada a cada carga (`build_star_schema`), cruzando o Delta atual x
`fact_explicacao_log` (`vigente = true`), **por universo** e **por escopo
temporal** (mês e acumulado — seção 3, item 4).

### 4.1 Sem threshold de gatilho (decisão do usuário 2026-09-06)

**Qualquer estouro precisa de justificativa** — não há valor mínimo no
nível Micro. Um item entra na Fila quando, no mês fechado:

- foi **realizado sem orçamento** (`orcado = 0` e `realizado != 0`), **ou**
- **realizado > orçado no mês** (`delta_mes > 0`), **ou**
- **realizado > orçado no acumulado** (`delta_acum > 0`).

(O threshold configurável de `docs/03` §3.3 fica só para o **Macro
(Pacote)** — a leitura executiva GG/PMO, onde faz sentido filtrar o
miúdo. O Micro, por Conta/Projeto, é 100%.)

### 4.2 O que gera pendência, por nível

- **Sustaining Micro** (Conta × Gerência) — **duas** pendências possíveis:
  - **mensal**: `delta_mes(competência) > 0` e sem linha `micro` `vigente`
    `escopo_temporal='mensal'` daquela competência cobrindo o Delta do mês.
  - **acumulada**: `delta_acum(até a competência) > 0` e sem linha `micro`
    `vigente` `escopo_temporal='acumulado'` cobrindo o Delta acumulado.
    Essa "carrega" (seção 3): já existindo versão de meses anteriores, a
    Fila mostra "acumulado ainda estourado — revisar" em vez de "sem
    justificativa".
  - 4 casos possíveis (mês sim/não × acum sim/não) → 0, 1 ou 2 itens.
- **Sustaining Macro** (Pacote) — **só acumulada**: `delta_acum_pacote > 0`
  **e** `abs(delta_acum_pacote) >= threshold_macro` (config, `docs/09` §6
  resposta 1) e sem linha `macro` `vigente` cobrindo. O Macro soma o Micro
  já lançado + resíduo (regra de `docs/03` §2.3).
- **Obras** (Projeto / Elemento PEP) — **só acumulada**:
  `abs(delta_acum_projeto) >= threshold_obras` (config) e sem
  justificativa `vigente` do Projeto cobrindo.

`delta_mes` e `delta_acum` vêm da mesma fonte de cada universo
(`fact_orcamento`/`fact_realizado` filtrado por `classificacao_contabil`
+ `gerencia_id` + Conta para Sustaining; `fact_cji4/cji3_capex_obras` por
`e_pep_projeto` para Obras).

### 4.3-bis Realidade do dado hoje (achado 2026-09-06, antes de codar o motor)

Conferido direto no warehouse (`data/warehouse/painel.duckdb`):

| Universo | Orçado | Realizado | Consequência no motor |
|---|---|---|---|
| **OPEX Sustaining** | `fact_orcamento` `classificacao_contabil='OPEX'` — R$48,3 MM | `fact_realizado` (100% das linhas são `OPEX`, R$23,9 MM) — `gerencia_id` 100% preenchido | **Funciona.** Delta por Conta × Gerência fecha nas 2 pernas. |
| **CAPEX Sustaining** | `fact_orcamento` `classificacao_contabil='CAPEX'` — R$43,1 MM | **não existe** em `fact_realizado` (0 linha CAPEX) | O motor roda mas **nunca gera pendência** (sem realizado, todo Delta é economia). Quando a MRS carregar o Realizado CAPEX Malha, acende sozinho. Não é bug — é dado ausente (mesma pendência da Alice/PMO citada em `visao_classificacao.py`). |
| **Obras** | `fact_cji4_capex_obras` por `e_pep_projeto` | `fact_cji3_capex_obras` por `e_pep_projeto` | **Funciona** (as 2 tabelas têm as mesmas colunas). |

6 Contas aparecem com as duas classificações no Orçado; no Realizado elas
caem todas em `OPEX`. Efeito irrelevante hoje (não há Realizado CAPEX pra
disputar), mas registrar: quando houver, a atribuição OPEX/CAPEX de uma
Conta mista no Realizado não tem De-Para — vai pelo lado que o SAP mandou.

### 4.3 Regras herdadas de `docs/03` §3.4

**Só mês fechado** (competência < mês corrente); pendência **some
sozinha** quando a soma das justificativas vigentes cobre o Delta; **reabre
sozinha** quando nova carga muda o Delta. Sem "marcar como resolvido"
manual.

**Recorte por usuário**: a Fila que cada ponto focal vê já é filtrada
pelo grant de escopo dele (`clausula_escopo` / `clausula_escopo_obras` do
`docs/08`) — não precisa de lógica nova de "quem vê o quê".

---

## 5. UI proposta (página "Pendências e Justificativas")

`st.segmented_control`: **Fila de Pendências | Em elaboração |
Consolidadas | Histórico** (mesmo padrão das Etapas 3–5).

- **Fila de Pendências**: lista calculada (seção 4), recortada pelo escopo
  do usuário, ordenável por Delta / Gerência / Competência. Cada linha
  diz se é pendência **do mês** ou **acumulada** (coluna/badge). Botão
  "Justificar" abre o formulário certo (Conta ou Projeto; mês ou
  acumulado), condicionado a `permissao_justificativa_micro` / `_macro`.
- **Formulário** (`st.form`): escopo (mês da competência **ou** acumulado
  até M — pré-selecionado pela linha da Fila), Categoria (taxonomia
  fechada de `categorias_causa`; "Taxa Bom/Mix" só em CAPEX), Valor
  explicado (sinal validado contra o sinal do Delta correspondente),
  Descrição, Autor/Gerência (do usuário logado, não texto livre — o RBAC
  já identifica). Grava linha nova em `fact_explicacao_log`
  (`status_ciclo='rascunho'`), nunca UPDATE. No escopo `acumulado`, se já
  existe `explicacao_id` da (Conta, ano), o formulário abre com a última
  narrativa carregada e grava `versao+1`.
- **Em elaboração**: linhas `rascunho` do ciclo corrente do usuário.
- **Consolidadas**: linhas `consolidado` — enviadas ao fechamento mensal.
- **Histórico**: todas as versões (autor, data/hora, diff, motivo da
  edição), estilo Nível 6 do lado das causas.
- Sem gate de aprovação (`docs/03` §3.1/§6): a consolidação é ação do
  próprio ponto focal na data de corte; Coordenador/Gerente auditam, não
  bloqueiam.
- Hover de justificativa nos gráficos/cards que já existem: `docs/03` §5.1
  (fase posterior, não bloqueia a página).

---

## 6. O que ainda precisa de validação com a MRS (Alice / Jaque / Laís)

### Respostas do usuário — 2026-09-06

1. **Threshold** = o valor de R$ a partir do qual justificar vira
   **obrigatório** (abaixo dele, opcional). Ex.: threshold R$100 mil no
   Macro OPEX = Pacote com |Delta| < R$100 mil não gera pendência; ≥ R$100
   mil, sim. Fica **configurável** (não hard-coded). Valores por domínio
   **ainda a definir** com a MRS — o `docs/03` §3.3 propõe R$100 mil
   Macro OPEX / 100% Micro OPEX / R$500 mil CAPEX Obras como ponto de
   partida.
2. **Ponto focal — CONFIRMADO**: 1 por Gerência, **delegado pelo admin**
   na Gestão de Usuários (grant de escopo `(universo, gerencia, X)` +
   `permissao_justificativa_micro`). Não vem de tabela da MRS.
3. **Data de corte — CONFIRMADO**: **todo dia 01**, corte para o **mês
   anterior**. No dia 1º, a Fila de Pendências libera o mês que fechou; o
   ponto focal tem o mês corrente pra preencher/consolidar até o próximo
   dia 1º.
4. **Taxonomia — CONFIRMADO** (a lista do OPEX serve) + detalhamento
   oficial na seção 8. Ajustes vs. `settings.yaml` atual: "Ajuste
   Contábil" → **"Sistema / Ajuste Contábil"** (rótulo). "Taxa Bom / Mix"
   existe no **CAPEX Sustaining** — **conceito ainda não definido** pelo
   usuário (único ponto de taxonomia em aberto).
5. **Escrita concorrente / base exportável — DIREÇÃO DADA**: precisa de
   uma base de dados que **exporte no formato da planilha do flag** pra
   ir pra base oficial da companhia. → `fact_explicacao_log` (Neon) é a
   base operacional (INSERT append-only, sem contenção de lock — cada
   ponto focal grava as próprias linhas); uma view/materialização
   "achatada" (só `vigente=true`, colunas no layout do flag) + botão
   **"Exportar base de justificativas" (CSV/XLSX)**, reaproveitando
   `app.artefato_exportado` (cópia auditada, já existe). Ver seção 9.
6. **Import do legado — PENDENTE**: o usuário vai fornecer **um arquivo**
   depois pra indexar no controle (fonte de verdade do que já foi
   preenchido). Até lá, `fact_explicacao_log` nasce vazio.

### Refinamento de 2026-09-06 — estouro do mês x acumulado (RESPONDIDO)

- **Obras** → **só justificativa acumulada** (Projeto/Elemento PEP).
- **Macro (Pacote)** → **só acumulada**.
- **Compensação** → quando o acumulado volta a ≤ 0, a pendência acumulada
  some e a última `versao` vira histórico (não fica "resolvida" marcada).
- **`escopo_temporal`** (`mensal`/`acumulado`) → confirmado.

### Ainda bloqueia a implementação FINAL da Etapa 7

- Conceito de **"Taxa Bom / Mix"** (CAPEX Sustaining) — não impede a Fase
  7a (schema + motor): é só uma categoria de dropdown, o motor não
  precisa da definição. Impede o texto de ajuda do formulário (7b) e o
  analista saber quando usá-la.
- **Arquivo de legado** — Fase 7d.

**A Fase 7a (schema + motor da Fila, sem UI) está desbloqueada.**

---

## 7. Sequência de implementação sugerida (depois da validação)

- **7a — schema + motor da Fila (sem UI)**: ALTERs em
  `fact_explicacao_log` (`gerencia_id`, `universo`, `e_pep_projeto`,
  `elemento_pep`, `escopo_temporal`); função da Fila de Pendências por
  universo, recortada pelo escopo; teste numérico ("ponto focal de SP tem
  N pendências = N Contas de SP com Delta sem justificativa").
  - **7a.1 ✅ (v9.0.0)** — schema (`config/schema_postgres.sql`, idempotente)
    + `threshold_justificativa` no `settings.yaml`. **Rodar o SQL no Neon.**
  - **7a.2 ✅ (v9.1.0)** — `src/engine/fila_pendencias.py` +
    `tests/fase7a_fila_pendencias_check.py` (8 checagens vs SQL direto).
    Hoje: OPEX Sustaining 654 pendências (517 mensais / 134 acum. micro /
    3 Macro ≥ R$100 mil); CAPEX Sustaining 0 (sem Realizado, §4.3-bis);
    Obras 35 (|Δ acum| ≥ R$500 mil). **Em aberto**: Obras usa `abs(Δ)` →
    25 dos 35 são underspend; confirmar com a MRS se a Fila de Obras é só
    estouro (`Δ > 0`) ou variação nos 2 sentidos.
- **7b — página "Pendências e Justificativas"**: Fila + formulário Micro
  (Conta / Projeto) + Em elaboração + Consolidadas + Histórico. Grava no
  log. Recorte por escopo.
- **7c — Macro + hover + consolidação mensal**: input Macro (Pacote),
  botão "Consolidar" na data de corte, tooltips de justificativa nos
  gráficos/cards existentes.
- **7d — import do legado** (arquivo que o usuário vai fornecer) +
  aposentar o CSV solto.

---

## 8. Taxonomia oficial (detalhamento do usuário — 2026-09-06)

Definições confirmadas de cada classificação. As **causas** compõem o
waterfall (soma + Não Justificado = Delta); os **estágios de valor** são
colunas da leitura executiva (Orçado → … → Real Contabilizado).

### 8.1 Estágios de valor

| Estágio | Definição |
|---|---|
| **Orçado** | Base Zero até o mês. |
| **Forecast** | Orçado sem efeito preço (Replan). |
| **Real Físico** | Real Físico com todas as variações anteriores — soma do realizado em sistema + itens baixados após a virada do mês. |
| **Real não Contabilizado** | Diferença que ainda não entrou no Real Físico mas já contabilizada — baixas de ordens realizadas após o fechamento do mês / pendentes de baixa. |
| **Real Contabilizado** | Soma do Realizado no sistema. |

### 8.2 Causas (waterfall)

| Causa | Definição / exemplos |
|---|---|
| **Físico** | Realizado + pendências de entrada no sistema (chegada de materiais indiretos, entrada de NF em atraso, mobilização de equipes; GOEV — Brita prevista no plano mas não incluída no orçamento). |
| **Efeito Preço** | Efeito Preço Brita + Combustível (GOEV). |
| **Não Previsto** | Escopo não orçado, fora do baseline: hora improdutiva, pagamento de reajuste de contrato, hora extra a mais, atendimentos emergenciais, mobilização de equipe extra, ferramentas não previstas. |
| **Carry Over** | Pendências de A-1: reajustes do ano anterior, notas não pagas, pagamentos do ano anterior realizados no ano vigente, itens executados em 2025 com pagamento postergado para 2026, custos com retrabalho. |
| **Sistema / Ajuste Contábil** | Ajuste de componentização (Ordens do OPEX com efeito de economia no CAPEX → positivo no Real OPEX e negativo no Real CAPEX), ajustes contábeis, ajustes de taxa de importação. |
| **Taxa Bom / Mix** | Só CAPEX Sustaining. **Conceito ainda não definido pelo usuário** — não codificar até ter a regra. |
| **Não Justificado** | Sempre calculado (`Delta − soma das causas`), nunca digitado. |

> `settings.yaml::categorias_causa` hoje tem "Ajuste Contábil" e
> "Realizado Não Contabilizado". A partir daqui: renomear para "Sistema /
> Ajuste Contábil"; e confirmar se "Realizado Não Contabilizado" continua
> como **causa** ou vira **estágio de valor** ("Real não Contabilizado"
> em 8.1). Mexer em `categorias_causa` afeta a regressão
> `validacao_rdg_julho_check` — só com o "ok" do usuário.

---

## 9. Base de dados exportável (formato "planilha do flag")

Requisito do usuário: as justificativas precisam sair numa base no estilo
da planilha do flag para alimentar a base oficial da companhia.

- **Operacional**: `app.fact_explicacao_log` (Neon) — append-only, uma
  linha por versão, `vigente=true` = valendo. Escrita concorrente de
  vários pontos focais é INSERT independente (sem lock).
- **Camada de exportação**: uma consulta que "achata" o log vigente no
  layout do flag (1 linha por Conta/Projeto/mês com Categoria, Valor,
  Descrição, Autor, Gerência, competência, status do ciclo) + botão
  **"Exportar base de justificativas"** (CSV / XLSX) na página. Cada
  export grava cópia auditada em `app.artefato_exportado` (infra já
  existe) — quem exportou, quando, com que filtro, e o conteúdo exato
  pra re-baixar.
- **Reconciliação**: a exportação tem que bater com o waterfall exibido
  (mesma regra de ouro do projeto: exportação reconcilia com o total da
  tela).
