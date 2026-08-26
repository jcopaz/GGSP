# 00 — Especificação Consolidada
### Painel Executivo de Explicação de Delta — DINFRA (MRS)
Consolida "Complemento da Especificação v2.0" e "Projeto Revisado (Copilot)".
Onde os dois documentos divergiam, a decisão final está marcada como
**[DECISÃO]**.

---

## 1. O que mudou em relação à primeira versão do projeto

A primeira versão (que já tínhamos desenhado) era um painel **Orçamento x
Realizado com 3 linhas (Planejado/Orçamento/Delta) + tooltip de causa**.

Os dois documentos novos mostram que essa hipótese estava **incompleta**: o
problema real do Gerente Geral não é ver o número, é **explicar o número
rápido, na linguagem que a Diretoria e o PMO já usam nas RDGs**. O projeto
evolui de "painel de controle orçamentário" para **"painel de explicação de
desvio"**.

---

## 2. Conceitos oficiais (substituem a versão anterior)

| Conceito | Definição | Fonte |
|---|---|---|
| **Orçamento** | Base Zero aprovada. **[DECISÃO]** Não existe uma segunda versão formal (pré-reajuste) que justifique manter "Planejado" como linha separada — isso **substitui** a decisão anterior de ter Planejado/Orçamento/Delta. Usar só **Orçamento Aprovado** como baseline. | Base Zero |
| **Real Físico** | Valor financeiramente equivalente ao que foi efetivamente executado (conceito já usado pelo PMO nas RDGs). | Fonte ainda não recebida — ver `02-perguntas-em-aberto.md` |
| **Real Contabilizado** | Valor efetivamente lançado no SAP no período. | Base Analítico SAP |
| **Forecast** | Projeção de fechamento construída pelo PMO. | Fonte ainda não recebida |
| **Delta** | `Real Contabilizado − Orçamento`. Delta > 0 = estouro; Delta < 0 = economia. | Calculado |
| **Delta Explicado** | Soma dos valores associados às categorias de causa registradas. | Calculado |
| **Delta Não Explicado** | `Delta Total − Delta Explicado`. | Calculado |
| **% Explicado** | `Delta Explicado / Delta Total`. | Calculado |
| **% Não Explicado** | `Delta Não Explicado / Delta Total`. | Calculado |

**[DECISÃO]** Fluxo conceitual final:
```
Orçamento → Real Físico → Real Contabilizado → Delta → Explicação do Delta
```

---

## 3. Eixo principal do modelo (muda a arquitetura anterior)

**[DECISÃO]** O eixo de navegação principal **não é CAPEX/OPEX** (como
assumido na primeira versão). É:

```
GG → Gerência → Pacote → Conta → Centro de Custo → Período
```

`CAPEX` / `OPEX` viram **atributo analítico** (um filtro/coluna), não uma
dimensão de navegação — isso é coerente com o que já tínhamos observado nos
dados reais: o mesmo Pacote pode ter linhas CAPEX e OPEX ao mesmo tempo.

---

## 4. Taxonomia oficial de causas (substitui a lista anterior)

A primeira versão tinha uma lista simplificada (Performance, Desempenho,
Câmbio/Preço, Escopo Adicional, Não Justificado). **[DECISÃO]** Ela é
substituída pela taxonomia que o PMO já usa nas RDGs, para o painel falar a
mesma língua da Diretoria:

| Categoria | O que cobre | Exemplos citados nos documentos |
|---|---|---|
| **Físico** | Desvio por execução diferente da planejada | Atraso de produção, volume inferior, antecipação, reprogramação, baixa produtividade, restrições operacionais |
| **Efeito Preço** | Desvio por variação de preço | Reajuste, inflação, renegociação contratual, aumento de insumos, fretes |
| **Não Previsto** | Despesa que não constava no orçamento original | Alojamentos, mobilizações, emergências, sobreaviso, horas improdutivas, contratrilho em ponte, deslocamentos adicionais, estruturas temporárias |
| **Carry Over** | Execução de período anterior, paga no exercício atual | Pagamentos postergados, notas atrasadas, medições de exercícios anteriores |
| **Ajuste Contábil** | Diferença por reclassificação/tratamento contábil | Reclassificações, ajustes sistêmicos, lançamentos de competência |
| **Realizado Não Contabilizado** | Executado fisicamente mas não lançado no SAP no período | Notas pendentes, medições pendentes, baixas em atraso, aprovações pendentes, fechamento de período |
| **Taxa Bom/Mix** | Mix de execução em projetos CAPEX (categoria específica do PMO) | — |
| **Não Justificado** | **Sempre calculado, nunca digitado**: `Delta Total − soma das causas registradas` | — |

