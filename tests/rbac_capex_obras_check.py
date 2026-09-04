"""RBAC-A.2 — enforcement de escopo no universo capex_obras (docs/08).

Semeia um escopo (Gerência de Obras e/ou Projeto) na sessão via AppTest e
confere que `resumo_geral_capex` / `dados_gerencia_obras` batem com a soma
SQL direta de `fact_cji4_capex_obras`, e que a página barra sem grant.

Precisa do warehouse real. Uso: python -m tests.rbac_capex_obras_check
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest

_GER = "Expansão"


def _script_dados() -> None:
    import streamlit as st
    import duckdb

    from src.dashboard.capex_dados import dados_gerencia_obras, resumo_geral_capex

    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    try:
        ger = "Expansão"
        rg = resumo_geral_capex(con)
        dfg = dados_gerencia_obras(con)

        (orc_d,) = con.execute(
            "select coalesce(sum(valor_orcado),0) from fact_cji4_capex_obras "
            "where gerencia_obras = ?", [ger],
        ).fetchone()
        (real_d,) = con.execute(
            "select coalesce(sum(valor_realizado),0) from fact_cji3_capex_obras "
            "where gerencia_obras = ?", [ger],
        ).fetchone()

        checks = {
            "resumo_orcado": abs(rg["orcado"] - orc_d) < 0.01,
            "resumo_realizado": abs(rg["realizado"] - real_d) < 0.01,
            "gerencia_obras_1linha": len(dfg) <= 1,  # só a Gerência do escopo
            "gerencia_obras_orcado": dfg.empty or abs(float(dfg["orcado"].sum()) - orc_d) < 0.01,
        }
        st.write("RESULT " + " ".join(f"{k}={v}" for k, v in checks.items()))
        st.write(f"VALORES orcado={rg['orcado']:.2f} sql={orc_d:.2f} linhas_gerencia={len(dfg)}")
    finally:
        con.close()


def _script_or() -> None:
    """Escopo com Gerência de Obras + Projeto ao mesmo tempo -> WHERE com
    OR entre `gerencia_obras IN (...)` e `e_pep_projeto IN (...)`. O projeto
    escolhido é passado em `st.session_state['_proj_or']` pelo main."""
    import streamlit as st
    import duckdb

    from src.dashboard.filtros import clausula_escopo_obras

    proj = st.session_state["_proj_or"]
    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    try:
        frag, params = clausula_escopo_obras()
        (v,) = con.execute(
            "select coalesce(sum(valor_orcado),0) from fact_cji4_capex_obras where 1=1" + frag,
            params,
        ).fetchone()
        (d,) = con.execute(
            "select coalesce(sum(valor_orcado),0) from fact_cji4_capex_obras "
            "where gerencia_obras=? or e_pep_projeto=?", ["Expansão", proj],
        ).fetchone()
        st.write(f"OR frag={frag!r}")
        st.write(f"OR scoped={v:.2f} direct={d:.2f} match={abs(v - d) < 0.01}")
    finally:
        con.close()


def _script_render_sem_grant() -> None:
    import duckdb
    from src.dashboard.capex_resumo import render_resumo_executivo_capex

    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    render_resumo_executivo_capex(con)
    con.close()


def _run(fn, escopos, extra_session=None):
    at = AppTest.from_function(fn, default_timeout=90)
    at.session_state["usuario"] = {"id": "u1", "papel": "especialista_analista", "nome_completo": "X"}
    at.session_state["logged_in"] = True
    at.session_state["_escopos_acesso_cache"] = escopos
    for k, v in (extra_session or {}).items():
        at.session_state[k] = v
    at.run()
    return at


def main() -> None:
    import duckdb

    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    proj_bs = con.execute(
        "select e_pep_projeto from fact_cji4_capex_obras "
        "where gerencia_obras='Baixada Santista' order by valor_orcado desc limit 1"
    ).fetchone()[0]
    con.close()

    at = _run(_script_dados, [{"universo": "capex_obras", "tipo": "gerencia_obras", "valor": _GER}])
    if at.exception:
        raise SystemExit(f"exceção no cenário recorte: {at.exception}")
    linha = next((m.value for m in at.markdown if m.value.startswith("RESULT")), "")
    vals = next((m.value for m in at.markdown if m.value.startswith("VALORES")), "")
    print(linha)
    print(vals)
    if "=False" in linha or not linha:
        raise SystemExit("FALHOU — algum total não bateu com a soma SQL direta.")

    at_or = _run(
        _script_or,
        [
            {"universo": "capex_obras", "tipo": "gerencia_obras", "valor": _GER},
            {"universo": "capex_obras", "tipo": "elemento_pep", "valor": proj_bs},
        ],
        extra_session={"_proj_or": proj_bs},
    )
    if at_or.exception:
        raise SystemExit(f"exceção no cenário OR: {at_or.exception}")
    linha_or = next((m.value for m in at_or.markdown if m.value.startswith("OR scoped")), "")
    frag_or = next((m.value for m in at_or.markdown if m.value.startswith("OR frag")), "")
    print(frag_or)
    print(linha_or)
    if "match=True" not in linha_or:
        raise SystemExit("FALHOU — combinação OR (Gerência + Projeto) não bateu.")

    at_sem = _run(_script_render_sem_grant, [])
    barrado = any("acesso a este universo" in (e.value or "") for e in at_sem.error)
    print(f"sem grant -> página barrada: {barrado}")
    if not barrado:
        raise SystemExit("FALHOU — página não barrou usuário sem grant.")

    print("\nOK — escopo capex_obras bate com a soma SQL direta e barra quem não tem grant.")


if __name__ == "__main__":
    main()
