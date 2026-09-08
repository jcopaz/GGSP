"""Etapa 5 da Visão Ideal (docs/07 §3.2) — página "Análise Financeira" de
Plano de Manutenção: `st.segmented_control` (Pacotes | Contas e Centros de
Custo | CAPEX Sustaining), cada painel um `@st.fragment`.

Atualizado 2026-09-08 pra reestruturação: "Pacotes" tem sub-abas por
família (PM/PD/PP via `render_visao_manutencao(familia=...)`), e "CAPEX
Sustaining" é só o lado CAPEX de `render_visao_classificacao`, fatiado por
Elemento PEP. O lado OPEX de `render_visao_classificacao` saiu do app —
não é mais exercitado aqui.

`AppTest` não navega bem entre páginas de `st.navigation` (ver
docs `feedback_orcamento_apptest_harness`), então os `render_*` que os
fragments chamam são exercitados direto, dentro de uma sessão.

Uso: python -m tests.etapa5_analise_financeira_check
"""
from __future__ import annotations

import os

from streamlit.testing.v1 import AppTest


def _script_paineis():
    """Roda os render_* que compõem os painéis da Análise Financeira, um
    após o outro, na mesma sessão: Pacotes PM/PD/PP + Contas + Centro de
    Custo + CAPEX Sustaining (por Elemento PEP)."""
    import streamlit as st
    import duckdb

    from src.dashboard.nivel4_contas import render_nivel4_contas
    from src.dashboard.nivel5_centro_custo import render_nivel5_centro_custo
    from src.dashboard.visao_classificacao import render_visao_classificacao
    from src.dashboard.visao_manutencao import render_visao_manutencao

    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    try:
        for fam in ("PM", "PD", "PP"):
            st.header(f"Pacotes — {fam}")
            render_visao_manutencao(con, ano_fiscal=2026, familia=fam)
        st.header("Contas")
        render_nivel4_contas(con, ano_fiscal=2026)
        st.header("Centro de Custo")
        render_nivel5_centro_custo(con, ano_fiscal=2026)
        st.header("CAPEX Sustaining (por Elemento PEP)")
        render_visao_classificacao(con, "CAPEX")
        st.write("RESULT ok")
    finally:
        con.close()


def _run(session: dict):
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_script_paineis, default_timeout=200)
    at.session_state["logged_in"] = True
    for k, v in session.items():
        at.session_state[k] = v
    at.run()
    return at


def main() -> None:
    # admin (escopo no-op) — todos os painéis renderizam sem exceção
    at = _run({"usuario": {"id": "a", "papel": "admin", "nome_completo": "A"}})
    if at.exception:
        raise SystemExit(f"admin: exceção num painel -> {list(at.exception)}")
    if not any(m.value == "RESULT ok" for m in at.markdown):
        raise SystemExit("admin: algum painel não chegou ao fim (sem 'RESULT ok').")
    print("admin: painéis renderizaram sem exceção -> OK")

    # analista escopado numa Gerência — mesmos painéis, recortados
    at2 = _run({
        "usuario": {"id": "u", "papel": "especialista_analista", "nome_completo": "X"},
        "_escopos_acesso_cache": [
            {"universo": "opex_sustaining", "tipo": "gerencia", "valor": "GGE_0025"},
            {"universo": "capex_sustaining", "tipo": "gerencia", "valor": "GGE_0025"},
        ],
    })
    if at2.exception:
        raise SystemExit(f"escopado: exceção num painel -> {list(at2.exception)}")
    if not any(m.value == "RESULT ok" for m in at2.markdown):
        raise SystemExit("escopado: algum painel não chegou ao fim.")
    tem_faixa = any("Recorte do seu acesso" in c.value for c in at2.caption)
    print(f"escopado GGE_0025: painéis sem exceção, faixa de recorte presente: {tem_faixa} -> OK")
    if not tem_faixa:
        raise SystemExit("escopado: nenhum painel mostrou a faixa 'Recorte do seu acesso'.")

    print("\nOK — os painéis da Análise Financeira renderizam de dentro dos fragments, com e sem recorte.")


if __name__ == "__main__":
    main()
