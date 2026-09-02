"""RBAC-A.2 — enforcement de escopo em Visão Manutenção + Nível 4/5
(universo opex_sustaining, docs/08).

Roda as funções de dado com um escopo de Gerência semeado na sessão (via
AppTest) e confere que os totais batem com a soma SQL direta por
`gerencia_id`, e que a página é barrada quando não há grant.

Precisa do warehouse real. Uso: python -m tests.rbac_sustaining_check
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest

_DB = "data/warehouse/painel.duckdb"
_ALVO = "GGE_0025"  # GER MALHA (SP)


def _script() -> None:
    # AppTest.from_function roda num namespace próprio — nada de global
    # deste módulo é visível aqui; constantes inline.
    import streamlit as st
    import duckdb

    from src.dashboard.filtros import clausula_escopo_centro_custo
    from src.dashboard.nivel4_contas import dados_conta, dados_familia
    from src.dashboard.visao_classificacao import resumo_classificacao
    from src.dashboard.visao_manutencao import resumo_manutencao

    _ALVO = "GGE_0025"
    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    try:
        r = resumo_manutencao(con)
        df_fam = dados_familia(con, "PM")
        df_cta = dados_conta(con, "PM")
        rc_opex = resumo_classificacao(con, "OPEX")
        rc_capex = resumo_classificacao(con, "CAPEX")

        (orc_d,) = con.execute(
            "select coalesce(sum(valor_orcado),0) from fact_orcamento "
            "where familia_pacote='PM' and gerencia_id in (?)", [_ALVO],
        ).fetchone()
        (real_d,) = con.execute(
            "select coalesce(sum(valor_realizado),0) from fact_realizado "
            "where familia_pacote='PM' and gerencia_id in (?)", [_ALVO],
        ).fetchone()
        (opex_d,) = con.execute(
            "select coalesce(sum(valor_orcado),0) from fact_orcamento "
            "where classificacao_contabil='OPEX' and gerencia_id in (?)", [_ALVO],
        ).fetchone()
        (capex_d,) = con.execute(
            "select coalesce(sum(valor_orcado),0) from fact_orcamento "
            "where classificacao_contabil='CAPEX' and gerencia_id in (?)", [_ALVO],
        ).fetchone()

        # Nível 6 — recorte via centro_custo_id (fact_realizado_documento
        # não tem gerencia_id).
        frag6, p6 = clausula_escopo_centro_custo(con, "opex_sustaining")
        (n6_scoped,) = con.execute(
            f"select count(*) from fact_realizado_documento where 1=1{frag6}", p6
        ).fetchone()
        (n6_direct,) = con.execute(
            "select count(*) from fact_realizado_documento where centro_custo_id in "
            "(select distinct centro_custo_id from fact_realizado where gerencia_id = ?)", [_ALVO],
        ).fetchone()

        checks = {
            "resumo_orcado": abs(r["orcado"] - orc_d) < 0.01,
            "resumo_realizado": abs(r["realizado"] - real_d) < 0.01,
            "n4_familia_orcado": abs(float(df_fam["orcado"].sum()) - orc_d) < 0.01,
            "n4_conta_orcado": abs(float(df_cta["orcado"].sum()) - orc_d) < 0.01,
            "classif_opex": abs(rc_opex["orcado"] - opex_d) < 0.01,
            "classif_capex": abs(rc_capex["orcado"] - capex_d) < 0.01,
            "n6_docs": n6_scoped == n6_direct and 0 < n6_scoped < con.execute(
                "select count(*) from fact_realizado_documento"
            ).fetchone()[0],
        }
        st.write("RESULT " + " ".join(f"{k}={v}" for k, v in checks.items()))
        st.write(f"VALORES orcado={r['orcado']:.2f} sql={orc_d:.2f}")
    finally:
        con.close()


def _run(escopos):
    at = AppTest.from_function(_script, default_timeout=90)
    at.session_state["usuario"] = {"id": "u1", "papel": "especialista_analista", "nome_completo": "X"}
    at.session_state["logged_in"] = True
    at.session_state["_escopos_acesso_cache"] = escopos
    at.run()
    return at


def main() -> None:
    at = _run([
        {"universo": "opex_sustaining", "tipo": "gerencia", "valor": _ALVO},
        {"universo": "capex_sustaining", "tipo": "gerencia", "valor": _ALVO},
    ])
    if at.exception:
        raise SystemExit(f"exceção no cenário recorte: {at.exception}")
    linha = next((m.value for m in at.markdown if m.value.startswith("RESULT")), "")
    vals = next((m.value for m in at.markdown if m.value.startswith("VALORES")), "")
    print(linha)
    print(vals)
    if "=False" in linha or not linha:
        raise SystemExit("FALHOU — algum total não bateu com a soma SQL direta.")

    # Sem grant: a página tem que barrar (require_universo -> st.stop()).
    def _script_render():
        import duckdb
        from src.dashboard.visao_manutencao import render_visao_manutencao
        con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
        render_visao_manutencao(con, 2026)
        con.close()

    at2 = AppTest.from_function(_script_render, default_timeout=90)
    at2.session_state["usuario"] = {"id": "u2", "papel": "especialista_analista", "nome_completo": "Y"}
    at2.session_state["logged_in"] = True
    at2.session_state["_escopos_acesso_cache"] = []
    at2.run()
    barrado = any("acesso a este universo" in (e.value or "") for e in at2.error)
    print(f"sem grant -> página barrada: {barrado}")
    if not barrado:
        raise SystemExit("FALHOU — página não barrou usuário sem grant.")

    print("\nOK — escopo bate com a soma SQL direta e a página barra quem não tem grant.")


if __name__ == "__main__":
    main()