Nenhum Delta pode ficar sem classificação — se ninguém preencheu causa, o
próprio painel mostra "Não Justificado" automaticamente.

---

## 5. Fontes de dados

| Fonte | Granularidade | Status |
|---|---|---|
| **Base Zero (Orçamento Aprovado)** | 1 linha por item de material/serviço planejado | ✅ Recebida e validada anteriormente |
| **Base Analítico SAP (Realizado)** | 1 linha por lançamento/nota fiscal | ✅ Recebida e validada anteriormente |
| **Forecast PMO** | Projeção de fechamento | ❌ Não recebida |
| **Real Físico** | Execução física valorada | ❌ Não recebida / fonte não identificada |
| **Explicação de causa (fact_explicacao)** | 1 linha por causa registrada, por pacote/conta/mês | ❌ Não existe formalmente — hoje é texto livre na tabela "Justificativas" do Power BI |

---

## 6. Modelo de dados

### Dimensões
- `dim_tempo` — ano, trimestre, mês
- `dim_gg` — SP, RJ, FA, LC
- `dim_gerencia` — Gerência, Coordenação
- `dim_pacote` — código, nome, família (PM / PD / PP)
- `dim_conta` — conta orçamento, conta razão
- `dim_classificacao` — CAPEX / OPEX (atributo, não eixo de navegação)
- `dim_causa` — as 7 categorias da seção 4 + Não Justificado

### Fatos
```
fact_orcamento     : Pacote, Conta, Centro de Custo, Mês, Valor Orçado
fact_realizado     : Pacote, Conta, Centro de Custo, Mês, Valor Realizado
fact_explicacao    : Pacote, Conta, Mês, Categoria, Valor Explicado, Descrição
```
(`fact_explicacao` substitui o nome `fact_justificativa` usado na primeira
versão do projeto — mesmo conceito, nome alinhado à spec nova.)

---

## 7. Estrutura de navegação (telas)

| Nível | Público | O que mostra |
|---|---|---|
| **1 — Diretoria** | Diretoria / réplica da RDG | Orçamento, Forecast, Real Físico, Real Contabilizado, Delta, Aderência — por SP/RJ/FA/LC/DINFRA |
| **2 — Gerência Geral** | GG | Delta Total da GG decomposto por categoria de causa, em **waterfall** |
| **3 — Pacotes** | GG | Ao clicar numa categoria: ranking de pacotes que compõem aquele valor, maior → menor |
| **4 — Contas** | GG/Coordenação | Ao clicar num pacote: conta orçamentária, conta razão, orçado, realizado, delta |
| **5 — Centro de Custo** | Coordenação | Centro de Custo, PEP, Coordenação, Gerência |
| **6 — SAP** | Rastreabilidade | Documento SAP, NF, fornecedor, data, valor, texto do lançamento, usuário — último nível, garante que todo número é rastreável até a origem |

---

## 8. Indicadores do painel

`Delta Total` · `Delta Explicado` · `Delta Não Explicado` · `% Explicado` ·
`% Não Explicado` · `Top Ofensores` (ranking de pacotes) · `Top Causas`
(ranking de categorias) · `Top Contas` · `Top Centros de Custo`.

---

## 9. Perguntas que o painel precisa responder (critério de aceite funcional)

1. Qual GG possui o maior desvio? 2. Quanto é o desvio? 3. Positivo ou
negativo? 4. É físico ou financeiro? 5. Qual causa responde pela maior
parcela? 6. Qual pacote gerou o desvio? 7. Qual conta gerou o desvio? 8. Qual
centro de custo gerou o desvio? 9. Existe valor não contabilizado? 10. Existe
ajuste contábil? 11. Quanto do delta já está explicado? 12. Quanto ainda
está sem justificativa? 13. Qual documento SAP suporta a explicação?

## 10. Critério de sucesso

Um Gerente Geral consegue responder, sem apoio do PMO, em menos de 2 minutos
durante uma RDG: qual o desvio, onde está, quem gerou, qual a causa
principal, se já está totalmente explicado, e qual evidência financeira
suporta a explicação.
