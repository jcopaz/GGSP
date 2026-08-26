"""Validação do motor de Delta (explanation_engine.calcular_explicacao)
contra números reais da RDG de julho/2026 — não é dado sintético nem
exemplo inventado: vem direto do PPT usado na reunião com a Diretoria
(`Conceito/Reunião Performance DINFRA - Julho - Final.pptx`, slide
"Financeiro CAPEX - DINFRA", linha "Total" da tabela por GG).

Escopo desta validação: só a ARITMÉTICA do motor (soma das categorias +
Não Justificado = Delta Total; % Explicado; fechamento do waterfall) — não
compara com o warehouse carregado aqui (Malha SP, ano fiscal inteiro). A
RDG cobre DINFRA inteira (FA+LC+RJ+SP) num corte Jan-Jun; comparar escopos
diferentes não validaria nada, só criaria uma divergência falsa.

# GAP: a coluna "Taxa Bom/Mix" da tabela por GG (FA/LC/RJ/SP) não fecha
# contra a linha "Total" do slide — soma de FA+LC+RJ+SP dá +0,20, o slide
# mostra -0,51 (diferença de 0,71). As outras 6 colunas da tabela (Físico,
# Efeito Preço, Não Previsto, Ajuste Contábil, Real executado, Real não
# contabilizado) fecham exatas. Por isso este teste usa só a linha
# "Total", que vem direta do slide (não é soma feita por mim) — não
# reconcilia o detalhe por GG até confirmar com quem apresentou a RDG se é
# erro de transcrição nossa ou do próprio slide.

Uso: python -m tests.validacao_rdg_julho_check
"""
from __future__ import annotations

import pandas as pd

from src.config import carregar_config
from src.engine.explanation_engine import calcular_explicacao

GG_TESTE = "DINFRA_JUL26"

# Linha "Total" da tabela "Financeiro CAPEX - DINFRA" (Jan-Jun/26), em R$ milhões.
CATEGORIAS_RDG_JULHO = {
    "Físico": -4.71,
    "Taxa Bom/Mix": -0.51,
    "Efeito Preço": -2.25,
    "Não Previsto": 0.53,
    "Ajuste Contábil": -0.72,
    "Realizado Não Contabilizado": 6.10,
}


def main() -> None:
    cfg = carregar_config()
    categorias_validas = cfg["categorias_causa"]

    delta_total = round(sum(CATEGORIAS_RDG_JULHO.values()), 2)
    print("=== Validação do motor contra a RDG de julho/2026 (linha 'Total', CAPEX DINFRA) ===")
    for categoria, valor in CATEGORIAS_RDG_JULHO.items():
        print(f"  {categoria:<30} {valor:>7.2f} MM")
    print(f"  Delta Total (soma das categorias) {delta_total:>7.2f} MM")

    df_delta = pd.DataFrame([{"gg_id": GG_TESTE, "delta_total": delta_total}])
    df_explicacao = pd.DataFrame([
        {
            "pacote_id": GG_TESTE, "conta_id": "", "ano": 2026, "mes": 6,
            "gg_id": GG_TESTE, "categoria": categoria, "descricao": "RDG julho/2026 (real)",
            "valor_explicado": valor,
        }
        for categoria, valor in CATEGORIAS_RDG_JULHO.items()
    ])

    resultado = calcular_explicacao(
        df_delta, df_explicacao, dims=["gg_id"], categorias_validas=categorias_validas
    )
    linha = resultado.iloc[0]

    print()
    print(f"Delta Explicado (motor):               {linha['delta_explicado']:.2f} MM")
    print(f"Delta Não Explicado / Não Justificado:  {linha['delta_nao_explicado']:.2f} MM")
    print(f"% Explicado:                            {linha['pct_explicado']:.1%}")

    assert abs(linha["delta_explicado"] - delta_total) < 0.01, (
        "Delta Explicado deveria fechar em 100% — a RDG já apresentou todas as categorias."
    )
    assert abs(linha["delta_nao_explicado"]) < 0.01, (
        "Não Justificado deveria ser ~0 — a RDG já explicou o delta inteiro por categoria."
    )
    assert abs(linha["pct_explicado"] - 1.0) < 0.001, "% Explicado deveria ser 100%."
    print()
    print(
        "OK — o motor fecha exatamente com os números reais da RDG "
        "(soma das categorias = Delta Total, Não Justificado = 0)."
    )

    # Mesmo critério de fechamento usado no Nível 2 (ver fase4_fase5_check.py):
    # soma das barras do waterfall (categorias + Não Justificado) tem que
    # fechar exatamente no Delta Total.
    soma_barras = sum(CATEGORIAS_RDG_JULHO.values()) + linha["delta_nao_explicado"]
    assert abs(soma_barras - delta_total) < 0.01, "Waterfall não fecha no Delta Total."
    print(
        "OK — waterfall (categorias + Não Justificado) fecha exatamente no "
        "Delta Total, como no Nível 2 do painel."
    )


if __name__ == "__main__":
    main()
