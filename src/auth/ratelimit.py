"""Rate limit / lockout de login (revisão de cibersegurança 2026-09-07 —
docs/10 achado A1).

`_autenticar` (src/auth/login.py) chamava `verificar_senha` sem nenhum freio
a tentativas. Aqui entra: toda tentativa (sucesso/falha) vira uma linha em
`app.tentativa_login`; antes de conferir a senha, o login pergunta se aquele
`identificador` OU aquele `ip` está bloqueado.

Regra (constantes abaixo): a partir de `MAX_FALHAS` falhas dentro de
`JANELA_MIN` minutos — contadas **depois do último sucesso** — bloqueia por
`BLOQUEIO_MIN` minutos, a contar da última falha. Um login bem-sucedido zera
o contador.

A checagem **falha-aberta** se o Neon cair (não trava login legítimo por
banco fora) — aceitável porque sem banco o próprio `_autenticar` já não
autentica ninguém.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

JANELA_MIN = 15
MAX_FALHAS = 5
BLOQUEIO_MIN = 15


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def avaliar_bloqueio(
    tentativas: list[dict], agora: datetime | None = None,
) -> tuple[bool, int]:
    """Função **pura** — decide o bloqueio a partir do histórico.

    `tentativas`: lista de dicts com `sucesso: bool` e `ocorrido_em: datetime`
    (tz-aware), de UM identificador ou de UM ip. Ordem não importa.

    Retorna `(bloqueado, segundos_restantes)`. `segundos_restantes` é 0
    quando não bloqueado.
    """
    agora = agora or _agora()
    inicio_janela = agora - timedelta(minutes=JANELA_MIN)

    # Só o que aconteceu depois do último sucesso conta — um login certo
    # "limpa a ficha".
    sucessos = [t["ocorrido_em"] for t in tentativas if t.get("sucesso")]
    ultimo_sucesso = max(sucessos) if sucessos else None

    falhas = sorted(
        t["ocorrido_em"]
        for t in tentativas
        if not t.get("sucesso")
        and t["ocorrido_em"] >= inicio_janela
        and (ultimo_sucesso is None or t["ocorrido_em"] > ultimo_sucesso)
    )

    if len(falhas) < MAX_FALHAS:
        return False, 0

    fim_bloqueio = falhas[-1] + timedelta(minutes=BLOQUEIO_MIN)
    if agora >= fim_bloqueio:
        return False, 0
    return True, int((fim_bloqueio - agora).total_seconds())


# --------------------------------------------------------------------------- #
# Invólucros que falam com o Neon (não testados por unidade — a lógica
# testável está em `avaliar_bloqueio`).
# --------------------------------------------------------------------------- #
# SQL fixo por coluna — sem interpolação (a coluna nunca vem de entrada de
# usuário, mas manter 2 literais é mais simples de auditar que um f-string).
_SQL_POR_IDENTIFICADOR = (
    "select sucesso, ocorrido_em from app.tentativa_login "
    "where identificador = %s and ocorrido_em >= %s"
)
_SQL_POR_IP = (
    "select sucesso, ocorrido_em from app.tentativa_login "
    "where ip = %s and ocorrido_em >= %s"
)


def _tentativas_recentes(sql: str, valor: str) -> list[dict]:
    from src.auth.db import buscar_todos

    desde = _agora() - timedelta(minutes=max(JANELA_MIN, BLOQUEIO_MIN) + 1)
    linhas = buscar_todos(sql, (valor, desde))
    return [dict(sucesso=bool(r["sucesso"]), ocorrido_em=r["ocorrido_em"]) for r in linhas]


def checar_bloqueio(identificador: str, ip: str | None) -> tuple[bool, int]:
    """`(bloqueado, segundos_restantes)` — bloqueia se o identificador OU o
    ip estourou a regra. Falha-aberta (retorna liberado) em qualquer erro
    de banco."""
    try:
        bloq_id, faltam_id = avaliar_bloqueio(
            _tentativas_recentes(_SQL_POR_IDENTIFICADOR, identificador)
        )
        bloq_ip, faltam_ip = (False, 0)
        if ip:
            bloq_ip, faltam_ip = avaliar_bloqueio(_tentativas_recentes(_SQL_POR_IP, ip))
    except Exception:
        return False, 0
    if bloq_id or bloq_ip:
        return True, max(faltam_id, faltam_ip)
    return False, 0


def registrar_tentativa(identificador: str, ip: str | None, sucesso: bool) -> None:
    """Best-effort — nunca derruba o login se o insert falhar."""
    try:
        from src.auth.db import executar

        executar(
            "insert into app.tentativa_login (identificador, ip, sucesso) values (%s, %s, %s)",
            (identificador, ip, sucesso),
        )
    except Exception:
        pass


def ip_do_cliente() -> str | None:
    """X-Forwarded-For quando o app está atrás de proxy (Streamlit Community
    Cloud). Sem proxy / API indisponível → None (aí o rate limit vale só por
    identificador)."""
    try:
        import streamlit as st

        headers = st.context.headers  # Streamlit >= 1.37
        xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    except Exception:
        pass
    return None
