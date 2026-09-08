# FIN360 — Visão Ideal Corrigida

## Referência funcional para comparação com o código atual

**Escopo:** Painel Executivo de Explicação de Delta da DINFRA, com foco na GGG_0054.

**Objetivo:** registrar a arquitetura funcional recomendada para o Fin360, corrigindo a versão anterior que apresentou o inventário de funcionalidades como se fosse a sidebar definitiva.

> **Correção principal:** a sidebar recomendada é compacta. As páginas antigas continuam preservadas como conteúdo, componentes ou abas internas, e não necessariamente como itens independentes do menu.

---

# 1. Visão do produto

O Fin360 deve permitir que a liderança responda rapidamente:

1. Qual é o desvio financeiro?
2. Onde está o desvio?
3. Qual Gerência, Pacote, Conta, Centro de Custo, Projeto ou PEP gerou o valor?
4. Qual é a causa predominante?
5. Quanto do Delta está explicado?
6. Quanto permanece Não Justificado?
7. Qual documento SAP ou CJI3 sustenta a análise?

Fluxo conceitual:

```text
Orçamento
→ Real Físico
→ Real Contabilizado
→ Delta
→ Explicação do Delta
→ Evidência SAP/CJI3
```

Fórmulas essenciais:

```text
Delta = Realizado - Orçamento
Delta Explicado = soma das causas registradas
Não Justificado = Delta - Delta Explicado
% Explicado = Delta Explicado / Delta
```

“Não Justificado” é sempre calculado pelo sistema e nunca digitado como causa manual.

---

# 2. Arquitetura final da sidebar

```text
PLANO DE MANUTENÇÃO
  • Resumo
  • Análise Financeira
  • Pendências e Justificativas
  • Evidências SAP

CAPEX PLANO DE OBRAS
  • Resumo
  • CAPEX Obras - Especialistas

GESTÃO
  • Dados e Qualidade
  • Administração
```

Essa é a estrutura recomendada para o menu principal.

## O que não deve acontecer

As páginas antigas não devem continuar todas expostas como itens independentes apenas porque existem como módulos separados no código. O objetivo é reduzir repetição visual sem eliminar funcionalidade.

A relação correta é:

```text
Sidebar compacta
→ páginas de jornada
→ abas internas
→ componentes existentes preservados
```

---

# 3. PLANO DE MANUTENÇÃO

O Plano de Manutenção reúne:

- OPEX de Manutenção Corrente;
- despesas de Pessoal;
- Despesas Gerais;
- CAPEX Sustaining ligado à Manutenção;
- análise de Pacotes, Contas e Centros de Custo;
- justificativas Macro e Micro;
- rastreabilidade SAP.

Não deve ser misturado ao CAPEX de grandes Projetos e Obras.

## 3.1 Página Resumo

A página **Resumo** consolida o conteúdo das páginas atuais:

- “Visão resumo Executivo- GGSP”;
- “Painel Executivo”;
- “Projeção Opex”.

A consolidação não significa eliminar conteúdo. Significa reorganizar os elementos em uma única experiência e retirar duplicações de cards, títulos e gráficos.

### Abas

```text
Visão Executiva | Desvios e Causas | Projeção
```

### 3.1.1 Visão Executiva

Origem principal: “Visão resumo Executivo- GGSP”.

Deve preservar:

- Orçamento;
- Realizado;
- Delta;
- Aderência;
- comparação OPEX x CAPEX Sustaining;
- visão por Gerência;
- principais ofensores;
- maior estouro;
- maior economia;
- destaques financeiros;
- evolução geral do Plano;
- tabela executiva de apoio;
- acesso direto à Análise Financeira.

Organização recomendada:

1. Uma única faixa de indicadores no topo.
2. Um único título para a página.
3. OPEX e CAPEX Sustaining em blocos comparáveis.
4. Ranking de maior estouro e maior economia.
5. Tabela executiva junto dos gráficos.
6. Link contextual para detalhamento.

Os conceitos executivos de Orçamento acumulado, Real Físico, Real Contabilizado, Forecast, Delta e Aderência devem permanecer disponíveis quando houver fonte ou regra confirmada. Conceitos indisponíveis não devem ser preenchidos por suposição.

### 3.1.2 Desvios e Causas

Origem principal: “Painel Executivo”.

Deve preservar:

