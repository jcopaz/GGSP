"""Critério de pronto da Fase 7a.2 — motor da Fila de Pendências
(`src/engine/fila_pendencias.py`, ver `docs/09` §4).

Confere o que o motor devolve contra SQL direto no warehouse (mesma lógica,
caminho independente) + testa cobertura por justificativa, recorte de escopo,
corte "só mês fechado" e os universos sem dado.

Uso: python -m tests.fase7a_fila_pendencias_check
"""
from __future__ import annotations

import duckdb
import pandas as pd

from src.config import carregar_config
from src.engine.fila_pendencias import (
    COLUNAS_JUSTIFICATIVA,
    calcular_fila_pendencias,
)

_EPS = 0.01
_ANO = 2026
_ATE_MES = 7  # último mês com Realizado "cheio" hoje (ago em diante é ~0).


def _falhou(msg: str) -> None:
    raise SystemExit(f"FALHOU — {msg}")


def _ok(msg: str) -> None:
    print(f"  OK — {msg}")


def _delta_sql_sustaining(con: duckdb.DuckDBPyConnection, dims: list[str], ate_mes: int) -> pd.DataFrame:
    """Orçado×Realizado OPEX por `dims` sobre meses 1..ate_mes — espelho
    independente de `_delta_sustaining_mensal` agregado."""
    d = ", ".join(dims)
    orc = con.execute(
        f"SELECT {d}, SUM(valor_orcado) orc FROM fact_orcamento "
        f"WHERE ano = ? AND classificacao_contabil = 'OPEX' AND mes <= ? GROUP BY {d}",
        [_ANO, ate_mes],
    ).df()
    rea = con.execute(
        f"SELECT {d}, SUM(valor_realizado) rea FROM fact_realizado "
        f"WHERE ano = ? AND classificacao_contabil = 'OPEX' AND mes <= ? GROUP BY {d}",
        [_ANO, ate_mes],
    ).df()
    m = orc.merge(rea, on=dims, how="outer")
    m["orc"] = m["orc"].fillna(0.0)
    m["rea"] = m["rea"].fillna(0.0)
    for c in dims:
        m[c] = m[c].fillna("")
    m["delta"] = m["rea"] - m["orc"]
    return m


