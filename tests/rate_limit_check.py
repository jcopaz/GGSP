"""Testes da regra de rate limit / lockout de login (docs/10 A1).

Só a função pura `avaliar_bloqueio` — os invólucros de Neon
(`checar_bloqueio`/`registrar_tentativa`) não têm lógica pra testar.

Uso: python -m pytest tests/rate_limit_check.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.auth.ratelimit import BLOQUEIO_MIN, JANELA_MIN, MAX_FALHAS, avaliar_bloqueio

_AGORA = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def _f(minutos_atras: float, sucesso: bool = False) -> dict:
    return {"sucesso": sucesso, "ocorrido_em": _AGORA - timedelta(minutes=minutos_atras)}


def test_sem_tentativas_libera():
    assert avaliar_bloqueio([], _AGORA) == (False, 0)


def test_abaixo_do_limite_libera():
    tent = [_f(i) for i in range(MAX_FALHAS - 1)]  # 4 falhas recentes
    assert avaliar_bloqueio(tent, _AGORA) == (False, 0)


def test_no_limite_bloqueia():
    tent = [_f(i) for i in range(MAX_FALHAS)]  # 5 falhas, a mais recente agora
    bloqueado, faltam = avaliar_bloqueio(tent, _AGORA)
    assert bloqueado is True
    assert 0 < faltam <= BLOQUEIO_MIN * 60


def test_sucesso_recente_zera_contador():
    tent = [_f(i) for i in range(MAX_FALHAS)] + [_f(0.1, sucesso=True)]
    assert avaliar_bloqueio(tent, _AGORA) == (False, 0)


def test_sucesso_antigo_nao_zera():
    # sucesso há 30 min, depois 5 falhas dentro da janela
    tent = [_f(30, sucesso=True)] + [_f(i) for i in range(MAX_FALHAS)]
    bloqueado, _ = avaliar_bloqueio(tent, _AGORA)
    assert bloqueado is True


def test_falhas_fora_da_janela_nao_contam():
    tent = [_f(JANELA_MIN + 5 + i) for i in range(MAX_FALHAS)]  # todas > 15 min atrás
    assert avaliar_bloqueio(tent, _AGORA) == (False, 0)


def test_bloqueio_expira_quando_falhas_saem_da_janela():
    # 5 falhas, a mais recente há 16 min → todas já fora da janela de 15 min
    tent = [_f(JANELA_MIN + 1 + i) for i in range(MAX_FALHAS)]
    assert avaliar_bloqueio(tent, _AGORA) == (False, 0)
    # 1 falha ainda dentro (há 14 min) + 4 mais antigas → só 1 conta → libera
    tent2 = [_f(JANELA_MIN - 1)] + [_f(JANELA_MIN + 2 + i) for i in range(MAX_FALHAS - 1)]
    assert avaliar_bloqueio(tent2, _AGORA) == (False, 0)


def test_segundos_restantes_decrescem():
    # 5 falhas, a mais recente há 5 min → resta ~10 min de bloqueio
    tent = [_f(5 + i) for i in range(MAX_FALHAS)]
    bloqueado, faltam = avaliar_bloqueio(tent, _AGORA)
    assert bloqueado is True
    assert (BLOQUEIO_MIN - 5 - 1) * 60 <= faltam <= (BLOQUEIO_MIN - 5) * 60


def test_ordem_das_tentativas_nao_importa():
    tent = [_f(3), _f(0), _f(4), _f(1), _f(2)]  # 5 falhas embaralhadas
    assert avaliar_bloqueio(tent, _AGORA)[0] is True
