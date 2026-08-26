"""Hash e verificação de senha — sempre bcrypt, nunca texto plano."""
from __future__ import annotations

import secrets
import string

import bcrypt


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
