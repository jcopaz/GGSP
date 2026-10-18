"""Tela "Perfil de acesso" da Administração + revalidação de acesso sem
novo login (docs/13). O Neon é substituído por funções falsas dentro do
AppTest — nada aqui abre conexão."""
from __future__ import annotations

import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

REPO = str(Path(__file__).resolve().parents[1])

USUARIOS = [
    {"id": "adm", "nome_completo": "Admin", "matricula": "1", "papel": "admin", "ativo": True},
    {"id": "u1", "nome_completo": "Ana", "matricula": "2", "papel": "gerente", "ativo": True,
     "permissao_upload": False, "permissao_exportacao": True,
     "permissao_justificativa_macro": False, "permissao_justificativa_micro": True},
]


def _admin(repo: str) -> None:
    import os as _os
    import sys as _sys

    import streamlit as st

    _sys.path.insert(0, repo)
    _os.chdir(repo)
    import src.dashboard.administracao as adm

    ss = st.session_state
    gravados = ss.setdefault("_gravados", [])
    adm.listar_usuarios = lambda: ss["_usuarios"]
    def _escopos(uid):
        if ss.get("_falha_leitura"):
            raise RuntimeError("neon fora")
        return [e for e in ss["_escopos"] if e["usuario_id"] == uid]

    adm.listar_escopos_universo = _escopos
    adm.listar_permissoes = lambda uid: ss.get("_perms", {}).get(uid, [])
    adm.listar_escopos = lambda uid: []
    adm.listar_escopos_todos_ativos = lambda: []
    adm.listar_atividades = lambda *a: []
    adm.listar_versoes_upload = lambda *a: []
    adm.listar_exportacoes = lambda *a: []
    adm.registrar_atividade = lambda *a, **k: None
    adm.salvar_perfil_acesso = lambda *a, **k: (gravados.append(a), ss.setdefault("_gravados_kw", []).append(k))
    adm.render_administracao(None)


def _rodar(escopos: list[dict]):
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_admin, args=(REPO,), default_timeout=60)
    at.session_state["usuario"] = {"id": "adm", "papel": "admin", "nome_completo": "Admin"}
    at.session_state["logged_in"] = True
    at.session_state["_usuarios"] = USUARIOS
    at.session_state["_escopos"] = escopos
    at.run()
    assert not at.exception, at.exception
    at.selectbox(key="admin-escopo-user").set_value("Ana · 2").run()
    assert not at.exception, at.exception
    return at


def test_detecta_perfil_atual_e_salva_manutencao_numa_gravacao_so():
    escopos = [{"usuario_id": "u1", "universo": u, "tipo": "gerencia", "valor": "GGE_0025", "descricao": ""}
               for u in ("opex_sustaining", "capex_sustaining")]
    at = _rodar(escopos)
    radio = at.radio(key="perfil-u1")
    assert radio.value == "manutencao"  # detectado a partir do que está gravado
    assert at.text_input(key="perfil-u1-man-ger-txt").value == "GGE_0025"  # sem base: texto livre
    at.text_input(key="perfil-u1-man-ger-txt").set_value("GGE_0025, GGE_0029").run()
    at.button(key="perfil-u1-salvar").click().run()
    assert not at.exception, at.exception
    (uid, papel, caps, escopos_g, paginas), = at.session_state["_gravados"]
    assert uid == "u1" and papel == "gerente"
    assert "contas" in at.session_state["_gravados_kw"][0]["paginas_remover"]
    esperado = [("gerencia", "GGE_0025", ""), ("gerencia", "GGE_0029", "")]
    assert escopos_g["opex_sustaining"] == esperado == escopos_g["capex_sustaining"]
    assert escopos_g["capex_obras"] == []
    assert caps["permissao_justificativa_micro"] is True and caps["permissao_upload"] is False
    assert paginas["upload"] is False and paginas["pce_especialista"] is False
    assert "Vale para a pessoa em até 1 minuto" in " ".join(s.value for s in at.success)


def test_recorte_vazio_nao_salva():
    at = _rodar([])
    assert at.radio(key="perfil-u1").value == "sem_acesso"  # usuário novo
    at.radio(key="perfil-u1").set_value("manutencao").run()
    at.checkbox(key="perfil-u1-man-todas").uncheck().run()
    assert at.button(key="perfil-u1-salvar").disabled
    assert any("Escolha ao menos uma" in e.value for e in at.error)


