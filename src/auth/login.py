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
    trocar_senha_primeiro_login,
)
from src.auth.senha import SENHA_PADRAO, gerar_hash, verificar_senha
from src.auth.session import get_usuario, set_usuario
from src.branding import render_logo_video
from src.versao import APP_VERSION

_MSG_CREDENCIAIS_INVALIDAS = "Matrícula/e-mail ou senha incorretos."


def _inject_login_css() -> None:
    """Card de login centralizado sobre fundo neutro, com identidade visual
    Fin360 (azul-marinho + dourado). Sidebar escondida (vazia nessa tela —
    todo conteúdo de sidebar só é montado depois do gate de sessão)."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stAppViewContainer"],
        .stApp {
            background: #eef1f6 !important;
        }
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 420px !important;
            margin: 6vh auto !important;
            background: #ffffff;
            border-radius: 20px;
            padding: 2.75rem 2.5rem 2rem !important;
            box-shadow: 0 12px 34px rgba(15, 23, 42, 0.10);
            text-align: center;
        }
        div[data-testid="stForm"] {
            text-align: left;
            margin-top: 1.4rem;
            border: none !important;
            padding: 0 !important;
        }
        div[data-testid="stForm"] .stTextInput input {
            border-radius: 10px !important;
        }
        div[data-testid="stForm"] .stFormSubmitButton button,
        div[data-testid="stForm"] .stButton button {
            width: 100%;
            background: linear-gradient(135deg, #0f2f52 0%, #1d5488 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.7rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em;
            margin-top: 0.4rem;
        }
        div[data-testid="stExpander"] {
            text-align: left;
            margin-top: 0.75rem;
            border-radius: 10px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    _inject_login_css()
    render_logo_video(size=112)
    st.markdown(
        f"""
        <div style="text-align:center;">
            <h1 style="font-size:1.85rem;font-weight:800;color:#0f2f52;
                margin:0.9rem 0 0.15rem;letter-spacing:0.02em;">Fin360</h1>
            <div style="color:#64748b;font-size:0.85rem;">Acesso Restrito</div>
            <div style="color:#94a3b8;font-size:0.75rem;margin-top:0.15rem;">v{APP_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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

    st.markdown(
        """
        <div style="text-align:center;color:#94a3b8;font-size:0.72rem;margin-top:1.5rem;">
            Desenvolvimento: Julio Paz
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_trocar_senha_obrigatoria() -> None:
    """Trava obrigatória de troca de senha — usuário criado pela
    Administração sempre entra com a senha padrão (`SENHA_PADRAO`,
    `precisa_trocar_senha=True`); antes de ver qualquer página do painel,
    precisa definir uma senha própria. Chamado por app.py logo após o
    gate de login, antes de `inject_shell_css()`/qualquer conteúdo —
    mesmo padrão de "tela única, sem sidebar" do login."""
    _inject_login_css()
    render_logo_video(size=112)
    st.markdown(
        """
        <div style="text-align:center;">
            <h1 style="font-size:1.6rem;font-weight:800;color:#0f2f52;
                margin:0.9rem 0 0.15rem;letter-spacing:0.02em;">Defina sua senha</h1>
            <div style="color:#64748b;font-size:0.85rem;">
                Primeiro acesso — troque a senha padrão antes de continuar.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    usuario = get_usuario()

    with st.form("form_trocar_senha_obrigatoria"):
        nova = st.text_input("Nova senha", type="password", placeholder="Mínimo 8 caracteres")
        confirmar = st.text_input("Confirme a nova senha", type="password")
        salvar = st.form_submit_button("Definir senha e entrar", use_container_width=True)

        if salvar:
            if len(nova) < 8:
                st.error("A senha precisa ter pelo menos 8 caracteres.")
            elif nova != confirmar:
                st.error("As senhas não coincidem.")
            elif nova == SENHA_PADRAO:
                st.error("Escolha uma senha diferente da padrão.")
            else:
                trocar_senha_primeiro_login(usuario["id"], gerar_hash(nova))
                # Atualiza a cópia em sessão também — senão o gate em
                # app.py continuaria vendo precisa_trocar_senha=True (do
                # login original) e voltaria pra esta tela num loop.
                usuario["precisa_trocar_senha"] = False
                set_usuario(usuario)
                try:
                    inserir_log_acesso(usuario["id"], "trocar_senha_primeiro_login")
                except Exception:
                    pass
                st.success("Senha definida.")
                st.rerun()
