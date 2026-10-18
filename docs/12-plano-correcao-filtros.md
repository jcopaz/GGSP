# 12 — Plano de correção dos filtros (validação de 18/10/2026)

Origem: varredura da v12.2.1 em produção, com 11 filtros × 22 visões (relatório
`fin360_validacao_filtros_v12.2.1.md`). Fluxo combinado: **Astra revisa → Fable
planeja → Opus/Sonnet executam**. Este documento é a entrada do Fable para o que
ainda falta e a entrada do Astra para o que já foi feito.

Regra central adotada (vale para todas as telas daqui em diante):

> **Sem filtro = visão da GG. Com filtro = todos os números da tela no recorte.**
> Quando um bloco não consegue respeitar um filtro sem inventar dado (ex.: causa
> por Gerência), ele **avisa no lugar** em vez de mostrar o total da GG calado.

A fonte única do recorte é `filtros.clausulas_recorte_sidebar()`, que devolve
`((where_orçado, params), (where_realizado, params))` com a mesma regra de negócio
nos dois fatos:

| Filtro | Orçado (`fact_orcamento`) | Realizado (`fact_realizado`) |
|---|---|---|
| Gerência (nome) | `gerencia_id` via `dim_gerencia` (inclui o CAPEX SP/VP já mapeado) | `gerencia_id` |
| Coordenação | CCs da Coordenação (subquery em `fact_realizado`) | `coordenacao` |
| Centro de Custo | `centro_custo_id` | `centro_custo_id` |
| PEP | `pep_id` | `1=0` (Realizado é só OPEX, sem PEP) |
| Classificação | `classificacao_contabil` | `classificacao_contabil` (sempre OPEX) |
| Pacote | `pacote_id` | `pacote_id` |
| Período | `clausula_periodo` (opcional: `incluir_periodo=False`) | idem |

O escopo de RBAC (`clausula_escopo`) continua separado. Quem chama combina os dois.

---

## ✅ Rodada 1 — Visão Executiva (não commitado; para revisão do Astra)

Arquivos: `src/dashboard/filtros.py`, `resumo_executivo.py`, `nivel2_gg.py`,
`nivel3_pacotes.py` e o teste novo `tests/test_resumo_filtros.py`.

| Item | O que mudou |
|---|---|
| **D1: Resumo › Visão Executiva responde aos filtros** | Card, Visão Anual (curva do ano inteiro no recorte), Composição OPEX, Gerências Locais, CAPEX Via/EE e SP/VP, ranking: tudo usa `_filtros_resumo()` = recorte da sidebar + escopo. Com filtro de Organização/Classificação/Pacote, o card passa a se chamar **"RECORTE FILTRADO — GG INFRAESTRUTURA (SP)"** e repete o recorte. |
| Waterfall de causa no recorte | Continua para Período, **Pacote** (novo `pacotes_filtro` em `dados_waterfall_gg`/`dados_ranking_pacotes`) e Classificação com OPEX. Com Gerência/Coordenação/CC/PEP ou só CAPEX, mostra aviso, % Explicado e Não Justificado ficam "—", e o ranking vira "Pacotes com Maior Desvio (recorte filtrado)" por Delta total. Motivo: a causa é rastreada por Pacote inteiro; ratear seria inventar dado (Regra de Ouro). |
| **Novo achado G1: Gerências Locais misturavam CAPEX no Orçado** | `dados_gerencia_gg(filtros=...)` + `_filtros_gerencias_opex()`: o Orçado por Gerência passa a ser só OPEX, igual ao Realizado. ⚠️ **Muda número em produção:** a Aderência de GER MALHA (SP) e de GER IMPLANT DE OBRAS E MALHA VP vai subir (antes o CAPEX SP/VP entrava no denominador; GER MALHA mostrava 22,9%). |
| **F3: "Limpar filtros" não limpava as tags** | O botão virou `on_click=_limpar_filtros`, que zera as chaves `w_*` antes do redesenho. |
| Usuário escopado (RBAC) | `_render_resumo_recorte` também aplica os filtros da sidebar, sempre em interseção com o escopo. Filtro fora do escopo dá zero, sem vazar dado. |