- waterfall;
- decomposição das causas;
- Delta explicado;
- Delta não explicado;
- percentual explicado;
- ranking de Pacotes;
- ranking de Gerências;
- tendência associada ao recorte;
- acesso ao detalhamento por Pacote, Conta e Centro de Custo.

Deve acrescentar, quando implementado:

- status da justificativa;
- narrativa Macro vigente;
- autor da última atualização;
- data da última atualização;
- botão “Abrir análise”;
- botão “Justificar desvio”, condicionado à permissão.

A coleta principal permanece em “Pendências e Justificativas”, mas o acesso pode ser contextual a partir do desvio selecionado.

### 3.1.3 Projeção

Origem principal: “Projeção Opex”.

Deve preservar:

- Orçamento anual;
- realizado acumulado;
- Forecast ou projeção calculada;
- diferença projetada;
- tendência mensal;
- análise por natureza ou família;
- execução acumulada;
- saldo remanescente;
- curva até dezembro.

A antiga “Projeção Opex” deixa de existir como item isolado da sidebar, mas sua funcionalidade permanece integralmente dentro da aba Projeção.

Se “Forecast” e “Projeção de ritmo” forem conceitos diferentes, a interface deve nomeá-los separadamente.

---

## 3.2 Página Análise Financeira

### Abas

```text
Pacotes | Contas e Centros de Custo | CAPEX Sustaining
```

### 3.2.1 Pacotes

Origem funcional:

- Visão Manutenção;
- Nível 3 — Pacotes;
- componentes de ranking já existentes.

Deve preservar:

- Orçamento;
- Realizado;
- Delta;
- Aderência;
- ranking de Pacotes;
- composição mensal;
- causa principal;
- justificativa Macro;
- acesso às Contas;
- acesso às evidências.

O filtro e o clique em uma causa devem levar aos Pacotes que compõem o valor selecionado.

### 3.2.2 Contas e Centros de Custo

Une funcionalmente as páginas atuais de Contas e Centro de Custo.

Controle interno:

```text
Analisar por: Conta | Centro de Custo
```

Deve preservar:

- Conta Orçamentária;
- Conta Razão;
- descrição da Conta;
- Centro de Custo;
- Gerência;
- Coordenação;
- Orçado;
- Realizado;
- Delta;
- Aderência;
- justificativa Micro;
- acesso aos lançamentos SAP.

Conta e Centro de Custo continuam dimensões distintas, mesmo estando reunidos em uma única página.

### 3.2.3 CAPEX Sustaining

Mantém o CAPEX ligado à Manutenção, sem misturá-lo ao CAPEX Plano de Obras.

Deve contemplar, conforme as fontes disponíveis:

- Malha;
- Via;
- EE;
- Infra;
- PEP;
- materiais;
- serviços;
- Orçamento;
- Realizado;
- Delta;
- Forecast ou projeção.

CAPEX de Malha e Infra são universos de Manutenção. CAPEX Projetos e Obras é outro universo financeiro.

---

## 3.3 Página Pendências e Justificativas

### Abas

```text
Fila de Pendências | Em elaboração | Consolidadas | Histórico
```

A primeira fase é orientada ao OPEX. O processo de CAPEX Obras possui materialidade e responsável diferentes e não deve ser copiado automaticamente.

### 3.3.1 Fila de Pendências

Porta de entrada principal para tratamento de desvios.

Deve mostrar automaticamente:

- Pacotes com Delta material ainda não explicado;
- Contas sem justificativa Micro;
- valor residual;
- percentual explicado;
- competência;
- Gerência;
- link para o input correto.

Regras:

- considerar somente mês fechado;
- não gerar cobrança automática durante o mês em andamento;
- remover a pendência quando o Delta estiver coberto;
- reabrir automaticamente quando nova carga alterar o Delta;
- não depender de marcação manual “resolvido”.

### 3.3.2 Em elaboração

Deve mostrar justificativas em rascunho, ainda dentro do ciclo de fechamento.

### 3.3.3 Consolidadas

Deve mostrar as justificativas vigentes enviadas ao processo de consolidação mensal.

### 3.3.4 Histórico

Deve manter:

- todas as versões;
- autor;
- data e hora;
- conteúdo anterior;
- conteúdo novo;
- motivo da edição;
- vínculo com Pacote, Conta ou Centro de Custo.

### Macro e Micro

