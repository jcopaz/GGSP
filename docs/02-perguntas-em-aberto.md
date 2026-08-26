# 02 — Perguntas em Aberto

Estes pontos **não devem ser resolvidos por suposição no código**. Onde o
código precisar de uma decisão provisória, marcar com `# GAP:` e apontar para
esta seção.

## 1. Fonte de "Real Físico" — RESOLVIDO em 2026-08-06

~~Os dois documentos citam "Real Físico" como conceito já usado pelo PMO nas
RDGs (valor financeiramente equivalente ao executado), mas nenhum dos
arquivos recebidos até agora continha essa informação.~~

Confirmado pelo usuário: **Real Físico é a mesma Base Analítico SAP
(Realizado)** já carregada — não é uma fonte separada. O painel passa a
mostrar Real Físico = Real Contabilizado (mesmo valor). Se no futuro
surgir uma distinção real entre os dois (por exemplo, separar por tipo de
documento SAP — movimentação física "WE"/"WL" x fatura "RE" — ver colunas
"Tipo de documento"/"Denominação do tipo de objeto" no Base Analítico),
essa seção volta a ser reaberta.

## 2. Fonte de "Forecast" — RESOLVIDO em 2026-08-12

~~Mesma situação do item 1 — citado como indicador do Nível 1 (Diretoria),
sem arquivo de origem identificado ainda.~~

Usuário passou a fórmula oficial do PMO:

```
saldo = Realizado_Acumulado(mês_referência) - Orçado_Acumulado(mês_referência)
Forecast_mês = Orçado_mês - (saldo / nº meses restantes), para cada mês > mês_referência
```

O saldo do que já desviou do Orçado até o mês de referência é
redistribuído igualmente pelos meses restantes, subtraído do Orçado
original de cada um — por construção, o Forecast Acumulado de dezembro
sempre fecha exatamente no Orçado Anual (validado: R$48.911.482,38 =
R$48.911.482,38, bate ao centavo). É a "curva S de volta ao ritmo do
Orçado" que o usuário descreveu. Implementado em
`src/dashboard/tendencia.py::dados_tendencia` (e espelhado em
`capex_dados.py::dados_tendencia_capex`), substituindo a extrapolação
run-rate mecânica usada antes — propagou pra todas as páginas que já
mostravam Tendência (Painel Executivo, Nível 4/5, Visão Manutenção,
Resumo Executivo, CAPEX Painel).

## 3. Processo de preenchimento da causa (fact_explicacao)

Hoje a explicação existe como texto livre na tabela "Justificativas" do
Power BI, preenchida por alguém do time. Para o MVP vamos usar um CSV de
apoio (`data/staging/explicacoes.csv`), mas falta decidir o processo
definitivo:
- Quem preenche? PMO, Coordenação, ou o próprio GG?
- Com que periodicidade (mensal, por RDG)?
- Vai virar uma tela dentro do próprio painel (fase futura) ou continua
  sendo um arquivo de apoio mantido à parte?

**Estrutura proposta em 2026-08-10** (a pedido do usuário: processo pra
captar justificativa de estouro/economia dentro do próprio painel, por
Analista de Gerência, com histórico auditável) — ver
`docs/03-processo-justificativas-causas.md`. É só proposta de estrutura,
**não implementada ainda**; várias decisões de negócio dentro dela seguem
marcadas `[A CONFIRMAR]`, entre elas a regra de precedência Pacote x Conta
(evitar dupla contagem) e o threshold oficial de obrigatoriedade (ver item
18 abaixo).

## 4. Categoria "Taxa Bom/Mix"

Descrita como "categoria utilizada pelo PMO para CAPEX" sem uma definição
operacional tão clara quanto as demais (ex.: quais eventos específicos
entram nela). Vale confirmar com o PMO um exemplo real antes de expor essa
categoria na tela, para não ficar uma opção que ninguém sabe quando usar.

## 5. Escopo de dados (GGs)

Os arquivos que validamos até agora cobrem só Malha SP/VP (orçamento) e Ger.
Malha SP + Pessoal/Despesas (realizado). A estrutura de navegação prevê
SP/RJ/FA/LC — falta confirmar se os exports completos (todas as GGs) têm o
mesmo layout ou exigem ajuste no loader.

**Materializou em 2026-08-10**: um upload de Realizado trouxe 5 GGs
(GGG_0010, GGG_0029, GGG_0043, GGG_0054, GGG_0057), enquanto a Base Zero
carregada continua sem coluna própria de GG (`_atribuir_gg_orcamento`
mapeia pra 1 GG só quando existe exatamente 1 — com mais de 1, fica
ambíguo). Isso quebrava o Nível 1 (erro de merge float64 x str, porque a
coluna de GG do Orçamento fica 100% nula). Corrigido para não quebrar mais.