Testes:
- `tests/test_resumo_filtros.py`: 10 casos com base sintética (8 falham no código antigo e passam no novo).
- `tests/etapa3_resumo_check`, `rbac_resumo_painel_check`, `etapa5_analise_financeira_check`, `etapa6b_links_check`: OK.
- `pytest tests`: 26 passed. Tudo rodado no `.venv` local, com a base local.

Para o Astra conferir:
1. Se a regra "Gerência filtra o CAPEX SP/VP pelo `gerencia_id`" está correta para o negócio.
2. O impacto de G1 nos números de GER MALHA e VP.
3. Se a lista de filtros "compatíveis com causa" (Período, Pacote, Classificação OPEX) está completa.
4. Versão já subida para **12.3.0** e `CHANGELOG.md` atualizado — conferir o texto.

---

## ✅ Rodada 2 — P1 a P9 (18/10, mesmo dia; não commitado, versão 12.3.0)

Decisões do Julio que valem para esta rodada:
- **Gerência no CAPEX:** SP = GER MALHA (SP) e VP = GER IMPLANT DE OBRAS E MALHA VP. Confirmado, segue `_GERENCIA_ID_POR_REGIAO_BASE_ZERO`.
- **Mês sem fechamento:** mostrar à parte como **"a realizar"**.

| Item | Situação | Onde |
|---|---|---|
| P1: Classificação CAPEX não filtrava o Realizado | ✅ `_filtros_padrao` usa `clausulas_recorte` (Classificação e PEP nos dois lados) | `nivel4_contas.py` (alimenta N4, N5 e Visão Manutenção) |
| P2: Contas e CC com Orçado CAPEX+OPEX | ✅ Orçado só OPEX quando não há filtro de Classificação; legenda com o CAPEX que ficou fora | `nivel4_contas.py`, `nivel5_centro_custo.py` |
| P3: faixa honesta + SAP | ✅ `FILTROS_APLICAVEIS` e `renderizar_badge_filtros_ativos(universo)`; SAP filtra Gerência (via CCs) e zera com Classificação CAPEX/PEP | `filtros.py`, `nivel6_sap.py`, `app.py` |
| P4: Desvios e Causas | ✅ Nível 1, waterfall, Tendência, Ver por Gerência (e cascata), Mapa de Calor e Nível 3 | `nivel1_diretoria.py`, `nivel2_gg.py`, `nivel3_pacotes.py`, `mapa_calor_gerencia_pacote.py`, `app.py` |
| P5: Projeção | ✅ Organização/Classificação/Pacote; Período fica de fora, com nota | `projecao_opex.py` |
| P6: CAPEX Sustaining | ✅ todos os filtros (Gerência por região SP/VP); aviso quando a Classificação exclui CAPEX | `visao_classificacao.py` |
| P7: "a realizar" | ✅ `ultimo_periodo_fechado` / `clausula_ate_fechamento` / `orcado_a_realizar` / `nota_fechamento`. Delta, Aderência, waterfall, rankings e visões por Gerência comparam até o último mês com Realizado; cards mostram "Orçado OPEX até Set" e "A realizar". Orçamento aprovado e Tendências continuam mostrando o ano inteiro | `filtros.py` + todas as telas de Manutenção |
| P8: Obras e Especialista | ✅ faixa mostra "Não se aplica nesta página" para os filtros de Manutenção (Obras) e para todos (Especialista, que tem filtros próprios no topo) | `app.py` |
| P9: lista de Gerência | ✅ união com `dim_gerencia` | `filtros.py` |

Testes: `tests/test_resumo_filtros.py` com 21 casos. No código antigo, 20 falham.

