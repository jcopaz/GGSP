# Briefing para Validação Interna — Gerência VP e Escopo de GG no CAPEX Malha

> Este documento é pra ser lido por uma IA com acesso a informação interna
> da MRS (SharePoint, Teams, sistemas corporativos), pra ajudar a validar
> conceitos de negócio que um assistente sem acesso à rede da empresa não
> consegue confirmar sozinho. Não é documentação técnica de código — é uma
> lista de perguntas de negócio, com o contexto mínimo pra cada uma.
> Continuação do `docs/briefing-copilot-validacao.md` (pergunta 2 de lá,
> sobre o CGG050, ganhou dado novo — ver pergunta 1 abaixo).

## Contexto do projeto

O Painel Executivo DINFRA (GG Infraestrutura SP, GGG_0054) explica o
desvio Orçado x Realizado de CAPEX/OPEX pro Gerente Geral. Em 2026-08-17 o
usuário trouxe uma planilha nova do PCM ("Transferência Combustível
Terceiras - FA, MG e RJ vf 30.04"), que revelou duas coisas: (1) um valor
de R$ 1,84 MM sem Gerência que já foi 100% resolvido direto com o usuário
(ver perguntas 1 e 2 abaixo, RESOLVIDAS); (2) um achado bem maior ainda em
aberto — parte do que hoje contamos como GGG_0054 pode na verdade
pertencer a outra GG (perguntas 3 e 4).

## Perguntas — RESOLVIDAS (2026-08-17, direto com o usuário, sem precisar do Copilot)

### 1. ~~O CGG050 (R$ 1,84 MM de Combustível Terceiros) deveria estar em GGG_0054 inteiro?~~ — RESOLVIDO

Usuário confirmou os 9 Centros de Custo da planilha do PCM, um por um:
**CGE041 (SP) e CGE053 (Vale do Paraíba, "faz parte do Vinicius")** ficam
em GGG_0054 — mapeados pra `GGE_0025` e `GGE_0197` respectivamente.
**CGE052 (Ferrovia do Aço), CGE039 (Linha do Centro/MG), CGE040 (Malha
RJ) e as 4 coordenações CCR101/CCR062/CCR071/CCR093** (apesar do nome
geográfico "Vale do Paraíba") são **"não é nossa"** — confirmado que
pertencem a outras GGs (GGRJ, GGFA) — excluídas do painel. Aplicado em
`_REGRAS_COMBUSTIVEL_TERCEIROS` (build_star_schema.py). Resíduo "Não
atribuído" do bucket CGG050 caiu de R$ 1.838.883,43 pra R$ 0,00 (só
sobrou R$ 0,002 de arredondamento).

### 2. ~~"GER. MANUTENÇÃO MALHA (VALE DO PARAÍBA)" é a mesma Gerência que "GER IMPLANT DE OBRAS E MALHA VP" (GGE_0197)?~~ — RESOLVIDO

Confirmado pelo usuário: CGE053 ("faz parte do Vinicius") é a mesma
Gerência que já usávamos pro CAPEX VP (GGE_0197) — não é uma Gerência
"Manutenção" distinta de "Implantação/Obras", é a mesma, só nome informal
diferente na planilha do PCM.

**Confirmação independente em 2026-08-17**: o usuário trouxe "Contas e
Hierarquia de Contas.xlsx" (de/para oficial SAP Centro de Custo →
Gerência → GG, escopado a GGG_0054) — os 9 Centros de Custo batem 100%
com o que já tínhamos aplicado: CGE041→GGE_0025 e CGE053→GGE_0197
aparecem literalmente na hierarquia oficial; os 7 excluídos (CGE052,
CGE039, CGE040, CCR101, CCR062, CCR071, CCR093) **não aparecem em
nenhuma linha** dessa hierarquia — confirma que são de fora de GGG_0054.
Zero divergência.

## Perguntas — Prioridade Alta (ainda em aberto)

### 3. O de/para "GG NOVA" da planilha do PCM já foi aplicado em algum lugar, ou ainda está pendente?

A aba "Base zero Transf. DG Vf" da mesma planilha reclassifica R$
3.840.861,03 do pacote PM03 (Materiais e Serviços de Malha, hoje 100%
contado em GGG_0054) — mas só R$ 1.188.468,86 fica em GGG_0054 pela
regra do PCM. O resto vai pra **outras GGs**:

| GG destino ("GG NOVA") | Valor |
|---|---|
| GGG_0052 (GER. GERAL DE INFRAESTRUTURA RJ) | R$ 844.963,60 |
| GGG_0055 (GER. GERAL DE INFRA LINHA DO CENTRO) | R$ 531.672,60 |
| GGG_0056 (GER. GERAL DE INFRA. FERROVIA DO AÇO) | R$ 1.275.755,97 |

Isso é um valor bem maior do que os R$ 233 mil (F.Aço/MG/RJ) da pergunta
1 — sugere que a redistribuição do PCM vai além do Combustível Terceiros,
cobre outras contas do PM03 também.

**Pergunta**: essa reclassificação "GG NOVA" já está refletida em algum
relatório oficial (SAP, Power BI, planilha-mãe do PMO) que a Diretoria já
vê? Se sim, nosso R$ 43 MM de "CAPEX Manutenção — Malha" (contado 100%
como GGG_0054 hoje) provavelmente está superestimado em até ~R$ 2,65 MM —
vale a pena excluir essa fatia do escopo do painel, ou ela é
legitimamente GGG_0054 até que a transferência seja formalmente lançada
no SAP?

### 4. A "Pendência transf. DG/Capex" de R$ 931.562,20 que o próprio PCM já calculou — o que significa exatamente?

A aba "Análise Transf. vf X Real" da planilha mostra uma coluna
"Pendência transf. DG/Capex" somando R$ 931.562,20 (dentro de um universo
maior de R$ 1.446.810,92 de "Transf. Capex e Opex" do 1º trimestre) e uma
"Pendência pagamento" de R$ 185.884,02.

**Pergunta**: essas "pendências" são valores que o PCM já sabe que
precisam ser transferidos mas ainda não foram lançados no SAP (ou seja,
uma dívida de reclassificação em aberto), ou são algo diferente (ex.:
pagamento pendente ao fornecedor, sem relação com Gerência/GG)? Isso
ajuda a entender se o gap que vemos no painel é o mesmo gap que o PCM já
rastreia.

## Como usar as respostas

Qualquer resposta concreta (de/para de Centro de Custo, confirmação de
Gerência, status da reclassificação) pode ser colada de volta na conversa
com o assistente que mantém este painel — ele cruza com os dados já
carregados (`fact_orcamento`, `dim_gerencia`) e ajusta o código conforme a
confirmação, sem precisar reperguntar o que já foi respondido aqui. Não é
necessário responder tudo de uma vez; cada pergunta é independente.
