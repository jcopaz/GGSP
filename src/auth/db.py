"""Conexão com o Postgres (Neon) — só guarda usuário/RBAC/justificativas/
auditoria. O warehouse analítico continua em DuckDB local (ver
docs/05-publicacao-online-e-seguranca.md).

Cada função abre e fecha sua própria conexão (sem @st.cache_resource): o
Streamlit roda um processo por servidor com N usuários simultâneos, e uma
conexão psycopg2 compartilhada entre threads é arriscada. O volume de
consulta aqui é baixo (login, gravar justificativa) — o custo de abrir
conexão a cada chamada é irrelevante perto disso.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.extras
import streamlit as st


@contextmanager
def conectar() -> Iterator[psycopg2.extensions.connection]:
    # connect_timeout curto (segundos) — achado em 2026-08-28: sem isso,
    # numa rede que bloqueia a porta em silêncio (não recusa, só some — ver
    # docs/05-publicacao-online-e-seguranca.md), o TCP fica esperando pelo
    # timeout padrão do SO (pode passar de 1 minuto). Isso virou problema
    # de verdade quando a auditoria (best-effort, "nunca deve travar a ação
    # principal") passou a rodar a cada visualização de página — uma
    # tentativa de conexão travada travava a página inteira, não só o log.
    # 8s tolera o "scale to zero" do Neon free (cold start) sem deixar a
    # UI pendurada por muito tempo se o banco estiver mesmo inalcançável.
    conn = psycopg2.connect(st.secrets["postgres_url"], connect_timeout=8)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def buscar_um(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    with conectar() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            linha = cur.fetchone()
            return dict(linha) if linha is not None else None


def buscar_todos(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with conectar() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(linha) for linha in cur.fetchall()]


def executar(sql: str, params: tuple = ()) -> None:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
