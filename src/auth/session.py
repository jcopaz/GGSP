"""Gerenciamento de estado de sessão do usuário logado.

Centraliza toda leitura/escrita do st.session_state relacionada ao usuário —
padrão portado de MRS Sentinel/Sentinel/auth/session.py (mesmo princípio,
campos adaptados ao domínio do Orçamento: papel/gg_id/gerencia_id/permissões
granulares em vez de perfil/gerencia único).
"""
from __future__ import annotations

import streamlit as st


def is_logged_in() -> bool:
    return bool(st.session_state.get("usuario"))


def get_usuario() -> dict | None:
    return st.session_state.get("usuario")


def get_papel() -> str | None:
    u = get_usuario()
    return u.get("papel") if u else None


def get_gg_id() -> str | None:
    u = get_usuario()
    return u.get("gg_id") if u else None


def get_gerencia_id() -> str | None:
    u = get_usuario()
    return u.get("gerencia_id") if u else None


def get_nome() -> str:
    u = get_usuario()
    return u.get("nome_completo", "Usuário") if u else "Usuário"


def get_id() -> str | None:
    u = get_usuario()
    return u.get("id") if u else None


def set_usuario(usuario_dict: dict) -> None:
    st.session_state["usuario"] = usuario_dict
    st.session_state["logged_in"] = True


def clear_session() -> None:
    """Limpa os dados de sessão do usuário (logout)."""
    for chave in ("usuario", "logged_in"):
        st.session_state.pop(chave, None)


def init_session() -> None:
    """Chamado no topo do app.py a cada rerun — usa setdefault, nunca
    sobrescreve uma sessão já existente."""
    st.session_state.setdefault("usuario", None)
    st.session_state.setdefault("logged_in", False)
