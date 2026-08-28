"""Hash e verificação de senha — sempre bcrypt, nunca texto plano."""
from __future__ import annotations

import secrets
import string

import bcrypt

# Não existe mais uma "senha padrão" fixa (removida em 2026-08-28 — era
# Fin360@123, literal no código-fonte e igual pra todo usuário novo:
# achado de revisão de segurança automática, HIGH — "Hardcoded
# Credentials / Shared Default Password"). Todo usuário criado pela
# Administração agora recebe uma senha temporária ÚNICA e aleatória via
# `gerar_senha_temporaria()` abaixo (mesma função já usada no reset
# autoatendido, `recuperar_senha.py`), mostrada só uma vez pra quem criou
# — nunca fica gravada em texto plano nem repetida entre contas.


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hash_armazenado.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def gerar_senha_temporaria(tamanho: int = 10) -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))
