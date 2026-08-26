"""Critério de pronto da Fase 2 (ver docs/01-plano-de-build-mvp.md).

"consulta simples SELECT pacote_id, SUM(valor) FROM fact_orcamento GROUP BY
pacote_id reproduz os mesmos números que já validamos manualmente na
primeira rodada do projeto" — aqui validado contra os totais já conferidos
na Fase 1 (tests/fase1_check.py), não contra números "de memória".

Uso: python -m tests.fase2_check
"""
from __future__ import annotations

import duckdb

from src.config import carregar_config

TOTAL_ORCADO_ESPERADO = 62_390_836.259436235
TOTAL_REALIZADO_ESPERADO = 7_718_526.977056287


def main() -> None:
    cfg = carregar_config()
    con = duckdb.connect(cfg["caminhos"]["warehouse_db"], read_only=True)

    print("=== Tabelas no warehouse ===")
    tabelas = con.execute("SHOW TABLES").fetchall()
    for (nome,) in tabelas:
        (n,) = con.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()
        print(f"  {nome}: {n:,} linhas")

    print()
    print("=== fact_orcamento por pacote_id ===")
    df_pacote = con.execute(
        "SELECT pacote_id, SUM(valor_orcado) AS total FROM fact_orcamento "
        "GROUP BY pacote_id ORDER BY pacote_id"
    ).df()
    print(df_pacote.to_string(index=False))

    (total_orcado,) = con.execute("SELECT SUM(valor_orcado) FROM fact_orcamento").fetchone()
    (total_realizado,) = con.execute("SELECT SUM(valor_realizado) FROM fact_realizado").fetchone()

    print()
    print(f"total fact_orcamento:  {total_orcado:,.2f}  (esperado {TOTAL_ORCADO_ESPERADO:,.2f})")
    print(f"total fact_realizado:  {total_realizado:,.2f}  (esperado {TOTAL_REALIZADO_ESPERADO:,.2f})")

    assert abs(total_orcado - TOTAL_ORCADO_ESPERADO) < 0.01, "fact_orcamento não bate com a Fase 1!"
    assert abs(total_realizado - TOTAL_REALIZADO_ESPERADO) < 0.01, "fact_realizado não bate com a Fase 1!"
    print()
    print("OK — fact_orcamento e fact_realizado batem com os totais validados na Fase 1.")

    print()
    print("=== Delta simples por pacote_id (Real Contabilizado - Orçamento) ===")
    df_delta = con.execute(
        """
        WITH orc AS (
            SELECT pacote_id, SUM(valor_orcado) AS orcado FROM fact_orcamento GROUP BY pacote_id
        ), real AS (
            SELECT pacote_id, SUM(valor_realizado) AS realizado FROM fact_realizado GROUP BY pacote_id
        )
        SELECT
            COALESCE(orc.pacote_id, real.pacote_id) AS pacote_id,
            orc.orcado,
            real.realizado,
            COALESCE(real.realizado, 0) - COALESCE(orc.orcado, 0) AS delta
        FROM orc FULL OUTER JOIN real USING (pacote_id)
        ORDER BY pacote_id
        """
    ).df()
    print(df_delta.to_string(index=False))

    con.close()


if __name__ == "__main__":
    main()
