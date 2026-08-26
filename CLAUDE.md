# CLAUDE.md — Painel Executivo de Explicação de Delta (DINFRA / MRS)

> Este arquivo é o ponto de entrada para o Claude Code. Antes de gerar qualquer
> código, leia nesta ordem:
> 1. `docs/00-especificacao-consolidada.md` — o que construir e por quê
> 2. `docs/01-plano-de-build-mvp.md` — em que ordem construir (fases/tarefas)
> 3. `docs/02-perguntas-em-aberto.md` — o que NÃO está resolvido ainda (não
>    tente adivinhar essas respostas; trate como TODO explícito no código)

## O que é este projeto

Um painel que não mostra só "Orçamento x Realizado", mas **explica automaticamente
o desvio (Delta)** usando a mesma taxonomia de causas que o PMO já usa nas
RDGs com a Diretoria (Físico, Efeito Preço, Não Previsto, Carry Over, Ajuste
Contábil, Realizado Não Contabilizado, Taxa Bom/Mix, Não Justificado).

Objetivo de negócio: um Gerente Geral consegue responder, em menos de 2
minutos e sem apoio do PMO, "qual o desvio, onde está, por quê, e quanto já
está explicado".

## Escopo do MVP (leia o plano de build para o detalhe)

Construir **apenas**:
- Nível 1 (Diretoria) e Nível 2 (Gerência Geral, waterfall por categoria de causa)
- Nível 3 (drill-down por Pacote dentro de uma categoria)
- Nível 4 (Contas — tabela Pacote macro → Conta micro)
- Nível 5 (Centro de Custo — Pacote macro → Centro de Custo micro, com
  Delta real porque o código de CC é compartilhado entre Orçamento e
  Realizado)
- Nível 6 (rastreabilidade até documento SAP — só para Realizado)
- Motor de cálculo de Delta / Delta Explicado / % Explicado
- Preenchimento de causa via arquivo de apoio (CSV/planilha), não via formulário ainda

Níveis 4-6 entraram no escopo a pedido do usuário em 2026-08-06 (eram
"fora do MVP" na versão original deste arquivo).

**Fora do MVP** (fica para depois): "Forecast PMO" (fonte de dado ainda
não recebida — ver perguntas em aberto). O painel tem uma "Tendência"
calculada (run-rate) como aproximação — ver `src/dashboard/tendencia.py` —
mas não é o Forecast oficial do PMO.

**Real Físico — RESOLVIDO em 2026-08-06**: confirmado pelo usuário que a
fonte de "Real Físico" é a mesma Base Analítico SAP (Realizado) já
carregada — não é uma fonte separada ainda não recebida. O painel mostra
Real Físico = Real Contabilizado (mesmo valor, mesma fonte). Se depois
aparecer uma distinção real entre os dois (ex.: por tipo de documento
SAP — movimentação física WE/WL x fatura RE), ajustar aqui.

## Decisões técnicas já fechadas

- **Linguagem/stack:** Python. ETL com `pandas`. Armazenamento analítico em
  `DuckDB` (arquivo local, sem servidor). Apresentação em `Streamlit`, com
  gráficos `Plotly` (`st.plotly_chart`, waterfall via
  `plotly.graph_objects.Waterfall`) — trocado de Plotly Dash em 2026-08-06 a
  pedido do usuário (Dash considerado pouco amigável de operar/depurar).
- **Eixo principal do modelo de dados:** `Pacote` (não CAPEX/OPEX — isso é
  atributo, não dimensão de navegação).
- **Fórmula de Delta:** `Real Contabilizado − Orçamento`. Positivo = estouro.
- **Baseline de orçamento:** só existe uma versão (Orçamento Aprovado / Base
  Zero) — não modelar "Planejado" como versão separada.
- **Categorias de causa:** lista fechada oficial do PMO (ver spec consolidada,
  seção 4). Não inventar categorias novas.
- **"Não Justificado" é sempre calculado, nunca digitado**: `Delta Total −
  soma das causas registradas`.

## Convenções de código

- Nomes de tabela/coluna em português, no padrão já usado na spec
  (`fact_orcamento`, `fact_realizado`, `fact_explicacao`, `dim_pacote`,
  `dim_causa`, `dim_gg`, `dim_gerencia`, `dim_conta`, `dim_classificacao`,
  `dim_tempo`) — isso facilita a conversa com o time de negócio, que já usa
  esses termos.
- Todo valor monetário fica em Reais (não formatar como string cedo demais —
  formatação só na camada de apresentação).
- Qualquer suposição feita para preencher um gap de dado (ver
  `docs/02-perguntas-em-aberto.md`) precisa vir com um comentário
  `# GAP:` explicando a suposição, para ser fácil de achar e substituir depois.

## Como rodar (ajustar conforme o setup final)

```bash
pip install -r requirements.txt
python -m src.model.build_star_schema   # ETL: Base Zero + SAP -> DuckDB
streamlit run src/dashboard/app.py      # sobe o painel
```

## Dados de entrada esperados em `data/raw/`

- Base Zero (Orçamento Aprovado) — export SAP/BW, mesmo layout já validado
  anteriormente (1 linha por item, colunas mensais Jan–Dez).
- Base Analítico SAP (Realizado) — 1 linha por lançamento/nota fiscal.
- Arquivo de apoio de explicação de causa (`justificativas.csv` ou similar) —
  ainda não existe formalmente; ver plano de build, Fase 3.
