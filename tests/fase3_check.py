"""Critério de pronto da Fase 3 (ver docs/01-plano-de-build-mvp.md).

Duas verificações:
1. Exemplo sintético da spec (SP: Delta Total +2,3 MM, Não Previsto
   +0,76 MM, Realizado Não Contabilizado +0,99 MM, Ajuste Contábil
   +0,30 MM, Físico -0,29 MM, Efeito Preço 0,00 MM) — confere que o "Não
   Justificado" calculado bate com a conta manual (0,54 MM).
2. Regra "Não Justificado nunca é digitado": validar_categorias tem que
   rejeitar um CSV que tente preencher essa categoria.
3. Base real (Fase 1/2): com explicacoes.csv ainda vazio (template, sem
   causa preenchida — processo de preenchimento ainda em aberto, ver
   docs/02-perguntas-em-aberto.md item 3), o Delta inteiro tem que aparecer
   como 100% não explicado — "nenhum Delta pode ficar sem classificação".

Uso: python -m tests.fase3_check
"""
from __future__ import annotations

import duckdb
import pandas as pd

from src.config import carregar_config
from src.engine.delta_calculator import calcular_delta
from src.engine.explanation_engine import calcular_explicacao, validar_categorias


def checar_exemplo_spec(categorias_validas: list[str]) -> None:
    print("=== Exemplo da spec (SP) ===")
    df_delta = pd.DataFrame({"gg_id": ["SP"], "delta_total": [2_300_000.0]})
    df_explicacao = pd.DataFrame([
        {"gg_id": "SP", "categoria": "Não Previsto", "valor_explicado": 760_000.0},
        {"gg_id": "SP", "categoria": "Realizado Não Contabilizado", "valor_explicado": 990_000.0},
        {"gg_id": "SP", "categoria": "Ajuste Contábil", "valor_explicado": 300_000.0},
        {"gg_id": "SP", "categoria": "Físico", "valor_explicado": -290_000.0},
        {"gg_id": "SP", "categoria": "Efeito Preço", "valor_explicado": 0.0},
    ])

    resultado = calcular_explicacao(df_delta, df_explicacao, dims=["gg_id"], categorias_validas=categorias_validas)
    print(resultado.to_string(index=False))

    linha = resultado.iloc[0]
    esperado_explicado = 760_000 + 990_000 + 300_000 - 290_000 + 0
    esperado_nao_justificado = 2_300_000 - esperado_explicado
    print(f"\n  delta_explicado calculado:      {linha['delta_explicado']:,.2f}")
    print(f"  delta_explicado esperado (spec): {esperado_explicado:,.2f}")
    assert abs(linha["delta_explicado"] - esperado_explicado) < 0.01
    print(f"  Não Justificado calculado:      {linha['delta_nao_explicado']:,.2f}")
    print(f"  Não Justificado esperado (spec): {esperado_nao_justificado:,.2f}  (0,54 MM)")
    assert abs(linha["delta_nao_explicado"] - esperado_nao_justificado) < 0.01
    assert abs(linha["pct_explicado"] - esperado_explicado / 2_300_000) < 1e-9
    print("  OK — bate com o exemplo da spec.")


def checar_nao_justificado_nunca_digitado(categorias_validas: list[str]) -> None:
    print()
    print("=== Regra: 'Não Justificado' nunca é digitado ===")
    df_invalido = pd.DataFrame([
        {"gg_id": "SP", "categoria": "Não Justificado", "valor_explicado": 100.0},
    ])
    try:
        validar_categorias(df_invalido, categorias_validas)
    except ValueError as exc:
        print(f"  OK — rejeitado como esperado: {exc}")
    else:
        raise AssertionError("validar_categorias deveria ter rejeitado 'Não Justificado' no CSV!")


def checar_base_real(cfg: dict) -> None:
    print()
    print("=== Base real (explicacoes.csv ainda vazio) ===")
    con = duckdb.connect(cfg["caminhos"]["warehouse_db"], read_only=True)
    try:
        df_delta = calcular_delta(con, dims=["pacote_id"])
    finally:
        con.close()

    df_explicacao_vazio = pd.DataFrame(columns=["pacote_id", "categoria", "valor_explicado"])
    resultado = calcular_explicacao(
        df_delta, df_explicacao_vazio, dims=["pacote_id"], categorias_validas=cfg["categorias_causa"]
    )
    print(resultado[["pacote_id", "orcado", "realizado", "delta_total", "delta_nao_explicado", "pct_nao_explicado"]].to_string(index=False))

    sem_causa_ainda_explicada = (resultado["delta_nao_explicado"] == resultado["delta_total"]).all()
    assert sem_causa_ainda_explicada, "Com explicacoes.csv vazio, todo Delta deveria estar 100% não explicado."
    print("\n  OK — com o CSV de apoio vazio, 100% do Delta aparece como Não Justificado (nada é omitido).")


if __name__ == "__main__":
    cfg = carregar_config()
    checar_exemplo_spec(cfg["categorias_causa"])
    checar_nao_justificado_nunca_digitado(cfg["categorias_causa"])
    checar_base_real(cfg)