**RESOLVIDO (parcialmente) em 2026-08-10**: investigando a coluna
Diretoria (só existe na Consulta de Contas), descobrimos que os 5 GGs
**não são todos DINFRA**:

| GG | Diretoria |
|---|---|
| GGG_0010 — GG. PLANEJ E CONTR OPERAC | GDI_0002 — DIR DE OPERAÇÕES E TECNOL DA INFORMAÇÃO (TI/Operações, não é DINFRA) |
| GGG_0029 — OFF GER. GERAL DE IMPLANT. EMP. P&T (SP) | GDI_0007 — OFF DIR DE INFRAESTRUTURA (relacionado, código diferente) |
| GGG_0043 — OFF GG IMPLANT EMPREENDIMENTOS (SP) | GDI_0007 — OFF DIR DE INFRAESTRUTURA (relacionado, código diferente) |
| **GGG_0054 — GER. GERAL DE INFRAESTRUTURA (SP)** | **GDI_0008 — DIR DE INFRAESTRUTURA (2026)** |
| GGG_0057 — GER. GERAL GESTAO, PLANEJ. E CONT. INFRA | GDI_0008 — DIR DE INFRAESTRUTURA (2026) |

Usuário confirmou: este painel é escopado só a **GGG_0054**. Implementado
via `config/settings.yaml` (`gg_escopo_dinfra: ["GGG_0054"]`) — filtrado em
`build_star_schema.py` antes de qualquer dimensão/agregação, pra nenhuma
tela vazar total de fora do escopo. Efeito colateral bom: com 1 GG só de
volta, `_atribuir_gg_orcamento` volta a atribuir CAPEX corretamente (o
problema "CAPEX sem gg_id" também era consequência do escopo errado, não
só da Base Zero não ter coluna de GG).

**Ainda em aberto**: se GGG_0057 (mesma Diretoria, GDI_0008) deveria entrar
no escopo também, ou se DINFRA aqui é mesmo só a Gerência Geral específica
(GGG_0054) — usuário optou pela 2ª opção por enquanto. Se RJ/FA/LC
chegarem depois, adicionar em `gg_escopo_dinfra`, não hardcoded no código.

## 6. Nível de detalhe SAP (Nível 6)

A lista de campos do Nível 6 (Documento, NF, Fornecedor, Data, Valor, Texto
do Lançamento, Usuário, Centro de Custo, Pacote) parece coberta pelas
colunas já vistas no Base Analítico SAP — mas isso só será confirmado quando
essa fase for implementada (está fora do MVP, ver plano de build).

## 7. Fonte "SAC Planning" — NOVO, 2026-08-10

A Ata da Reunião 07/08 (`Conceito/Ata Reunião 07.08.md`) registra divergência
entre SAP, CJ3, PMO e SAC Planning como fontes de planejamento econômico, e
orienta usar **SAC Planning como fonte principal** daqui pra frente — não
Base Zero. Ainda não recebemos esse arquivo nem sabemos o layout. Até
chegar, o loader continua em Base Zero (fonte já validada); não trocar de
fonte por suposição.

## 8. Base Zero não é um arquivo único — NOVO, 2026-08-10

A mesma Ata cita ao menos 5 arquivos "Base Zero" distintos: Manutenção,
Despesas Gerais, Veículos, Pessoas, Serviços — "nem todos seguem a mesma
estrutura". `load_base_zero()` hoje assume um único layout (o de Malha SP,
já validado). Antes de ingerir qualquer um dos outros 4, confirmar se o
layout de colunas é o mesmo; se não for, `load_base_zero` precisa de um
parâmetro de variante ou de um loader por arquivo — não assumir compatível.

## 9. Módulo SAP de Ordem de Serviço (OS) / Ordem de Manutenção (OM) — NOVO, 2026-08-10

A Ata aponta que quase toda execução operacional de manutenção (o módulo
mais crítico hoje, OPEX Malha) passa por OS/OM, e que o time "ainda não
possui domínio completo deste módulo do SAP" — classificado como frente
obrigatória de investigação. Nenhuma das colunas de OS/OM está mapeada no
modelo de dados atual (nem em `fact_orcamento`/`fact_realizado`, nem no
Base Analítico SAP já carregado). Sem essa informação, o OPEX de Malha
continua sem rastreabilidade real (só orçado x realizado agregado, sem
saber qual atividade gerou o gasto).