### Ainda em aberto
- **Plano de Obras com "a realizar":** o CJI4 (Orçado anual) contra o CJI3 (Realizado até o mês) tem o mesmo efeito do P7. Não foi mexido nesta rodada, porque é outro universo e outra fonte. Próxima entrega.
- **Especialista herdar Projeto/Período da sidebar:** hoje a faixa só avisa que os filtros não valem lá. Fica para decidir se vale a pena.
- **Simplificação das permissões dos usuários:** proposta à parte (Administração).

### Pontos de dado (Julio / PMO, sem código)
- Projeto DM/21973: Real (CJI3) R$ 297,3 MM contra Orçado R$ 28,8 MM. Pode ser duplicidade ou Orçado incompleto.
- Elemento PEP DM/21973C-01: Orçado R$ 0 com Real R$ 5,7 MM.
- Aderências de 812% e 962% (GER IMPLANT DE OBRAS (SP), GER ENGENHARIA EMPREEND (SP)) sobre Orçados de R$ 12–17 mil. Confirmar o mapeamento CC → Gerência.

---

## ✅ Rodada 3 — B1, B4, N4, N5 (18/10, Frente A; não commitado, segue na 12.3.0)

Fluxo: Astra revisou → Fable planejou → Opus executou. Ajustes da validação com o
Copilot da MRS incluídos (5º dia útil, alerta de competência futura, texto do CAPEX).

| Item | Situação | Onde |
|---|---|---|
| **B1: Contas, CC e Tendência sempre OPEX x OPEX** (opção b) | ✅ `_filtros_padrao` força OPEX sempre; Classificação continua nos dois lados (CAPEX → 0/0). `orcado_capex_fora_da_arvore` usa o recorte de `capex_sustaining` (filtros + RBAC; sem acesso → 0). `aviso_capex_sustaining`: "Orçado CAPEX Sustaining do recorte: R$ X · Realizado: — (não carregado)", sem citar fonte; `st.info` sem OPEX no recorte, senão legenda. Árvore vazia avisa antes do return. Card da Manutenção também. | `nivel4_contas.py`, `nivel5_centro_custo.py`, `visao_manutencao.py` |
| **B4: mês da carga "em andamento"** | ✅ `meta_carga` (build, mtime dos arquivos; auto-restore repõe `enviado_em`). `corte_fechamento` = min(último mês com Realizado, M-1 se carga ≥ 5º dia útil de M, senão M-2). Realizado parcial à parte (card + nota), nunca no Delta. Alerta de Realizado com competência após o mês da carga. Sem `meta_carga` → regra antiga, com aviso. | `filtros.py`, `build_star_schema.py`, `arquivo_bruto.py`, `resumo_executivo.py` + herdeiros |
| B4: projeção | ✅ ritmo e Forecast ancorados no último mês fechado; mês em aberto entra como projetado | `tendencia.py`, `projecao_opex.py` |
| **N4: rótulos** | ✅ "Orçado até Ago/2026" nos cards de Contas, CC (inclusive "sem Indireto GG") e Manutenção | idem |
| **N5: CAPEX Sustaining** | ✅ "Realizado OPEX do mesmo recorte (referência)" no card, banner e aviso | `visao_classificacao.py` |

Testes: `test_resumo_filtros.py` 33 casos (os 21 anteriores sem mudança), `test_corte_fechamento.py`
18 casos, `test_projecao_ritmo.py` com mês parcial. `pytest tests`: 101 passed.

### Pontos em aberto da Rodada 3
- **GAP 5º dia útil:** seg–sex sem feriados; confirmar com a GGFC se a regra do calendário de jul/26 vale todo mês.
- **GAP mtime:** `meta_carga.carregado_em` é o mtime local do arquivo; arquivo copiado à mão leva o mtime da cópia. Reversão de versão conta como carga nova (aceito).
- `meta_carga` só existe depois de "Reprocessar base" — até lá o painel usa a regra antiga e avisa na nota.
- Fonte do Realizado CAPEX Sustaining: a decidir.

---

## Como validar depois de cada entrega
1. `python -m pytest -q tests` e os `tests/*_check.py` afetados.
2. Repetir a varredura de produção (11 filtros × todas as visões) e comparar com a matriz do relatório de 18/10.
