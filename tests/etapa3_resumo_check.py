"""Etapa 3 da Visão Ideal (docs/07) — página "Resumo" de Plano de
Manutenção com `st.segmented_control` (Visão Executiva | Desvios e Causas |
Projeção), cada painel um `@st.fragment`.

Confere que o item de menu "Resumo" é o default, que o seletor tem os 3
painéis, e que trocar de painel renderiza o conteúdo certo sem exceção —
tanto pra admin (waterfall completo) quanto pra analista escopado numa
Gerência (waterfall vira aviso).

Uso: python -m tests.etapa3_resumo_check
"""
from __future__ import annotations

import os
import re

from streamlit.testing.v1 import AppTest

_ABAS = ["Visão Executiva", "Desvios e Causas", "Projeção"]


def _banner(at) -> str | None:
    for m in at.markdown:
        x = re.search(r"font-weight:600;[^>]*>([^<]+)</span>", m.value or "")
        if x:
            return x.group(1).strip()
    return None


def _run(session: dict):
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_file("app.py", default_timeout=180)
    at.session_state["logged_in"] = True
    at.session_state["_permissoes_pagina_cache"] = {}
    for k, v in session.items():
        at.session_state[k] = v
    at.run()
    return at


def _checar(nome: str, session: dict, aviso_recorte_esperado: bool) -> int:
    at = _run(session)
    if at.exception:
        print(f"{nome}: FALHOU (exceção no load: {list(at.exception)})")
        return 1
    if _banner(at) != "Resumo Executivo":
        print(f"{nome}: FALHOU — default não é o painel 'Visão Executiva' (banner {_banner(at)!r})")
        return 1
    sc = at.segmented_control
    if not sc or list(sc[0].options) != _ABAS:
        print(f"{nome}: FALHOU — segmented_control ausente ou opções erradas ({sc[0].options if sc else None})")
        return 1

    sc[0].set_value("Desvios e Causas").run()
    if at.exception:
        print(f"{nome}: FALHOU — exceção em 'Desvios e Causas' ({list(at.exception)})")
        return 1
    tem_aviso = any(("GG inteira" in i.value or "Macro" in i.value) for i in at.info)
    if tem_aviso != aviso_recorte_esperado:
        print(f"{nome}: FALHOU — aviso de recorte no waterfall = {tem_aviso}, esperado {aviso_recorte_esperado}")
        return 1

    sc[0].set_value("Projeção").run()
    if at.exception or _banner(at) != "Projeção OPEX":
        print(f"{nome}: FALHOU — 'Projeção' não renderizou (banner {_banner(at)!r}, exc {bool(at.exception)})")
        return 1

    print(f"{nome}: OK")
    return 0


def main() -> None:
    falhas = 0
    falhas += _checar(
        "admin (waterfall completo)",
        {"usuario": {"id": "a1", "papel": "admin", "nome_completo": "A"}},
        aviso_recorte_esperado=False,
    )
    falhas += _checar(
        "analista escopado GGE_0025",
        {
            "usuario": {"id": "u1", "papel": "especialista_analista", "nome_completo": "X"},
            "_escopos_acesso_cache": [{"universo": "opex_sustaining", "tipo": "gerencia", "valor": "GGE_0025"}],
        },
        aviso_recorte_esperado=True,
    )
    if falhas:
        raise SystemExit(f"{falhas} caso(s) falharam.")
    print("\nOK — 'Resumo' consolida os 3 painéis; seletor troca sem exceção; recorte respeitado.")


if __name__ == "__main__":
    main()
