# 08 — RBAC de escopo por universo (DRAFT — aguardando validação do usuário)

Pedido do usuário em 2026-09-01, durante o planejamento da Visão Ideal
(`docs/07`). O bloqueio de visualização tem **duas camadas** e é aplicado
**no dado**, não só na navegação.

> **Status:** proposta para revisão. Nada codificado. Confirmar o modelo e
> responder as perguntas da seção 7 antes de virar etapa.

---

## 1. As duas camadas

### 1ª camada — Universo (o QUE a pessoa pode ver)

Três universos financeiros independentes:

| Universo | Fonte | Recorte |
|---|---|---|
| `opex_sustaining` | `fact_orcamento` / `fact_realizado` | `classificacao_contabil = 'OPEX'` (Manutenção Corrente + Pessoal + Despesas Gerais) |
| `capex_sustaining` | `fact_orcamento` / `fact_realizado` | `classificacao_contabil = 'CAPEX'` (Malha / Infra) |
| `capex_obras` | `fact_cji4_capex_obras` / `fact_cji3_capex_obras` / `fact_pce_*` | tabelas próprias (Projetos e Obras) |

`opex_sustaining` e `capex_sustaining` são a **mesma tabela**, separados pelo
campo `classificacao_contabil`. `capex_obras` é outro conjunto de tabelas.

### 2ª camada — Escopo dentro do universo (QUAIS Gerências / Projetos)

Para cada `(usuário, universo)` liberado, um ou mais recortes:

| Nível | Alvo | Vale para |
|---|---|---|
| `gg` | — (universo inteiro, todas as Gerências) | todos os universos |
| `gerencia` | `gerencia_id` (Sustaining) ou `gerencia_obras` (Obras) | todos |
| `projeto` | `e_pep_projeto` | só `capex_obras` |
| `elemento_pep` | `elemento_pep` | só `capex_obras` |

Regra: 1+ linha `gg` para o par → vê o universo inteiro. Senão, vê só a
**união** dos alvos das linhas `gerencia` / `projeto` / `elemento_pep`.
Nenhuma linha para o par → **não vê o universo** (fail closed).

### Papéis

- `admin`, `gg` → veem tudo, todos os universos, escopo GG. **Bypass total**,
  nunca dependem de grant.
- `gerente`, `especialista_analista` → veem só o que tiver grant.

---

## 2. Exemplos do usuário mapeados

| Pessoa | Grant(s) |
|---|---|
| Analista X — só Gerência SP | `(opex_sustaining, gerencia, GER MALHA (SP))` + `(capex_sustaining, gerencia, GER MALHA (SP))` |
| Analista Y — OPEX de toda a GG | `(opex_sustaining, gg)` |
| Analista W — só CAPEX Sustaining de uma Gerência | `(capex_sustaining, gerencia, <X>)` |
| Analista Z — OPEX + CAPEX Sustaining de toda a GG | `(opex_sustaining, gg)` + `(capex_sustaining, gg)` |
| Analista de Obras — uma Gerência de Obras | `(capex_obras, gerencia, <Gerência de Obras>)` |
| Analista de Obras — projetos específicos | `(capex_obras, projeto, <e_pep_projeto>)` (1+ linhas) |
| Analista "visão total de uma região" | grant de `gerencia` em cada universo que ele deve ver (os 3, se for o caso) |
| Analista "visão total da GG" | `(opex_sustaining, gg)` + `(capex_sustaining, gg)` + `(capex_obras, gg)` |

---

## 3. Modelo de dados

Reusar `app.escopo_acesso` (já existe) + coluna `universo` + tipo `gg`:

```sql
alter table app.escopo_acesso
    add column if not exists universo text
    check (universo in ('opex_sustaining', 'capex_sustaining', 'capex_obras'));

alter table app.escopo_acesso drop constraint if exists escopo_acesso_tipo_check;
alter table app.escopo_acesso add constraint escopo_acesso_tipo_check check (tipo in (
    'gg', 'gerencia', 'gerencia_obras', 'projeto', 'elemento_pep',
    'pep_filho', 'coordenacao', 'centro_custo', 'pacote'
));

-- unicidade passa a considerar o universo
alter table app.escopo_acesso drop constraint if exists escopo_acesso_usuario_id_tipo_valor_key;
create unique index if not exists escopo_acesso_uk
    on app.escopo_acesso (usuario_id, coalesce(universo, ''), tipo, valor);
```

- linha de universo inteiro: `tipo = 'gg'`, `valor = '(todas)'`, `universo` preenchido.
- linhas antigas (`universo IS NULL`) = legado nunca aplicado; migração cria linhas novas com `universo` setado.

**Migração dos usuários atuais** (seção 7, pergunta 1): para cada
`gerente` / `especialista_analista` com `usuario.gerencia_id` preenchido,
criar `(opex_sustaining, gerencia, gerencia_id)` + `(capex_sustaining,
gerencia, gerencia_id)`. Quem tem `gerencia_id` nulo precisa de grant
explícito do admin ou perde acesso (fail closed).

---

## 4. Aplicação (enforcement)

### Cláusula de escopo sempre-ligada

Espelho de como `gg_escopo_dinfra` já trava tudo em GGG_0054. Nova função
em `filtros.py`:

