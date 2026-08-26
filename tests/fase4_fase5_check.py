"""Critério de pronto das Fases 4 e 5 (ver docs/01-plano-de-build-mvp.md).

- Fase 4: "a soma das barras de categoria + 'Não Justificado' fecha
  exatamente no Delta Total mostrado no Nível 1."
- Fase 5: "clicar em uma categoria mostra os pacotes cuja soma bate com o
  valor da categoria no waterfall" — testado aqui com "Não Justificado"
  (única categoria com valor real hoje, já que explicacoes.csv ainda é só
  o template vazio).

Uso: python -m tests.fase4_fase5_check
"""
from __future__ import annotations

import duckdb

from src.config import carregar_config
from src.dashboard.nivel1_diretoria import GG_TOTAL, resumo_nivel1
from src.dashboard.nivel2_gg import dados_waterfall_gg
from src.dashboard.nivel3_pacotes import dados_ranking_pacotes


def main() -> None:
    cfg = carregar_config()
    con = duckdb.connect(cfg["caminhos"]["warehouse_db"], read_only=True)

    try:
        print("=== Nível 1 — resumo por GG (sem card de total sintético, ver 2026-08-10) ===")
        resumo = resumo_nivel1(con)
        print(resumo.to_string(index=False))
        # Soma de todos os GGs reais = escopo DINFRA inteiro, mesmo cálculo
        # que dados_waterfall_gg(GG_TOTAL) faz sem filtro de pacote.
        delta_dinfra = resumo["delta_total"].sum()

        print()
        print("=== Nível 2 — waterfall DINFRA ===")
        _, delta_total, df_categorias = dados_waterfall_gg(
            con, GG_TOTAL, cfg["caminhos"]["explicacoes"], cfg["categorias_causa"]
        )
        print(df_categorias.to_string(index=False))
        soma_barras = df_categorias["valor"].sum()
        print(f"\n  Delta Total (Nível 1):        {delta_dinfra:,.2f}")
        print(f"  Delta Total (Nível 2, calc):  {delta_total:,.2f}")
        print(f"  soma das barras (Nível 2):    {soma_barras:,.2f}")
        assert abs(delta_dinfra - delta_total) < 0.01, "Nível 1 e Nível 2 divergem no Delta Total!"
        assert abs(soma_barras - delta_total) < 0.01, "Barras do waterfall não fecham no Delta Total!"
        print("  OK — waterfall fecha exatamente no Delta Total do Nível 1.")

        print()
        print("=== Nível 3 — drill-down em 'Não Justificado' ===")
        valor_categoria = df_categorias.loc[df_categorias["categoria"] == "Não Justificado", "valor"].iloc[0]
        ranking = dados_ranking_pacotes(
            con, GG_TOTAL, "Não Justificado", cfg["caminhos"]["explicacoes"], cfg["categorias_causa"]
        )
        print(ranking.to_string(index=False))
        soma_ranking = ranking["valor"].sum()
        print(f"\n  valor da categoria no waterfall: {valor_categoria:,.2f}")
        print(f"  soma do ranking de pacotes:      {soma_ranking:,.2f}")
        assert abs(valor_categoria - soma_ranking) < 0.01, "Ranking de pacotes não bate com a barra da categoria!"
        print("  OK — soma dos pacotes bate com o valor da categoria no waterfall.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