def test_admin_nao_tira_o_proprio_acesso():
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_admin, args=(REPO,), default_timeout=60)
    at.session_state["usuario"] = {"id": "adm", "papel": "admin", "nome_completo": "Admin"}
    at.session_state["_usuarios"] = USUARIOS
    at.session_state["_escopos"] = []
    at.run()
    assert at.radio(key="perfil-adm").value == "admin"
    at.radio(key="perfil-adm").set_value("gestao_gg").run()
    assert at.button(key="perfil-adm-salvar").disabled


def test_falha_ao_ler_acesso_no_neon_nao_permite_salvar():
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_admin, args=(REPO,), default_timeout=60)
    at.session_state["usuario"] = {"id": "adm", "papel": "admin", "nome_completo": "Admin"}
    at.session_state["_usuarios"] = USUARIOS
    at.session_state["_escopos"] = []
    at.session_state["_falha_leitura"] = True
    at.run()
    at.selectbox(key="admin-escopo-user").set_value("Ana · 2").run()
    assert not at.exception, at.exception
    assert any("Não consegui ler" in e.value for e in at.error)
    assert not [b for b in at.button if b.key == "perfil-u1-salvar"]
    assert not [r for r in at.radio if r.key == "perfil-u1"]
    assert at.session_state["_gravados"] == []


def test_personalizado_salva_numa_gravacao_so():
    escopos = [
        {"usuario_id": "u1", "universo": "opex_sustaining", "tipo": "gerencia", "valor": "GGE_0025", "descricao": ""},
        {"usuario_id": "u1", "universo": "capex_obras", "tipo": "gerencia_obras", "valor": "Expansão", "descricao": ""},
    ]
    at = _rodar(escopos)
    assert at.radio(key="perfil-u1").value == "personalizado"
    keys = {b.key for b in at.button}
    assert not keys & {"uni-u1-salvar", "perm-u1-salvar", "perfil-u1-salvar-caps"}
    at.button(key="perfil-u1-salvar").click().run()
    assert not at.exception, at.exception
    (uid, papel, caps, escopos_g, paginas), = at.session_state["_gravados"]
    assert uid == "u1" and papel == "gerente"
    assert escopos_g["opex_sustaining"][0][:2] == ("gerencia", "GGE_0025")
    assert escopos_g["capex_obras"][0][:2] == ("gerencia_obras", "Expansão")
    assert paginas["pce_especialista"] is False and paginas["upload"] is False
    assert "paginas_remover" not in at.session_state["_gravados_kw"][0]


# ===== Revalidação sem novo login =====

def _revalida(repo: str) -> None:
    import sys as _sys

    import streamlit as st

    _sys.path.insert(0, repo)
    import src.auth.permissions as perm

    ss = st.session_state
    perm._assinatura_acesso = lambda uid: ss["_fake_assinatura"]

    def _recarrega(uid):
        if ss.get("_fake_falha_recarga"):
            raise RuntimeError("neon fora")
        return ss["_fake_usuario"]

    perm._recarregar_usuario = _recarrega
    perm.revalidar_acesso_da_sessao(agora=ss["_agora"])
    st.write("CACHE=" + str("_escopos_acesso_cache" in ss) + " USUARIO=" + str((ss.get("usuario") or {}).get("papel")))
    st.write("ASSIN=" + str(ss.get("_acesso_assinatura")))


def _estado(at) -> str:
    return next(m.value for m in at.markdown if m.value.startswith("CACHE="))


def _assin(at) -> str:
    return next(m.value for m in at.markdown if m.value.startswith("ASSIN="))