```python
def clausula_escopo(universo: str, colunas: dict[str, str]) -> tuple[str, list]:
    # -> ("", [])                         se nível 'gg' (vê tudo)
    # -> (" AND gerencia_id IN (?, ?)", [...])   se recorte por Gerência
    # -> (" AND 1=0", [])                 se nenhum grant (bloqueia)
```

Toda consulta do universo cola isso depois de `WHERE 1=1`, junto de
`clausula_periodo` / `clausula_where` — mesmo mecanismo, mesma ordem.
`capex_obras` usa `e_pep_projeto` / `elemento_pep` no lugar de `gerencia_id`.

### Navegação (1ª camada)

`app.py` monta o menu consultando `universos_permitidos(usuario)`:

- sem nenhum universo Sustaining → grupo **PLANO DE MANUTENÇÃO** some;
- só `opex_sustaining` → em **Análise Financeira**, a opção "CAPEX
  Sustaining" some; Resumo / Pacotes / Contas mostram só OPEX;
- só `capex_sustaining` → espelho (só a opção "CAPEX Sustaining");
- sem `capex_obras` → grupo **CAPEX PLANO DE OBRAS** some;
- Especialistas (`pce_especialista`): ver pergunta 3.

### "Recorte não é total"

Quando o escopo é um subconjunto de Gerências, os cards / waterfall /
rankings mostram só esse subconjunto e ganham faixa explícita
("Recorte: GER MALHA (SP) — não é o total da GG"), alinhado ao princípio
"uma fonte de verdade / não confundir recorte com total" do `docs/07`.

---

## 5. Tela de delegação (Administração)

Nova seção em `src/dashboard/administracao.py`: por usuário, uma grade —
uma linha por universo, toggle "vê este universo"; se sim, escolha
"GG inteira" | "Gerências específicas" → multiselect (opções do
warehouse). Para `capex_obras`, multiselect adicional de Projeto /
Elemento PEP. Escreve linhas em `app.escopo_acesso`. Só `admin` (e talvez
`gg`) delega.

---

## 6. Interação com o que já existe

- `app.permissao_pagina` (allow/deny por página) — **mantida**, ortogonal.
  Esconde página-jornada específica (ex.: "Evidências SAP", "Pendências")
  de alguém, independente de universo/escopo.
- `can_ver_gerencia`, `permissao_exportacao`, `permissao_justificativa_*` —
  mantidas. O escopo por universo é uma camada **a mais**, não substitui.
- `gg_escopo_dinfra` (trava tudo em GGG_0054) — continua, é o teto.

---

## 7. Perguntas a confirmar (antes de virar etapa)

1. **Migração fail-closed.** Hoje `gerente` / `especialista_analista` sem
   linha de escopo = irrestrito (nada aplicado). Novo: sem grant = não vê.
   Migro todos a partir de `usuario.gerencia_id` (OPEX + CAPEX Sustaining
   da própria Gerência). Quem tem `gerencia_id` nulo perde acesso até o
   admin conceder. OK? Tem a lista de usuários atuais pra eu semear certo?
2. **Papel `gg`** vê tudo sempre (igual admin), ou também passa por grant
   de universo?
3. **CAPEX Obras — Especialistas** (`pce_especialista`): entra no grant
   `capex_obras` (mesma porta que o resto de Obras), ou tem chave própria
   (análise densa, só alguns analistas)?
4. **Níveis de escopo de `capex_obras`**: Gerência de Obras + Projeto +
   Elemento PEP bastam? Precisa escopar por Classe de Custo / rubrica?
5. **Cross-universo**: os grants são independentes por universo (o admin
   concede a Gerência em cada universo separadamente), sem ligação
   automática "Gerência Sustaining ↔ Gerência de Obras". Confere?
6. **Totais no recorte**: analista escopado numa Gerência vê **só** os
   números daquela Gerência em tudo (cards, waterfall, ranking) — não vê
   o total da GG nem como contexto. Confere?
7. **Pendências e Justificativas + Evidências SAP** herdam universo +
   escopo (só vê pendência / evidência das Gerências que pode ver).
   Confere?
8. **Várias Gerências**: um analista pode receber N Gerências específicas
   (não só 1) — união. Confere?
9. Finura do Sustaining: Gerência é o nível mais fino nesta fase?
   (`coordenacao` / `centro_custo` / `pacote` continuam no schema, sem uso.)

---

## 8. Sequenciamento sugerido

Esta camada é **pré-requisito** das Etapas 3–6 do `docs/07` (as páginas
consolidadas precisam consultar a 1ª camada pra navegação e a 2ª pro
filtro sempre-ligado). Proposta:

- **Fase RBAC-A** — schema (`universo` em `escopo_acesso`) + helpers em
  `permissions.py` + `clausula_escopo` em `filtros.py`, aplicada às
  **páginas atuais** (sem mexer na navegação ainda). Validável
  numericamente: "Analista SP vê R$X" e "R$X = soma das linhas SP".
- **Fase RBAC-B** — tela de delegação na Administração.
- **Etapas 3–6** (`docs/07`) — consolidação, já consumindo o RBAC.

A **Etapa 2** do `docs/07` (grupo GESTÃO) é independente e pode ir antes
de tudo isso.
