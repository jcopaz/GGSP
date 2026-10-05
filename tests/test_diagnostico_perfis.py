"""Diagnóstico "Perfis com problema" da Administração (caso Sandra,
2026-10-04): usuário entra, vê o menu e nenhuma tela com dado."""
from src.dashboard.administracao import diagnosticar_perfis

BASE = {"gerencia": {"GER_1"}, "gerencia_obras": {"Baixada"}, "elemento_pep": {"P-01"}}


def _u(uid, papel="especialista_analista", ativo=True):
    return {"id": uid, "nome_completo": f"User {uid}", "papel": papel, "ativo": ativo}


def _e(uid, universo, tipo, valor):
    return {"usuario_id": uid, "universo": universo, "tipo": tipo, "valor": valor}


def test_sem_universo_nenhum():
    p = diagnosticar_perfis([_u("1")], [], BASE)
    assert "nenhum universo" in p[0]["Problema"]


def test_so_escopo_legado():
    p = diagnosticar_perfis([_u("1")], [_e("1", None, "pacote", "X")], BASE)
    assert "legados" in p[0]["Problema"]


def test_tipo_invalido_em_obras():
    p = diagnosticar_perfis([_u("1")], [_e("1", "capex_obras", "gerencia", "GER_1")], BASE)
    assert "não é filtrável" in p[0]["Problema"]


def test_valor_inexistente_na_base():
    p = diagnosticar_perfis([_u("1")], [_e("1", "opex_sustaining", "gerencia", "GER_VELHA")], BASE)
    assert "GER_VELHA" in p[0]["Problema"]


def test_perfil_ok_e_admin_e_inativo_nao_aparecem():
    usuarios = [_u("1"), _u("2", papel="admin"), _u("3", ativo=False)]
    escopos = [
        _e("1", "opex_sustaining", "gerencia", "GER_1"),
        _e("1", "capex_obras", "gg", "(todas)"),
    ]
    assert diagnosticar_perfis(usuarios, escopos, BASE) == []


def test_sem_base_pula_checagem_de_valor():
    p = diagnosticar_perfis([_u("1")], [_e("1", "opex_sustaining", "gerencia", "QUALQUER")], None)
    assert p == []