def test_mudanca_de_acesso_limpa_cache_em_ate_um_minuto():
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_revalida, args=(REPO,), default_timeout=30)
    at.session_state["usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_escopos_acesso_cache"] = [{"universo": "opex_sustaining", "tipo": "gg", "valor": "x"}]
    at.session_state["_fake_assinatura"] = "A"
    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_agora"] = 1000.0
    at.run()
    assert _estado(at) == "CACHE=False USUARIO=gerente"  # 1ª medição também descarta o cache (B3)

    at.session_state["_escopos_acesso_cache"] = [{"universo": "opex_sustaining", "tipo": "gg", "valor": "x"}]
    at.session_state["_fake_assinatura"] = "B"  # admin mudou o acesso
    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_agora"] = 1030.0
    at.run()
    assert _estado(at) == "CACHE=True USUARIO=gerente"  # dentro do minuto: não consulta

    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "gg", "ativo": True}
    at.session_state["_agora"] = 1061.0
    at.run()
    assert _estado(at) == "CACHE=False USUARIO=gg"  # cache descartado, usuário recarregado


def test_falha_ao_recarregar_nao_congela_acesso_antigo():
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_revalida, args=(REPO,), default_timeout=30)
    at.session_state["usuario"] = {"id": "u1", "papel": "admin", "ativo": True, "permissao_upload": True}
    at.session_state["_fake_assinatura"] = "A"
    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "admin", "ativo": True}
    at.session_state["_agora"] = 1000.0
    at.run()
    assert "USUARIO=admin" in _estado(at) and _assin(at) == "ASSIN=A"

    at.session_state["_fake_assinatura"] = "B"  # acesso mudou, mas a recarga falha
    at.session_state["_fake_falha_recarga"] = True
    at.session_state["_agora"] = 1061.0
    at.run()
    assert "USUARIO=admin" not in _estado(at)  # rebaixado (fail closed)
    assert at.session_state["usuario"]["permissao_upload"] is False
    assert _assin(at) == "ASSIN=A"  # assinatura nova NÃO gravada -> tenta de novo

    at.session_state["_fake_falha_recarga"] = False
    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_agora"] = 1122.0
    at.run()
    assert "USUARIO=gerente" in _estado(at) and _assin(at) == "ASSIN=B"


def test_primeira_medicao_descarta_cache_antigo():
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_revalida, args=(REPO,), default_timeout=30)
    at.session_state["usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_escopos_acesso_cache"] = [{"universo": "opex_sustaining", "tipo": "gg", "valor": "x"}]
    at.session_state["_fake_assinatura"] = "A"
    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "gg", "ativo": True}
    at.session_state["_agora"] = 1000.0
    at.run()
    assert _estado(at) == "CACHE=False USUARIO=gg"


def test_troca_de_usuario_sem_logout():
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_revalida, args=(REPO,), default_timeout=30)
    at.session_state["usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_acesso_usuario_id"] = "u0"
    at.session_state["_acesso_assinatura"] = "X"
    at.session_state["_acesso_verificado_em"] = 1000.0
    at.session_state["_escopos_acesso_cache"] = [{"universo": "opex_sustaining", "tipo": "gg", "valor": "x"}]
    at.session_state["_fake_assinatura"] = "A"
    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_agora"] = 1010.0
    at.run()
    assert "CACHE=False" in _estado(at)
    assert at.session_state["_acesso_usuario_id"] == "u1"
    assert at.session_state["_acesso_assinatura"] == "A"


def test_usuario_desativado_cai_para_o_login():
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    at = AppTest.from_function(_revalida, args=(REPO,), default_timeout=30)
    at.session_state["usuario"] = {"id": "u1", "papel": "gerente", "ativo": True}
    at.session_state["_fake_assinatura"] = "A"
    at.session_state["_fake_usuario"] = {"id": "u1", "papel": "gerente", "ativo": False}
    at.session_state["_agora"] = 1000.0
    at.run()
    at.session_state["_fake_assinatura"] = "B"
    at.session_state["_agora"] = 2000.0
    at.run()
    assert "usuario" not in at.session_state or not at.session_state["usuario"]


def test_logout_limpa_caches_de_acesso():
    import streamlit as st  # noqa: F401  (session_state fora de app vira dict local)
    from src.auth import session

    estado: dict = {"usuario": {"id": "a"}, "logged_in": True, "_escopos_acesso_cache": [1],
                    "_permissoes_pagina_cache": {}, "_acesso_assinatura": "x"}

    class _SS(dict):
        pass

    original = session.st.session_state
    try:
        session.st.session_state = _SS(estado)  # type: ignore[attr-defined]
        session.clear_session()
        restou = dict(session.st.session_state)
    finally:
        session.st.session_state = original  # type: ignore[attr-defined]
    assert restou == {}
