# 03 — Processo de Captura de Justificativas de Causa (fact_explicacao)

**Status: proposta de estrutura, NÃO implementada.** Pedido do usuário em
2026-08-10 ("crie um processo... inicialmente não quero que você codifique,
mas monte uma estrutura completa"). Responde ao item 3 de
`docs/02-perguntas-em-aberto.md` e formaliza a decisão do item 17 do mesmo
documento (Pacote e Conta/Centro de Custo como campos separados).

**Escopo desta primeira fase: só OPEX.** CAPEX (Obras e Projetos) tem
threshold (R$500 mil) e dono (Especialista de Obras/Projetos da Gerência,
não a Analista) diferentes — ver 3.3. Fica de fora por enquanto; todo o
resto deste documento é desenhado pensando em OPEX.

## Decisões fechadas nesta rodada (2026-08-10)

1. **Princípio central**: o sistema aponta a pendência sozinho — a Analista
   não precisa notar o desvio primeiro (hoje, na planilha real, é o
   contrário). É o que separa "dashboard" de "planilha digitalizada" — ver
   3.4.
2. **Macro (Pacote) x Micro (Conta/CC)**: complementares, nunca competem
   pelo mesmo R$ — ver 2.3.
3. **Hierarquia de consumo**: GG/PMO só veem o Macro por padrão; o Micro é
   carga do gestor de área, some da visão executiva — ver 2.3.
4. **Threshold**: R$100mil (Macro/OPEX) e 100% sem threshold (Micro/OPEX)
   não são a mesma régua do R$500mil de CAPEX — são domínios e donos
   diferentes, não uma divergência a resolver — ver 3.3.
5. **Ciclo mensal**: dado chega semanal, cobrança de justificativa é
   mensal — a Fila de Pendências só considera mês já fechado — ver 3.2/3.4.
6. **Sem gate de aprovação**: a Analista é ponto de entrada *e* final do
   dado; Coordenador/Gerente podem auditar, nunca bloqueiam — ver 3.1/3.2.
7. **"Taxa Bom/Mix" é exclusiva de CAPEX** — não aparece no formulário
   OPEX desta fase.
8. Planilha real do flag (`data/raw/SP - Flag.xlsx`) localizada e lida —
   achados no Anexo (seção 9), com ressalvas.

---

## 1. Por que isso não é greenfield

O modelo já prevê a granularidade fina: `fact_explicacao` (spec, seção 6) é
`Pacote, Conta, Mês, Categoria, Valor Explicado, Descrição`, e o CSV de
apoio (`COLUNAS_EXPLICACAO` em `explanation_engine.py`) já tem `conta_id`
desde o início. Mas na prática hoje:

- O motor (`calcular_explicacao`) só é chamado com `dims=["pacote_id"]`
  (Nível 3). `conta_id` existe no arquivo, mas nenhuma tela agrega por ela.
- O preenchimento é 100% manual, fora do painel — alguém edita
  `explicacoes.csv` num editor de texto. Sem autor, sem timestamp, sem
  histórico: uma edição apaga a anterior sem deixar rastro.
- Fora do painel, a Laís/PMO já mantém um "flag" real de justificativa por
  Pacote, preenchido por analistas (ex.: Jaque) — ver Anexo. O processo
  daqui deve **espelhar esse fluxo já existente**, não competir com ele.

---

## 2. Modelo de dados proposto

### 2.1 Log append-only, nunca sobrescreve

Uma edição no CSV hoje apaga a versão anterior — inaceitável pra uma "fonte
de registro auditável com histórico" (pedido explícito do usuário). Regra:
**nunca UPDATE numa linha existente, toda edição cria uma linha nova.** O
motor sempre lê só a versão `vigente`; versões antigas ficam gravadas, só
param de contar. Mesmo princípio do projeto irmão SGO Workforce ("toda
transição idempotente e auditável") — não é regra formal daqui, mas vale
pelo mesmo motivo.

### 2.2 Tabela proposta: `fact_explicacao_log`

Substitui o CSV solto (ver seção 4). Uma linha = uma versão de um
apontamento.

| Coluna | Tipo | Obrig. | Descrição |
|---|---|---|---|
| `explicacao_id` | UUID | sim | Identifica o registro lógico — todas as versões de uma justificativa compartilham o mesmo ID. |
| `versao` | int | sim | Incrementa a cada edição do mesmo `explicacao_id`. |
| `vigente` | bool | sim | `True` só na versão mais recente. O motor só soma `vigente = True`. |
| `gg_id` | texto | sim | Redundante com pacote, guardado explícito pra auditoria/filtro sem join. |
| `pacote_id` | texto | sim | Todo apontamento é, no mínimo, de um Pacote. |
| `conta_interna_id` | texto | não | Preenchido = Micro por Conta (chave unificada do Catálogo de Contas). Exclusivo com `centro_custo_id`. |
| `centro_custo_id` | texto | não | Preenchido = Micro por Centro de Custo. Exclusivo com `conta_interna_id`. |
| `nivel` | texto | sim | `macro` ou `micro` — deriva dos 2 campos acima, guardado explícito pra simplificar a query de soma (2.3). |
| `ano` / `mes` | int | sim | Competência do desvio. |
| `categoria` | texto | sim | Uma das categorias fechadas de `categorias_causa` (nunca "Não Justificado"), sem "Taxa Bom/Mix" nesta fase OPEX. |
| `valor_explicado` | numérico | sim | Mesmo sinal do Delta sendo explicado. |
| `descricao` | texto | sim acima do threshold | Narrativa. Numa linha `macro`, pode citar as Contas/CCs detalhadas em paralelo (`refs_micro`). |
| `refs_micro` | lista | não | Só em linhas `macro`: Contas/CCs que a Analista já detalhou (ou vai) no Micro — informativo, não soma. |
| `autor_nome` / `autor_gerencia` | texto | sim | Quem preencheu (texto livre, sem login — ver seção 6). |
| `criado_em` | timestamp | sim | Data/hora do preenchimento. |
| `substitui_id` / `motivo_edicao` | UUID / texto | não | Preenchidos só em edição — dão o diff completo (o que mudou, quem, quando). |
| `status_ciclo` | texto | sim | `rascunho` ou `consolidado` (3.2) — sem estados de aprovação. |
| `origem` | texto | sim | `dashboard` ou `importacao_legado`, só pra rastrear a migração do CSV atual. |

### 2.3 Regra Macro x Micro

Os dois níveis não competem pelo mesmo R$ — são complementares por
construção:

- **Micro** (`conta_interna_id` OU `centro_custo_id`, nunca os dois): valor
  exato de uma Conta ou CC específico. Dado atômico, preenchível tanto na
  aba de Conta (Nível 4) quanto na de Centro de Custo (Nível 5) — a
  Analista usa a que fizer mais sentido pro caso.
- **Macro** (sem Conta/CC): narrativa do Pacote inteiro, e um
  `valor_explicado` que cobre **só a parte do Delta ainda não detalhada
  por Conta/CC**. Se 100% for detalhado no Micro, o valor Macro fica 0.

```
Delta Explicado (Pacote) = SUM(valor_explicado WHERE nivel="micro" E pacote_id=X)
                          + SUM(valor_explicado WHERE nivel="macro" E pacote_id=X)
```

Sem dupla contagem por construção — cada R$ mora em 1 lugar só. O painel
pode mostrar aviso soft (não bloqueante) se a soma Micro de um Pacote
ultrapassar o Delta Total dele — sinal de erro de preenchimento, não de
dupla contagem entre níveis.

**Hierarquia de consumo → onde cada métrica aparece**: Nível 1/2/3 e Resumo
Executivo (telas de GG/PMO) mostram só o "% Explicado" consolidado e a
narrativa Macro — GG/PMO olham o Pacote pra apontar desvios de maior
percepção em reunião executiva, não acompanham Conta/CC no dia a dia (isso
é carga do gestor de área). Nível 4/5 mostra as 2 métricas lado a lado
(termômetro de quão auditável está o número). Nível 3 pode oferecer o
Micro como *drill-down* opcional (expander), não card fixo — cobre o caso
raro de alguém abrir o Micro numa reunião executiva pra sustentar o Macro.

---

## 3. Processo humano

### 3.1 Papéis

| Papel | O que faz | Consome por padrão |
|---|---|---|
| **Analista de Gerência** | Preenche Macro e Micro — ponto de entrada *e* final do dado, sem aprovação de ninguém antes do PMO (3.2). Referência real: Jaque. | Micro no dia a dia |
| **Gestor de Área/Coordenador/Gerente** | Pode auditar/consultar o Micro da própria área a qualquer momento — **não é ponto de checagem**: hoje não fazem isso nem são cobrados por acompanhar/validar. | Micro, só sob demanda |
| **PMO** | Consolida direto o que a Analista imputou até a data de corte, sem aprovação intermediária. Referência real: Laís/RDG. | Macro |
| **Admin do painel** | Mantém taxonomia e threshold em `config/settings.yaml`. Hoje: Julio. | — |

### 3.2 Ciclo mensal (padrão e repetível)

```
[Fechando]           Realizado (SAP) atualizado semanalmente — Delta se
                      move, mas NENHUMA pendência aparece ainda (3.4)
   ↓  virada do mês (1º dia útil subsequente, régua de executado fecha)
[Aberto/Rascunho]     Fila de Pendências libera o mês recém-fechado;
                      Analista preenche livremente ao longo das semanas,
                      sem revisão de ninguém no meio do caminho
   ↓  data de corte (alinhada à RDG do mês)
[Consolidado]         Vai direto pro PMO. Edição depois disso exige nova
                      versão com `motivo_edicao` (correção pós-fechamento,
                      visível como tal). Auditoria de gestores pode
                      acontecer antes ou depois — nunca bloqueia a
                      passagem.
```

O dado é semanal, a cobrança é mensal — sem esse desacoplamento a Analista
seria cobrada toda semana por um Delta ainda se movendo, antes do mês
fechar de verdade. **[A CONFIRMAR]**: cadência exata do "Consolidado" (é
sempre a data da RDG? a RDG acontece todo mês sem exceção?).

### 3.3 Threshold de obrigatoriedade

Não é 1 régua divergente (como o item 18 de `docs/02-perguntas-em-aberto.md`
sugeria) — são 2 domínios com donos diferentes:

| Domínio | Nível | Threshold | Quem justifica |
|---|---|---|---|
| OPEX | Macro (Pacote) | Obrigatório acima de **R$100mil** | Analista de Gerência |
| OPEX | Micro (Conta) | **100% — sem threshold** | Analista de Gerência |
| CAPEX (Obras/Projetos) | — | **R$500mil** | Especialista de Obras/Projetos — outro papel, fora de escopo agora |

`src/engine/semaforo.py` hoje usa só R$500mil pro status Roxo, misturando
OPEX+CAPEX — fica pendente de ajuste quando a captação for codificada.

### 3.4 Fila de Pendências — detecção automática

A cada rodada de `build_star_schema.py`, depois de recalcular o Delta, o
painel recalcula (via *query*, não tabela gravada) a lista de pendências,
cruzando o Delta atual contra `fact_explicacao_log` (`vigente = True`) e
3.3:

- **Pendência Macro**: Pacote OPEX com `abs(delta_total) >= R$100mil` cuja
  soma Micro+Macro vigente não cobre 100% do Delta.
- **Pendência Micro**: Conta OPEX com `delta_total != 0` sem nenhuma linha
  `micro` vigente.

**Filtro de mês fechado**: só considera `(ano, mes)` anteriores ao mês
corrente — nunca o mês em andamento, mesmo com Realizado parcial já
carregado (3.2). As cargas semanais dentro do mês não geram pendência
nova; só a virada do mês libera aquele mês pra Fila.

Uma pendência some sozinha quando a soma das justificativas vigentes cobre
o Delta — não existe "marcar como resolvido" manual. E **reabre sozinha**
se uma rodada nova de dado muda o Delta de algo já justificado (ex.: SAP
lança nota atrasada) — o resíduo (Delta atual − soma vigente) volta a
aparecer, sem precisar de ninguém notar a mudança.

---

## 4. Onde isso mora tecnicamente

O CSV solto não aguenta múltiplas Analistas editando ao mesmo tempo (risco
de corrupção) nem dá consulta estruturada de auditoria.

1. **Curto prazo**: `fact_explicacao_log` vira tabela dentro do próprio
   `data/warehouse/painel.duckdb` — sem infra nova. `build_star_schema.py`
   materializa `fact_explicacao` (só `vigente = True`) a partir do log,
   como já faz com `fact_orcamento`/`fact_realizado`.
2. **Import do legado**: o CSV atual vira "versão 1, origem =
   importacao_legado" na migração — não perde o que já foi preenchido.

**[A CONFIRMAR]**: escrita concorrente de múltiplas Analistas ao mesmo
tempo é problema de infra mais amplo (hoje o painel roda local, sem
servidor compartilhado) — depende de saber se o uso real é 1 pessoa por
vez ou precisa de servidor único.

---

## 5. Onde isso aparece no painel

**Porta de entrada principal: "Fila de Pendências"**, não os formulários —
a Analista abre o painel e já vê a lista calculada (3.4), ordenada por
Delta ou Gerência, cada item com link direto pro input certo.

Dois pontos de entrada pro input em si:

- **Input Macro** (Visão de Pacote, Nível 3): narrativa, Categoria,
  Descrição (pode citar Contas/CCs em paralelo), Valor residual. Visível
  por padrão pro GG/PMO no waterfall/Resumo Executivo.
- **Input Micro** (Visão de Conta — Nível 4 — e Centro de Custo — Nível
  5): Categoria, Valor, Descrição por Conta/CC específico — soma
  automática no Macro (2.3). Uso do gestor de área no dia a dia; só
  aparece pro GG/PMO sob demanda.

Ambos validam: sinal do valor coerente com o sinal do Delta, Categoria só
da taxonomia fechada, Autor/Gerência obrigatórios.

- **Tela de auditoria/histórico**: por Pacote ou Conta/CC, todas as
  versões — quem, quando, o que mudou. Mesmo espírito do Nível 6 (SAP),
  agora do lado das causas.
- **Waterfall (Nível 2/Resumo Executivo)**: sem mudança de fórmula, só
  passa a somar Micro+Macro. Cada barra pode ganhar tooltip "📝 preenchido
  por X em DD/MM".
- **Nível 4/5**: hoje nenhum chama `calcular_explicacao` — precisam
  ganhar a mesma chamada do Nível 3, filtrada por `nivel = "micro"`.

### 5.1 Justificativa aparece ao passar o cursor (hover), onde já houver Delta/aderência

Confirmado como tecnicamente viável (pergunta do usuário, 2026-08-10) — não
precisa de tela nova pra cada lugar, é o mesmo `fact_explicacao_log`
alimentando o hover de componentes que **já existem hoje**, por tipo:

- **Gráficos Plotly** (waterfall dos Níveis 2/Resumo Executivo, tabela de
  ranking do Nível 3, barras de maiores desvios do Nível 4/5): Plotly já
  suporta `hovertext`/`customdata` + `hovertemplate` — é só trocar o texto
  estático do hover de hoje (só o valor) por um texto composto (Categoria +
  Descrição + Autor + Data, puxados da justificativa `vigente` daquele
  Pacote/Conta/CC), sem mudar o tipo de gráfico.
- **Cards de resumo em `st.markdown`** (Nível 1, Resumo Executivo, Nível
  4/5 — onde mostra Aderência/semáforo 🟢🟡🔴🟣): o painel já usa
  `unsafe_allow_html=True` pra outras coisas (o divisor vertical entre
  colunas) — o mesmo caminho permite envolver o número/emoji num
  `<span title="...">`, que o navegador já mostra como tooltip nativo ao
  passar o cursor, sem biblioteca nova.
- **`st.metric`** (usado em alguns cards, ex. Visão Manutenção): tem
  parâmetro nativo `help=` — mostra um ícone (?) com tooltip ao passar o
  cursor, sem HTML manual.
- Onde **não existe** justificativa vigente ainda pro item sob o cursor, o
  tooltip mostra isso também ("⚠️ Pendente de justificativa") — reforça a
  Fila de Pendências (3.4) no próprio lugar onde o número aparece, não só
  numa lista separada.

---

## 6. Ideias registradas para o futuro (fora de escopo agora)

- **Checagem de justificativa órfã por remapeamento de Conta** — registrado
  em 2026-08-26, durante o desenho da publicação online (ver
  `docs/05-publicacao-online-e-seguranca.md`). Risco identificado: a soma de
  `valor_explicado` no nível Pacote (seção 2.3 acima) agrupa só por
  `pacote_id`, sem reconferir se o `conta_interna_id` de cada linha `micro`
  ainda existe na base atual. Se o Catálogo de Contas (De/Para) ganhar um
  mapeamento novo para um código que antes caía no fallback
  (`build_star_schema.py:253`, `conta_interna_id` = código bruto quando não
  achado no catálogo), a Conta passa a ter um `conta_interna_id` diferente
  do dia para a noite: (1) a Fila de Pendências abre uma pendência nova pra
  essa Conta (comportamento correto, esperado); (2) mas a justificativa
  antiga, presa ao código antigo, continua contando no total do Pacote —
  se alguém preencher a pendência nova sem saber da antiga, o mesmo real
  vira contado duas vezes no Pacote. Mitigação proposta (não implementada):
  depois de cada reprocessamento, checar se existe alguma linha
  `vigente=true` em `fact_explicacao_log` cujo `conta_interna_id` não
  aparece mais na base atual, e mostrar isso como aviso soft (não
  bloqueante) na tela de Auditoria/Histórico (seção 5 acima) — mesmo padrão
  de aviso já usado no upload ("sobrou linha sem Gerência"). Raro na
  prática (só ocorre quando o Catálogo de Contas muda), não é bloqueio para
  a Camada 4 nascer sem essa checagem.

- **Alerta antecipado pro Gerente responsável (Coordenações/Projetos,
  Elementos PEP)** — sugerido pelo usuário em 2026-08-10: além da Analista
  ver a Fila de Pendências, o Gerente responsável pela Coordenação/Projeto
  (dono do Elemento PEP) poderia **receber alerta antecipado** de
  estouro/economia, pra "dar o acordo" antes do fechamento — uma camada de
  ciência prévia, não um gate de aprovação (não contradiz a decisão 6 da
  seção "Decisões fechadas": ele é avisado, não bloqueia). Registrado como
  possibilidade — não desenhado em detalhe, não faz parte desta proposta.
  Pré-requisitos que precisariam existir antes de detalhar: mecanismo de
  notificação (o painel hoje não tem — é Streamlit local, sem
  e-mail/push) e mapeamento Elemento PEP → Gerente responsável (hoje o PEP
  só existe do lado do Orçamento, ver `nivel5_centro_custo.py`).

---

## 7. O que este documento propositalmente não resolve

- **Login/autenticação real** — `autor_nome` é texto livre sem
  verificação; amarrar a identidade autenticada é decisão de infra maior.
- **Nome exato dos campos** — parcialmente resolvido pelo Anexo (seção 9),
  mas com ressalva: só 1 exemplo real disponível.
- **Processo de CAPEX** — fora de escopo (3.3); quando entrar, provável
  papel novo e threshold próprio, não necessariamente Macro/Micro 1:1.
- **[A CONFIRMAR]** consolidado: cadência exata da consolidação mensal
  (3.2); concorrência de escrita multi-usuário (4); coluna "Tipo" da
  planilha real (9.1); se o Micro deveria ser por `conta_interna_id` exata
  ou por um bucket mais largo tipo "Classif. Conta" (9.1); se os 4 valores
  extras da lista "Justificativa PMO" entram em `categorias_causa` (9.2).

---

## 8. Ordem de implementação sugerida

1. Migrar o CSV atual pra `fact_explicacao_log` no DuckDB, linhas
   existentes como versão 1/legado — sem mudar nenhum número já exibido.
2. Ligar o Nível 4 (Contas) ao motor de explicação (hoje só o Nível 3
   chama `calcular_explicacao`).
3. **Query/tela da Fila de Pendências (3.4)** — antes do formulário de
   captura. É o motivo de existir a feature; pode nascer só-leitura pra
   validar a lógica contra o dado real antes de construir o input em cima.
4. Tela de captura (Input Macro no Nível 3, Input Micro no Nível 4/5) — a
   Fila linka direto pra cá.
5. Tela de auditoria/histórico.
6. Trava de ciclo (rascunho → consolidado na data de corte) — última
   camada, só depois de validado em uso real por pelo menos 1 Gerência.

---

## 9. Anexo — planilha real (`data/raw/SP - Flag.xlsx`)

Lida em 2026-08-10. **Ressalva**: das 59 linhas da aba principal, só **1
tem dado real** — achados preliminares, precisam validação com a
Jaque/Laís antes de fechar o layout final.

### 9.1 Colunas e mapeamento proposto

Aba "Justificativas Oficial SP" (a aba "Ações" está vazia — só um
rastreador de ação/prazo/responsável por Gerência, feature separada, fora
de escopo):

| Coluna real | Exemplo | Leitura |
|---|---|---|
| `Classificação Pacote` | "Manutenção" | próximo de `familia_pacote`, em texto |
| `Classificação` | "Indiretos" | **achado**: pode ser a divisão Opex Via/EE/Indiretos que falta hoje no painel (`visao_manutencao.py` já documenta esse gap) — investigar como fonte, independente desta feature |
| `Pacote` | "PM05" | bate com `pacote_id` |
| `Tipo` | "Manut VP" | não confirmado (VP = outro domínio/GG?) — **[A CONFIRMAR]** |
| `Classif. Conta` | "Indiretos - Serviço" | **achado importante**: NÃO é um código de conta exato — é um bucket/rótulo em texto. O Micro real da Jaque pode ser mais grosso do que "por `conta_interna_id` exata" — **[A CONFIRMAR]** antes de fechar a granularidade |
| `Var finan` | 2791.03 | `valor_explicado` |
| `Nova GG` / `Gerência` | "SP" / "MALHA SP" | `gg_id`/`gerencia_nome`, em rótulo curto |
| `Data preenchimento` | 2026-07-15 | `criado_em`, granularidade de data |
| `Justificativa detalhada` | "...compensar no PM03" | `descricao` — mostra um padrão real não modelado: apontar realocação pra **outro** Pacote (reclassificação entre Pacotes, fora de escopo agora) |
| `Questionamentos Gestão financeira` | "Físico" | bate com a lista "Justificativa PMO" — candidato a carregar a categoria oficial |

### 9.2 Duas taxonomias diferentes na planilha

- **"Justificativa PMO"**: Não considerar, Físico replanejado, Realizado
  não contabilizado, Não previsto, Efeito preço, Combustível, Físico,
  Sistema/Ajuste contábil, Pendências 2025 — a mais próxima de
  `categorias_causa`, mas com **4 valores fora da nossa lista fechada**
  (Não considerar, Físico replanejado, Combustível, Pendências 2025).
  **[A CONFIRMAR]** com o PMO se algum entra na taxonomia oficial.
- **"Justificativa App fechamento"**: Postergação, Pendência Entrada, Não
  previsto, Sazonalidade — não bate com nossa taxonomia de causa, parece
  motivo de fechamento/reconciliação de sistema. Não misturar as duas
  listas no mesmo campo.

### 9.3 O que confirma a proposta

O grão real é **1 linha por Pacote/mês** — bate exatamente com o nível
Macro (seção 2), validando a decisão de espelhar o fluxo real da Jaque no
Pacote.
