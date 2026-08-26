# Briefing para Validação Interna — Painel Executivo DINFRA (Orçamento x CAPEX)

> Este documento é pra ser lido por uma IA com acesso a informação interna
> da MRS (SharePoint, Teams, sistemas corporativos), pra ajudar a validar
> conceitos de negócio e localizar fontes de dado que um assistente sem
> acesso à rede da empresa não consegue confirmar sozinho. Não é
> documentação técnica de código — é uma lista de perguntas de negócio,
> com o contexto mínimo pra cada uma.

## Contexto do projeto

A Diretoria de Infraestrutura (DINFRA) da MRS está construindo um painel
executivo que explica automaticamente o desvio entre Orçado e Realizado
(CAPEX e OPEX), pra um Gerente Geral conseguir responder "qual o desvio,
onde está, por quê" sem depender do PMO a cada reunião. O painel já está
funcionando com dados reais (SAP, Consulta de Contas, exports CJI3/CJI4),
mas há pontos de linguagem e de fonte de dado que só alguém com acesso
interno à empresa consegue confirmar — é isso que este documento pede.

**Objetivo maior**: o painel precisa falar a **mesma língua** que o PMO já
usa nas apresentações pra Diretoria. Se os números ou os nomes de
categoria divergirem, o Gerente Geral que usa o painel pode ser
questionado numa reunião por mostrar um valor diferente do que o PMO
mostra — isso é o principal risco a evitar.

## Glossário rápido (pra situar quem for buscar)

| Termo | Significado no nosso projeto |
|---|---|
| DINFRA / GGG_0054 | Gerência Geral de Infraestrutura (SP) — o escopo do painel |
| Malha | Manutenção corrente da via permanente (trilhos, dormentes etc.) |
| Infra | Pequenas obras de infraestrutura (drenagem, saneamento vegetal) — universo distinto de Malha |
| Obras / Projetos | Grandes projetos de capital (CAPEX), acompanhados via metodologia FEL |
| OPEX | Despesas operacionais correntes (Manutenção, Pessoal, Despesas Gerais) |
| CAPEX | Investimento de capital — hoje dividido em "CAPEX Malha" (pequeno, ligado à manutenção) e "CAPEX Obras" (grande, projetos) |
| PMO | Escritório de projetos que consolida a visão pra Diretoria |
| Gestão Econômica | Área que fornece as bases de Orçado/Realizado (hoje nosso contato é a Alice) |
| CJI3 / CJI4 | Relatórios SAP de Realizado/Orçado de Obras que já carregamos |
| Consulta de Contas | Planilha que já carregamos como fonte de Orçado/Realizado de OPEX |

## Perguntas — Prioridade Alta

### 1. Onde está a planilha-mãe usada pelo PMO/Gestão Econômica?

Encontramos referência a um arquivo Excel chamado algo como **"00.
Acompanhamento Financeiro - DINFRA - Versão Trabalho.xlsx"**, que
consolidaria Orçamento, Realizado, Forecast, Portfólio e um de/para entre
SAP e Portfólio, com abas como `APOIO`, `orç+real`, `TAB_DePara_SAP_
Portfólio`, `Portfólio_Infra`, `Portfólio_DiPO`, `2 - Comite Financeiro` e
`1-Aderencia_Realizado_Forecast`.

**Pergunta**: esse arquivo existe hoje em algum SharePoint/Teams da MRS?
Quem mantém? Conseguimos acesso (mesmo que só leitura) pra reconciliar
números com o painel?

### 2. O que é o Centro de Custo CGG050?

No SAP, achamos uma linha de R$ 1,84 milhão de Orçado (2026, dentro do
pacote "Materiais e Serviços de Malha") lançada no Centro de Custo
**CGG050 (GER. GERAL DE INFRAESTRUTURA SP)**, com a coluna de Gerência
vindo com o valor `#GERENCIA INEXISTENTE` e a descrição do domínio como
"Indireto Manutenção".

**Pergunta**: o CGG050 é um centro de custo corporativo/indireto da GG,
que concentra verba ainda não distribuída entre as Gerências de campo?
Existe um relatório oficial do PMO que trata esse tipo de valor como "Não
Distribuído" (ou termo parecido)? Ele deveria entrar no Orçado "oficial"
que a Diretoria vê, ou é normalmente mostrado à parte?

### 3. Qual é a classificação oficial de portfólio de Obras?

No cadastro de projetos de CAPEX Obras que já carregamos, existem 2
colunas — "Classificação inicial" e "Classificação atualizada" — com
valores **A+1 até A+8** e **"Não renovação"**.

**Pergunta**: o que esses códigos significam (ex.: "A+1" é o ano do ciclo
de renovação em que o trecho está programado)? Além disso, existe também
uma categorização de Obras em **"Renovação / Infraestrutura /
Comerciais"** — é a mesma coisa que A+1..A+8, ou é um corte diferente e
independente?

## Perguntas — Prioridade Média

### 4. Existe fonte de dado pra CAPEX de pequenas obras de Infraestrutura?

O painel já cobre CAPEX de Malha (renovação de via) e CAPEX de Obras
(grandes projetos), mas não tem nenhuma fonte pra **CAPEX de Infra**
(pequenas obras de drenagem, saneamento vegetal etc.).

**Pergunta**: existe uma base/relatório separado pra isso dentro da
Diretoria de Infraestrutura? Em qual sistema é controlado (SAP, planilha
própria, outro)?

### 5. O que o módulo "Infra" do Power BI mostra?

Identificamos que a área usa um Power BI com módulos "Executivo, Infra,
PEP, Contratos, Portfólio, Prazo".

**Pergunta**: o módulo "Infra" desse Power BI cobre o mesmo universo da
pergunta 4? Qual a fonte de dado dele? O gráfico que mostra Orçado x
Realizado por região/domínio (ex.: um rótulo "SP" com % de aderência)
vem do módulo Executivo?

## Perguntas — Prioridade Baixa (confirmação de regra já assumida)

### 6. Regra de dígito da conta contábil

Estamos assumindo, com base numa conversa já tida com a Alice, que conta
contábil SAP começando em **"4" = OPEX** e **"5" = CAPEX** (administrativo).

**Pergunta**: essa é uma regra formal/documentada, ou só prática
informal da área? Existe exceção conhecida?

### 7. Taxonomia oficial de causa de desvio

Usamos hoje a lista: Físico, Efeito Preço, Não Previsto, Carry Over,
Ajuste Contábil, Realizado Não Contabilizado, Taxa Bom/Mix, Não
Justificado (validada contra uma RDG real de julho/2026).

**Pergunta**: essa é a lista única e oficial usada em todas as RDGs de
Diretoria da MRS, ou cada PMO/Gerência usa uma variação própria?

## Como usar as respostas

Qualquer resposta concreta (link de arquivo, definição confirmada, nome
de sistema) pode ser colada de volta na conversa com o assistente que
mantém este painel — ele vai cruzar com os dados já carregados e ajustar
o código/telas conforme a confirmação. Não é necessário responder tudo de
uma vez; cada pergunta é independente.
