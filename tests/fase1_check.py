"""Critério de pronto da Fase 1 (ver docs/01-plano-de-build-mvp.md).

Roda os loaders contra os arquivos reais em data/raw/ e confere:
- Base Zero: soma de "Vl <mês>" (melted) bate com a soma de "Total P26" bruto.
- Realizado: soma de "Montante em moeda da empresa" bate com a linha de
  Total do próprio export (excluindo rodapé/filtros).

Uso: python -m tests.fase1_check
"""
from __future__ import annotations

import pandas as pd

from src.config import carregar_config
from src.ingestion.loaders import load_base_zero, load_realizado


def checar_base_zero(cfg: dict) -> pd.DataFrame:
    caminho = cfg["caminhos"]["base_zero"]
    ano_fiscal = cfg["ano_fiscal_orcamento"]

    df = load_base_zero(caminho, ano_fiscal=ano_fiscal)
    total_calculado = df["valor_orcado"].sum()

    # Recalcula o total bruto direto do arquivo (independente do loader)
    # para servir de comparação cega.
    raw = pd.read_excel(caminho, sheet_name=0, header=None)
    linha_cab = next(i for i in range(10) if str(raw.iat[i, 0]).strip() == "Área")
    header = list(raw.iloc[linha_cab])
    idx_total_p26 = header.index("Total P26")
    total_bruto = pd.to_numeric(
        raw.iloc[linha_cab + 1:, idx_total_p26], errors="coerce"
    ).sum()

    print("=== Base Zero (Orçamento Aprovado) ===")
    print(f"  linhas carregadas (item x mês): {len(df):,}")
    print(f"  total valor_orcado (loader, soma Vl <mês>): {total_calculado:,.2f}")
    print(f"  total bruto (coluna 'Total P26' do export):  {total_bruto:,.2f}")
    diff = abs(total_calculado - total_bruto)
    print(f"  diferença: {diff:,.6f}")
    assert diff < 0.01, "Total do loader não bate com 'Total P26' do export!"
    print("  OK — bate.")
    return df


def checar_realizado(cfg: dict) -> pd.DataFrame:
    caminho = cfg["caminhos"]["realizado"]
    df = load_realizado(caminho)
    total_calculado = df["valor_realizado"].sum()

    # Linha de "Total" no rodapé do próprio export, para comparação cega.
    raw = pd.read_excel(caminho, sheet_name=0)
    linha_total = raw[raw.iloc[:, 0].astype(str).str.strip() == "Total"]
    total_export = pd.to_numeric(
        linha_total["Montante em moeda da empresa"], errors="coerce"
    ).sum()

    print()
    print("=== Base Analítico SAP (Realizado) ===")
    print(f"  linhas carregadas (lançamentos): {len(df):,}")
    print(f"  total valor_realizado (loader):     {total_calculado:,.2f}")
    print(f"  total bruto (linha 'Total' do export): {total_export:,.2f}")
    diff = abs(total_calculado - total_export)
    print(f"  diferença: {diff:,.6f}")
    assert diff < 0.01, "Total do loader não bate com a linha 'Total' do export!"
    print("  OK — bate.")
    return df


if __name__ == "__main__":
    cfg = carregar_config()
    df_orc = checar_base_zero(cfg)
    df_real = checar_realizado(cfg)

    print()
    print("=== Achados de dado tratados explicitamente (ver plano de build) ===")
    print("Classificação contábil (CAPEX/OPEX) por Pacote, Base Zero:")
    print(
        df_orc.drop_duplicates(["pacote_id", "classificacao_contabil"])
        .groupby("pacote_id")["classificacao_contabil"]
        .apply(lambda s: sorted(s.unique()))
    )
    print()
    print("Famílias de pacote encontradas:")
    print("  Base Zero:", sorted(df_orc["familia_pacote"].dropna().unique()))
    print("  Realizado:", sorted(df_real["familia_pacote"].dropna().unique()))
