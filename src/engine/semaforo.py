"""Semáforo CAPEX — classificação de status por Aderência (Realizado /
Orçado). Regra trazida do Capex Control Center
(`agente/03_regras_negocio.md`, seções 4 e 9), aplicada aqui com o dado
real do Orçamento.

Cores:
- Verde: aderência entre 95% e 105% (dentro do esperado).
- Amarelo: aderência entre 90-95% ou 105-110% (atenção).
- Vermelho: aderência abaixo de 90% ou acima de 110% (fora do esperado).
- Cinza: sem orçamento e sem realizado, ou aderência indefinida.
- Roxo: delta relevante sem justificativa — tem prioridade sobre a faixa
  de aderência, porque "sem dono" é mais grave que estar fora da faixa
  (mesmo espírito da Regra de Ouro do Orçamento: nenhum delta sem dono).
  Só é avaliado quando `delta_nao_justificado`/`delta_total` são
  informados — sem essa informação (ex.: card que não calcula causa), o
  semáforo fica restrito a Verde/Amarelo/Vermelho/Cinza.
"""
from __future__ import annotations

import pandas as pd

VERDE = "Verde"
AMARELO = "Amarelo"
VERMELHO = "Vermelho"
CINZA = "Cinza"
ROXO = "Roxo"

# Delta relevante: mesmo limiar documentado no Capex Control Center
# (03_regras_negocio.md, seção 9) — abs(delta) >= R$500 mil OU abs(%) >= 10%.
LIMIAR_DELTA_RELEVANTE_VALOR = 500_000.0
LIMIAR_DELTA_RELEVANTE_PERCENTUAL = 0.10


def classificar_semaforo(
    aderencia: float | None,
    delta_nao_justificado: float | None = None,
    delta_total: float | None = None,
) -> str:
    """Usa `pd.isna` (não só `is None`) porque valores vindos de DataFrame
    (ex.: linha de GG sem Orçado mapeado) chegam como `NaN`, não `None` —
    `NaN > 0`/`NaN < 0` não geram erro, mas também não caem no `is None`,
    e classificariam errado como Vermelho sem essa checagem."""
    if (
        delta_nao_justificado is not None and not pd.isna(delta_nao_justificado)
        and delta_total is not None and not pd.isna(delta_total) and delta_total
    ):
        relevante = (
            abs(delta_nao_justificado) >= LIMIAR_DELTA_RELEVANTE_VALOR
            or abs(delta_nao_justificado / delta_total) >= LIMIAR_DELTA_RELEVANTE_PERCENTUAL
        )
        if relevante:
            return ROXO

    if aderencia is None or pd.isna(aderencia):
        return CINZA
    if 0.95 <= aderencia <= 1.05:
        return VERDE
    if (0.90 <= aderencia < 0.95) or (1.05 < aderencia <= 1.10):
        return AMARELO
    return VERMELHO
