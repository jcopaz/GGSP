"""Fase 3 — cálculo de Delta.

Delta = Real Contabilizado - Orçamento. Positivo = estouro, negativo =
economia (ver docs/00-especificacao-consolidada.md, seção 2). Funciona para
qualquer conjunto de dimensões comuns às duas fact tables (ex.: só
`pacote_id`, ou `ano, mes, pacote_id`) — quem decide o recorte é quem chama,
não fica fixo em GG nem em Pacote.
"""
from __future__ import annotations

import duckdb
import pandas as pd


def calcular_delta(
    con: duckdb.DuckDBPyConnection,
    dims: list[str],
    filtro_orcado: tuple[str, list] | None = None,
    filtro_realizado: tuple[str, list] | None = None,
) -> pd.DataFrame:
    """Agrega fact_orcamento e fact_realizado pelas mesmas `dims` e junta.

    Linhas presentes só num dos dois lados entram com o outro lado = 0
    (ex.: pacote sem orçamento carregado ainda, como PD/PP/PASSIVO no
    Realizado — ver GAP em build_star_schema.py sobre escopo de dados).

    `filtro_orcado`/`filtro_realizado`: (fragmento_sql, params) opcionais,
    aplicados cada um só na tabela correspondente — as duas fact tables não
    têm exatamente as mesmas colunas (ex.: Coordenação só existe no
    Realizado), então o filtro de cada lado é independente. Ver
    src/dashboard/filtros.py:clausula_where.
    """
    if not dims:
        raise ValueError("Informe ao menos uma dimensão para agrupar o Delta.")

    dims_sql = ", ".join(dims)
    where_orc, params_orc = filtro_orcado or ("", [])
    where_real, params_real = filtro_realizado or ("", [])

    orcado = con.execute(
        f"SELECT {dims_sql}, SUM(valor_orcado) AS orcado "
        f"FROM fact_orcamento WHERE 1=1{where_orc} GROUP BY {dims_sql}",
        params_orc,
    ).df()
    realizado = con.execute(
        f"SELECT {dims_sql}, SUM(valor_realizado) AS realizado "
        f"FROM fact_realizado WHERE 1=1{where_real} GROUP BY {dims_sql}",
        params_real,
    ).df()

    delta = orcado.merge(realizado, on=dims, how="outer")
    delta["orcado"] = delta["orcado"].fillna(0.0)
    delta["realizado"] = delta["realizado"].fillna(0.0)
    delta["delta_total"] = delta["realizado"] - delta["orcado"]
    return delta
