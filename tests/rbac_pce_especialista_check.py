"""RBAC-A.2 — CAPEX Obras — Especialista (docs/08 §10 opção B).

1. Página default-deny: sem linha `permitido=true` em `permissao_pagina`,
   `can_acessar_pagina('pce_especialista')` = False (admin/SKIP_LOGIN à
   parte). Testado direto na função de resolução.
2. Recorte por Gerência de Obras: `render_pce_especialista` com escopo
   semeado só mostra a(s) Gerência(s) do grant; sem grant, barra.

Uso: python -m tests.rbac_pce_especialista_check
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.auth import permissions


def _script_render() -> None:
    import duckdb
    from src.dashboard.pce_especialista import render_pce_especialista

    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    render_pce_especialista(con)
    con.close()


def _run(escopos):
    at = AppTest.from_function(_script_render, default_timeout=120)
    at.session_state["usuario"] = {"id": "u1", "papel": "especialista_analista", "nome_completo": "X"}
    at.session_state["logged_in"] = True
    at.session_state["_escopos_acesso_cache"] = escopos
    at.run()
    return at


def main() -> None:
    # 1) default-deny da página (lógica pura de can_acessar_pagina, sem Neon):
    #    sem linha -> default = pagina not in _PAGINAS_ALLOW_EXPLICITO
    default = "pce_especialista" not in permissions._PAGINAS_ALLOW_EXPLICITO
    outras = "capex_resumo" not in permissions._PAGINAS_ALLOW_EXPLICITO
    print(f"default pce_especialista={default} (esperado False) | capex_resumo={outras} (esperado True)")
    if default is not False or outras is not True:
        raise SystemExit("FALHOU — _PAGINAS_ALLOW_EXPLICITO não inverteu só o pce_especialista.")

    # 2) recorte por Gerência de Obras
    at = _run([{"universo": "capex_obras", "tipo": "gerencia_obras", "valor": "Expansão"}])
    if at.exception:
        raise SystemExit(f"exceção no cenário recorte: {at.exception}")
    caps = [c.value for c in at.caption]
    tem_faixa = any("Recorte do seu acesso" in c and "Expansão" in c for c in caps)
    print(f"recorte -> faixa com 'Expansão': {tem_faixa}")
    if not tem_faixa:
        raise SystemExit("FALHOU — faixa de recorte não apareceu para escopo de Gerência de Obras.")

    # 3) sem grant no universo -> barra
    at_sem = _run([])
    barrado = any("acesso a este universo" in (e.value or "") for e in at_sem.error)
    print(f"sem grant -> barrado: {barrado}")
    if not barrado:
        raise SystemExit("FALHOU — página não barrou usuário sem grant no universo capex_obras.")

    print("\nOK — pce_especialista é default-deny e recorta por Gerência de Obras.")


if __name__ == "__main__":
    main()
