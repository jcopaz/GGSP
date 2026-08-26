"""Consultas de usuário/autenticação contra app.usuario (Neon Postgres)."""
from __future__ import annotations

from src.auth.db import buscar_um, executar


def buscar_usuario_por_matricula(matricula: str) -> dict | None:
    return buscar_um("select * from app.usuario where matricula = %s", (matricula,))


def buscar_usuario_por_email(email: str) -> dict | None:
    return buscar_um("select * from app.usuario where email = %s", (email,))


def buscar_usuario_por_identificador(identificador: str) -> dict | None:
    """Aceita matrícula OU e-mail no mesmo campo de login."""
    identificador = identificador.strip()
    if "@" in identificador:
        return buscar_usuario_por_email(identificador.lower())
    return buscar_usuario_por_matricula(identificador)


def atualizar_ultimo_login(usuario_id: str) -> None:
    executar(
        "update app.usuario set ultimo_login = now() where id = %s",
        (usuario_id,),
    )


def atualizar_senha_hash(usuario_id: str, senha_hash: str) -> None:
    executar(
        "update app.usuario set senha_hash = %s, atualizado_em = now() where id = %s",
        (senha_hash, usuario_id),
    )


def inserir_log_acesso(usuario_id: str | None, acao: str, detalhe: dict | None = None) -> None:
    import json

    executar(
        "insert into app.log_auditoria (usuario_id, acao, recurso, detalhe) values (%s, %s, %s, %s)",
        (usuario_id, acao, "auth", json.dumps(detalhe or {})),
    )


def criar_usuario(
    *,
    nome_completo: str,
    papel: str,
    senha_hash: str,
    matricula: str | None = None,
    email: str | None = None,
    gg_id: str | None = None,
    gerencia_id: str | None = None,
    permissao_upload: bool = False,
    permissao_exportacao: bool = True,
    permissao_justificativa_macro: bool = False,
    permissao_justificativa_micro: bool = False,
) -> None:
    executar(
        """
        insert into app.usuario (
            matricula, email, senha_hash, nome_completo, papel, gg_id, gerencia_id,
            permissao_upload, permissao_exportacao,
            permissao_justificativa_macro, permissao_justificativa_micro
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            matricula, email, senha_hash, nome_completo, papel, gg_id, gerencia_id,
            permissao_upload, permissao_exportacao,
            permissao_justificativa_macro, permissao_justificativa_micro,
        ),
    )