## 10. Camada de catalogação (Contrato, Localidade, Pátio, Disciplina) — NOVO, 2026-08-10

A Ata propõe uma estrutura de catalogação em 4 grupos — Identificação
(CAPEX/OPEX, Infra/Malha, Gerência, Coordenação), Controle (Responsável,
Pacote, Conta, **Contrato**), SAP (PEP, **OM**, **OS**, Centro de Custo) e
Operação (**Localidade**, **Pátio**, **Disciplina**) — e um drill-down que
inclui Contrato entre Conta e Detalhamento. Nenhuma dessas dimensões novas
(Contrato, Localidade, Pátio, Disciplina) existe hoje no `dim_pacote`/
`dim_conta`/`dim_gg` do Orçamento. Não inventar essas colunas nem tentar
derivá-las de outra coluna existente — esperar confirmação de onde cada uma
vem (Base Zero? SAC Planning? cadastro à parte?).

## 11. Taxonomia de causa — três listas divergentes, NOVO, 2026-08-10

Existem hoje três listas de categoria de desvio circulando, com nomes
diferentes para conceitos parecidos:

| Fonte | Lista |
|---|---|
| RDG oficial (`CLAUDE.md`, spec consolidada) — a que o Orçamento implementa | Físico, Efeito Preço, Não Previsto, Carry Over, Ajuste Contábil, Realizado Não Contabilizado, Taxa Bom/Mix, Não Justificado |
| Ata 07/08 (dashboard proposto na reunião) | Físico, Preço, Reprogramação, Over, Ajuste contábil, Não realizado, Não justificado |
| Capex Control Center (`03_regras_negocio.md`, seção 5) | heurísticas algorítmicas: Antecipação, Postergação, Atraso de execução, Realizado sem orçamento, Orçamento sem realizado, Divergência de rubrica, Divergência de cadastro, Consumo de contingência, Saving |

**Não reconciliar por suposição.** A lista RDG (já usada em produção
conceitual no Orçamento e validada contra o PPT real da RDG de julho —
`Conceito/Reunião Performance DINFRA - Julho - Final.pptx`) é a mais
testada contra dado real e deve continuar sendo a fonte de verdade da UI
até confirmação explícita do PMO. A lista da Ata 07/08 parece ser a mesma
ideia com nomenclatura mais informal usada na reunião (Reprogramação ≈
Carry Over? Over ≈ Não Previsto ou Taxa Bom/Mix?) — mas isso é hipótese
nossa, não confirmação, e não deve virar código. As heurísticas do Capex
Control Center não são uma quarta taxonomia paralela: devem virar sugestão
automática de qual categoria RDG marcar, nunca um rótulo próprio exposto
na tela.

## 12. Elemento PEP — RESOLVIDO PARCIALMENTE em 2026-08-10

O campo `"Centro de Custo/PEP"` da Base Zero era tratado como um único
`centro_custo_id`. Investigando os 19 valores reais, achamos um padrão
100% consistente: código sem "/" (formato `CCRxxx`/`CGExxx`) é Centro de
Custo de verdade (bate 1:1 com o Realizado); código com "/" (ex.:
`"ME/22001"`, `"MC/24004C-04-02-05 (CREMALHEIRA-SP-IPA-Cremalheira)"`) é
Elemento PEP — e essa divisão bate exatamente com `Classificação
contábil` (CAPEX sempre tem "/", OPEX nunca tem), confirmando a regra que
a Ata 07/08 já descrevia. Implementado em
`_dividir_centro_custo_pep` (src/ingestion/loaders.py) — vira filtro de
sidebar "PEP", mas só do lado do Orçamento.

**Ainda em aberto:** por que o campo próprio de PEP no Realizado (SAP)
continua 100% vazio (0/5253 linhas)? É um problema de export/parametrização
do relatório Base Analítico SAP, ou a Malha realmente não lança PEP nas
notas/documentos de CAPEX? Vale confirmar com a Alice/PMO antes de tentar
qualquer correção — não é algo pra resolver adivinhando no código.

## 14. Regra de CAPEX/OPEX para o Realizado — validada, ainda não implementada (reunião 2026-08-10, Julio/Alice)

