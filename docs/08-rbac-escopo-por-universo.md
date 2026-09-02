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

## 7. Respostas do usuário (2026-09-02)

1. **Migração fail-closed — CONFIRMADO, sem migração automática agora.**
   Poucos usuários, ambiente em teste. Não semear a partir de
   `usuario.gerencia_id`. Construir o enforcement fail-closed + a tela de
   delegação; os usuários atuais ficam sem escopo (não veem nada nos
   universos escopados) até o admin conceder pela tela. SQL de inspeção
   dos usuários atuais entregue na conversa (seção 9).
2. **Totais no recorte — CONFIRMADO.** Analista de uma Gerência vê **só**
   os números dela em tudo — inclusive Projeção (só a projeção da própria
   Gerência). Quem tem escopo `gg` vê a projeção da GG inteira (Orçado,
   Realizado, Forecast, curva de Realizado médio etc.). O recorte vale pra
   toda métrica, sem "total da GG como contexto".
3. **CAPEX Obras — Especialistas — EM ABERTO.** Usuário quer entender a
   diferença antes de decidir. Ver seção 10 (execução CJI3/CJI4 x
   planejamento PCE) e a recomendação (chave de página própria em cima do
   grant `capex_obras`).
4. **Papel `gg` — NÃO é bypass.** Só `admin` é bypass total. `gg` também
   recebe escopo delegado pela Gestão de Usuários, como analista (o
   normal é conceder `(todos os universos, gg)` num clique). `can_ver_
   gerencia` deixa de tratar `gg` como "vê tudo" — passa a depender de
   grant.

### Refinamentos (respostas anteriores / assumidos, confirmar se divergir)

- **Níveis de `capex_obras`**: Gerência de Obras + Projeto + Elemento PEP.
  Sem escopo por Classe de Custo / rubrica.
- **Cross-universo**: grants independentes por universo; sem ligação
  automática Gerência Sustaining ↔ Gerência de Obras.
- **Pendências e Justificativas + Evidências SAP**: herdam universo +
  escopo (só vê o das Gerências que pode ver).
- **Várias Gerências**: N Gerências específicas por analista — união.
- **Finura do Sustaining**: Gerência é o nível mais fino nesta fase
  (`coordenacao` / `centro_custo` / `pacote` continuam no schema, sem uso).

---

## 8. Sequenciamento

Esta camada é **pré-requisito** das Etapas 3–6 do `docs/07`. Quebrada em
incrementos validáveis (a lição de `docs/06` pesa: aplicar escopo sem
validar contra o schema real de cada página arrisca mudar total /
reconciliação — então enforcement é página a página, com regressão a
cada uma):

- **RBAC-A.1 ✅ (2026-09-02, v7.0.0)** — schema + leitura + tela de
  delegação, **sem enforcement**. `universo` em `app.escopo_acesso` (+
  tipo `gg` + índice único novo); `permissions.py::universos_permitidos`
  e `escopo_universo(universo) -> (tem_acesso, tudo, alvos)` com cache
  1x/sessão e fail-closed; seção "Acesso por universo financeiro" na aba
  "Permissões e escopos" da Administração (`substituir_escopo_universo`,
  delete+insert atômico; checkbox da tela do Especialista grava
  `permissao_pagina['pce_especialista']`). `tests/test_rbac_escopo.py`
  (9 casos da lógica pura). **Migração `config/schema_postgres.sql` tem
  que rodar no Neon** antes de valer. Nada mudou no que as páginas do
  painel mostram.
- **RBAC-A.2 — `clausula_escopo` + enforcement, página a página.**
  Cada uma com AppTest numérico: "usuário escopado em SP vê R$X" e
  "R$X = soma SQL direta das linhas SP". Página que mostra OPEX **e**
  CAPEX aplica o escopo por seção (universo diferente por bloco).
  - **Projeção OPEX ✅ (v7.1.0)** — `require_universo` +
    `clausula_escopo("opex_sustaining")` nos filtros de `dados_tendencia`.
    `tests/rbac_projecao_check.py`.
  - **Visão Manutenção + Nível 4 + Nível 5 ✅ (v7.2.0)** — helper
    `guardar_e_faixa_universo` (gate + faixa "🔒 Recorte"); escopo em
    `nivel4_contas._filtros_padrao` (Nível 5 e as árvores embutidas na
    Visão Manutenção herdam) e nas 5 consultas diretas da Visão
    Manutenção. `tests/rbac_sustaining_check.py`.
  - Falta: Resumo Executivo, Painel Executivo (waterfall — precisa
    recortar `explicacoes.csv` também), OPEX/CAPEX Manutenção
    (`visao_classificacao`), **Nível 6** (`fact_realizado_documento` não
    tem `gerencia_id` — recorte via `centro_custo_id`), CAPEX Obras
    (universo `capex_obras`, coluna `gerencia_obras`/`e_pep_projeto` —
    `clausula_escopo` precisa separar alvos por tipo), + ligar o
    default-deny do `pce_especialista` em `can_acessar_pagina`.
