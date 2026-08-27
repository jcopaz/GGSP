"""Reset de senha autoatendido ("Esqueci minha senha").

Padrão portado de MRS Sentinel/Sentinel/auth/recuperar_senha.py: gera uma
senha temporária no servidor, grava o hash bcrypt direto no Postgres (aqui:
Neon, em vez da Admin API do Supabase) e envia por e-mail via SMTP simples
(Brevo). Só funciona para conta com e-mail cadastrado — login só por
matrícula sem e-mail precisa de reset por um Admin (Camada 3).
"""
from __future__ import annotations

import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

from src.auth.queries import (
    buscar_usuario_por_identificador,
    inserir_log_acesso,
)
from src.auth.senha import gerar_hash, gerar_senha_temporaria
from src.auth.queries import atualizar_senha_hash

# Mesma mensagem de sucesso independente de a conta existir ou não — evita
# que alguém descubra quais matrículas/e-mails têm conta só tentando o reset.
_MSG_GENERICA = (
    "Se existe uma conta ativa com e-mail cadastrado para essa matrícula/"
    "e-mail, uma nova senha temporária foi enviada. Confira sua caixa de "
    "entrada (e o spam)."
)
_MSG_SEM_EMAIL = (
    "Essa conta não tem e-mail cadastrado — o reset autoatendido não tem "
    "como avisar você em lugar nenhum. Peça a um administrador para "
    "resetar sua senha."
)
_MSG_FALHA_ENVIO = (
    "A senha foi trocada, mas não conseguimos enviar o e-mail agora "
    "(SMTP indisponível). Peça a um administrador para resetar de novo."
)

_COOLDOWN_SEGUNDOS = 60


def _enviar_email_senha(destinatario: str, nome: str, senha_temp: str) -> bool:
    smtp_cfg = st.secrets.get("smtp", {})
    host = smtp_cfg.get("host")
    if not host:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "[Fin360] Sua nova senha temporária"
        msg["From"] = smtp_cfg.get("remetente", smtp_cfg.get("usuario", ""))
        msg["To"] = destinatario
        corpo = f"""
        <p>Olá, {nome},</p>
        <p>Recebemos um pedido de reset de senha para sua conta no Fin360.</p>
        <p>Sua nova senha temporária é: <b style="font-size:1.15em">{senha_temp}</b></p>
        <p>Use essa senha para entrar. Se não foi você quem pediu, avise um administrador.</p>
        """
        msg.attach(MIMEText(corpo, "html"))

        porta = int(smtp_cfg.get("port", 587))
        with smtplib.SMTP(host, porta, timeout=20) as server:
            server.starttls()
            if smtp_cfg.get("usuario"):
                server.login(smtp_cfg["usuario"], smtp_cfg.get("senha", ""))
            server.sendmail(msg["From"], [destinatario], msg.as_string())
        return True
    except Exception:
        return False


def solicitar_reset_senha(identificador: str) -> str:
    identificador = identificador.strip()
    if not identificador:
        return _MSG_GENERICA

    usuario = buscar_usuario_por_identificador(identificador)
    if not usuario or not usuario.get("ativo", False):
        return _MSG_GENERICA

    if not usuario.get("email"):
        return _MSG_SEM_EMAIL

    senha_temp = gerar_senha_temporaria()
    try:
        atualizar_senha_hash(usuario["id"], gerar_hash(senha_temp))
    except Exception:
        return _MSG_GENERICA

    if not _enviar_email_senha(usuario["email"], usuario.get("nome_completo", ""), senha_temp):
        return _MSG_FALHA_ENVIO

    try:
        inserir_log_acesso(usuario["id"], "solicitar_reset_senha")
    except Exception:
        pass

    return _MSG_GENERICA


def render_esqueci_senha() -> None:
    with st.expander("Esqueci minha senha"):
        st.caption(
            "Funciona só para contas com e-mail cadastrado. Login só por "
            "matrícula precisa de reset pelo administrador."
        )
        with st.form("form_esqueci_senha"):
            identificador = st.text_input(
                "Matrícula ou e-mail", placeholder="Ex: 123456 ou seu.nome@mrs.com.br",
                key="esqueci_senha_id",
            )
            enviar = st.form_submit_button("Enviar nova senha por e-mail")

        if enviar:
            agora = st.session_state.get("_ultimo_reset_ts")
            ts = time.time()
            if agora and (ts - agora) < _COOLDOWN_SEGUNDOS:
                st.warning(f"Aguarde {int(_COOLDOWN_SEGUNDOS - (ts - agora))}s antes de tentar de novo.")
            elif not identificador.strip():
                st.error("Informe a matrícula ou o e-mail.")
            else:
                st.session_state["_ultimo_reset_ts"] = ts
                with st.spinner("Processando..."):
                    msg = solicitar_reset_senha(identificador)
                if msg == _MSG_GENERICA:
                    st.success(msg)
                else:
                    st.warning(msg)
