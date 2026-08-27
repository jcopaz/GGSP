# 04 — Lições Aprendidas e Incidentes

Prática adotada em 2026-08-17, a pedido do usuário — mesmo padrão já usado
no app irmão Gestão_OS/SGO Workforce (`docs/84_LICOES_OPERACIONAIS_E_
INCIDENTES.md` lá). Registrar aqui todo incidente real corrigido (bug
relatado, interpretação errada de especificação, decisão revertida) com
causa raiz, correção e lição — não é changelog de feature, é o que evitaria
o erro se alguém (ou o próprio Claude) ler antes de mexer de novo no mesmo
ponto.

---

## 1. `algum_filtro_ativo()` ficou referenciando chave de sessão antiga depois de o Período virar multiselect

**Causa raiz**: ao converter o filtro de Período de árvore em cascata
(`filtro_periodo_ano`, singular, 1 valor) para 3 multiselects independentes
(`filtro_periodo_anos`, plural, lista), atualizei o widget e o
`clausula_periodo()` mas esqueci de atualizar a referência dentro de
`algum_filtro_ativo()`, que continuou lendo a chave singular antiga —
função ficaria sempre `False` pra Período mesmo com filtro aplicado.

**Correção**: pego em revisão antes de entregar, não em produção — busquei
todas as ocorrências de `filtro_periodo_` no arquivo antes de considerar o
refactor pronto.

**Lição**: ao renomear uma chave de `st.session_state`, dar `grep` no
arquivo inteiro por todas as ocorrências antes de considerar o refactor
concluído — não confiar só nas funções que estão sendo ativamente editadas
na hora. Ver `src/dashboard/filtros.py`.

---

## 2. Filtro assimétrico (existe só num lado do Delta) distorce a comparação Orçado x Real enquanto ativo

**Causa raiz**: o filtro de Classificação Contábil (CAPEX/OPEX) só existe
em `fact_orcamento` — `fact_realizado` não carrega essa coluna por linha.
Aplicado, o filtro encolhe só o lado Orçado; o Realizado permanece cheio
(CAPEX+OPEX misturados). Isso já era um padrão aceito antes (Coordenação/
Gerência são "só Realizado", o inverso), mas é fácil esquecer que gera
Delta comparando fatias diferentes.

**Correção**: não é bug a corrigir — é comportamento esperado e já
documentado. A mitigação foi deixar explícito na UI (`help=` no selectbox:
"Só Orçamento — Realizado (SAP) não carrega Classificação Contábil por
linha") e no docstring do módulo.

**Lição**: sempre que um filtro novo só existir num lado de uma comparação
Orçado x Real, avisar isso na própria UI (não só em comentário de código) —
o usuário vendo o número na tela precisa saber que aquele Delta não é
"maçã com maçã" enquanto o filtro estiver ativo. Ver
`src/dashboard/filtros.py` (seção do filtro de Classificação) e
`src/dashboard/nivel4_contas.py`/`nivel5_centro_custo.py` (onde ele é
aplicado só no lado Orçado).

---

## 3. "Gerência sempre indisponível pro CAPEX" era gap temporário, não decisão de arquitetura fechada

**Causa raiz**: `_atribuir_gg_orcamento` (build_star_schema.py) fixava
`gerencia_id = NA` pra todo o CAPEX da Base Zero, com um comentário GAP
bem documentado ("não dá pra supor... nunca inventada"). Isso é correto
enquanto não existe informação — mas o comentário lia como se fosse
definitivo, e quase virou "não tem solução" na cabeça de quem lesse depois.

**Correção**: o usuário trouxe `catalogo_pep_financial_control_center.xlsx`
(de-para PEP → Gerência, 2 regras específicas) e depois confirmou
diretamente que a granularidade real precisa é por região inteira, não por
PEP: toda a fatia "SP" é da Gerência do Jefferson Luders (GER MALHA (SP),
GGE_0025) e toda a fatia "VP" é da Gerência do Vinicius Nascimento (GER
IMPLANT DE OBRAS E MALHA VP, GGE_0197) — sem terceira Gerência no Plano de
Manutenção. Isso fechou R$ 43,07M dos R$ 45,02M que estavam em "Não
atribuído" (só sobrou R$ 1,95M de OPEX sem PEP/região, que é um gap
diferente: falta na origem, não falta de regra).

