# 11 — Referência: regras do projeto "CAPEX Control Center"

**Origem:** `C:\Users\30028203\Documents\Capex Control Center\agente\` (+ `Sprint0/`),
material de Sprint 0 preparado em jul/2026 para validação com o gerente
**Douglas Ito**. A reunião já aconteceu; o projeto **não avançou como app
separado** — o conceito ("CAPEX Control Center — Obras, PMO Malha e DINFRA")
foi absorvido pelo módulo **CAPEX Obras** que já existe aqui no Fin360
(`docs/08-rbac-escopo-por-universo.md`, `src/dashboard/capex_*.py`). Pasta
original arquivada/removida em 2026-09-11 — este documento preserva as regras
de negócio de lá que ainda **não estão implementadas** no Fin360, pra não
perder o trabalho de especificação se um dia servirem de base pro Explicador
de Delta automático.

**Status: referência, não implementado.** Nada aqui vira código sem passar
pelo fluxo normal (plano → aprovação → implementação).

---

## O que JÁ foi absorvido pelo Fin360 (não duplicar)
- Comparação BP × Orçamento × Realizado × Forecast por projeto/PEP.
- Justificativa de desvio com dono e status (`app.fact_explicacao_log`,
  `docs/03-processo-justificativas-causas.md`).
- Regra visual de gráfico temporal: realizado em linha contínua, forecast em
  linha pontilhada, "Real + Forecast" contínuo até o mês de referência e
  pontilhado depois, partindo sempre do último realizado acumulado (nunca de
  zero) — já é o padrão de `paleta.py`/`tema_plotly.py`
  (`feedback-orcamento-regras-grafico`, decisão de 2026-08-13).
- Catálogo CAPEX Obras (`data/raw/Catalago CAPEX Obras.xlsx` já está aqui).

## O que NÃO está implementado — candidato a feature futura

### Semáforo CAPEX (aderência acumulada = realizado_acum / orçado_acum)
| Faixa | Cor |
|---|---|
| 95%–105% | 🟢 Verde |
| 90%–95% ou 105%–110% | 🟡 Amarelo |
| < 90% ou > 110% | 🔴 Vermelho |
| Sem orçamento e sem realizado, ou dado insuficiente | ⚪ Cinza |
| Delta relevante sem justificativa ou sem dono | 🟣 Roxo |

### Motor de "motivo provável" (sugestão automática de causa do delta)
Regras condicionais sobre orçado/realizado/forecast acumulado e anual:

| Motivo sugerido | Condição |
|---|---|
| Antecipação | `realizado_acum > orçado_acum` **e** `forecast_anual ≈ orçado_anual` |
| Postergação | `realizado_acum < orçado_acum` **e** forecast futuro mantém valor relevante |
| Atraso de execução | `realizado_acum` muito abaixo do orçado **e** forecast futuro não compensa |
| Realizado sem orçamento | `orçado_anual = 0` **e** `realizado_acum > 0` |
| Orçamento sem realizado | `orçado_acum > 0` **e** `realizado_acum = 0` |
| Divergência de rubrica | total do projeto próximo, mas valor por rubrica muito diferente |
| Divergência de cadastro/de-para | PEP existe no realizado mas não no cadastro oficial, ou GG/origem/trecho divergente |
| Consumo de contingência | há registro de consumo na base de contingências |
| Saving | `forecast_anual < orçado_anual` e diferença validada como economia |

**Delta relevante** (limiar sugerido, deixar configurável): `abs(delta) >= R$ 500.000` OU `abs(delta_percentual) >= 10%`.

### Classificação CAPEX (categorias)
Pré-Obra · Obra · Contingência · Escalation · Mão de Obra · Rateio · Capitalização.

### Regras de responsabilidade sugerida por tipo de delta
| Tipo de delta | Área sugerida |
|---|---|
| Execução, medição, fornecedor, campo | Obras |
| Cronograma, baseline, versão de forecast | PMO Malha |
| BP, orçamento, rubrica, capitalização, contingência | Financeiro/CAPEX |
| PEP, de/para, projeto, origem, GG | PMO Malha |
| Sem explicação | Compartilhado |

### Tratamento de zero
- Orçado = 0 e realizado = 0 → `Sem movimento`.
- Orçado = 0 e realizado > 0 → `Realizado sem orçamento` (possível novo projeto, erro de cadastro/PEP, verba extra fora do BP).
- Orçado > 0 e realizado = 0 → `Orçamento sem realizado` (possível atraso de contratação/medição/licença, postergação, forecast ainda não realizado).

---

## Dados brutos NÃO transferidos (avaliados e descartados)
- `data_raw/00. Acompanhamento Financeiro - DINFRA - Versão Trabalho.xlsx` (09/jul) — já existe versão mais nova aqui em `data/raw/` (12/ago, hash diferente); a cópia de lá era mais antiga.
- `Acompanhamento GGIE - SP.pbix`, `Gestão de Contratos.pdf` — confirmado pelo Julio (2026-09-11): **não estão atuais**, não transferidos.
- Material de apresentação/Sprint 0 (`Sprint0/*`, `apresentacao_capex_control_center_douglas_ito.html`, `Script.docx`, `transcrição.txt`, `Capex Control Center.zip`) — histórico da reunião já realizada com Douglas Ito, sem uso — não transferido.
