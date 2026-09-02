"""RBAC de escopo por universo (docs/08) — Fase RBAC-A.1.

Testa só a lógica pura de resolução (`_resolver_*`), sem Streamlit/Neon.
O enforcement nas telas é a Fase RBAC-A.2 e terá regressão numérica própria.

Uso: python -m pytest -q tests/test_rbac_escopo.py
"""
from __future__ import annotations

from src.auth.permissions import (
    UNIVERSOS,
    _resolver_escopo_universo,
    _resolver_universos_permitidos,
)


def _linha(universo, tipo, valor="x"):
    return {"universo": universo, "tipo": tipo, "valor": valor}


# --- universos_permitidos ---------------------------------------------------

def test_admin_ve_os_tres_universos():
    assert _resolver_universos_permitidos([], eh_admin=True, tem_usuario=True) == set(UNIVERSOS)


def test_sem_usuario_nao_ve_nada():
    assert _resolver_universos_permitidos([], eh_admin=False, tem_usuario=False) == set()


def test_sem_linha_nao_ve_nada_fail_closed():
    assert _resolver_universos_permitidos([], eh_admin=False, tem_usuario=True) == set()


def test_ve_so_os_universos_com_grant():
    linhas = [_linha("opex_sustaining", "gg"), _linha("capex_obras", "gerencia_obras", "Expansão")]
    assert _resolver_universos_permitidos(linhas, eh_admin=False, tem_usuario=True) == {
        "opex_sustaining", "capex_obras",
    }


# --- escopo_universo ------------------------------------------------------

def test_admin_tudo_em_qualquer_universo():
    assert _resolver_escopo_universo("capex_obras", [], eh_admin=True, tem_usuario=True) == (True, True, [])


def test_sem_grant_no_universo_nao_ve():
    linhas = [_linha("opex_sustaining", "gg")]
    assert _resolver_escopo_universo("capex_sustaining", linhas, eh_admin=False, tem_usuario=True) == (
        False, False, [],
    )


def test_grant_gg_ve_universo_inteiro():
    linhas = [_linha("opex_sustaining", "gg", "(todas)")]
    assert _resolver_escopo_universo("opex_sustaining", linhas, eh_admin=False, tem_usuario=True) == (
        True, True, [],
    )


def test_recorte_por_gerencia_uniao_das_linhas():
    linhas = [
        _linha("opex_sustaining", "gerencia", "GGE_0025"),
        _linha("opex_sustaining", "gerencia", "GGE_0197"),
        _linha("capex_sustaining", "gerencia", "GGE_0025"),  # outro universo, ignorado
    ]
    tem, tudo, alvos = _resolver_escopo_universo(
        "opex_sustaining", linhas, eh_admin=False, tem_usuario=True
    )
    assert (tem, tudo, alvos) == (True, False, ["GGE_0025", "GGE_0197"])


def test_gg_com_gerencia_junto_gg_manda():
    linhas = [
        _linha("capex_obras", "gg", "(todas)"),
        _linha("capex_obras", "gerencia_obras", "Expansão"),
    ]
    assert _resolver_escopo_universo("capex_obras", linhas, eh_admin=False, tem_usuario=True) == (
        True, True, [],
    )


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
