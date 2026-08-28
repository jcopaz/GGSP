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

import os

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


def can_acessar_pagina(pagina: str) -> bool:
    """Permissão por página (app.permissao_pagina) — adicionado em
    2026-08-28 (integração v3.4.0). Admin sempre acessa tudo. Usuário sem
    linha própria pra essa página é permitido por padrão (compatibilidade
    com quem já existia antes desta tabela).

    **Correção de segurança sobre o design original recebido**: se a
    consulta ao Postgres falhar (indisponibilidade, rede), o pacote de
    melhorias trazido pelo usuário devolvia `True` (fail **aberto** —
    todo mundo vê tudo se o banco cair). Isso contradiz o resto do
    projeto, que usa fail closed em ação crítica (ver `require_upload`
    etc. acima). Aqui devolve `False` na falha — nega por padrão, não
    libera. Registrado como decisão em
    docs/06-administracao-auditoria-e-projecao.md.

    `ORCAMENTO_SKIP_LOGIN=1` (bypass de login só local, ver app.py) libera
    tudo aqui também — sem essa saída, o próprio flag de teste local
    ficava inútil: sem usuário real de sessão, toda página seria negada
    (fail closed corretamente, mas contra o propósito do flag, que é
    "sem Neon, mas ainda dá pra olhar o painel"). Nunca fica ligado no
    deploy (mesmo aviso já existente no app.py)."""
    if os.environ.get("ORCAMENTO_SKIP_LOGIN") == "1":
        return True
    if is_admin():
        return True
    u = get_usuario()
    if not u:
        return False
    try:
        from src.auth.db import buscar_um

        linha = buscar_um(
            "select permitido from app.permissao_pagina where usuario_id = %s and pagina = %s",
            (u["id"], pagina),
        )
        return True if linha is None else bool(linha["permitido"])
    except Exception:
        return False


def require_acesso_pagina(pagina: str) -> None:
    require_login()
    if not can_acessar_pagina(pagina):
        st.error("🚫 Você não tem permissão para acessar esta página.")
        st.stop()
