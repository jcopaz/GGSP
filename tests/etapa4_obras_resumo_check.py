"""Etapa 4 da Visão Ideal (docs/07) — página "Resumo" de CAPEX Plano de
Obras com `st.segmented_control` (Visão Executiva | Desvios e Evolução),
cada painel um `@st.fragment`.

Confere que um usuário de CAPEX Obras cai em "Resumo", que o seletor tem
os 2 painéis e que trocar de painel renderiza sem exceção (inclui o
`render_painel_executivo_capex`, que estourava com KeyError
'projecao_ritmo_acumulada' antes da guarda em `tendencia.figura_tendencia`).

Uso: python -m tests.etapa4_obras_resumo_check
"""
from __future__ import annotations

import os
import re

from streamlit.testing.v1 import AppTest

_ABAS = ["Visão Executiva", "Desvios e Evolução"]


def _banner(at) -> str | None:
    for m in at.markdown:
        x = re.search(r"font-weight:600;[^>]*>([^<]+)</span>", m.value or "")
        if x:
            return x.group(1).strip()
    return None


def main() -> None:
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_file("app.py", default_timeout=180)
    at.session_state["usuario"] = {"id": "u1", "papel": "especialista_analista", "nome_completo": "X"}
    at.session_state["logged_in"] = True
    at.session_state["_permissoes_pagina_cache"] = {}
    at.session_state["_escopos_acesso_cache"] = [
        {"universo": "capex_obras", "tipo": "gg", "valor": "(todas)"}
    ]
    at.run()
    if at.exception:
        raise SystemExit(f"exceção no load: {list(at.exception)}")
    if _banner(at) != "Resumo Executivo":
        raise SystemExit(f"default não é o painel 'Visão Executiva' (banner {_banner(at)!r})")

    sc = [s for s in at.segmented_control if list(s.options) == _ABAS]
    if not sc:
        raise SystemExit(f"segmented_control da Etapa 4 não encontrado ({[list(s.options) for s in at.segmented_control]})")

    sc[0].set_value("Desvios e Evolução").run()
    if at.exception:
        raise SystemExit(f"exceção em 'Desvios e Evolução': {list(at.exception)}")
    if _banner(at) != "Painel Executivo":
        raise SystemExit(f"'Desvios e Evolução' não renderizou o Painel Executivo (banner {_banner(at)!r})")

    print("OK — 'Resumo' de Obras consolida os 2 painéis; troca sem exceção.")


if __name__ == "__main__":
    main()