**Lição**: um comentário `# GAP` no código documenta o que falta HOJE, não
uma decisão permanente — quando o usuário traz uma planilha/catálogo novo
ou confirma uma regra de negócio, checar se ela fecha (total ou
parcialmente) um GAP já documentado antes de assumir que "não tem como
resolver" continua valendo. Ver `_GERENCIA_ID_POR_REGIAO_BASE_ZERO` em
`src/model/build_star_schema.py`.

---

## 4. Catálogo de-para trazido pelo usuário nem sempre tem a granularidade que fecha o gap

**Causa raiz**: o catálogo novo (`catalogo_pep_financial_control_center.xlsx`)
mapeia **PEP individual → Gerência** (funciona pra MC/24004 e MC/24005,
PEPs próprios de Eletroeletrônica). Mas 95%+ do valor sem Gerência estava
dentro de um único PEP agregado (`ME/22001`, "Malha Capex"), sem
granularidade de PEP nenhuma — o catálogo, do jeito que foi entregue,
fechava só R$ 6,17M dos R$ 45,02M.

**Correção**: em vez de tentar forçar o catálogo PEP→Gerência a cobrir o
resto, voltei pro usuário com a pergunta certa ("qual Gerência formal é a
do Jefferson/Vinicius?") e ele confirmou que a regra real é por região
inteira (SP/VP), não por PEP — resolvendo o problema com uma regra mais
simples e mais ampla do que o catálogo original sugeria.

**Lição**: quando um catálogo/planilha de-para só fecha uma fração pequena
de um gap conhecido, não presumir que a granularidade dele é a única
saída — mapear onde está o volume que falta (`GROUP BY` no que sobrou) e
perguntar ao usuário se existe uma regra mais grosseira (região,
disciplina, etc.) que cobre o resto. Nunca inventar esse mapeamento sem
confirmação explícita — é decisão de organograma, não coisa que dá pra
inferir dos dados.

---

## 5. Data de modificação de arquivo não é prova confiável de "isso foi atualizado agora"

**Causa raiz**: ao investigar qual planilha o usuário tinha acabado de
atualizar ("Planilhas dos Projetos Capex do Plano de Manutenção foi
atualizada"), havia múltiplos arquivos em `data/raw/` com datas de
modificação recentes e nomes plausíveis — nenhum deles óbvio o suficiente
pra escolher sem risco de errar (e errar aqui significa analisar dado
errado e levar número furado pro usuário).

**Correção**: em vez de escolher pela data mais recente, perguntei
diretamente ao usuário (`AskUserQuestion`) qual arquivo era. A resposta
(`catalogo_pep_financial_control_center.xlsx`) nem era a mais óbvia pela
data isoladamente — era a mais recente, mas isso só ficou claro depois de
perguntar.

**Lição**: quando existir mais de um arquivo candidato pra "a planilha que
foi atualizada" e a análise for de dado financeiro que vai virar decisão
real, confirmar explicitamente com o usuário em vez de escolher pela data
de modificação — o custo de perguntar é 1 mensagem, o custo de analisar a
fonte errada é confiança perdida no número inteiro.

---

## 6. Estado do app muda muito entre uma pergunta e outra na mesma conversa — não confiar em leitura antiga

**Causa raiz**: no início desta conversa, `app.py` tinha navegação simples
(7 páginas, ~369 linhas). Quando o usuário pediu pra atualizar a análise de
CAPEX Manutenção, o mesmo arquivo já tinha 548 linhas, navegação
reestruturada em 2 seções ("Plano de Manutenção"/"Plano de Obras") e 6+
módulos novos (`capex_dados.py`, `capex_painel.py`, `capex_resumo.py`,
`capex_contas.py`, `capex_rastreabilidade.py`, `visao_classificacao.py`)
que eu não tinha lido ainda.

**Correção**: antes de responder sobre "o que a página X mostra hoje", reli
`app.py` e os módulos relevantes do zero, em vez de confiar no que tinha
visto mais cedo na mesma conversa.

**Lição**: passagem de tempo real entre mensagens do usuário (mesmo dentro
da "mesma conversa") pode significar horas ou dias de trabalho no projeto
por fora — sempre reler arquivos-chave (navegação do app, schema do banco)
antes de fazer afirmação sobre "o que existe hoje", principalmente quando a
pergunta é sobre um dado financeiro que vai embasar decisão real.

---

## 7. Técnica que funcionou bem: `AppTest` contra o DuckDB real, sem navegador

Validar mudança de filtro/sessão do Streamlit (botões Aplicar/Limpar,
multiselect de Período, filtro CAPEX/OPEX, correção do gap de Gerência) foi
feito rodando `streamlit.testing.v1.AppTest` contra o `painel.duckdb` real
(não mockado), simulando clique/seleção de widget e conferindo
`st.session_state` e os números resultantes — sem precisar de navegador.
Pegou bugs reais (SQL gerado errado, exceção em runtime) antes de reportar
qualquer coisa como pronta. Mesmo padrão já usado no SGO Workforce
("sempre lança exceção real, verificado com AppTest"). Vale continuar
usando pra qualquer mudança em `filtros.py`, `nivel*.py`, `capex_*.py` ou
`build_star_schema.py` antes de reportar como concluído.

---

## 8. "#GERENCIA INEXISTENTE" no SAP não é erro de carga — é o mesmo CGG050 de outra forma

**Causa raiz**: ao investigar o R$ 1,84 MM sem Gerência (item 3 acima), a
suspeita natural seria um bug no parser (`_parte_hierarquia_generico` em
`loaders.py`) engolindo um valor real. Só ao ler a linha bruta da
"Consulta de Contas.xlsx" (não o `fact_orcamento` já processado) que ficou
claro: a própria coluna "GERENCIA" do SAP já vem com o texto literal
`"#GERENCIA INEXISTENTE"` pra essa linha — não é falha de parsing, é o SAP
avisando que aquela verba (CC CGG050) nunca foi decomposta por Gerência.
Mesmo fenômeno do CGG050 já documentado em 2026-08-12 (memória
`project_orcamento_dinfra_status`), só que agora com o texto de erro
literal confirmado.

**Correção**: `_aplicar_correcao_combustivel_terceiros` (build_star_schema.py)
usa uma planilha do PCM (de-para Centro de Custo → região) pra fechar a
fatia de SP desse bucket — só a fatia de SP, porque foi a única com
Centro de Custo (`CGE041`) que bate com algo que a Consulta de Contas já
usa em outras linhas. As demais fatias (VP genérico, coordenações, F.Aço/
MG/RJ) usam Centro de Custo que não aparece em nenhuma linha nossa hoje —
ver `docs/briefing-copilot-gerencia-vp-e-escopo-gg.md`.

**Lição**: quando um valor aparece "sem Gerência"/"sem categoria" num
dado de origem SAP, olhar a linha bruta da fonte (não só o dado já
processado) antes de supor bug de parsing — o próprio sistema de origem
às vezes já documenta o motivo em texto (`"#GERENCIA INEXISTENTE"`,
`"Não Distribuído"`, etc.), e esse texto costuma ser mais confiável do
que qualquer suposição.

---

## 9. De/para novo pode revelar que o escopo em si está errado, não só faltando um atributo

**Causa raiz**: ao investigar a planilha do PCM pra fechar o gap de
Gerência (item 8), apareceu uma aba extra ("Base zero Transf. DG Vf")
mostrando que parte do valor que o painel conta 100% como GGG_0054 (GG
Infraestrutura SP) na verdade é redistribuída pelo PCM pra **outras GGs**
(RJ/Linha do Centro/Ferrovia do Aço) — R$ 2,65 MM de R$ 3,84 MM
analisados. Isso é uma categoria de problema diferente: não é "falta
Gerência dentro do escopo", é "o escopo (GG) pode estar errado pra esse
valor".

**Correção**: não apliquei nada disso ainda — é grande demais e afeta o
total do painel (não só a quebra por Gerência), então virou pergunta pro
Copilot (`docs/briefing-copilot-gerencia-vp-e-escopo-gg.md`, pergunta 3)
em vez de mudança de código direto.

**Lição**: ao investigar um de/para novo trazido pelo usuário, checar se
ele mexe só no atributo que motivou a pergunta original (aqui, Gerência)
ou se ele também toca uma dimensão maior (aqui, GG/escopo do painel
inteiro). Mudança de escopo tem raio de impacto muito maior que mudança
de atributo — nunca aplicar as duas junto sem separar qual é qual pro
usuário decidir cada uma.

---

## 10. "Sem Gerência" pode ser categoria estrutural, não gap — CGG050 é conta própria da GG, não pendência

**Causa raiz**: depois de fechar o Combustível Terceiros, sobrou um
resíduo de R$107.029,24 (Passagens, Hospedagem, Material de Escritório
etc.) que eu continuei tratando como "Não atribuído"/gap, na mesma linha
de raciocínio do caso anterior — assumindo que precisava de uma
Gerência de campo (SP/VP) pra fechar. O usuário corrigiu: essas contas
são a própria conta Orçado/Realizado da Gerência Geral (Marcelo Modolo),
não pendência de distribuição nenhuma — "conta própria ligada ao GG para
as Despesas". Eu tinha essa informação certa numa memória de 2026-08-12
("CGG050 é o CC da própria GG... estrutural, não erro de cadastro") mas
não conectei os pontos durante a investigação atual.

**Correção**: `_aplicar_correcao_cgg050_direto_gg` (build_star_schema.py)
— regra geral (não pontual): qualquer linha sem Gerência com Centro de
Custo CGG050 vira sua própria "Gerência" na dim_gerencia (`CGG050`, nome
"...DIRETO GG (Marcelo Modolo)"), não fica mais em "Não atribuído". Roda
depois da correção do Combustível Terceiros de propósito (aquela ainda
precisa achar as linhas nulas antes de excluir/redirecionar a fatia de
campo). "Não atribuído" no Orçado zerou de vez.

**Lição**: "sem Gerência" numa fonte de dado pode significar 2 coisas
bem diferentes — (1) dado que realmente falta ser classificado (gap de
verdade, precisa de de/para) ou (2) categoria estrutural própria que só
parece "vazia" porque não é uma das Gerências de campo que eu já conhecia
(o nível "GG direto" existe e é legítimo). Antes de tratar todo "sem
Gerência" como pendência a fechar, perguntar se aquele bucket específico
já é, ele mesmo, o destino final — e checar a própria memória/histórico
do projeto antes, porque a resposta pode já estar registrada de uma
investigação anterior.

**Complemento (mesmo dia)**: o mesmo padrão CGG050 apareceu também no
Realizado (R$34.989,15, Consulta de Contas VersãoComparativo2, mesmas 8
contas de Despesas Gerais) — como a regra já tinha sido confirmada como
geral (não pontual), bastou replicar a correção pro lado Realizado
(`_aplicar_correcao_cgg050_direto_gg_realizado`) sem precisar perguntar
de novo. "Não atribuído" (Orçado + Realizado) zerou por completo.

---

## 11. "Upload de Dados" devolvido à navegação — todo o conhecimento de Gerência agora roda sozinho a cada reprocessamento

**Contexto**: todas as correções de Gerência desta sessão (itens 3-4, 8 e
10 acima) já estavam escritas dentro de `build_star_schema()` — ou seja,
já rodavam automaticamente a cada `python -m src.model.build_star_schema`,
não eram um script avulso. O que faltava era o **caminho de operação**:
a aba "Upload de Dados" tinha sido tirada da navegação em 2026-08-11 e só
cobria 3 dos ~9 tipos de arquivo que o pipeline já consome (faltavam
Consulta de Contas, CJI3, CJI4, Catálogo CAPEX Obras, Catálogo de Contas,
Transferência Combustível Terceiros).

**Correção**: `TIPOS_ARQUIVO` (app.py) expandido pra cobrir todos os
arquivos que `build_star_schema()` já sabe processar, agrupados por
origem ("Plano de Manutenção — fundação/ajustes do PCM", "Plano de
Obras", "De/Para e apoio") em vez de uma fileira única de colunas. Página
devolvida à navegação numa seção própria "Dados" (não fazia sentido só
dentro de "Plano de Manutenção" ou só "Plano de Obras", já que cobre os
dois). Depois de "Reprocessar base", a tela agora mostra quantas linhas
ficaram sem Gerência (Orçado/Realizado) — se aparecer alguma, é sinal de
dado novo que as correções conhecidas não cobrem ainda, não silencioso.

**Lição**: separar sempre "a lógica está certa no pipeline" de "dá pra
operar isso sem abrir terminal" — a primeira sem a segunda ainda deixa o
usuário de negócio dependente de alguém rodar comando manualmente toda
vez que uma planilha nova chega. Quando o pedido for "quando eu subir X,
quero que Y aconteça sozinho", isso quase sempre implica revisar o
caminho de UI/operação, não só a função que processa o dado.

**Correção no mesmo dia**: o agrupamento inicial (por origem — "Plano de
Manutenção"/"Plano de Obras") não era o que o usuário queria operar. Ele
reorganizou por **cadência real**: "Rotina periódica" (Base Analítico SAP
— mesmo formato de `Base Analitico - GG.xlsx` —, CJI3, CJI4) x "Sob
demanda" (Base Zero, os 2 Catálogos de Conta, Explicações de Causa) x
**fora da rotina de upload** (Consulta de Contas — "fora de uso" — e a
planilha de transferência do PCM — "não entrará como rotina"). `TIPOS_
ARQUIVO` reorganizado por esses 2 grupos; os 2 arquivos "fora de uso"
saíram da tela de upload (o pipeline continua lendo se o arquivo existir
em data/raw/, só não tem mais zona própria).

**Resolvido no mesmo dia, logo em seguida**: o "fora de uso" da Consulta
de Contas era só sobre o **Realizado** (`VersãoComparativo2`) — o
**Orçado** (`VersãoComparativo1`, "Comparativo 1") continua vindo
exclusivamente dela, então ela **voltou** pra "Rotina periódica" (com um
título mais específico: "OPEX Orçado — Comparativo 1", pra não confundir
de novo). Perguntei explicitamente se o Realizado deveria reverter pro
Base Analítico SAP direto (que já alimenta `fact_realizado_documento`) —
usuário confirmou que **não**, `VersãoComparativo2` continua sendo a
fonte de `fact_realizado`, sem mudança de lógica no pipeline, só na
categorização da tela de upload.

---

## 12. Código de PEP pode trocar entre planejamento e execução — cruzar por identidade do projeto, não pelo código bruto

**Causa raiz**: reportei um gap de R$91,57 milhões (CAPEX Obras, Realizado sem Orçado) cruzando CJI4 x CJI3 pelo código `e_pep_projeto` exato. Analisando "PCE Base Luiz.xlsx" (aba `consolidado`, mais rica que CJI4) descobri que Terminal Pederneiras e Terminal São Simão têm **2 códigos PEP diferentes pro mesmo projeto**: `HM/25001`/`HM/25002` no Orçado (criados em 2025, fase de planejamento) e `HM/26002`/`HM/26001` no Realizado (criados em 2026, fase de execução) — confirmado batendo `ID Megabase` do catálogo (839 e 840 respectivamente, idênticos nos dois códigos).

**Correção**: refiz o cruzamento Orçado x Realizado agrupando por `ID Megabase` (identidade estável do projeto no catálogo) em vez do `e_pep_projeto` bruto — o gap real caiu de R$91,57MM para R$7,17MM (97% do "achado" anterior era falso positivo).

**Lição**: em bases com ciclo de vida de projeto (planejamento → aprovação → execução), o código "chave" de um sistema transacional (SAP PEP, neste caso) pode não ser estável ao longo do tempo — sistemas de projeto costumam ter um identificador de negócio separado (aqui, `ID Megabase`/`ID Projeto` do catálogo) feito exatamente pra isso. Antes de declarar "sem correspondência" entre 2 fontes (Orçado x Realizado, Sistema A x Sistema B), checar se existe um catálogo/de-para de identidade de projeto que sobrevive à troca de código — um JOIN por código bruto sem essa checagem pode fabricar um gap que não existe.

---

## 13. Nome de coluna pode não ser o que a pessoa lembra — verificar antes de aceitar a premissa

**Causa raiz**: o usuário descreveu a coluna `Grupo` de "PCE Base Luiz.xlsx" como tendo as categorias finas (SERVIÇOS, MATERIAIS, ENGENHARIA...). Ao inspecionar os dados reais, `Grupo` é na verdade um rollup grosso (81% cai em "OBRA/PRÉ-OBRA") — a categoria fina que o usuário descreveu está na coluna `Descrição`, que tem os mesmos valores 1:1 com `Grupo` só nas categorias "especiais" (Escalation, Contingência, Capitalização etc.), por isso a confusão é fácil de fazer folheando a planilha.

**Correção**: usei `Descrição` como a categoria fina em toda a análise e no filtro "Grupo" da Label do Especialista, com uma nota explícita corrigindo a nomenclatura (não apliquei a instrução literal sem checar).

**Lição**: quando o usuário descreve a estrutura de uma planilha de memória (sem eu já ter aberto o arquivo), tratar como hipótese a confirmar nos dados reais, não como fato — principalmente nome exato de coluna. Aplicar literalmente sem checar teria produzido um filtro "Grupo" que na prática só mostra "OBRA/PRÉ-OBRA" pra 92% dos dados, inútil pro Especialista.

**Complemento (mesma sessão, 1 dia depois)**: o próprio usuário trouxe a
tabela real Versão×Grupo×Descrição e confirmou que a classificação bruta
`Grupo` é **inconsistente entre versões** (ex.: "RATEIOS"/"DESAFIO" às
vezes aparecem como Descrição dentro de `Grupo=OBRA/PRÉ-OBRA`, às vezes
como `Grupo` próprio) — pediu pra eu **normalizar** com 2 grupos
compostos definidos por lista fixa de Descrição ("Obra e Pré-Obra" e
"Rateios", propositalmente sobrepostos) em vez de confiar na coluna
`grupo` bruta pra esses 2 casos. Também achei a mesma categoria fina do
lado Realizado: não é `Classificação atualizada` (que eu já usava), é
a coluna **`Classificação`** — praticamente idêntica a `Descrição` do
lado Orçado/Forecast, só não tinha reparado que existiam as 2 colunas
parecidas (`Classificação` x `Classificação atualizada`) na mesma aba.

---

## 14. "Orçado x Forecast" precisa de grão mensal — recarregar quando o pedido evolui

**Causa raiz**: carreguei `fact_pce_consolidado` só com "Valor total" (1 valor por linha, já anual) — suficiente pro pedido inicial (totais por Grupo/Projeto/Ano). Quando o usuário pediu Orçado Mensal/Forecast Mensal x Acumulado, essa granularidade não existia na tabela — precisei voltar no loader e explodir as 12 colunas `Valor/moeda ACC001`..`ACC012` (mesmo padrão já usado em `load_cji4_capex_obras`), recarregando ~1,07 milhão de linhas (12x o volume anterior).

**Lição**: ao carregar uma fonte nova, perguntar "que nível de detalhe o pedido ATUAL precisa" em vez de "que nível de detalhe a fonte tem disponível" — carregar só o necessário é certo no momento, mas o pedido evolui na mesma conversa (aconteceu 2x nesta sessão: CAPEX Obras primeiro só anual, depois mensal). Quando o pipeline já está isolado em tabela própria (como aqui, `fact_pce_consolidado` não é consumida por mais nada), recarregar com mais grão é barato — vale fazer sem resistência quando o pedido pedir, em vez de tentar aproximar com o que já está carregado.

**Lição reforçada**: quando o usuário usa uma sigla/termo técnico da
própria fonte de dado ("Comparativo 1") pra descrever de onde vem uma
informação, isso quase sempre aponta pro nome exato de uma coluna/aba já
existente no código — vale grepar o termo no código antes de perguntar
"qual arquivo é esse", porque a resposta pode já estar documentada (era
`VersãoComparativo1` em `load_consulta_contas`, achei em segundos). E
quando uma resposta anterior ("fora de uso") parecer contradizer uma
nova ("vem do Comparativo 1"), não reconciliar sozinho por suposição —
perguntar de novo, de forma concreta, mostrando a implicação técnica
exata (aqui, "isso significa reverter `fact_realizado` pro Base
Analítico?") antes de tocar em código que já tinha sido validado com
cuidado numa decisão anterior.

---

## 15. Coluna "bruta" inconsistente entre versões — normalizar na carga (loader), não filtrar na consulta

**Causa raiz**: confirmado (direto na planilha bruta, não bug de leitura) que só a versão `FC06+06` de "PCE Base Luiz.xlsx" grava `Grupo` no nível fino (SERVIÇOS, MATERIAIS, ENGENHARIA, EQUIPAMENTOS, INDIRETOS MRS, SMA, FUNDIÁRIO_RI_REGULATÓRIO aparecem como `Grupo` próprio) em vez de rolar pra `OBRA/PRÉ-OBRA` como em toda outra versão — inflava o filtro "Grupo" da Label do Especialista pra 15 opções só nessa versão, contra 8-10 nas demais.

**Correção**: o usuário passou o de-para Versão×Grupo×Descrição correto (texto + imagem) e pediu que a regra fosse aplicada **internamente, de forma permanente** — porque "a base será imputada" (reupload periódico) e uma correção pontual só nos dados de hoje não sobreviveria ao próximo upload. Criei `_GRUPO_CANONICO_POR_DESCRICAO` + `_reclassificar_grupo()` em `src/ingestion/loaders.py`, aplicada no fim de `load_pce_consolidado`/`load_pce_realizado`: o `grupo` de saída é sempre **derivado de `descricao`** (17 valores finos → os 9 grupos oficiais), ignorando o `Grupo` bruto da fonte — que só sobra como fallback se aparecer uma Descrição nova/não catalogada no futuro (não vira nulo). De brinde, a normalização (`strip().upper()`) também resolveu duplicidade de caixa que existia em `descricao` (ex.: "Contingência" x "CONTINGÊNCIA" na FEL3).

**Lição**: quando uma coluna de categoria "oficial" da fonte se mostra inconsistente entre fatias dos dados (aqui, entre versões) e existe uma coluna irmã mais granular que é estável, a correção correta é normalizar **na carga** (derivar a grossa a partir da fina, sempre) — não filtrar/corrigir na consulta, porque isso teria que ser repetido em cada query e não protege contra o próximo reupload trazer a mesma inconsistência de novo. Vale generalizar: sempre que o usuário disser algo como "a base será reimputada" ou "isso é rotina periódica", é sinal de que a correção pertence ao loader (dado -> modelo), nunca à camada de dashboard.

---

## 16. `ModuleNotFoundError: No module named 'src'` no primeiro deploy no Streamlit Community Cloud (2026-08-27)

**Causa raiz**: `src/dashboard/app.py` sempre importou módulos do projeto como pacote absoluto (`from src.config import ...`, `from src.dashboard.filtros import ...` etc.) sem nunca garantir explicitamente que a raiz do repositório estivesse em `sys.path`. Isso nunca deu erro porque o único jeito de rodar o painel até então era `python -m streamlit run src/dashboard/app.py` a partir da raiz do projeto — o flag `-m` do Python adiciona o diretório de trabalho atual ao `sys.path` automaticamente. O Streamlit Community Cloud executa o "main module" de outra forma (não via `python -m` a partir da raiz), então só o diretório do próprio arquivo (`src/dashboard/`) entrava no path — qualquer `from src.xxx import yyy` quebrava com `ModuleNotFoundError: No module named 'src'`. Só apareceu agora porque este foi o primeiro deploy real do painel (sempre rodou local antes).

**Correção**: adicionado um shim no topo de `app.py`, antes de qualquer import `src.*`: calcula a raiz do projeto via `Path(__file__).resolve().parent.parent.parent` e insere em `sys.path` se ainda não estiver lá. Funciona independente de como o executor invoca o arquivo.

**Lição**: um projeto que só roda via `python -m streamlit run` a partir da raiz está com essa dependência de `sys.path` escondida — nunca fica evidente até o dia em que alguém (ou alguma plataforma de deploy) executa o arquivo de um jeito diferente. Ao preparar qualquer app Python multi-módulo para deploy pela primeira vez, adicionar o shim de `sys.path` no entrypoint é mais seguro do que confiar no jeito como ele "sempre foi rodado localmente".

---

## 17. `duckdb.IOException` ao clicar "Reprocessar base" logo após o primeiro deploy (2026-08-27)

**Causa raiz**: `build_star_schema()` (`src/model/build_star_schema.py:603-608`) devolve `caminho_db` mesmo quando os 2 arquivos obrigatórios (`base_zero`, `realizado`) ainda não existem em `data/raw/` — só imprime um aviso no console e retorna, **sem criar o arquivo `.duckdb`**. Isso nunca deu problema localmente porque o PC de desenvolvimento sempre teve `data/raw/` populado há meses. No primeiro deploy real (Streamlit Community Cloud), `data/raw/` nasce vazio (é gitignored, de propósito — dado sensível não vai pro git). O código em `pagina_upload()` chamava `_conectar()` (modo só-leitura) logo depois, sem checar se o arquivo de fato existia — abrir um arquivo inexistente em modo leitura quebra com `duckdb.IOException`, sem mensagem clara pro usuário.

**Correção**: `pagina_upload()` agora checa `os.path.exists(caminho_db)` depois de `build_star_schema()` e antes de conectar — se faltar, mostra aviso claro pedindo pra subir Base Zero + Base Analítico SAP (Realizado) primeiro, em vez de deixar o app quebrar.

**Lição**: uma função que "sai cedo sem fazer nada" (early return) precisa sinalizar isso de um jeito que o chamador consiga distinguir de "rodou e funcionou" — aqui, devolver o mesmo `caminho_db` nos dois casos (sucesso e "nada pra fazer ainda") escondeu a diferença. Vale generalizar pra qualquer pipeline que teve o primeiro deploy real: o ambiente de produção começa vazio (sem dado, sem base) de um jeito que o ambiente de desenvolvimento local — já rodado há meses com dado de verdade — nunca reproduz sozinho. Testar mentalmente o "dia zero" (pasta de dado vazia) antes do primeiro deploy real teria pego isso sem precisar do usuário bater de frente com o erro em produção.

---

## 18. `FileNotFoundError` no CSV de explicações no primeiro deploy — mesma classe do item 17 (2026-08-27)

**Causa raiz**: `carregar_explicacoes()` (`src/engine/explanation_engine.py`) fazia `pd.read_csv(caminho_csv)` direto, sem checar se `data/staging/explicacoes.csv` existia. Local, esse CSV já existia há meses (uso real contínuo). No primeiro deploy, `data/staging/` nasce vazio (gitignored) — ninguém preencheu nenhuma justificativa ainda nesta instância nova, então o arquivo genuinamente não existe. Quebrou com `FileNotFoundError` ao abrir a Visão Resumo Executivo (que chama `calcular_explicacao` → `carregar_explicacoes`).

**Correção**: `carregar_explicacoes()` agora trata "arquivo não existe" como "nenhuma justificativa preenchida ainda" — devolve um `DataFrame` vazio com as colunas certas (`COLUNAS_EXPLICACAO`) em vez de quebrar. O resto do motor (`calcular_explicacao`, `validar_categorias`) já lida bem com DataFrame vazio (soma 0, sem erro) — não precisou mudar mais nada.

**Lição reforçada**: mesmo padrão do item 17 — qualquer arquivo que hoje só existe porque o ambiente de desenvolvimento local acumulou meses de uso real (warehouse, CSV de apoio, o que for) é um candidato certo a quebrar no "dia zero" de um ambiente novo. Antes de considerar um deploy pronto, vale listar todo `pd.read_csv`/`open`/`duckdb.connect` que lê um caminho de `data/` e confirmar que cada um trata "arquivo ainda não existe" como estado válido (vazio), não como bug.

---

## 19. `duckdb.CatalogException` em `fact_pce_realizado` — arquivo sem zona de upload própria (2026-08-27)

**Causa raiz**: "PCE Base Luiz.xlsx" (fonte de `fact_pce_realizado`, usado pela página "CAPEX Obras — Especialista") tinha sido deixado de propósito fora de `TIPOS_ARQUIVO`/da rotina de upload (decisão de quando o app só rodava local: arquivo raro de mudar, dava pra colocar direto em `data/raw/` pelo sistema de arquivos). Isso parou de fazer sentido no deploy online: não existe jeito de colocar um arquivo no disco do Streamlit Cloud a não ser pela própria tela de Upload — sem zona própria, o arquivo nunca existe lá, e `fact_pce_realizado` nunca é criada. `pce_especialista.py` consultava a tabela direto em 2 lugares, sem checar se existia — quebrava com `duckdb.CatalogException` (tabela não existe) toda vez que alguém abria a página.

**Correção**: adicionada zona de upload "Sob demanda" pra `pce_realizado` em `TIPOS_ARQUIVO` (`app.py`). Além disso, `pce_especialista.py` ganhou `_tabela_pce_realizado_existe()` e os 2 pontos que consultavam `fact_pce_realizado` direto passaram a checar antes — devolvem 0/vazio se a tabela ainda não existir, em vez de quebrar (mesma defesa mesmo com a zona de upload nova, cobre o caso de ninguém ter subido o arquivo ainda).

**Lição**: "arquivo colocado manualmente no disco, fora da rotina de upload" é uma decisão que só faz sentido enquanto o app roda só local — no dia em que ele for publicado, todo arquivo que o pipeline lê precisa de algum caminho pelo qual ele possa chegar até lá (upload pela tela, ou os dois: zona de upload rara e defesa contra tabela ausente). Vale revisar todo `cfg["caminhos"].get(...)` usado em `build_star_schema.py` que NÃO tem entrada correspondente em `TIPOS_ARQUIVO` antes de publicar qualquer painel — é a mesma pergunta do item 18 ("esse caminho pode não existir?"), mas aplicada a arquivos opcionais que nunca tiveram tela de upload nenhuma.