Alice confirmou a regra usada na prática: `conta_razao_id` começando em
**"4" = conta contábil operacional (OPEX)**, **"5" = conta contábil
administrativa (CAPEX — "se lança separado, sobe nível de aprovação")**,
**"52" = comercial**, **"3" = legado Oracle, não usar**. Testei contra o
`fact_realizado` carregado: dígito 4 = R$22,79 MM (94% do valor), dígito 2 =
R$1,38 MM (bate com o pseudo-pacote "PASSIVO" que já aparece no ranking do
Nível 3 — provável classe de Passivo/balanço, não coberta pela explicação
da Alice), dígito 5 = R$1.248,62 (quase nada — bate com o que a Jaquicele
confirmou ao vivo: "capex ainda não tô controlando"). Regra validada, mas
não implementada ainda — decisão de quando/como aplicar ficou em aberto
(usuário optou por só registrar nesta rodada).

## 15. Catálogo "Consulta Contas" — De/Para Conta Razão → Pacote (existe, ainda não recebido)

Alice mostrou uma aba/relatório real chamado "Consulta Contas" que mapeia
Conta Razão SAP → Pacote (PD/PM) — exatamente o De/Para que falta pro
Nível 4 parar de abrir em duas subárvores separadas (Base Zero e Razão SAP
usam vocabulários diferentes, ver `nivel4_contas.py`). Segundo Alice, o
catálogo é praticamente estático (atualiza a cada 1-2 meses, só quando um
material novo e muito específico é cadastrado). Ainda não recebemos o
arquivo — não implementar De/Para nenhum sem ele.

## 16. Pedido de feature: visão em tabela (não é gap de dado, é backlog)

Alice: gerentes se adaptam melhor a formato tabela do que gráfico, e isso
ajuda na pré-reunião de confirmação de números com cada gerência antes da
RDG. Vale adicionar uma visão tabular (Orçado/Realizado/Delta por GG ou
Pacote) ao lado dos gráficos existentes — ainda não implementado.

## 17. Desenho de justificativa em 2 campos separados (decisão de design, não de dado)

Julio e Alice alinharam: quando a tela de input de causa existir (hoje é
só CSV de apoio, ver item 3), deve ter **2 campos separados, não
concatenados** — "justificativas de pacote" (espelha o flag atual que a
Laís/PMO usa, preenchido por analistas como a Jaque) e "justificativas de
conta/centro de custo" (mais fino, pra rastreabilidade, mesmo que uma
única linha baste). Não implementar a tela ainda (fora do MVP), só
registrar a decisão de formato pra quando ela for construída.

## 18. Threshold de materialidade real diverge do documentado

**RESOLVIDO em 2026-08-10** — não era divergência, eram 2 domínios
diferentes: R$100 mil é o threshold de **OPEX** (nível Pacote/Macro,
Analista de Gerência); R$500 mil é o threshold de **CAPEX** (Obras e
Projetos, dono é o Especialista de Obras/Projetos da Gerência, não a
Analista — `src/engine/semaforo.py` usa esse limiar pro status Roxo, que
hoje mistura os 2 domínios sem distinguir). Ver detalhe completo e a regra
do nível Micro (Conta, 100% sempre justificado, sem threshold) em
`docs/03-processo-justificativas-causas.md`, seção 3.3. `semaforo.py`
ainda não foi ajustado pra diferenciar OPEX x CAPEX — fica pendente pro
código quando a captação de justificativas for implementada.

## 19. Riscos de qualidade de dado observados ao vivo (reunião 2026-08-10)

Não corrigir nenhum destes por suposição — são casos reais que precisam de
decisão de negócio, não de código:

- Aluguel de caminhão (destinado à manutenção/PM) caiu no PD02 (Despesas
  Gerais) por causa da classificação da nota fiscal na entrada, não da
  intenção orçamentária — atribuição de pacote pode divergir do
  planejado por decisão de quem lança a NF.
- Frota/veículos: defendida em CAPEX no orçamento, mas a Contabilidade
  classifica como OPEX ("bem de uso da empresa") — conflito real e
  reconhecido pela própria Alice. É exatamente o caso de uso da "tabela de
  overrides aprovada pela Controladoria" do Finance Control Center (ver
  item 13) — não é hipotético, já está acontecendo.
- "Despesas Gerais" x "Opex Infra": a Laís faz uma divisão manual (~30%)
  fora do sistema, por volta do dia 18-19 do mês — processo não
  documentado formalmente até agora.
- Contas começando em "3" (legado Oracle) e itens com descrição em branco
  (estoque de imobilizado obsoleto) são candidatos a filtro de dado sujo —
  não filtrar sem confirmar que não há exceção legítima.

## 20. Arquivos pendentes (ação combinada com Alice em 2026-08-10)