def main() -> None:
    cfg = carregar_config()
    con = duckdb.connect(cfg["caminhos"]["warehouse_db"], read_only=True)
    thr = cfg["threshold_justificativa"]
    thr_macro = float(thr["macro_pacote"])
    thr_obras = float(thr["obras_projeto"])

    try:
        print("=== A. OPEX Sustaining — mensal casa com SQL direto (mês a mês) ===")
        fila = calcular_fila_pendencias(
            con, "opex_sustaining", None, ano_fiscal=_ANO,
            threshold_macro=thr_macro, threshold_obras=thr_obras, ate_mes=_ATE_MES,
        )
        mensal = fila[fila["escopo_temporal"] == "mensal"]
        for mes in range(1, _ATE_MES + 1):
            base = _delta_sql_sustaining_mes(con, mes)
            esperado = set(
                tuple(x) for x in base.loc[base["delta"] > _EPS, ["gerencia_id", "conta_interna_id"]].itertuples(index=False, name=None)
            )
            obtido = set(
                tuple(x) for x in mensal.loc[mensal["mes_competencia"] == mes, ["gerencia_id", "conta_interna_id"]].itertuples(index=False, name=None)
            )
            if esperado != obtido:
                _falhou(
                    f"mês {mes}: chaves de pendência mensal divergem "
                    f"(só no SQL: {sorted(esperado - obtido)[:3]}; só no motor: {sorted(obtido - esperado)[:3]})"
                )
            soma_motor = mensal.loc[mensal["mes_competencia"] == mes, "delta"].sum()
            soma_sql = base.loc[base["delta"] > _EPS, "delta"].sum()
            if abs(soma_motor - soma_sql) > _EPS:
                _falhou(f"mês {mes}: soma do Delta mensal {soma_motor:.2f} != SQL {soma_sql:.2f}")
        _ok(f"{len(mensal)} pendências mensais (meses 1..{_ATE_MES}) batem chave a chave e na soma")

        print("=== B. OPEX Sustaining — acumulada (micro) casa com SQL direto ===")
        acum_motor = fila[(fila["escopo_temporal"] == "acumulado") & (fila["nivel"] == "micro")]
        base_acum = _delta_sql_sustaining(con, ["gerencia_id", "conta_interna_id"], ate_mes=_ATE_MES)
        esp = set(
            tuple(x) for x in base_acum.loc[base_acum["delta"] > _EPS, ["gerencia_id", "conta_interna_id"]].itertuples(index=False, name=None)
        )
        obt = set(
            tuple(x) for x in acum_motor[["gerencia_id", "conta_interna_id"]].itertuples(index=False, name=None)
        )
        if esp != obt:
            _falhou(f"acumulada micro: chaves divergem (só SQL {len(esp - obt)}, só motor {len(obt - esp)})")
        if abs(acum_motor["delta"].sum() - base_acum.loc[base_acum["delta"] > _EPS, "delta"].sum()) > _EPS:
            _falhou("acumulada micro: soma do Delta != SQL")
        _ok(f"{len(acum_motor)} pendências acumuladas (micro) batem com o SQL")

        print("=== C. OPEX Sustaining — Macro (Pacote) respeita threshold ===")
        macro_motor = fila[fila["nivel"] == "macro"]
        base_pac = _delta_sql_sustaining(con, ["pacote_id"], ate_mes=_ATE_MES)
        esp_pac = set(base_pac.loc[(base_pac["delta"] > _EPS) & (base_pac["delta"] >= thr_macro), "pacote_id"])
        obt_pac = set(macro_motor["pacote_id"])
        if esp_pac != obt_pac:
            _falhou(f"macro: pacotes divergem — SQL {sorted(esp_pac)}, motor {sorted(obt_pac)}")
        if not (macro_motor["delta"] >= thr_macro).all():
            _falhou("macro: alguma pendência abaixo do threshold vazou")
        _ok(f"{len(macro_motor)} pendências Macro, todas >= R$ {thr_macro:,.0f}, casam com o SQL")

        print("=== D. Cobertura por justificativa vigente (some / encolhe) ===")
        alvo = mensal.sort_values("delta", ascending=False).iloc[0]
        just_total = pd.DataFrame([{
            "universo": "opex_sustaining", "nivel": "micro", "escopo_temporal": "mensal",
            "gerencia_id": alvo["gerencia_id"], "conta_interna_id": alvo["conta_interna_id"],
            "pacote_id": alvo["pacote_id"], "e_pep_projeto": "",
            "ano": _ANO, "mes": int(alvo["mes_competencia"]),
            "valor_explicado": float(alvo["delta"]),
        }], columns=COLUNAS_JUSTIFICATIVA)
        fila2 = calcular_fila_pendencias(
            con, "opex_sustaining", just_total, ano_fiscal=_ANO,
            threshold_macro=thr_macro, threshold_obras=thr_obras, ate_mes=_ATE_MES,
        )
        ainda = fila2[
            (fila2["escopo_temporal"] == "mensal")
            & (fila2["gerencia_id"] == alvo["gerencia_id"])
            & (fila2["conta_interna_id"] == alvo["conta_interna_id"])
            & (fila2["mes_competencia"] == alvo["mes_competencia"])
        ]
        if not ainda.empty:
            _falhou("cobertura total: a pendência não sumiu")
        just_metade = just_total.copy()
        just_metade["valor_explicado"] = float(alvo["delta"]) / 2.0
        fila3 = calcular_fila_pendencias(
            con, "opex_sustaining", just_metade, ano_fiscal=_ANO,
            threshold_macro=thr_macro, threshold_obras=thr_obras, ate_mes=_ATE_MES,
        )
        parcial = fila3[
            (fila3["escopo_temporal"] == "mensal")
            & (fila3["gerencia_id"] == alvo["gerencia_id"])
            & (fila3["conta_interna_id"] == alvo["conta_interna_id"])
            & (fila3["mes_competencia"] == alvo["mes_competencia"])
        ]
        if parcial.empty or abs(parcial.iloc[0]["delta_pendente"] - float(alvo["delta"]) / 2.0) > _EPS:
            _falhou("cobertura parcial: delta_pendente deveria ser ~metade")
        _ok("cobertura total remove a pendência; cobertura parcial reduz delta_pendente pela metade")

        print("=== E. Recorte de escopo por Gerência ===")
        alvo_ger = mensal["gerencia_id"].value_counts().index[0]
        filaE = calcular_fila_pendencias(
            con, "opex_sustaining", None, ano_fiscal=_ANO,
            threshold_macro=thr_macro, threshold_obras=thr_obras, ate_mes=_ATE_MES,
            escopo_sustaining=(" AND gerencia_id IN (?)", [alvo_ger]),
        )
        micro_e = filaE[filaE["nivel"] == "micro"]
        if micro_e.empty or not (micro_e["gerencia_id"] == alvo_ger).all():
            _falhou(f"escopo: vazaram Gerências fora de {alvo_ger}")
        if len(micro_e) >= len(fila[fila["nivel"] == "micro"]):
            _falhou("escopo: recorte não reduziu a Fila")
        _ok(f"recorte em {alvo_ger}: {len(micro_e)} de {len(fila[fila['nivel']=='micro'])} pendências micro, todas da Gerência")

        print("=== F. CAPEX Sustaining — sem Realizado, Fila vazia ===")
        filaF = calcular_fila_pendencias(
            con, "capex_sustaining", None, ano_fiscal=_ANO,
            threshold_macro=thr_macro, threshold_obras=thr_obras, ate_mes=_ATE_MES,
        )
        if not filaF.empty:
            _falhou(f"capex_sustaining deveria vir vazio (sem Realizado), veio com {len(filaF)}")
        _ok("capex_sustaining: 0 pendências (dado ausente, docs/09 §4.3-bis)")

        print("=== G. Obras — threshold sobre |Delta| casa com SQL ===")
        filaG = calcular_fila_pendencias(
            con, "capex_obras", None, ano_fiscal=_ANO,
            threshold_macro=thr_macro, threshold_obras=thr_obras, ate_mes=_ATE_MES,
        )
        orc_o = con.execute(
            "SELECT e_pep_projeto, SUM(valor_orcado) orc FROM fact_cji4_capex_obras "
            "WHERE ano=? AND mes<=? GROUP BY 1", [_ANO, _ATE_MES],
        ).df()
        rea_o = con.execute(
            "SELECT e_pep_projeto, SUM(valor_realizado) rea FROM fact_cji3_capex_obras "
            "WHERE ano=? AND mes<=? GROUP BY 1", [_ANO, _ATE_MES],
        ).df()
        mo = orc_o.merge(rea_o, on="e_pep_projeto", how="outer")
        mo["orc"] = mo["orc"].fillna(0.0)
        mo["rea"] = mo["rea"].fillna(0.0)
        mo["delta"] = mo["rea"] - mo["orc"]
        esp_o = set(mo.loc[mo["delta"].abs() >= thr_obras, "e_pep_projeto"])
        obt_o = set(filaG["e_pep_projeto"])
        if esp_o != obt_o:
            _falhou(f"obras: projetos divergem — só SQL {sorted(esp_o - obt_o)}, só motor {sorted(obt_o - esp_o)}")
        _ok(f"{len(filaG)} pendências de Obras, |Delta| >= R$ {thr_obras:,.0f}, casam com o SQL")

        print("=== H. Só mês fechado (ate_mes corta a competência) ===")
        filaH = calcular_fila_pendencias(
            con, "opex_sustaining", None, ano_fiscal=_ANO,
            threshold_macro=thr_macro, threshold_obras=thr_obras, ate_mes=6,
        )
        mensalH = filaH[filaH["escopo_temporal"] == "mensal"]
        if mensalH["mes_competencia"].max() != 6:
            _falhou(f"ate_mes=6 mas apareceu competência {mensalH['mes_competencia'].max()}")
        if (filaH[filaH["escopo_temporal"] == "acumulado"]["mes_competencia"] != 6).any():
            _falhou("ate_mes=6 mas acumulada não foi avaliada em 6")
        _ok("ate_mes=6: nenhuma competência > 6; acumulada avaliada em 6")

        print()
        print("OK — motor da Fila de Pendências (Fase 7a.2) fecha com o SQL direto em todos os universos com dado.")
    finally:
        con.close()


