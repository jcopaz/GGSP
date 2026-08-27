"""Tela de login do Painel Orçamento GGSP.

Autenticação própria (bcrypt) contra app.usuario no Neon — sem depender de
provedor externo. Padrão de fluxo portado de
MRS Sentinel/Sentinel/auth/login.py (matrícula OU e-mail no mesmo campo,
mensagem de erro sempre genérica, sem revelar se a conta existe).
"""
from __future__ import annotations

import streamlit as st

from src.auth.queries import (
    atualizar_ultimo_login,
    buscar_usuario_por_identificador,
    inserir_log_acesso,
)
from src.auth.senha import verificar_senha
from src.auth.session import set_usuario
from src.branding import render_logo_video
from src.versao import APP_VERSION

_MSG_CREDENCIAIS_INVALIDAS = "Matrícula/e-mail ou senha incorretos."


def _autenticar(identificador: str, senha: str) -> tuple[bool, str]:
    if not identificador.strip() or not senha:
        return False, _MSG_CREDENCIAIS_INVALIDAS

    usuario = buscar_usuario_por_identificador(identificador)
    if not usuario or not usuario.get("ativo", False):
        # Mesma mensagem para "não existe" e "inativo" — não revela status da conta.
        return False, _MSG_CREDENCIAIS_INVALIDAS

    if not verificar_senha(senha, usuario["senha_hash"]):
        return False, _MSG_CREDENCIAIS_INVALIDAS

    set_usuario(usuario)

    # Auditoria: falha silenciosa, login não pode quebrar por causa disso.
    try:
        atualizar_ultimo_login(usuario["id"])
        inserir_log_acesso(usuario["id"], "login")
    except Exception:
        pass

    return True, ""


def render_login() -> None:
    render_logo_video(width=220)
    st.title("Fin360")
    st.caption("GER. GERAL DE INFRAESTRUTURA (SP) — acesso restrito")
    st.caption(f"v{APP_VERSION}")

    with st.form("form_login", clear_on_submit=False):
        identificador = st.text_input("Matrícula ou e-mail", placeholder="Ex: 123456 ou seu.nome@mrs.com.br")
        senha = st.text_input("Senha", type="password", placeholder="••••••••")
        entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            if not identificador.strip():
                st.error("Informe a matrícula ou o e-mail.")
            elif not senha:
                st.error("Informe a senha.")
            else:
                with st.spinner("Autenticando..."):
                    sucesso, msg_erro = _autenticar(identificador, senha)
                if sucesso:
                    st.rerun()
                else:
                    st.error(msg_erro)

    from src.auth.recuperar_senha import render_esqueci_senha
    render_esqueci_senha()
