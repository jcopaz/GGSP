# 01 — Plano de Build do MVP

Cada fase é um passo executável e testável isoladamente. Não pule fase — a
fase seguinte depende do modelo de dados da fase anterior estar validado
contra dados reais.

---

## Fase 0 — Preparar o esqueleto do projeto

- Estrutura de pastas: `src/ingestion/`, `src/model/`, `src/engine/`,
  `src/dashboard/`, `config/`, `data/raw/`, `data/staging/`, `data/warehouse/`.
- `config/settings.yaml` com caminhos de arquivo e a lista fechada de
  categorias de causa (seção 4 da spec consolidada) — a lista **não pode
  ficar hardcoded no código**, tem que vir de config, porque o PMO pode
  ajustar a taxonomia no futuro.

**Critério de pronto:** projeto roda `python -m src.model.build_star_schema`
sem erro, mesmo que ainda sem dado real carregado.

---

## Fase 1 — ETL das duas fontes já validadas

- `src/ingestion/loaders.py`: `load_base_zero(path)` e `load_realizado(path)`.
  Reaproveitar o mapeamento de colunas já validado anteriormente contra os
  arquivos reais (Base Zero tem 12 colunas mensais wide → converter para
  long; Realizado é 1 linha por lançamento, usar `Exercício Período Fiscal`
  para derivar ano/mês).
- Tratar explicitamente o achado: **o mesmo Pacote pode ter linhas CAPEX e
  OPEX ao mesmo tempo** — `Classificação contábil` não pode ser inferida do
  Pacote, tem que vir linha a linha da própria Base Zero.
- Tratar as 3 famílias de código de pacote (PM / PD / PP) como uma dimensão
  `familia_pacote`, não misturar.

**Critério de pronto:** rodar o loader contra os arquivos reais e conferir
que a soma de `Total P26`/`Vl <mês>` bate com o total agregado calculado.

---

## Fase 2 — Modelo dimensional (fact_orcamento, fact_realizado)

- `src/model/build_star_schema.py`: materializa `fact_orcamento` e
  `fact_realizado` em DuckDB, seguindo exatamente os nomes de coluna da
  seção 6 da spec consolidada.
- **Não** criar `dim_classificacao` como derivada — ela é atributo de cada
  linha de fato, direto da fonte.

**Critério de pronto:** consulta simples `SELECT pacote_id, SUM(valor) FROM
fact_orcamento GROUP BY pacote_id` reproduz os mesmos números que já
validamos manualmente na primeira rodada do projeto.

---

## Fase 3 — fact_explicacao (o motor de causa)

Esta fonte **não existe ainda formalmente** — é o principal item novo do
MVP. Duas frentes em paralelo:

1. **Estrutura de dados:** criar `data/staging/explicacoes.csv` com colunas
   `pacote_id, conta_id, ano, mes, categoria, descricao, valor_explicado`.
   `categoria` só aceita valores da lista fechada da Fase 0.
2. **Motor de cálculo** (`src/engine/delta_calculator.py` +
   `src/engine/explanation_engine.py`):
   - `delta_total = realizado - orcamento` (por pacote, GG, ou qualquer
     dimensão pedida);
   - `delta_explicado = soma(valor_explicado)` agrupado por categoria;
   - `delta_nao_explicado = delta_total - delta_explicado` — **calculado,
     nunca lido de uma célula preenchida manualmente**;
   - `% explicado` e `% não explicado` com proteção de divisão por zero.

**Critério de pronto:** rodar o motor com um CSV de exemplo (usar os números
do próprio exemplo da spec: SP com Delta Total +2,3 MM, Não Previsto +0,76
MM, Realizado Não Contabilizado +0,99 MM, Ajuste Contábil +0,30 MM, Físico
-0,29 MM, Preço 0,00 MM) e conferir que o "Não Justificado" calculado bate
com a conta manual.

---

## Fase 4 — Nível 1 (Diretoria) e Nível 2 (GG, waterfall)

- `src/dashboard/nivel1_diretoria.py`: cards de Orçamento, Real
  Contabilizado, Delta, Aderência, por GG (SP/RJ/FA/LC) — **sem** Forecast e
  Real Físico ainda (fontes não disponíveis, ver perguntas em aberto:
  renderizar como "—" ou ocultar o card, não inventar valor).
- `src/dashboard/nivel2_gg.py`: ao selecionar uma GG, gráfico **waterfall**
  com a decomposição do Delta por categoria de causa (usar `plotly.graph_objects.Waterfall`).

**Critério de pronto:** selecionar SP no Nível 1 abre o waterfall do Nível 2
e a soma das barras de categoria + "Não Justificado" fecha exatamente no
Delta Total mostrado no Nível 1.

---

## Fase 5 — Nível 3 (Pacotes)

- Ao clicar numa categoria do waterfall, mostrar ranking de pacotes que
  compõem aquele valor (maior → menor), reaproveitando o mesmo
  `delta_calculator` com `dims=("pacote_id",)` e filtro de categoria.

**Critério de pronto:** clicar em "Não Previsto" mostra os pacotes cuja soma
bate com o valor da categoria no waterfall.

---

## Fora do MVP (não implementar ainda, deixar como próxima fase)

- Nível 4 (Contas), Nível 5 (Centro de Custo), Nível 6 (rastreabilidade SAP)
  — dependem de mais tempo de UI, não de dado novo; podem vir depois do MVP
  validado.
- Indicadores de **Real Físico** e **Forecast PMO** — fonte de dado ainda
  não recebida (ver `02-perguntas-em-aberto.md`). Não simular valor: deixar
  o campo vazio/"—" no layout até a fonte chegar.
- Formulário de preenchimento de causa (hoje é CSV de apoio, não tela).

---

## Ordem de execução recomendada para o agente

```
Fase 0 → Fase 1 → Fase 2 → Fase 3 → Fase 4 → Fase 5
```

Cada fase deve terminar com um teste manual (`python -c "..."` ou script em
`tests/`) que imprime o resultado e é conferido contra os números já
validados manualmente antes de avançar para a próxima fase.