def _delta_sql_sustaining_mes(con: duckdb.DuckDBPyConnection, mes: int) -> pd.DataFrame:
    """Delta SÓ do mês `mes` (não acumulado) por (gerencia_id, conta_interna_id),
    incluindo linhas que só têm orçado (sem realizado no mês) e vice-versa."""
    orc = con.execute(
        "SELECT gerencia_id, conta_interna_id, SUM(valor_orcado) orc FROM fact_orcamento "
        "WHERE ano=? AND mes=? AND classificacao_contabil='OPEX' GROUP BY 1,2",
        [_ANO, mes],
    ).df()
    rea = con.execute(
        "SELECT gerencia_id, conta_interna_id, SUM(valor_realizado) rea FROM fact_realizado "
        "WHERE ano=? AND mes=? AND classificacao_contabil='OPEX' GROUP BY 1,2",
        [_ANO, mes],
    ).df()
    m = orc.merge(rea, on=["gerencia_id", "conta_interna_id"], how="outer")
    m["orc"] = m["orc"].fillna(0.0)
    m["rea"] = m["rea"].fillna(0.0)
    for c in ["gerencia_id", "conta_interna_id"]:
        m[c] = m[c].fillna("")
    m["delta"] = m["rea"] - m["orc"]
    return m


if __name__ == "__main__":
    main()