```text
Macro = justificativa do Pacote
Micro = justificativa de Conta ou Centro de Custo
```

Regras:

- Macro e Micro são complementares;
- cada valor financeiro deve contar uma única vez;
- GG e PMO consomem Macro por padrão;
- Micro fica disponível no detalhamento;
- alteração consolidada gera nova versão;
- “Não Justificado” nunca é digitado.

Referência de materialidade do desenho:

- OPEX Macro: R$ 100 mil;
- OPEX Micro: todos os Deltas, sem threshold;
- CAPEX Obras/Projetos: R$ 500 mil, com responsabilidade do Especialista de Obras/Projetos.

Esses parâmetros devem permanecer configuráveis e sujeitos à validação de negócio.

---

## 3.4 Página Evidências SAP

A página centraliza o último nível de rastreabilidade da Manutenção.

Deve permitir acesso por links contextuais vindos de Pacote, Conta e Centro de Custo.

Campos esperados, conforme disponibilidade da fonte:

- Documento SAP;
- Nota Fiscal;
- fornecedor;
- data;
- valor;
- texto do lançamento;
- usuário;
- Centro de Custo;
- Pacote;
- Conta;
- período fiscal.

A página deve preservar os filtros herdados do drill-down e oferecer retorno à análise sem perder o contexto.

---

# 4. CAPEX PLANO DE OBRAS

O CAPEX Plano de Obras é o universo de grandes Projetos e Obras, acompanhado por Projeto, PEP, Classe de Custo, rubrica e documento CJI3.

Não deve usar a estrutura PM/PD/PP como eixo principal.

## 4.1 Página Resumo

### Abas

```text
Visão Executiva | Desvios e Evolução
```

A página unifica:

- “Resumo Executivo” de Obras;
- parte sintética do “Painel Executivo” de Obras.

### 4.1.1 Visão Executiva

Deve preservar:

- Orçamento;
- Realizado;
- Delta;
- Aderência;
- evolução;
- principais Projetos ofensores;
- Gerências de Obras;
- classificação do portfólio;
- composição por rubrica;
- quantidade ou composição de Projetos, somente se já existir na fonte ou no painel atual.

Rubricas que podem existir no universo de Obras:

- Pré-Obra;
- Obra;
- Pós-Obra;
- Contingência;
- Escalation;
- Rateios;
- Capitalização;
- Mão de Obra;
- Engenharia;
- Serviços;
- Indiretos.

As classificações A+1 a A+8, Renovação/Não Renovação e natureza do Projeto são eixos independentes.

### 4.1.2 Desvios e Evolução

Origem principal: parte analítica do atual Painel Executivo de Obras.

Deve preservar:

- tendência;
- variação;
- composição do Delta;
- ranking de Projetos;
- evolução do Realizado;
- detalhamento por Gerência;
- detalhamento por Projeto;
- composição por Classe de Custo;
- acesso à rastreabilidade CJI3.

---

## 4.2 Página CAPEX Obras - Especialistas

### Regra inviolável

A label deve permanecer exatamente:

```text
CAPEX Obras - Especialistas
```

### Recomendação de posicionamento

Manter como página própria dentro do grupo CAPEX Plano de Obras:

```text
CAPEX PLANO DE OBRAS
  • Resumo
  • CAPEX Obras - Especialistas
```

Essa opção reduz o risco de interferência de sessão, filtros, ordem de renderização ou experiência de uso.

### Não permitido

- alterar a label;
- remover conteúdo;
- mudar regra;
- mudar cálculo;
- renomear filtro;
- remover filtro;
- mudar coluna;
- mudar gráfico;
- mudar ordenação;
- simplificar informação;
- aplicar filtro global que altere o resultado atual;
- substituir a página por um resumo genérico.

### Permitido

Somente mudanças técnicas indispensáveis, com teste de regressão que demonstre que o comportamento permaneceu igual.

---

# 5. GESTÃO

## 5.1 Página Dados e Qualidade

Concentra:

- upload dos arquivos rotineiros;
- validação de estrutura;
- processamento;
- situação das cargas;
- histórico de versões dos arquivos;
- alertas de qualidade;
- reconstrução controlada do warehouse;
- restauração administrativa, quando autorizada.

Fluxo ideal:

```text
Upload
→ validação do arquivo
→ armazenamento da versão bruta
→ staging
→ validação dos totais
→ construção do warehouse
→ publicação da nova versão
→ auditoria e possibilidade de rollback
```

