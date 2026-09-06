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
4. `status_ciclo` (já existe: `rascunho` / `consolidado`) alimenta as abas
   "Em elaboração" (rascunho) e "Consolidadas".

Migração idempotente, mesmo padrão dos ALTERs de `docs/08`.

---

## 4. Motor da Fila de Pendências (query, não tabela)

Recalculada a cada carga (`build_star_schema`), cruzando o Delta atual x
`fact_explicacao_log` (`vigente = true`), **por universo**:

- **Sustaining** (`opex_`/`capex_sustaining`): Conta com `delta_total != 0`
  no recorte de Gerência, sem linha `micro` vigente que cubra 100% do
  Delta. `delta_total` vem de `fact_orcamento`/`fact_realizado` filtrado
  por `classificacao_contabil` + `gerencia_id` + Conta (a mesma
  `calcular_delta` do Nível 4, hoje sem a chamada de causa).
- **Obras** (`capex_obras`): Projeto (`e_pep_projeto`) com
  `abs(delta_total) >= threshold` sem justificativa vigente cobrindo o
  Delta. `delta_total` vem de `fact_cji4/cji3_capex_obras`.

Regras de `docs/03` §3.4 mantidas: **só mês fechado**; pendência **some
sozinha** quando a soma cobre o Delta; **reabre sozinha** quando nova
carga muda o Delta. Sem "marcar como resolvido" manual.

**Recorte por usuário**: a Fila que cada ponto focal vê já é filtrada
pelo grant de escopo dele (`clausula_escopo` / `clausula_escopo_obras` do
`docs/08`) — não precisa de lógica nova de "quem vê o quê".

---

## 5. UI proposta (página "Pendências e Justificativas")

`st.segmented_control`: **Fila de Pendências | Em elaboração |
Consolidadas | Histórico** (mesmo padrão das Etapas 3–5).

- **Fila de Pendências**: lista calculada (seção 4), recortada pelo escopo
  do usuário, ordenável por Delta / Gerência / Competência. Cada item →
  botão "Justificar" que abre o formulário certo (Conta ou Projeto),
  condicionado a `permissao_justificativa_micro` / `_macro`.
- **Formulário** (`st.form`): Categoria (taxonomia fechada de
  `categorias_causa`; "Taxa Bom/Mix" só em CAPEX), Valor explicado (sinal
  validado contra o sinal do Delta), Descrição (obrigatória acima do
  threshold), Autor/Gerência (do usuário logado, não texto livre — o
  RBAC já identifica). Grava linha nova em `fact_explicacao_log`
  (`status_ciclo='rascunho'`), nunca UPDATE.
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

Nada aqui deve virar código antes de confirmar:

1. **Thresholds reais**: CAPEX Sustaining Micro (100%? outro?) e CAPEX
   Obras por Projeto (R$500 mil confirmado? por Projeto ou por Elemento
   PEP?). `docs/03` §4 diz "configuráveis, sujeitos a validação".
2. **"Ponto focal da Gerência"**: 1 pessoa por Gerência? Como é
   nomeado/mantido — pelo admin na Gestão de Usuários (grant de escopo +
   flag), ou vem de uma tabela da MRS?
3. **Data de corte do ciclo**: alinhada a qual data da RDG? Fixa no mês ou
   variável?
4. **Taxonomia de causa para CAPEX** (Sustaining e Obras): a lista de
   `categorias_causa` do OPEX serve? "Taxa Bom/Mix" entra? Há categoria
   específica de Obras (Rateios / Escalation / Contingência)?
5. **Escrita concorrente**: hoje o painel roda por sessão Streamlit
   Cloud; várias pessoas gravando ao mesmo tempo em `fact_explicacao_log`
   (Neon) — o Neon aguenta, mas confirmar se o fluxo real é "cada ponto
   focal na sua janela" ou simultâneo.
6. **Import do legado**: o `explicacoes.csv` atual (e/ou `SP - Flag.xlsx`)
   entra como "versão 1, origem=importacao_legado"? Qual é a fonte de
   verdade do que já foi preenchido?

---

## 7. Sequência de implementação sugerida (depois da validação)

- **7a — schema + motor da Fila (sem UI)**: ALTERs em
  `fact_explicacao_log` (`gerencia_id`, `universo`, `e_pep_projeto`,
  `elemento_pep`); função da Fila de Pendências por universo, recortada
  pelo escopo; teste numérico ("ponto focal de SP tem N pendências = N
  Contas de SP com Delta sem justificativa").
- **7b — página "Pendências e Justificativas"**: Fila + formulário Micro
  (Conta / Projeto) + Em elaboração + Consolidadas + Histórico. Grava no
  log. Recorte por escopo.
- **7c — Macro + hover + consolidação mensal**: input Macro (Pacote),
  botão "Consolidar" na data de corte, tooltips de justificativa nos
  gráficos/cards existentes.
- **7d — import do legado** + aposentar o CSV solto.
