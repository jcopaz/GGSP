"""Fase 3 — motor de explicação do Delta.

Delta Explicado = soma dos valores associados às categorias de causa
registradas (fact_explicacao). Delta Não Explicado ("Não Justificado") é
**sempre calculado, nunca digitado**: Delta Total - Delta Explicado (ver
docs/00-especificacao-consolidada.md, seção 4). Este módulo não sabe de onde
o CSV de apoio veio nem como ele chega até aqui — isso é o processo de
preenchimento descrito em docs/02-perguntas-em-aberto.md, item 3, ainda em
aberto.
"""
from __future__ import annotations

import pandas as pd

COLUNAS_EXPLICACAO = [
    "pacote_id", "conta_id", "ano", "mes", "categoria", "descricao", "valor_explicado",
]

CATEGORIA_CALCULADA = "Não Justificado"


def carregar_explicacoes(caminho_csv: str) -> pd.DataFrame:
    df = pd.read_csv(caminho_csv)
    faltando = set(COLUNAS_EXPLICACAO) - set(df.columns)
    if faltando:
        raise ValueError(f"explicacoes.csv sem as colunas: {sorted(faltando)}")
    return df


def validar_categorias(df_explicacao: pd.DataFrame, categorias_validas: list[str]) -> None:
    """Valida contra a lista fechada de config/settings.yaml.

    "Não Justificado" nunca deve aparecer no CSV de apoio — é sempre o
    resíduo calculado por `calcular_explicacao`, nunca um valor digitado.
    """
    categorias_no_csv = set(df_explicacao["categoria"].dropna().unique())

    if CATEGORIA_CALCULADA in categorias_no_csv:
        raise ValueError(
            f"'{CATEGORIA_CALCULADA}' não pode ser digitado em explicacoes.csv "
            f"— é sempre calculado (Delta Total - soma das causas registradas)."
        )

    categorias_preenchiveis = set(categorias_validas) - {CATEGORIA_CALCULADA}
    invalidas = categorias_no_csv - categorias_preenchiveis
    if invalidas:
        raise ValueError(
            f"Categorias fora da taxonomia fechada do PMO: {sorted(invalidas)}. "
            f"Válidas: {sorted(categorias_preenchiveis)}."
        )


def explicado_por_categoria(df_explicacao: pd.DataFrame, dims: list[str]) -> pd.DataFrame:
    """Delta Explicado quebrado por categoria — insumo do waterfall (Fase 4)."""
    return (
        df_explicacao.groupby([*dims, "categoria"], dropna=False)["valor_explicado"]
        .sum()
        .reset_index()
    )


def calcular_explicacao(
    df_delta: pd.DataFrame,
    df_explicacao: pd.DataFrame,
    dims: list[str],
    categorias_validas: list[str],
) -> pd.DataFrame:
    """Junta Delta Total (de delta_calculator.calcular_delta) com o CSV de
    apoio e calcula Delta Explicado / Não Explicado / % Explicado.

    `df_delta` precisa ter as colunas `dims` + `delta_total`.
    """
    validar_categorias(df_explicacao, categorias_validas)

    explicado_total = (
        df_explicacao.groupby(dims, dropna=False)["valor_explicado"]
        .sum()
        .reset_index(name="delta_explicado")
    )

    resultado = df_delta.merge(explicado_total, on=dims, how="left")
    resultado["delta_explicado"] = resultado["delta_explicado"].fillna(0.0)
    resultado["delta_nao_explicado"] = resultado["delta_total"] - resultado["delta_explicado"]

    # Proteção de divisão por zero: Delta Total = 0 deixa % Explicado
    # indefinido (None), não 0 nem 100% — não existe um "% de nada".
    def _pct(explicado: float, total: float) -> float | None:
        return (explicado / total) if total != 0 else None

    resultado["pct_explicado"] = [
        _pct(e, t) for e, t in zip(resultado["delta_explicado"], resultado["delta_total"])
    ]
    resultado["pct_nao_explicado"] = [
        _pct(e, t) for e, t in zip(resultado["delta_nao_explicado"], resultado["delta_total"])
    ]
    return resultado
