"""Perfis de acesso (docs/13): perfil -> linhas e linhas -> perfil."""
import pytest

from src.auth.perfis import (
    PAGINA_ESPECIALISTA, PAGINA_UPLOAD, TODAS, UNIVERSO_DA_PAGINA, Recorte,
    detectar_perfil, montar_plano, paginas_visiveis,
)

SEM_CAP = {}
UNIVERSOS_TESTE = ("opex_sustaining", "capex_sustaining", "capex_obras")


def _linhas(plano):
    escopos = [{"universo": u, "tipo": t, "valor": v} for u, ls in plano.escopos.items() for t, v in ls]
    perms = [{"pagina": p, "permitido": ok} for p, ok in plano.paginas.items()]
    return {"papel": plano.papel}, escopos, perms


@pytest.mark.parametrize("perfil, recorte", [
    ("gestao_gg", Recorte()),
    ("gestao_gg", Recorte(especialista=True)),
    ("manutencao", Recorte()),
    ("manutencao", Recorte(gerencias=("GGE_0025", "GGE_0029"))),
    ("obras", Recorte()),
    ("obras", Recorte(gerencias_obras=("Baixada Santista",), projetos=("DM/21973",), especialista=True)),
    ("sem_acesso", Recorte()),
])
def test_ida_e_volta(perfil, recorte):
    plano = montar_plano(perfil, recorte, SEM_CAP)
    assert detectar_perfil(*_linhas(plano)) == (perfil, recorte)


def test_admin():
    plano = montar_plano("admin", Recorte(), SEM_CAP)
    assert plano.papel == "admin" and all(plano.capacidades.values())
    assert detectar_perfil({"papel": "admin"}, [], [])[0] == "admin"


def test_manutencao_mesma_lista_nos_dois_sustaining_e_sem_obras():
    p = montar_plano("manutencao", Recorte(gerencias=("GGE_0025",)), SEM_CAP)
    assert p.escopos["opex_sustaining"] == p.escopos["capex_sustaining"] == [("gerencia", "GGE_0025")]
    assert p.escopos["capex_obras"] == []
    assert montar_plano("manutencao", Recorte(), SEM_CAP).escopos["opex_sustaining"] == [("gg", TODAS)]


def test_paginas_de_universo_sempre_liberadas_e_universo_decide():
    p = montar_plano("obras", Recorte(), SEM_CAP)
    for pagina in UNIVERSO_DA_PAGINA:
        if pagina != PAGINA_ESPECIALISTA:
            assert p.paginas[pagina] is True
    visiveis = paginas_visiveis(p)
    assert "obras_resumo" in visiveis and "manutencao_resumo" not in visiveis


def test_upload_segue_a_capacidade():
    sem = montar_plano("gestao_gg", Recorte(), {"permissao_upload": False})
    com = montar_plano("gestao_gg", Recorte(), {"permissao_upload": True})
    assert sem.paginas[PAGINA_UPLOAD] is False and PAGINA_UPLOAD not in paginas_visiveis(sem)
    assert com.paginas[PAGINA_UPLOAD] is True and PAGINA_UPLOAD in paginas_visiveis(com)


def test_especialista_so_com_obras():
    assert montar_plano("manutencao", Recorte(especialista=True), SEM_CAP).paginas[PAGINA_ESPECIALISTA] is False
    p = montar_plano("obras", Recorte(especialista=True), SEM_CAP)
    assert p.paginas[PAGINA_ESPECIALISTA] is True and PAGINA_ESPECIALISTA in paginas_visiveis(p)


@pytest.mark.parametrize("escopos, perms", [
    # Gerências diferentes entre OPEX e CAPEX Sustaining
    ([{"universo": "opex_sustaining", "tipo": "gerencia", "valor": "A"},
      {"universo": "capex_sustaining", "tipo": "gerencia", "valor": "B"}], []),
    # Manutenção + Obras ao mesmo tempo
    ([{"universo": "opex_sustaining", "tipo": "gg", "valor": TODAS},
      {"universo": "capex_sustaining", "tipo": "gg", "valor": TODAS},
      {"universo": "capex_obras", "tipo": "gerencia_obras", "valor": "Expansão"}], []),
    # página de universo liberado negada à mão
    ([{"universo": "capex_obras", "tipo": "gg", "valor": TODAS}], [{"pagina": "capex_contas", "permitido": False}]),
    # só OPEX, sem CAPEX Sustaining
    ([{"universo": "opex_sustaining", "tipo": "gerencia", "valor": "A"}], []),
])
def test_fora_do_molde_vira_personalizado(escopos, perms):
    assert detectar_perfil({"papel": "gerente"}, escopos, perms)[0] == "personalizado"


def test_negacao_em_universo_que_nao_tem_nao_impede_perfil():
    escopos = [{"universo": u, "tipo": "gerencia", "valor": "A"} for u in ("opex_sustaining", "capex_sustaining")]
    perms = [{"pagina": "obras_resumo", "permitido": False}, {"pagina": "pce_especialista", "permitido": True}]
    assert detectar_perfil({"papel": "gerente"}, escopos, perms) == ("manutencao", Recorte(gerencias=("A",)))


def test_personalizado_nao_tem_plano_automatico():
    with pytest.raises(ValueError):
        montar_plano("personalizado", Recorte(), SEM_CAP)


# ===== Correções pós-revisão de 18/10 (docs/13, N2) =====

def _manut_escopos():
    return [{"universo": u, "tipo": "gerencia", "valor": "GGE_0025"}
            for u in ("opex_sustaining", "capex_sustaining")]


def test_negacao_legada_de_subpagina_vira_personalizado():
    perms = [{"pagina": "contas", "permitido": False}]
    assert detectar_perfil({"papel": "gerente"}, _manut_escopos(), perms)[0] == "personalizado"
    # sem a negação, continua Manutenção
    assert detectar_perfil({"papel": "gerente"}, _manut_escopos(), [])[0] == "manutencao"


def test_upload_negado_com_capacidade_ligada_vira_personalizado():
    escopos = [{"universo": u, "tipo": "gg", "valor": TODAS} for u in UNIVERSOS_TESTE]
    perms = [{"pagina": "upload", "permitido": False}]
    com = {"papel": "gg", "permissao_upload": True}
    sem = {"papel": "gg", "permissao_upload": False}
    assert detectar_perfil(com, escopos, perms)[0] == "personalizado"
    assert detectar_perfil(sem, escopos, perms)[0] == "gestao_gg"


def test_paginas_visiveis_respeita_negacao_legada():
    p = montar_plano("manutencao", Recorte(), SEM_CAP)
    assert "manutencao_analise_financeira" in paginas_visiveis(p)
    assert "manutencao_analise_financeira" not in paginas_visiveis(p, {"contas": False})
    assert "manutencao_resumo" in paginas_visiveis(p, {"contas": False})


def test_plano_pronto_remove_negacoes_legadas():
    p = montar_plano("manutencao", Recorte(), SEM_CAP)
    assert {"contas", "centro_custo", "resumo_executivo", "capex_painel"} <= set(p.paginas_remover)
    assert not set(p.paginas_remover) & set(p.paginas)  # nunca apaga o que acabou de gravar
