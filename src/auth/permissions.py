"""Verificação de permissões (RBAC) — padrão de guards portado de
MRS Sentinel/Sentinel/auth/permissions.py, adaptado ao domínio do Orçamento.

Matriz de papéis (ver docs/03-processo-justificativas-causas.md, seção 3.1,
e docs/05-publicacao-online-e-seguranca.md):

    Ação                     | Admin | GG | Gerente          | Especialista/Analista
    Ver visão executiva      | sim   | sim| escopo (gerência) | escopo (gerência)
    Fazer upload             | sim   | não| não               | se permissao_upload
    Justificar Macro (Pacote)| sim   | não| não (só ciência)  | se permissao_justificativa_macro
    Justificar Micro (Conta) | sim   | não| não (só ciência)  | se permissao_justificativa_micro
    Exportar dado            | sim   | se permissao_exportacao (default true, todo papel)
    Gerir usuários           | sim   | não| não               | não

Como o painel inteiro já é escopado a uma única GG (GGG_0054, ver
config/settings.yaml), o recorte que importa no dia a dia é `gerencia_id`
(a Gerência dentro dessa GG — Malha SP/VP etc.), não `gg_id`.
"""
from __future__ import annotations

import streamlit as st

from src.auth.session import get_papel, get_usuario, is_logged_in


def is_admin() -> bool:
    return get_papel() == "admin"


def is_gg() -> bool:
    return get_papel() == "gg"


def is_gerente() -> bool:
    return get_papel() == "gerente"


def is_especialista_analista() -> bool:
    return get_papel() == "especialista_analista"


def can_ver_gerencia(gerencia_alvo: str | None) -> bool:
    """Admin e GG veem qualquer Gerência dentro do escopo da GG. Gerente e
    Especialista/Analista só veem a própria."""
    papel = get_papel()
    if papel in ("admin", "gg"):
        return True
    u = get_usuario()
    return bool(u) and u.get("gerencia_id") == gerencia_alvo


def can_fazer_upload() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_upload", False)


def can_exportar() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_exportacao", True)


def can_justificar_macro() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_justificativa_macro", False)


def can_justificar_micro() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_justificativa_micro", False)


def can_administrar_usuarios() -> bool:
    return is_admin()


# ---------------------------------------------------------------------------
# Guards de tela — usar st.stop() no topo de módulos/páginas protegidas.
# ---------------------------------------------------------------------------

def require_login() -> None:
    if not is_logged_in():
        st.error("🔒 Acesso restrito. Faça login para continuar.")
        st.stop()


def require_admin() -> None:
    require_login()
    if not is_admin():
        st.error("🚫 Esta área é restrita a administradores.")
        st.stop()


def require_upload() -> None:
    require_login()
    if not can_fazer_upload():
        st.error("🚫 Você não tem permissão para fazer upload de dados.")
        st.stop()


def require_justificativa_macro() -> None:
    require_login()
    if not can_justificar_macro():
        st.error("🚫 Você não tem permissão para justificar no nível Pacote.")
        st.stop()


def require_justificativa_micro() -> None:
    require_login()
    if not can_justificar_micro():
        st.error("🚫 Você não tem permissão para justificar no nível Conta/Centro de Custo.")
        st.stop()
