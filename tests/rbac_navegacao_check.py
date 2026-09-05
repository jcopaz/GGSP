"""RBAC-B — navegação escondida por universo (docs/08).

Um usuário só de CAPEX Obras não vê o grupo "Plano de Manutenção"; só de
Sustaining não vê "Plano de Obras"; um capex_sustaining-only só vê a
página OPEX/CAPEX Manutenção (as OPEX-only somem). Sem NENHUM universo
nem upload -> página única "Sem acesso" (não `st.navigation({})`, que
quebraria).

Uso: python -m tests.rbac_navegacao_check
"""
from __future__ import annotations

import os
import re

from streamlit.testing.v1 import AppTest


def _pagina_ativa(escopos, perms=None):
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_file("app.py", default_timeout=150)
    at.session_state["usuario"] = {"id": "u1", "papel": "especialista_analista", "nome_completo": "X"}
    at.session_state["logged_in"] = True
    at.session_state["_escopos_acesso_cache"] = escopos
    at.session_state["_permissoes_pagina_cache"] = {} if perms is None else perms
    at.run()
    titulo = None
    for m in at.markdown:
        mt = re.search(r"font-weight:600;[^>]*>([^<]+)</span>", m.value or "")
        if mt:
            titulo = mt.group(1).strip()
            break
    return at, titulo


_GG = lambda u: [{"universo": u, "tipo": "gg", "valor": "(todas)"}]

_CASOS = [
    ("opex_sustaining", _GG("opex_sustaining"), "Resumo Executivo"),
    ("capex_obras", _GG("capex_obras"), "Resumo Executivo"),  # cai no Resumo de Obras
    ("capex_sustaining", _GG("capex_sustaining"), "CAPEX Manutenção — Malha"),
    ("sem universo, com upload", [], "Dados e Qualidade"),
]


def main() -> None:
    falhas = 0
    for nome, esc, esperado in _CASOS:
        at, titulo = _pagina_ativa(esc)
        ok = (not at.exception) and titulo == esperado
        print(f"{nome:28} -> {titulo!r} (esperado {esperado!r}) {'OK' if ok else 'FALHOU'}")
        falhas += 0 if ok else 1

    # sem universo E sem upload -> pagina "Sem acesso" (nao quebra)
    at, titulo = _pagina_ativa([], perms={"upload": False})
    ok = (not at.exception) and titulo == "Sem acesso"
    print(f"{'sem nada':28} -> {titulo!r} (esperado 'Sem acesso') {'OK' if ok else 'FALHOU'}")
    falhas += 0 if ok else 1

    if falhas:
        raise SystemExit(f"{falhas} caso(s) falharam.")
    print("\nOK — navegação some conforme o universo do usuário; fail-safe cobre o caso vazio.")


if __name__ == "__main__":
    main()