Alertas esperados:

- arquivo ausente;
- coluna ausente;
- layout incompatível;
- linha de subtotal;
- total geral duplicado;
- estorno;
- Projeto ou PEP sem correspondência;
- Conta sem descrição;
- Centro de Custo fora do escopo;
- divergência entre fontes.

Planilhas históricas usadas para descobrir regras não devem virar input obrigatório sem decisão explícita.

## 5.2 Página Administração

Concentra:

- Gestão de Usuários;
- perfis;
- permissões;
- escopos;
- ativação e inativação;
- troca obrigatória de senha;
- auditoria administrativa;
- configurações autorizadas.

Gestão de Usuários, Permissões e Auditoria podem existir como abas internas, sem ocupar itens independentes na sidebar.

---

# 6. Estrutura de filtros

## 6.1 Princípios

- filtros seguem a hierarquia do dado;
- opções inferiores dependem das superiores;
- permissões limitam as opções disponíveis;
- o drill-down preserva o contexto;
- páginas consolidadas compartilham o mesmo estado de filtros;
- a tela especialista de Obras não deve receber filtros globais que alterem seu comportamento atual.

## 6.2 Filtros do Plano de Manutenção

Ordem recomendada:

```text
Ano
→ Mês de referência
→ Visão mensal/acumulada/anual
→ GG
→ Gerência
→ Coordenação
→ Universo OPEX/CAPEX Sustaining
→ Pacote
→ Conta
→ Centro de Custo ou PEP
```

Filtros:

- Ano fiscal;
- mês de referência;
- período;
- Gerência Geral;
- Gerência;
- Coordenação;
- classificação contábil;
- família PM/PD/PP;
- Pacote;
- Conta;
- Centro de Custo;
- Elemento PEP;
- natureza ou área, quando confirmada.

Centro de Custo e PEP devem permanecer separados.

## 6.3 Filtros do CAPEX Plano de Obras

- Ano;
- mês/período;
- Gerência de Obras;
- Projeto;
- Elemento PEP;
- Classe de Custo;
- rubrica;
- classificação inicial;
- classificação atualizada;
- Renovação/Não Renovação;
- fase FEL, quando disponível;
- situação de orçamento/realização.

## 6.4 Controles de usabilidade

- botão “Limpar filtros”;
- resumo dos filtros ativos;
- defaults coerentes;
- opção de voltar sem perder o recorte;
- prevenção de combinações incompatíveis;
- labels indicando mês, acumulado ou anual;
- filtros técnicos escondidos do usuário quando não agregarem valor.

---

# 7. Matriz de preservação

| Área atual | Decisão | Destino recomendado |
|---|---|---|
| Visão resumo Executivo- GGSP | Preservar e reorganizar | Plano de Manutenção > Resumo > Visão Executiva |
| Painel Executivo da Manutenção | Preservar e reorganizar | Plano de Manutenção > Resumo > Desvios e Causas |
| Projeção Opex | Preservar integralmente | Plano de Manutenção > Resumo > Projeção |
| Visão Manutenção | Preservar | Plano de Manutenção > Análise Financeira |
| Pacotes | Preservar | Análise Financeira > Pacotes |
| Contas | Preservar | Análise Financeira > Contas e Centros de Custo |
| Centro de Custo | Preservar | Análise Financeira > Contas e Centros de Custo |
| CAPEX Manutenção | Preservar separado de Obras | Análise Financeira > CAPEX Sustaining |
| SAP | Preservar | Plano de Manutenção > Evidências SAP |
| Resumo Executivo de Obras | Unificar sem perda | CAPEX Plano de Obras > Resumo > Visão Executiva |
| Painel Executivo de Obras | Unificar sem perda | CAPEX Plano de Obras > Resumo > Desvios e Evolução |
| CAPEX Obras - Especialistas | Preservação absoluta | Página própria em CAPEX Plano de Obras |
| Upload e processamento | Preservar | Gestão > Dados e Qualidade |
| Administração | Preservar | Gestão > Administração |

---

# 8. Mudanças permitidas e proibidas

## Permitido

- mover funcionalidade para uma aba;
- retirar label duplicada do menu;
- reunir cards repetidos;
- compartilhar filtros;
- criar links entre análise, justificativa e SAP;
- melhorar responsividade;
- reaproveitar componentes existentes;
- reduzir repetição de títulos e gráficos.

