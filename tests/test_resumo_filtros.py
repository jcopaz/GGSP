"""Filtros da sidebar em todas as telas de Manutenção + "a realizar"
(validação de 18/10/2026, itens D1 e P1-P9 de docs/12).

Base sintética em DuckDB (tmp_path) — não depende de data/raw nem do
warehouse local. Valores escolhidos pra conta fechar de cabeça:
- OPEX: 4 CCs x 2 Pacotes x R$100 mil/mês x 12 meses = R$ 9,6 MM Orçado.
- CAPEX: 2 PEPs (SP->GER MALHA, VP->GER IMPLANT VP) x R$50 mil x 12 = R$ 1,2 MM.
- Realizado (OPEX, Jan-Set): GER MALHA R$80 mil/linha, demais R$120 mil.
  Último mês fechado = Set/2026 -> Delta/Aderência comparam Jan-Set
  (Orçado OPEX R$ 7,2 MM); Out-Dez (R$ 2,4 MM) é "a realizar".
- Fixture `base` não tem `meta_carga` (valida o fallback da regra antiga);
  `base_carga_set` (carga 15/09/2026 -> Set em andamento, corte Ago) e
  `base_carga_out` (carga 10/10/2026 -> Out em andamento, corte Set)
  validam o B4 de docs/12. `base_futuro` = carga Out + R$ 50 mil de
  Realizado em Nov (competência posterior à carga -> alerta).

Uso: python -m pytest tests/test_resumo_filtros.py -q
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

REPO = str(Path(__file__).resolve().parents[1])

_GER = {"GGE_0025": "GER MALHA (SP)", "GGE_0029": "GER INFRAESTRUTURA (SP)", "GGE_0197": "GER IMPLANT DE OBRAS E MALHA VP"}
_CC = {"CCR022": ("GGE_0025", "MALHA - JUNDIAI"), "CCR063": ("GGE_0025", "MALHA - TAUBATE"),
       "CCR099": ("GGE_0029", "MANUT DRENAGEM E INFRA DE VIA SP"), "CCR288": ("GGE_0197", "OBRAS - VALE DO PARAIBA")}


def _criar_base(caminho: str, data_carga: datetime | None = None, realizado_nov: float = 0.0) -> None:
    orc, real = [], []
    base_orc = dict(ano=2026, conta_orcamento_id="PM03009", conta_interna_id="PM03009", conta_interna_nome="X",
                    pep_nome="", area="", gg_id="GGG_0054", gg_nome="GG", tipo_item="", grupo_disciplina="",
                    sub_grupo_escopo="")
    for mes in range(1, 13):
        for cc, (ger, coord) in _CC.items():
            for pac, fam in (("PM03", "PM"), ("PD01", "PD")):
                orc.append({**base_orc, "mes": mes, "pacote_id": pac, "familia_pacote": fam,
                            "classificacao_contabil": "OPEX", "centro_custo_id": cc, "pep_id": "",
                            "gerencia_raw": _GER[ger], "gerencia_id": ger, "valor_orcado": 100_000.0})
                if mes <= 9:
                    real.append(dict(ano=2026, mes=mes, pacote_id=pac, familia_pacote=fam, conta_razao_id="",
                                     conta_razao_nome="", conta_interna_id="PM03009", conta_interna_nome="X",
                                     centro_custo_id=cc, centro_custo_nome=cc, coordenacao=coord,
                                     classificacao_contabil="OPEX", gg_id="GGG_0054", gg_nome="GG",
                                     gerencia_id=ger, gerencia_nome=_GER[ger],
                                     valor_realizado=80_000.0 if ger == "GGE_0025" else 120_000.0))
        for pep, reg, ger in (("MC/24004C-04-01-02", "SP", "GGE_0025"), ("MC/24005C-04-01-01", "VP", "GGE_0197")):
            orc.append({**base_orc, "mes": mes, "pacote_id": "PM03", "familia_pacote": "PM",
                        "conta_interna_nome": "VIA", "classificacao_contabil": "CAPEX", "centro_custo_id": "",
                        "pep_id": pep, "gerencia_raw": reg, "gerencia_id": ger, "valor_orcado": 50_000.0})
    if realizado_nov:
        real.append(dict(ano=2026, mes=11, pacote_id="PM03", familia_pacote="PM", conta_razao_id="",
                         conta_razao_nome="", conta_interna_id="PM03009", conta_interna_nome="X",
                         centro_custo_id="CCR099", centro_custo_nome="CCR099", coordenacao=_CC["CCR099"][1],
                         classificacao_contabil="OPEX", gg_id="GGG_0054", gg_nome="GG",
                         gerencia_id="GGE_0029", gerencia_nome=_GER["GGE_0029"], valor_realizado=realizado_nov))
    tabelas = {
        "fact_orcamento": pd.DataFrame(orc),
        "fact_realizado": pd.DataFrame(real),
        "dim_gerencia": pd.DataFrame(
            [*_GER.items(), ("CGG050", "GER. GERAL DE INFRAESTRUTURA (SP) - DIRETO GG")],
            columns=["gerencia_id", "gerencia_nome"],
        ),
        "fact_realizado_documento": pd.DataFrame(real)[
            ["ano", "mes", "pacote_id", "centro_custo_id", "coordenacao", "valor_realizado"]
        ],
        "dim_pacote": pd.DataFrame([("PM03", "PM", "MALHA"), ("PD01", "PD", "DESPESAS")],
                                   columns=["pacote_id", "familia_pacote", "nome_pacote"]),
        "dim_tempo": pd.DataFrame([(2026, m, (m - 1) // 3 + 1) for m in range(1, 13)], columns=["ano", "mes", "trimestre"]),
    }
    if data_carga is not None:
        # Mesmo schema que o build grava (`build_star_schema._linhas_meta_carga`).
        tabelas["meta_carga"] = pd.DataFrame(
            [("consulta_contas", "Orçado x Realizado.xlsx", data_carga, "mtime_arquivo")],
            columns=["tipo", "arquivo", "carregado_em", "origem"],
        )
    con = duckdb.connect(caminho)
    for nome, df in tabelas.items():
        con.register("df_tmp", df)
        con.execute(f"CREATE TABLE {nome} AS SELECT * FROM df_tmp")
        con.unregister("df_tmp")
    con.close()


def _app(db: str, repo: str) -> None:
    import os as _os
    import sys as _sys

    import duckdb as _duckdb

    _sys.path.insert(0, repo)
    _os.chdir(repo)
    from src.config import carregar_config
    from src.dashboard.resumo_executivo import render_resumo_executivo

    con = _duckdb.connect(db, read_only=True)
    render_resumo_executivo(con, "/inexistente.csv", carregar_config()["categorias_causa"], False, 2026)


def _card(at) -> dict[str, str]:
    md = " ".join(m.value for m in at.markdown)
    return {a.strip().replace("&nbsp;", ""): b.strip().replace("\\$", "$")
            for a, b in re.findall(r"\| ([^|]+?) \| ([^|]+?) \|", md)}


def _render(db: str, sessao: dict):
    at = AppTest.from_function(_app, args=(db, REPO), default_timeout=60)
    for k, v in sessao.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> str:
    os.environ["ORCAMENTO_SKIP_LOGIN"] = "1"
    caminho = str(tmp_path_factory.mktemp("w") / "w.duckdb")
    _criar_base(caminho)
    return caminho


def _base_com_carga(tmp_path_factory, nome: str, data_carga: datetime, realizado_nov: float = 0.0) -> str:
    os.environ["ORCAMENTO_SKIP_LOGIN"] = "1"
    caminho = str(tmp_path_factory.mktemp(nome) / "w.duckdb")
    _criar_base(caminho, data_carga=data_carga, realizado_nov=realizado_nov)
    return caminho


@pytest.fixture(scope="module")
def base_carga_set(tmp_path_factory) -> str:
    return _base_com_carga(tmp_path_factory, "set", datetime(2026, 9, 15, 10, 0))


@pytest.fixture(scope="module")
def base_carga_out(tmp_path_factory) -> str:
    return _base_com_carga(tmp_path_factory, "out", datetime(2026, 10, 10, 10, 0))


@pytest.fixture(scope="module")
def base_futuro(tmp_path_factory) -> str:
    return _base_com_carga(tmp_path_factory, "fut", datetime(2026, 10, 10, 10, 0), realizado_nov=50_000.0)


@pytest.mark.parametrize("sessao, orcado, capex, real, aderencia, a_realizar, waterfall", [
    ({}, "R$ 10,8 MM", "R$ 1,2 MM", "R$ 7,2 MM", "100,0%", "R$ 2,4 MM", True),
    ({"filtro_gerencia": ["GER MALHA (SP)"]}, "R$ 5,4 MM", "R$ 600 mil", "R$ 2,9 MM", "80,0%", "R$ 1,2 MM", False),
    ({"filtro_coordenacao": ["MALHA - JUNDIAI"]}, "R$ 2,4 MM", "R$ 0", "R$ 1,4 MM", "80,0%", "R$ 600 mil", False),
    ({"filtro_centro_custo": ["CCR099"]}, "R$ 2,4 MM", "R$ 0", "R$ 2,2 MM", "120,0%", "R$ 600 mil", False),
    ({"filtro_pep": ["MC/24004C-04-01-02"]}, "R$ 600 mil", "R$ 600 mil", "R$ 0", "—", "R$ 0", False),
    ({"filtro_classificacao": ["CAPEX"]}, "R$ 1,2 MM", "R$ 1,2 MM", "R$ 0", "—", "R$ 0", False),
    ({"filtro_pacote": ["PD01"]}, "R$ 4,8 MM", "R$ 0", "R$ 3,6 MM", "100,0%", "R$ 1,2 MM", True),
    ({"filtro_gerencia": ["GER MALHA (SP)"], "filtro_periodo_trimestres": [1]},
     "R$ 1,4 MM", "R$ 150 mil", "R$ 960 mil", "80,0%", "R$ 0", False),
    # P7: mês sem fechamento não vira desvio — vai inteiro pra "a realizar".
    ({"filtro_periodo_meses": [12]}, "R$ 900 mil", "R$ 100 mil", "R$ 0", "—", "R$ 800 mil", True),
])
def test_card_responde_ao_filtro(base, sessao, orcado, capex, real, aderencia, a_realizar, waterfall):
    at = _render(base, sessao)
    card = _card(at)
    assert card["Orçamento (CAPEX+OPEX)"] == orcado
    assert card["↳ CAPEX"] == capex
    assert card["Real Contabilizado (OPEX)"] == real
    assert card["Aderência (OPEX x OPEX)"] == aderencia
    assert card["A realizar (Orçado OPEX após Set/2026)"] == a_realizar
    aviso_causa = any("Decomposição por causa indisponível" in i.value for i in at.info)
    assert aviso_causa is (not waterfall)
    titulo = next(m.value for m in at.markdown if "GER. GERAL" in m.value or "RECORTE FILTRADO" in m.value)
    filtro_org = any(not k.startswith("filtro_periodo") for k in sessao)
    assert ("RECORTE FILTRADO" in titulo) is filtro_org


def test_gerencias_locais_orcado_so_opex(base):
    at = _render(base, {"filtro_gerencia": ["GER MALHA (SP)"]})
    tabela = next(d.value for d in at.dataframe if "Gerência Local" in getattr(d.value, "data", d.value).columns)
    df = getattr(tabela, "data", tabela)
    linha = df[df["Gerência Local"] == "GER MALHA (SP)"].iloc[0]
    assert linha["Orçado"] == pytest.approx(3_600_000.0)  # OPEX Jan-Set, sem o CAPEX SP
    assert linha["Realizado"] == pytest.approx(2_880_000.0)
    assert set(df["Gerência Local"]) == {"GER MALHA (SP)"}


def _sidebar(db: str, repo: str) -> None:
    import os as _os
    import sys as _sys

    import duckdb as _duckdb

    _sys.path.insert(0, repo)
    _os.chdir(repo)
    from src.dashboard.filtros import renderizar_filtros_sidebar

    renderizar_filtros_sidebar(_duckdb.connect(db, read_only=True))


def test_limpar_filtros_zera_os_seletores(base):
    at = AppTest.from_function(_sidebar, args=(base, REPO), default_timeout=60)
    at.run()
    caixa = lambda: next(m for m in at.sidebar.multiselect if m.label == "Classificação (CAPEX/OPEX)")  # noqa: E731
    caixa().select("OPEX").run()
    next(b for b in at.sidebar.button if b.label == "Aplicar filtros").click().run()
    assert at.session_state["filtro_classificacao"] == ["OPEX"]
    next(b for b in at.sidebar.button if b.label == "Limpar filtros").click().run()
    assert not at.exception
    assert caixa().value == []
    assert "filtro_classificacao" not in at.session_state


# ===== Demais telas (P1-P9) — funções chamadas dentro de um AppTest, que
# fornece o session_state; o resultado volta em JSON via st.code.

def _app_valores(db: str, repo: str, alvo: str) -> None:
    import json as _json
    import os as _os
    import sys as _sys

    import duckdb as _duckdb
    import streamlit as _st

    _sys.path.insert(0, repo)
    _os.chdir(repo)
    con = _duckdb.connect(db, read_only=True)
    out: dict = {}
    if alvo == "cc":
        from src.dashboard.nivel5_centro_custo import dados_centro_custo

        out = {"orc": dados_centro_custo(con)["orcado"].sum(), "real": dados_centro_custo(con)["realizado"].sum()}
    elif alvo == "render_n4":
        from src.dashboard.nivel4_contas import render_nivel4_contas

        render_nivel4_contas(con, 2026)
        return
    elif alvo == "analise":
        from src.dashboard.nivel4_contas import dados_familia, orcado_capex_fora_da_arvore
        from src.dashboard.visao_manutencao import resumo_manutencao

        fam = dados_familia(con)
        pm = resumo_manutencao(con, "PM")
        out = {"orc": fam["orcado"].sum(), "real": fam["realizado"].sum(),
               "capex_fora": orcado_capex_fora_da_arvore(con),
               "pm_orc": pm["orcado"], "pm_real": pm["realizado"]}
    elif alvo == "desvios":
        from src.dashboard.filtros import clausulas_gerencias_opex
        from src.dashboard.mapa_calor_gerencia_pacote import dados_heatmap_gerencia_pacote
        from src.dashboard.nivel1_diretoria import resumo_nivel1

        n1 = resumo_nivel1(con).iloc[0]
        hm = dados_heatmap_gerencia_pacote(con, "DINFRA", filtros=clausulas_gerencias_opex(con))
        out = {"delta": n1["delta_total"], "aderencia": n1["aderencia"],
               "hm_gerencias": sorted(set(hm["gerencia_rotulo"]))}
    elif alvo == "sap":
        from src.dashboard.filtros import clausula_where, combinar_clausulas
        from src.dashboard.nivel6_sap import _clausula_gerencia_classificacao_pep

        where, params = combinar_clausulas(
            clausula_where({"pacote_id": "pacote_id", "centro_custo_id": "centro_custo_id",
                            "coordenacao": "coordenacao"}),
            _clausula_gerencia_classificacao_pep(),
        )
        (n,) = con.execute(f"SELECT COUNT(*) FROM fact_realizado_documento WHERE 1=1{where}", params).fetchone()
        out = {"n": n}
    elif alvo == "projecao":
        from src.dashboard.projecao_opex import render_projecao_opex

        render_projecao_opex(con, 2026)
        return
    elif alvo == "sustaining":
        from src.dashboard.visao_classificacao import resumo_classificacao

        out = {"orc": resumo_classificacao(con, "CAPEX")["orcado"]}
    elif alvo == "badge_obras":
        from src.dashboard.filtros import renderizar_badge_filtros_ativos

        renderizar_badge_filtros_ativos("obras")
        return
    _st.code(_json.dumps(out, default=float))


def _valores(db: str, alvo: str, sessao: dict):
    at = AppTest.from_function(_app_valores, args=(db, REPO, alvo), default_timeout=60)
    for k, v in sessao.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def _json(at) -> dict:
    import json

    return json.loads(at.code[0].value)


def test_p1_p2_analise_financeira_opex_x_opex(base):
    v = _json(_valores(base, "analise", {}))
    assert v["orc"] == pytest.approx(7_200_000.0)  # Orçado só OPEX, Jan-Set
    assert v["real"] == pytest.approx(7_200_000.0)
    assert v["capex_fora"] == pytest.approx(1_200_000.0)  # CAPEX fica fora, com legenda

    v = _json(_valores(base, "analise", {"filtro_classificacao": ["CAPEX"]}))
    # B1: Contas/CC são sempre OPEX x OPEX — CAPEX zera os dois lados e o
    # CAPEX do recorte aparece só como aviso (capex_fora).
    assert v["orc"] == 0
    assert v["real"] == 0  # antes: Realizado OPEX inteiro contra Orçado CAPEX
    assert v["capex_fora"] == pytest.approx(1_200_000.0)
    assert v["pm_orc"] == 0 and v["pm_real"] == 0

    v = _json(_valores(base, "analise", {"filtro_gerencia": ["GER MALHA (SP)"]}))
    assert v["orc"] == pytest.approx(3_600_000.0)
    assert v["real"] == pytest.approx(2_880_000.0)


def test_p4_desvios_e_causas_responde_ao_filtro(base):
    v = _json(_valores(base, "desvios", {"filtro_gerencia": ["GER MALHA (SP)"]}))
    assert v["delta"] == pytest.approx(2_880_000.0 - 3_600_000.0)
    assert v["aderencia"] == pytest.approx(0.8)
    assert v["hm_gerencias"] == ["GER MALHA (SP)"]


@pytest.mark.parametrize("sessao, esperado", [
    ({}, 72),
    ({"filtro_gerencia": ["GER MALHA (SP)"]}, 36),  # só os CCs da GER MALHA
    ({"filtro_pep": ["MC/24004C-04-01-02"]}, 0),
    ({"filtro_classificacao": ["CAPEX"]}, 0),
])
def test_p3_evidencias_sap_respeita_gerencia_classificacao_pep(base, sessao, esperado):
    assert _json(_valores(base, "sap", sessao))["n"] == esperado


def test_p5_projecao_responde_a_gerencia(base):
    at = _valores(base, "projecao", {"filtro_gerencia": ["GER MALHA (SP)"]})
    orcado_anual = [m.value for m in at.metric if m.label == "Orçamento anual"]
    assert orcado_anual[2] == "R$ 2,4 MM"  # aba Manutenção (PM): 2 CCs x R$100 mil x 12


def test_p6_capex_sustaining_responde_a_gerencia(base):
    assert _json(_valores(base, "sustaining", {}))["orc"] == pytest.approx(1_200_000.0)
    v = _json(_valores(base, "sustaining", {"filtro_gerencia": ["GER MALHA (SP)"]}))
    assert v["orc"] == pytest.approx(600_000.0)  # só o PEP de SP


def test_p3_badge_separa_filtros_que_nao_se_aplicam(base):
    at = _valores(base, "badge_obras", {"filtro_gerencia": ["GER MALHA (SP)"]})
    html = " ".join(m.value for m in at.markdown)
    assert "Não se aplica nesta página" in html and "GER MALHA (SP)" in html
    assert "Filtros ativos" not in html


def test_p9_lista_de_gerencia_inclui_quem_so_tem_orcado(base):
    at = AppTest.from_function(_sidebar, args=(base, REPO), default_timeout=60)
    at.run()
    caixa = next(m for m in at.sidebar.multiselect if m.label == "Gerência")
    assert "GER. GERAL DE INFRAESTRUTURA (SP) - DIRETO GG" in caixa.options


# ===== B1 (docs/12, 2026-10-18): Contas, CC e Tendência sempre OPEX x OPEX;
# CAPEX Sustaining só como informação ("Realizado: —"), respeitando filtros
# e o RBAC do universo capex_sustaining.

def test_b1_capex_mais_opex_compara_so_opex(base):
    v = _json(_valores(base, "analise", {"filtro_classificacao": ["CAPEX", "OPEX"]}))
    assert v["orc"] == pytest.approx(7_200_000.0)
    assert v["real"] == pytest.approx(7_200_000.0)
    assert v["capex_fora"] == pytest.approx(1_200_000.0)

    assert _json(_valores(base, "analise", {"filtro_classificacao": ["OPEX"]}))["capex_fora"] == 0
    v = _json(_valores(base, "analise", {"filtro_gerencia": ["GER MALHA (SP)"]}))
    assert v["capex_fora"] == pytest.approx(600_000.0)  # só o PEP de SP


def test_b1_centro_custo_capex_mais_opex(base):
    v = _json(_valores(base, "cc", {"filtro_classificacao": ["CAPEX", "OPEX"]}))
    assert v["orc"] == pytest.approx(7_200_000.0)
    assert v["real"] == pytest.approx(7_200_000.0)


def test_b1_render_contas_capex_mostra_traco(base):
    from src.dashboard.nivel4_contas import TEXTO_REALIZADO_CAPEX_AUSENTE

    at = _valores(base, "render_n4", {"filtro_classificacao": ["CAPEX"]})
    infos = [i.value for i in at.info]
    assert any("Nenhum OPEX no recorte" in i for i in infos)
    aviso = [i for i in infos if TEXTO_REALIZADO_CAPEX_AUSENTE in i.replace("\\$", "$")]
    assert len(aviso) == 1
    assert "Realizado: —" in aviso[0] and "1,2 MM" in aviso[0]
    assert "R$ 0" not in aviso[0].replace("\\$", "$")


def test_b1_capex_fora_respeita_universo(base, monkeypatch):
    # Gerente com a GG inteira só em OPEX: o CAPEX Sustaining não pode vazar.
    monkeypatch.delenv("ORCAMENTO_SKIP_LOGIN", raising=False)
    v = _json(_valores(base, "analise", {
        "usuario": {"id": "u", "papel": "gerente", "nome_completo": "G"},
        "_escopos_acesso_cache": [{"universo": "opex_sustaining", "tipo": "gg", "valor": None}],
    }))
    assert v["capex_fora"] == 0
    assert v["orc"] == pytest.approx(7_200_000.0)


# ===== B4 (docs/12, 2026-10-18): mês da carga do Realizado fica "em
# andamento" — fora do Delta, mostrado à parte como Realizado parcial.

def _nota(at) -> str:
    return " ".join(c.value for c in at.caption).replace("\\$", "$")


def test_b4_carga_set_card(base_carga_set):
    at = _render(base_carga_set, {})
    card = _card(at)
    assert card["Orçamento (CAPEX+OPEX)"] == "R$ 10,8 MM"
    assert card["Orçado OPEX até Ago/2026"] == "R$ 6,4 MM"
    assert card["Real Contabilizado (OPEX)"] == "R$ 6,4 MM"  # Set (parcial) fora
    assert card["Aderência (OPEX x OPEX)"] == "100,0%"
    assert card["A realizar (Orçado OPEX após Ago/2026)"] == "R$ 3,2 MM"
    assert card["Set/2026 em andamento — Realizado parcial"] == "R$ 800 mil (Orçado R$ 800 mil, fora do Delta)"
    nota = _nota(at)
    assert "Realizado carregado em 15/09/2026" in nota and "fora do Delta" in nota
    assert "5º dia útil" in nota


def test_b4_carga_set_gerencia_desvios(base_carga_set):
    v = _json(_valores(base_carga_set, "desvios", {"filtro_gerencia": ["GER MALHA (SP)"]}))
    assert v["delta"] == pytest.approx(2_560_000.0 - 3_200_000.0)
    assert v["aderencia"] == pytest.approx(0.8)


def test_b4_carga_out_mes_sem_lancamento(base_carga_out):
    card = _card(_render(base_carga_out, {}))
    assert card["Orçado OPEX até Set/2026"] == "R$ 7,2 MM"
    assert card["Real Contabilizado (OPEX)"] == "R$ 7,2 MM"
    assert card["A realizar (Orçado OPEX após Set/2026)"] == "R$ 2,4 MM"
    # Carga no começo do mês: Realizado 0 x Orçado > 0 aparece (decisão do dono).
    assert card["Out/2026 em andamento — Realizado parcial"] == "R$ 0 (Orçado R$ 800 mil, fora do Delta)"


def test_b4_contas_herdam_corte(base_carga_set):
    v = _json(_valores(base_carga_set, "analise", {}))
    assert v["orc"] == pytest.approx(6_400_000.0)
    assert v["real"] == pytest.approx(6_400_000.0)


def test_b4_sem_meta_usa_regra_antiga(base):
    at = _render(base, {})
    assert "A realizar (Orçado OPEX após Set/2026)" in _card(at)
    assert "não registrada" in _nota(at)
    assert not any("em andamento" in k for k in _card(at))


def test_b4_realizado_futuro_gera_alerta(base_futuro):
    at = _render(base_futuro, {})
    card = _card(at)
    assert card["Real Contabilizado (OPEX)"] == "R$ 7,2 MM"  # Nov fora do Delta
    alertas = [w.value.replace("\\$", "$") for w in at.warning]
    assert any(
        "R$ 50 mil de Realizado com competência após Out/2026" in a and "verificar a base" in a
        for a in alertas
    ), alertas


# ===== N4 (2026-10-18): rótulo do card de Contas diz até quando vai o Orçado.

@pytest.mark.parametrize("fixture, rotulo", [("base", "Orçado até Set/2026"), ("base_carga_set", "Orçado até Ago/2026")])
def test_n4_rotulo_orcado_ate_corte(fixture, rotulo, request):
    at = _valores(request.getfixturevalue(fixture), "render_n4", {})
    assert rotulo in " ".join(m.value for m in at.markdown)
