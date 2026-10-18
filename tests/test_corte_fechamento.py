"""Corte de fechamento contábil pela data da carga do Realizado (B4,
docs/12, 2026-10-18) — funções puras, sem Streamlit nem warehouse.

Regra: o mês M da carga é sempre aberto; M-1 só fecha se a carga foi no
5º dia útil de M ou depois (calendário da GGFC, dias úteis = seg-sex sem
feriados — GAP em `filtros.DIA_UTIL_FECHAMENTO_CONTABIL`).
corte = min(último mês com Realizado ≠ 0, M-1 ou M-2).

Uso: python -m pytest tests/test_corte_fechamento.py -q
"""
from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.dashboard.filtros import (
    corte_fechamento,
    dia_util_fechamento,
    meses_abertos_na_carga,
    rotulo_meses_em_aberto,
)


@pytest.mark.parametrize("ano, mes, esperado", [
    (2026, 10, date(2026, 10, 7)),   # qui 1, sex 2, seg 5, ter 6, qua 7
    (2026, 9, date(2026, 9, 7)),
    (2027, 1, date(2027, 1, 7)),     # sex 1, seg 4 ... qui 7
])
def test_quinto_dia_util(ano, mes, esperado):
    assert dia_util_fechamento(ano, mes) == esperado


@pytest.mark.parametrize("ultimo, data_carga, esperado", [
    (202609, datetime(2026, 9, 15), 202608),    # Set é o mês da carga: parcial
    (202609, datetime(2026, 10, 10), 202609),   # Out: depois do 5º dia útil, Set fechou
    (202609, datetime(2026, 10, 7), 202609),    # no próprio 5º dia útil, Set fechou
    (202609, datetime(2026, 10, 3), 202608),    # antes do 5º dia útil: Set aguardando
    (202609, datetime(2026, 12, 5), 202609),    # limitado pelo dado (min)
    (202609, None, 202609),                     # sem meta_carga: regra antiga
    (None, datetime(2026, 10, 10), None),       # sem Realizado: sem corte
    (202601, datetime(2026, 1, 20), 202512),    # virada de ano
    (202612, datetime(2027, 1, 5), 202611),     # 5º dia útil de Jan/2027 = 07/01
    (202609, date(2026, 9, 15), 202608),        # aceita date também
])
def test_corte_fechamento(ultimo, data_carga, esperado):
    assert corte_fechamento(ultimo, data_carga) == esperado


def test_meses_abertos_e_rotulo():
    assert meses_abertos_na_carga(datetime(2026, 10, 10)) == [(202610, "em andamento")]
    abertos = meses_abertos_na_carga(datetime(2026, 10, 3))
    assert abertos == [(202609, "aguardando fechamento contábil"), (202610, "em andamento")]
    assert rotulo_meses_em_aberto(abertos) == (
        "Set/2026 aguardando fechamento contábil e Out/2026 em andamento"
    )


def test_regra_desligada_volta_ao_mes_anterior(monkeypatch):
    import src.dashboard.filtros as filtros

    monkeypatch.setattr(filtros, "DIA_UTIL_FECHAMENTO_CONTABIL", None)
    assert corte_fechamento(202609, datetime(2026, 10, 3)) == 202609


def test_linhas_meta_carga(tmp_path):
    from src.model.build_star_schema import _linhas_meta_carga

    arquivo = tmp_path / "Orçado x Realizado.xlsx"
    arquivo.write_bytes(b"x")
    ts = datetime(2026, 10, 10, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo")).timestamp()
    os.utime(arquivo, (ts, ts))
    df = _linhas_meta_carga({
        "consulta_contas": str(arquivo),
        "base_zero": str(tmp_path / "inexistente.xlsx"),
        "data_raw": str(tmp_path),
    })
    assert list(df["tipo"]) == ["consulta_contas"]
    linha = df.iloc[0]
    assert linha["arquivo"] == "Orçado x Realizado.xlsx"
    assert linha["origem"] == "mtime_arquivo"
    assert linha["carregado_em"].to_pydatetime() == datetime(2026, 10, 10, 12, 0)
    assert corte_fechamento(202609, linha["carregado_em"].to_pydatetime()) == 202609


def test_linhas_meta_carga_vazia_tem_colunas(tmp_path):
    from src.model.build_star_schema import _linhas_meta_carga

    df = _linhas_meta_carga({"consulta_contas": str(tmp_path / "nao_existe.xlsx")})
    assert df.empty and list(df.columns) == ["tipo", "arquivo", "carregado_em", "origem"]


def test_restaurar_arquivo_bruto_repoe_data_do_upload(tmp_path, monkeypatch):
    import src.ingestion.arquivo_bruto as arquivo_bruto

    enviado_em = datetime(2026, 9, 15, 10, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    monkeypatch.setattr(
        arquivo_bruto, "buscar_um", lambda sql, params: {"conteudo": b"abc", "enviado_em": enviado_em},
    )
    destino = tmp_path / "raw" / "consulta.xlsx"
    assert arquivo_bruto.restaurar_arquivo_bruto("consulta_contas", str(destino))
    assert destino.read_bytes() == b"abc"
    assert os.path.getmtime(destino) == pytest.approx(enviado_em.timestamp(), abs=1)