## Permitido com validação de regressão

- unificar Resumo Executivo e Painel Executivo;
- centralizar Projeção Opex;
- unir Conta e Centro de Custo na mesma página;
- alterar componentes internos compartilhados;
- reorganizar estado de sessão.

## Proibido

- eliminar funcionalidade ao esconder uma página antiga;
- misturar CAPEX Sustaining com CAPEX Obras;
- inventar Forecast ou Real Físico;
- alterar fórmulas para forçar fechamento;
- transformar “Não Justificado” em input;
- quebrar o drill-down até SAP/CJI3;
- substituir a página de Login;
- alterar a experiência CAPEX Obras - Especialistas.

---

# 9. Login e segurança

A página de Login atual deve ser preservada visual e funcionalmente.

Não substituir por formulário genérico.

A aplicação deve manter:

- autenticação;
- sessão;
- usuário ativo/inativo;
- troca obrigatória de senha;
- recuperação de senha;
- permissões por página;
- escopo por usuário;
- auditoria;
- segredos fora do código.

Esconder um item na sidebar não substitui a validação de autorização na página e na consulta.

---

# 10. Checklist de comparação com o código atual

## Sidebar

- [ ] A sidebar possui somente os três grupos principais?
- [ ] Plano de Manutenção possui quatro páginas?
- [ ] CAPEX Plano de Obras possui Resumo e CAPEX Obras - Especialistas?
- [ ] Gestão possui Dados e Qualidade e Administração?
- [ ] Páginas antigas foram transformadas em abas sem perda de conteúdo?

## Plano de Manutenção

- [ ] Resumo possui Visão Executiva, Desvios e Causas e Projeção?
- [ ] Análise Financeira possui Pacotes, Contas e Centros de Custo e CAPEX Sustaining?
- [ ] Pendências possui Fila, Em elaboração, Consolidadas e Histórico?
- [ ] Evidências SAP preserva o recorte do drill-down?

## CAPEX Obras

- [ ] Resumo possui Visão Executiva e Desvios e Evolução?
- [ ] Resumo Executivo e Painel Executivo foram unificados sem perdas?
- [ ] CAPEX Obras - Especialistas permanece como página própria?
- [ ] Label, filtros, colunas, gráficos, fórmulas e ordenação foram preservados?

## Filtros

- [ ] Filtros seguem a hierarquia?
- [ ] Há distinção mensal, acumulada e anual?
- [ ] Conta, Centro de Custo e PEP permanecem conceitos distintos?
- [ ] O contexto é preservado entre abas e drill-downs?
- [ ] Obras utiliza filtros próprios de Projeto/PEP/Classe de Custo?

## Motor financeiro

- [ ] Delta = Realizado - Orçamento?
- [ ] Não Justificado é calculado?
- [ ] Waterfall fecha no Delta?
- [ ] Não existe dupla contagem Macro/Micro?
- [ ] Não existe mistura indevida entre universos financeiros?

## Segurança

- [ ] Login original preservado?
- [ ] Bypass desativado em produção?
- [ ] Permissões validadas além da sidebar?
- [ ] Segredos fora do repositório?
- [ ] Uploads e alterações auditados?

---

# 11. Recomendação definitiva

```text
PLANO DE MANUTENÇÃO

  Resumo
    Visão Executiva
    Desvios e Causas
    Projeção

  Análise Financeira
    Pacotes
    Contas e Centros de Custo
    CAPEX Sustaining

  Pendências e Justificativas
    Fila de Pendências
    Em elaboração
    Consolidadas
    Histórico

  Evidências SAP


CAPEX PLANO DE OBRAS

  Resumo
    Visão Executiva
    Desvios e Evolução

  CAPEX Obras - Especialistas
    Conteúdo atual integral, sem alterações


GESTÃO

  Dados e Qualidade
  Administração
```

## Síntese

A recomendação definitiva é:

- mudança ampla e integrada no Plano de Manutenção;
- consolidação moderada no Resumo de CAPEX Obras;
- preservação absoluta da experiência “CAPEX Obras - Especialistas”;
- Administração e cargas fora das análises financeiras;
- sidebar compacta, com complexidade dentro das páginas e abas;
- nenhuma perda funcional durante a reorganização.
