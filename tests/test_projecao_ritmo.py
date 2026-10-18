import pandas as pd

def test_formula_media_realizada():
    realizado_ate_agora=600.0; ultimo_mes=3
    media=realizado_ate_agora/ultimo_mes
    fechamento=realizado_ate_agora+media*(12-ultimo_mes)
    assert fechamento == 2400.0


# ===== B4 (docs/12, 2026-10-18): a projeção pelo ritmo (e o Forecast) se
# ancora no último mês FECHADO — o mês da carga, com Realizado parcial,
# entra como projetado, não puxa a média pra baixo.

def _base_tendencia(caminho, data_carga):
    import duckdb

    con = duckdb.connect(caminho)
    orc = pd.DataFrame({"ano": 2026, "mes": range(1, 13), "valor_orcado": 100.0,
                        "classificacao_contabil": "OPEX", "familia_pacote": "PM", "pacote_id": "PM03"})
    # Jan-Ago cheios (100/mês); Set parcial (30) — carga em 15/09.
    real = pd.DataFrame({"ano": 2026, "mes": range(1, 10), "valor_realizado": [100.0] * 8 + [30.0],
                         "familia_pacote": "PM", "pacote_id": "PM03"})
    con.execute("CREATE TABLE fact_orcamento AS SELECT * FROM orc")
    con.execute("CREATE TABLE fact_realizado AS SELECT * FROM real")
    if data_carga is not None:
        meta = pd.DataFrame([("consulta_contas", "x.xlsx", data_carga, "mtime_arquivo")],
                            columns=["tipo", "arquivo", "carregado_em", "origem"])
        con.execute("CREATE TABLE meta_carga AS SELECT * FROM meta")
    return con


def test_ritmo_ignora_mes_em_andamento(tmp_path):
    from datetime import datetime

    import pytest

    from src.dashboard.tendencia import dados_tendencia

    def dez(data_carga, nome):
        con = _base_tendencia(str(tmp_path / nome), data_carga)
        df = dados_tendencia(con, 2026)
        con.close()
        linha = df[df["mes"] == 12].iloc[0]
        return float(linha["projecao_ritmo_acumulada"]), float(linha["tendencia_acumulada"]), df

    # Carga 15/09: Set em andamento -> média de Jan-Ago (100) -> 800 + 4 x 100.
    ritmo_set, forecast_set, df_set = dez(datetime(2026, 9, 15, 10, 0), "set.duckdb")
    assert ritmo_set == pytest.approx(1200.0)
    assert forecast_set == pytest.approx(1200.0)
    assert bool(df_set.loc[df_set["mes"] == 9, "tem_realizado"].iloc[0])  # curva do Realizado mostra Set
    # Carga 10/10: Set fechado (com 30) -> entra na média: 830 + 3 x 830/9.
    ritmo_out, _, _ = dez(datetime(2026, 10, 10, 10, 0), "out.duckdb")
    assert ritmo_out == pytest.approx(830.0 + 3 * 830.0 / 9)
    # Sem meta_carga: regra antiga (igual à carga em Out).
    ritmo_sem, _, _ = dez(None, "sem.duckdb")
    assert ritmo_sem == pytest.approx(ritmo_out)


# ===== 2ª revisão do Astra (2026-10-18): o mês em aberto continua na curva
# do Realizado, mas marcado como parcial (marcador próprio + hover).

def test_curva_marca_realizado_parcial(tmp_path):
    from datetime import datetime

    from src.dashboard.tendencia import dados_tendencia, figura_tendencia

    con = _base_tendencia(str(tmp_path / "parcial.duckdb"), datetime(2026, 9, 15, 10, 0))
    df = dados_tendencia(con, 2026)
    con.close()
    assert df.loc[df["realizado_parcial"], "mes"].tolist() == [9]  # só Set (carga 15/09)

    fig = figura_tendencia(df, "t")
    marcador = [t for t in fig.data if t.name == "Realizado parcial (mês em aberto)"]
    assert len(marcador) == 1 and list(marcador[0].x) == ["Set"]
    textos_realizado = list(fig.data[3].text)  # linha do Realizado acumulado
    assert textos_realizado[-1].endswith("(parcial — mês em aberto)")
    assert not any("parcial" in t for t in textos_realizado[:-1])


def test_curva_sem_meta_nao_marca_parcial(tmp_path):
    from src.dashboard.tendencia import dados_tendencia, figura_tendencia

    con = _base_tendencia(str(tmp_path / "sem.duckdb"), None)
    df = dados_tendencia(con, 2026)
    con.close()
    assert not df["realizado_parcial"].any()  # sem data da carga: regra antiga, nada marcado
    assert not any(t.name == "Realizado parcial (mês em aberto)" for t in figura_tendencia(df, "t").data)


def _nota_sem_realizado(repo: str, db: str) -> None:
    import sys as _sys

    import duckdb as _duckdb

    _sys.path.insert(0, repo)
    from src.dashboard.filtros import nota_fechamento

    con = _duckdb.connect(db, read_only=True)
    nota_fechamento(con)
    con.close()


def test_nota_avisa_base_sem_realizado(tmp_path):
    """Sem nenhum Realizado ≠ 0 não há corte: a nota avisa que o Delta
    compara com Realizado zero (antes sumia calada)."""
    from pathlib import Path

    import duckdb
    from streamlit.testing.v1 import AppTest

    db = str(tmp_path / "vazio.duckdb")
    con = duckdb.connect(db)
    con.execute("CREATE TABLE fact_realizado AS SELECT 2026 AS ano, 9 AS mes, 0.0 AS valor_realizado")
    con.close()
    repo = str(Path(__file__).resolve().parents[1])
    at = AppTest.from_function(_nota_sem_realizado, args=(repo, db), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert any("Não há Realizado contabilizado" in w.value for w in at.warning)