- Catálogo "Consulta Contas" (De/Para Conta Razão → Pacote) — item 15.
- ~~Planilha real do flag de justificativa~~ — **RECEBIDA em 2026-08-10**
  (`data/raw/SP - Flag.xlsx`), lida e mapeada em
  `docs/03-processo-justificativas-causas.md`, seção 8. Só 1 de 59 linhas
  tem dado real preenchido — achados são preliminares, ainda faltam
  confirmar com a Jaque/Laís: o que significa a coluna "Tipo" (ex.: "Manut
  VP"), se o nível "Micro" na prática é por `conta_interna_id` exata ou por
  um bucket mais largo ("Classif. Conta", ex.: "Indiretos - Serviço"), e se
  os 4 valores da lista "Justificativa PMO" que não estão em
  `categorias_causa` (Não considerar, Físico replanejado, Combustível,
  Pendências 2025) precisam entrar na taxonomia oficial.
- Confirmação com o Luís de 2 arquivos de Base Zero de CAPEX (um de
  vagões/eletroeletrônica/via, outro vinculado a Centro de Custo — este
  pode estar desatualizado, a Drenagem migrou de Obras pra Malha e a
  planilha não foi atualizada).
- Confirmação se CJ8 é o "Orçamento liberado" (Base Zero de CAPEX Obras).
- O "OnePage"/Overview que o Douglas Ito recebeu (blocos: Drenagem,
  Sustaining, Malha, Infra, Obras, Despesas) — referência visual de como a
  Diretoria já vê o consolidado hoje.

## 13. "Finance Control Center (MRS).md" — entendimento trazido em 2026-08-10

Documento externo (evolução do Capex Control Center, mesma origem do
`bootstrap_fcc.py`) trouxe itens novos que não tínhamos em lugar nenhum —
nenhum tem fonte de dado carregada aqui ainda, então ficam registrados como
gap, não implementados por suposição:

- **Categorias internas de CAPEX**: Pré-Obra, Obra, Contingência,
  Escalation, Mão de Obra, Rateio, Capitalização — dimensão nova, ortogonal
  a Bloco/Pacote. Não sabemos de que coluna da fonte isso viria.
- **Chaves de integração propostas** (ainda não aplicáveis — não temos SAC
  Planning nem export SAP PS/PM carregados): CAPEX `[exercício, PEP]` ou
  `[projeto, PEP, conta/contrato]`; OPEX `[exercício, mês, centro_custo,
  conta_contábil, OM/OS]`; Planejamento x Realizado `[exercício, mês,
  pacote/centro_custo/conta]` + enriquecimento por PEP/OM/OS.
- **Duas taxonomias de desvio são deliberadas, não um erro de nomenclatura**:
  o documento chama a lista de 7 categorias (Físico, Preço, Reprogramação,
  Over, Ajuste contábil, Não realizado, Não justificado) de "camada
  gerencial", distinta da lista RDG de 8 categorias que o Orçamento já usa.
  Isso não resolve o item 11 sozinho, mas muda a pergunta pro PMO: não é
  "qual lista está certa", é "quando cada uma se aplica".
- **Tabela de overrides de classificação CAPEX/OPEX, aprovada pela
  Controladoria** — governança de reclassificação com log/evidência (AFE,
  notas técnicas). Não construir sem confirmar o processo real primeiro.
- **Salvaguarda a registrar como princípio**: *"a pré-classificação serve
  para gestão analítica e não substitui julgamento contábil"* — o painel
  não deve virar ferramenta de reclassificação contábil oficial.

## 21. CAPEX de Projetos e Obras (CJI4 + CJI3) — carregados em tabelas separadas — RESOLVIDO em 2026-08-12 (escopo confirmado)

`CJI4.xlsx` (financeiro Orçado/Planejado, R$1,008 bilhão),
`Catalago CAPEX Obras.xlsx` (cadastro de projeto: nome, Gerência,
coordenadas) e `CJI3 ... EXPORT ....xlsx` (financeiro Realizado, R$438,47
milhões, recebido em 2026-08-11 — o Realizado que faltava). Carregados em
`fact_cji4_capex_obras`/`fact_cji3_capex_obras`, **sem entrar em
`fact_orcamento`/`fact_realizado`** — não mais por dúvida de escopo, e
sim porque são universos financeiros diferentes (ver item 22: "Projetos"
x "Manutenção Corrente").

**Escopo DINFRA confirmado em 2026-08-12.** Investigação: cruzamos os 66
projetos do CJI4 contra `TAB_DePara_SAP_Portfólio` (planilha-mãe do PMO)
e contra a "Relação de Centro de Custo - DINFRA" (mapeamento oficial de
Centro de Custo do GGG_0054, trazido pelo usuário) — achamos 2
correspondências fortes por nome de projeto (Pederneiras↔GER.IMPLANT.
OBRAS EXP.-PEDERNEIRAS, Mobilidade Urbana↔GER.IMPLANT.DE OBRAS(SP)
[Mobilidade Urbana]), mas 2 grupos ficaram sem confirmação só por
inspeção: os 22 projetos rotulados "GG Implant Empreendimentos (MG/RJ)"
no de/para (fisicamente no Vale do Paraíba/SP) e os 4 projetos sem
de/para nenhum (R$310,4 MM — Terminal Pederneiras/São Simão/São Bento,
reparos Bracell). **Usuário confirmou diretamente: todas as obras (os 66
projetos, sem exceção) estão dentro da GGG_0054/DINFRA.** Não é mais
necessário aplicar filtro de exclusão nenhum — as 5 Gerências de Obras
(Expansão, Obras Ferroviárias, Baixada Santista, Mobilidade Urbana,
Corredor São Paulo) são todas DINFRA.

Achados técnicos, já resolvidos: os nomes dos 2 arquivos originais (CJI4/
Catálogo) chegaram trocados (usuário confirmou e corrigiu); a chave que
liga financeiro↔catálogo é `Definição do projeto` = `E_PEP`, bate 100%
(66/66); o export CJI4 tem 1 linha de "subtotal" por Objeto que duplica a
soma das linhas de detalhe — excluída no loader, senão o total dobrava
(R$3,02 bi em vez de R$1,008 bi); o export CJI3 tem uma flag `estornado`
(lançamento revertido no SAP, 218 documentos/R$39,3 MM) excluída por
convenção padrão de relatório CJI3, e uma linha de total geral no final
do arquivo (R$477,79 MM) que também duplicava se não excluída; 27 dos 29
códigos de `Classe de custo` já batem com o Catálogo de Contas existente,
reaproveitado pra dar nome via `conta_interna_id`. Cruzamento por
`e_pep_projeto`: 22 projetos têm Realizado sem Orçado correspondente no
CJI4 (e vice-versa) — não investigado a fundo ainda, registrar se isso
importar quando o escopo DINFRA for confirmado.

## 22. Os 3 universos financeiros de DINFRA (diagrama do usuário, 2026-08-11) — CAPEX Infra ainda sem fonte

Usuário trouxe um diagrama (Portfólio → Projetos / Manutenção Corrente)
que confirma e organiza o que os itens 13/21 já vinham apontando em
pedaços soltos. Estrutura confirmada:

1. **Manutenção Corrente → OPEX** (Despesas Gerais / Manutenção / Pessoal)
   — já carregado, é `fact_orcamento`/`fact_realizado` com
   `classificacao_contabil='OPEX'` (pacotes PD/PM/PP, fonte Consulta de
   Contas). Painel: seção "OPEX".
2. **Manutenção Corrente → CAPEX → Malha** — já carregado, sem saber que
   já cobria isso: é o CAPEX da Base Zero (`fact_orcamento` com
   `classificacao_contabil='CAPEX'`, R$43,07 MM, campo `area` = literalmente
   `"Malha Capex"`, pacote PM03, materiais/serviços de renovação de via —
   dormente/trilho/AMV/cremalheira). Até 2026-08-11 estava dentro da seção
   "OPEX" do sidebar como "Visão CAPEX" — reorganizado pro usuário nesta
   mesma data pra virar seção própria "CAPEX Manutenção (Malha e Infra)",
   página "CAPEX Manutenção — Malha" (`visao_classificacao.py`).
3. **Manutenção Corrente → CAPEX → Infra** (Drenagem, Saneamento Vegetal,
   pequenas obras) — **sem fonte carregada**. Não achei nada com esses
   termos em nenhum arquivo já recebido (Base Zero, Consulta de Contas,
   CJI4/CJI3). Pode ter relação com o item 8 (Base Zero não é 1 arquivo só
   — existem variantes "Manutenção, Despesas Gerais, Veículos, Pessoas,
   Serviços") ou com a observação já registrada no item 20 ("a Drenagem
   migrou de Obras pra Malha e a planilha não foi atualizada"). **Pedido à
   Alice/PMO em 2026-08-11, aguardando retorno** — não inventar fonte nem
   tentar achar por adivinhação dentro dos arquivos já carregados de novo.
4. **Projetos → CAPEX (Capex Control Center, metodologia FEL)** — já
   carregado via CJI4 (Orçado) + CJI3 (Realizado), ver item 21. Painel:
   seção "CAPEX Projetos (Obras)".

**Investigação de escopo em 2026-08-12 — parcialmente resolvida.** Usando
a aba `TAB_DePara_SAP_Portfólio` da planilha-mãe do PMO (chave `CÓDIGO
SAP` = nosso `e_pep_projeto`), cruzamos os 66 projetos do CJI4:

| Grupo | Projetos | Orçado |
|---|---|---|
| GG Implant Empreendimentos (SP) | 40 | R$ 677,4 MM |
| GG Implant Empreendimentos (MG/RJ) | 22 | R$ 20,4 MM |
| Sem de/para nessa aba | 4 | R$ 310,4 MM |

Cruzando por nome de projeto contra a "Relação de Centro de Custo -
DINFRA" (mapeamento oficial do GGG_0054 trazido pelo usuário em
2026-08-12), achamos 2 correspondências fortes (nomes de projeto batem
literalmente, não é suposição):
- `GER. IMPLANT. OBRAS EXP. - PEDERNEIRAS` (CC "COORD. OBRAS PEDERNEIRAS
  (SP)") ↔ projetos "Expansão"/Pederneiras do catálogo CJI4.
- `GER. IMPLANT. DE OBRAS (SP) [Mobilidade Urbana]` ↔ "Gerência de
  Implantação de Mobilidade Urbana (SP)" do catálogo CJI4.

**Ainda não resolvido**: os grupos "Baixada Santista"/"Obras Ferroviárias"
do catálogo CJI4 não têm correspondência clara confirmada contra a lista
oficial de Centro de Custo (são 2 hierarquias diferentes — Centro de
Custo/Malha x "Implantação de Empreendimentos"/Obras, relacionadas mas
não a mesma árvore); o grupo "MG/RJ" (22 projetos, cidades do Vale do
Paraíba — Guaratinguetá, Aparecida, Caçapava etc.) não foi confirmado
como dentro ou fora do escopo DINFRA; e os 4 projetos sem de/para
(R$310,4 MM — Terminal Pederneiras, Terminal São Simão, Terminal São
Bento, reparos Bracell) continuam sem resposta. **Não aplicar filtro de
escopo em `fact_cji4_capex_obras`/`fact_cji3_capex_obras` até esses 3
pontos serem esclarecidos** — ver CSV completo do cruzamento salvo no
scratchpad da sessão (`cruzamento_escopo_obras.csv`) se precisar
reconstruir a análise.

**Sub-categorização "Obras Renovação / Obras de Infraestrutura / Obras
Comerciais"** (citada pelo usuário pro universo Projetos) não foi
encontrada como campo explícito nem no Catálogo CAPEX Obras carregado
(`classificacao`/`grupo` = tipo de custo: Serviços, Engenharia, Materiais,
Capitalização, Contingência etc. — bate com o item 13, "Categorias
internas de CAPEX", não com Renovação/Infraestrutura/Comercial) nem na
documentação do Capex Control Center (`agente/KnowledgeBase_v1/
09_classificacao_capex.md`, `14_modulo_portfolio.md` — ainda em esqueleto,
fase Sprint 0). O único campo próximo é `origem` (Catálogo CAPEX Obras):
só 2 valores, "Renovação"/"Não-renovação" — bate parcial (falta o corte
Infraestrutura x Comercial). Não usar essa aproximação em tela nenhuma sem
confirmar com o usuário/PMO se é o mesmo conceito.

**Achado em 2026-08-11 (2ª rodada, lendo a KB do Capex Control Center):**
o `Catalago CAPEX Obras.xlsx` tem 2 colunas que `load_catalogo_capex_obras`
**não carrega hoje** — `Classificação inicial` e `Classificação
atualizada` — com valores **A+1 até A+8** e **"Não renovação"**. Bate
exatamente com `agente/KnowledgeBase_v1/14_modulo_portfolio.md` do Capex
Control Center ("Classificações: A+1..A+8, Não Renovação"). Essa é
provavelmente a classificação oficial de portfólio (provável leitura:
"em qual ano do ciclo plurianual de renovação da via aquele trecho está
programado" — não confirmado). **Não é a mesma coisa** que "Obras
Renovação/Infraestrutura/Comerciais" do diagrama do usuário — são 2
conceitos que podem ou não se relacionar, não presumir sem confirmar.
Também achamos `agente/01_entendimento_planilha.md` citando a planilha-mãe
do PMO (`00. Acompanhamento Financeiro - DINFRA - Versão Trabalho.xlsx`,
aba `TAB_DePara_SAP_Portfólio`) como o de/para oficial SAP×Portfólio×
Classificação — se essa planilha existir num SharePoint/Teams acessível,
é o caminho mais direto pra fechar essa pergunta (e possivelmente também
a aba `Portfólio_Infra`, candidata a fonte do CAPEX Infra que falta — ver
[[reference_capex_control_center_kb]] na memória pra detalhe completo).

**Atualização em 2026-08-11 — retorno do Copilot (M365, busca interna
MRS) sobre `docs/briefing-copilot-validacao.md`:**

- **Planilha-mãe do PMO — localizada, confiança alta.** O Copilot achou
  o arquivo exato (`00. Acompanhamento Financeiro - DINFRA - Versão
  Trabalho`) e, mais importante: **o Douglas Ito já compartilhou esse
  arquivo com o Julio por Teams/e-mail**, e existe uma cópia "modificada
  por Julio Paz" — ou seja, é possível que já esteja acessível sem
  precisar pedir a ninguém. Ainda não recebemos o arquivo em si — só a
  confirmação de que ele existe e onde procurar.
- **CAPEX Infra — fonte localizada, confiança alta.** Existe uma família
  de arquivos **"Base Zero Infra 2026 _ Capex e Opex"** (uma variante:
  "...enviado dia 09-01 - com preço - Confisco de topografia"), com abas/
  campos explícitos "Infra Capex", "Infra Opex", "Drenagem", "Bueiros",
  "Obras", "Saneamento". **Confirmado que ainda não está em `data/raw/`**
  (conferido em 2026-08-11) — precisa ser obtido e trazido antes de
  qualquer loader ser escrito (não supor layout sem o arquivo real).
- **A+1..A+8 / Não Renovação — reforçado**, mesma conclusão que já
  tínhamos (classificação de portfólio/ciclo de renovação, não tipo de
  obra).
- **"Renovação/Infraestrutura/Comercial" como eixo separado de A+1..A+8**
  — isso é **hipótese do próprio Copilot** ("hipótese muito consistente
  com o que apareceu na base"), não uma citação de fonte confirmada. Não
  tratar como resolvido.
- **CGG050 — mecanismo explicado, tratamento no painel implementado em
  2026-08-12, mas confirmação formal ainda pendente.** Usuário trouxe o
  mapeamento oficial completo de Centro de Custo do GGG_0054 ("Relação de
  Centro de Custo - DINFRA"): **CGG050 é literalmente o Centro de Custo da
  própria GG** ("OFF/GER. GERAL DE INFRAESTRUTURA (SP)"), não pertence a
  nenhuma das 8 Gerências de campo — explica por que cai em `gerencia_id
  IS NULL`/`#GERENCIA INEXISTENTE` (estrutural, não erro de cadastro). As
  8 Gerências oficiais batem quase 1:1 com as 9 que já carregamos via
  `gerencia_raw`/`gerencia_nome` — confirma que o OPEX/Malha já estava
  correto. Usuário levantou a hipótese de ser um Centro de Custo
  **desabilitado** — descartada por enquanto (tem orçamento ativo em
  2026, R$1,84 MM, e aparece normal na relação oficial, sem marcação de
  inativo), mas **não é 100% confirmado ainda**: só a Laís Machado pode
  confirmar o status/tratamento oficial no SAP, e ela está de férias.
  Enquanto isso, o painel já mostra o valor "sem Indireto GG (CGG050)"
  como card auxiliar no Nível 5 — Centro de Custo (ver
  `nivel5_centro_custo.py::_render_card_nivel5`), pra não precisar
  subtrair na mão toda vez que o PMO pedir esse número. **Pendência
  formal**: confirmar com a Laís Machado quando ela voltar de férias se
  o tratamento (excluir CGG050) está correto, se é assim que o PMO
  realmente calcula, e se existe algum outro Centro de Custo com o mesmo
  papel (ex.: um CGG-equivalente pra outras GGs, se o escopo crescer).
- **Regra conta 4=OPEX/5=CAPEX** — confirmado como prática validada pelo
  PMO, sem procedimento corporativo formal documentado (mesmo status de
  antes, só reforçado).
- **Taxonomia de causa** — confirmado que a lista RDG que já usamos é a
  dominante nos materiais encontrados, mas não é prova de taxonomia única
  pra toda a MRS (mesma conclusão que já tínhamos).
