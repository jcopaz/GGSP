"""Simulador de causas/justificativas — só para demonstração.

Gera um `explicacoes.csv` sintético (mesmo schema de
explanation_engine.COLUNAS_EXPLICACAO) distribuindo o Delta REAL de cada
pacote entre categorias da taxonomia fechada, deixando uma fração como
resíduo ("Não Justificado", calculado, nunca escrito aqui). O objetivo é
deixar waterfall/ranking/resumo executivo "totalmente operantes" para
visualização antes do processo real de preenchimento de causa existir (ver
docs/02-perguntas-em-aberto.md, item 3).

Nunca escreve em data/staging/explicacoes.csv (o arquivo real) — sempre em
um caminho separado (config: `explicacoes_simuladas`), e toda linha gerada
tem "[SIMULADO]" na descrição para não ser confundida com dado real se
alguém abrir o CSV.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from src.engine.delta_calculator import calcular_delta
from src.engine.explanation_engine import CATEGORIA_CALCULADA, COLUNAS_EXPLICACAO

MESES_COM_REALIZADO = list(range(1, 9))  # jan-ago, ver caveat no build_star_schema


def gerar_explicacoes_simuladas(
    con: duckdb.DuckDBPyConnection,
    categorias_validas: list[str],
    ano_fiscal: int,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    categorias_preenchiveis = [c for c in categorias_validas if c != CATEGORIA_CALCULADA]

    df_delta = calcular_delta(con, dims=["pacote_id"])
    linhas: list[dict] = []

    for _, linha in df_delta.iterrows():
        delta = linha["delta_total"]
        if delta == 0:
            continue

        # Explica só uma fração do delta — o resto sobra como "Não
        # Justificado" (residual calculado pelo motor, não escrito aqui),
        # pra parecer uma explicação parcial real, não 100% perfeita.
        fracao_explicada = rng.uniform(0.35, 0.85)
        alvo = delta * fracao_explicada

        n_causas = int(rng.integers(2, min(5, len(categorias_preenchiveis)) + 1))
        causas_sorteadas = rng.choice(categorias_preenchiveis, size=n_causas, replace=False)
        pesos = rng.dirichlet(np.ones(n_causas))

        for categoria, peso in zip(causas_sorteadas, pesos):
            linhas.append({
                "pacote_id": linha["pacote_id"],
                "conta_id": "SIMULADO",
                "ano": ano_fiscal,
                "mes": int(rng.choice(MESES_COM_REALIZADO)),
                "categoria": categoria,
                "descricao": f"[SIMULADO] {categoria.lower()} — gerado automaticamente para demonstração",
                "valor_explicado": round(float(alvo * peso), 2),
            })

    return pd.DataFrame(linhas, columns=COLUNAS_EXPLICACAO)