- **RBAC-B — navegação (1ª camada).** Esconder grupo / opção de
  `segmented_control` conforme `universos_permitidos`. Entra junto das
  Etapas 3–6 do `docs/07` (as páginas já consolidadas).

A **Etapa 2** do `docs/07` (grupo GESTÃO) já foi, era independente.

## 9. SQL de inspeção dos usuários atuais

Rodar no **SQL Editor do Neon** (rede da MRS não abre a porta 5432 direto
— ver `docs/05`).

```sql
-- 1) Usuários e o que já têm hoje
select id, coalesce(matricula,'') matricula, coalesce(email,'') email,
       nome_completo, papel, gg_id, gerencia_id, ativo,
       permissao_upload, permissao_exportacao,
       permissao_justificativa_macro, permissao_justificativa_micro,
       precisa_trocar_senha, ultimo_login
from app.usuario
order by papel, nome_completo;

-- 2) Escopos já cadastrados (provável: nenhum aplicado, mas pode haver linha)
select u.nome_completo, u.papel, e.universo, e.tipo, e.valor, e.ativo, e.criado_em
from app.escopo_acesso e join app.usuario u on u.id = e.usuario_id
order by u.nome_completo, e.universo, e.tipo, e.valor;

-- 3) Overrides de página por usuário
select u.nome_completo, p.pagina, p.permitido, p.atualizado_em
from app.permissao_pagina p join app.usuario u on u.id = p.usuario_id
order by u.nome_completo, p.pagina;
```

## 10. CAPEX Obras — execução (CJI3/CJI4) x planejamento (PCE)

O grupo "CAPEX Plano de Obras" tem **dois tipos de tela**:

**A) Execução / contábil — CJI4 (Orçado) x CJI3 (Realizado).**
Páginas: `capex_resumo`, `capex_painel`, `capex_contas`, `capex_
rastreabilidade`. Respondem "onde estamos vs o orçamento aprovado":
Orçado CJI4 x Realizado CJI3, Delta, aderência, drill Gerência de Obras →
Projeto → Conta → documento CJI3. Público: GG / PMO / gestão executiva.

**B) Planejamento especializado — PCE (`fact_pce_consolidado` /
`fact_pce_realizado`).** Página: `pce_especialista` ("CAPEX Obras —
Especialista"). Tem o que A não tem: 13 versões de planejamento
(Orçamento 2026, PN24/25/26, FEL3, forecasts FC01+11…FC06+06), comparação
livre entre versões, curva plurianual 2022–2038, % Contingência /
Escalation / Capitalização, análise fina por Descrição (Serviços /
Materiais / Engenharia / SMA…). Público: Especialista de Obras/Projetos —
quem constrói e revisa o plano (metodologia FEL), dono do threshold de
CAPEX (R$500k, papel diferente do Analista de OPEX — ver `docs/03`).
Densidade bem maior, é tela de trabalho técnico.

**Nota técnica:** A e B usam a **mesma** dimensão de Gerência
(`gerencia_obras`) — então o recorte por Gerência de Obras funciona igual
nos dois. A escolha é só de público.

**Opções de RBAC:**
- **A) Mesma porta (`capex_obras`)** — um grant só; quem vê Obras vê
  execução E planejamento. Menos administração; ruim se GG/PMO devem ver
  só o "vs orçamento aprovado" e não as versões de forecast/PN/FEL.
- **B) Chave de página própria** (`capex_obras_especialista`) **em cima
  do grant `capex_obras`** — `capex_obras` libera as telas de execução +
  fornece o escopo por Gerência de Obras; uma 2ª permissão (via
  `app.permissao_pagina`, mas invertida: exige allow explícito) libera a
  tela do Especialista. Dá execução sem plano, ou o especialista só com o
  plano da Gerência dele. Custo: 1 checkbox a mais por usuário.

**Recomendação: B.** PCE é dado de planejamento (cenários, forecast, FEL),
público e sensibilidade diferentes da execução contábil; e o próprio
`FIN360_VISAO_IDEAL.md` já trata "CAPEX Obras - Especialistas" como página
à parte, "preservação absoluta", "maior densidade". Formaliza isso a custo
quase zero e o escopo por `gerencia_obras` continua valendo.
