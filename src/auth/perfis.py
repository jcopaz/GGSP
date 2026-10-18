"""Perfis de acesso prontos (docs/13, aprovado pelo usuário em 2026-10-18).

Antes, deixar alguém vendo o que devia exigia passar por 5 lugares da
Administração (papel, capacidades, caixas por página, universo/escopo,
escopos legados) — liberar uma camada e esquecer outra deixava a tela em
branco (caso Sandra). Aqui um PERFIL vira, numa conta só, as mesmas linhas
que o RBAC já lê:

- `app.escopo_acesso` (universo + gg/gerencia/gerencia_obras/elemento_pep),
- `app.permissao_pagina` (só as páginas que fogem do padrão),
- `app.usuario` (papel + 4 capacidades).

Não muda o enforcement (`permissions.py`, `filtros.clausula_escopo*`): o
perfil é só um jeito mais curto e consistente de GRAVAR as mesmas linhas.
Módulo puro (sem Streamlit/Neon) — testável direto.

Regras de página (`montar_plano`):
- Páginas de universo (`UNIVERSO_DA_PAGINA`) gravam `permitido=True` — quem
  decide se aparecem é o universo liberado. Acaba o "liberou o universo mas
  esqueceu a caixa da página".
- `pce_especialista` (default-deny, docs/08 §10) = caixa "Especialista".
- `upload` ("Dados e Qualidade") = capacidade Upload. Antes a página ficava
  visível pra todo usuário logado sem bloqueio explícito, e a capacidade
  "Upload" não era checada em lugar nenhum.
"""
from __future__ import annotations

from dataclasses import dataclass, field

UNIVERSOS = ("opex_sustaining", "capex_sustaining", "capex_obras")

# Página -> universo(s) que ela exige (fonte única; app.py importa daqui).
UNIVERSO_DA_PAGINA: dict[str, frozenset[str]] = {
    "manutencao_resumo": frozenset({"opex_sustaining"}),
    "manutencao_analise_financeira": frozenset({"opex_sustaining", "capex_sustaining"}),
    "rastreabilidade_sap": frozenset({"opex_sustaining"}),
    "obras_resumo": frozenset({"capex_obras"}),
    "capex_contas": frozenset({"capex_obras"}),
    "capex_rastreabilidade": frozenset({"capex_obras"}),
    "pce_especialista": frozenset({"capex_obras"}),
}
PAGINA_ESPECIALISTA = "pce_especialista"
PAGINA_UPLOAD = "upload"
PAGINAS_PERFIL = (*UNIVERSO_DA_PAGINA, PAGINA_UPLOAD)

TITULO_PAGINA = {
    "manutencao_resumo": "Manutenção › Resumo",
    "manutencao_analise_financeira": "Manutenção › Análise Financeira",
    "rastreabilidade_sap": "Manutenção › Evidências SAP",
    "obras_resumo": "Obras › Resumo",
    "capex_contas": "Obras › Nível 4 — Contas",
    "capex_rastreabilidade": "Obras › Rastreabilidade CJI3",
    "pce_especialista": "Obras › CAPEX Obras — Especialista",
    "upload": "Gestão › Dados e Qualidade",
    "administracao": "Gestão › Administração",
}

CAPACIDADES = {
    "permissao_upload": "Upload e reprocessar base",
    "permissao_exportacao": "Download / exportação",
    "permissao_justificativa_macro": "Justificativa macro (Pacote)",
    "permissao_justificativa_micro": "Justificativa micro (Conta/CC)",
}

TODAS = "(todas)"

# Página-jornada consolidada -> sub-páginas antigas que ela absorveu (movido de
# permissions._JORNADA_HERDA_DENY em 2026-10-18, docs/13 N2: o módulo puro
# precisa enxergar as negações legadas). Um `permitido=false` numa delas nega a
# jornada inteira (permissions.can_acessar_pagina). Etapa 3 da Visão Ideal
# (docs/07): "manutencao_resumo" = Resumo Executivo + Painel Executivo + Projeção OPEX.
SUBPAGINAS_LEGADAS: dict[str, tuple[str, ...]] = {
    "manutencao_resumo": ("resumo_executivo", "painel_executivo", "projecao_opex"),
    "obras_resumo": ("capex_resumo", "capex_painel"),
    "manutencao_analise_financeira": (
        "visao_manutencao", "contas", "centro_custo", "opex_capex_manutencao",
    ),
}


@dataclass(frozen=True)
class Perfil:
    rotulo: str
    descricao: str
    papel: str | None  # None = mantém o papel atual (Personalizado)
    capacidades_padrao: dict[str, bool]


_SEM_CAP = {k: False for k in CAPACIDADES}

PERFIS: dict[str, Perfil] = {
    "admin": Perfil(
        "Administrador", "Vê e faz tudo, inclusive a Administração.", "admin",
        {k: True for k in CAPACIDADES},
    ),
    "gestao_gg": Perfil(
        "Gestão GG (consulta)", "Os 3 universos, GG inteira. Só consulta.", "gg",
        {**_SEM_CAP, "permissao_exportacao": True},
    ),
    "manutencao": Perfil(
        "Gerência de Manutenção",
        "Plano de Manutenção (OPEX e CAPEX Sustaining) nas Gerências escolhidas — uma lista só, vale para os dois.",
        "gerente", {**_SEM_CAP, "permissao_exportacao": True, "permissao_justificativa_micro": True},
    ),
    "obras": Perfil(
        "Obras", "Plano de Obras nas Gerências de Obras e/ou Projetos escolhidos.",
        "especialista_analista", {**_SEM_CAP, "permissao_exportacao": True},
    ),
    "sem_acesso": Perfil(
        "Sem acesso", "Entra no app e vê só o aviso \"Sem acesso\". Para bloquear sem desativar o usuário.",
        "especialista_analista", dict(_SEM_CAP),
    ),
    "personalizado": Perfil(
        "Personalizado", "Controles avançados (universo a universo e página a página).", None, dict(_SEM_CAP),
    ),
}


@dataclass(frozen=True)
class Recorte:
    """O que o perfil precisa de dado do usuário. Vazio = "todas" (GG
    inteira / Plano de Obras inteiro)."""
    gerencias: tuple[str, ...] = ()          # gerencia_id (Manutenção)
    gerencias_obras: tuple[str, ...] = ()    # gerencia_obras (nome)
    projetos: tuple[str, ...] = ()           # e_pep_projeto
    especialista: bool = False


@dataclass
class Plano:
    """Linhas a gravar. `escopos[universo]` = [(tipo, valor)]; lista vazia =
    sem acesso àquele universo."""
    papel: str
    escopos: dict[str, list[tuple[str, str]]]
    paginas: dict[str, bool]
    capacidades: dict[str, bool] = field(default_factory=dict)
    # Sub-páginas legadas cujas linhas em app.permissao_pagina o salvar APAGA
    # (perfil pronto limpa as negações antigas — decisão do dono, docs/13 N2).
    paginas_remover: tuple[str, ...] = ()


def _gerencias(tipo: str, valores: tuple[str, ...]) -> list[tuple[str, str]]:
    return [("gg", TODAS)] if not valores else [(tipo, v) for v in sorted(set(valores))]


def montar_plano(
    perfil_id: str, recorte: Recorte, capacidades: dict[str, bool], papel_atual: str | None = None,
) -> Plano:
    """Perfil + recorte + capacidades -> linhas. `personalizado` não passa
    por aqui (os controles avançados gravam direto)."""
    if perfil_id not in PERFIS or perfil_id == "personalizado":
        raise ValueError(f"perfil sem plano automático: {perfil_id!r}")
    vazio: dict[str, list[tuple[str, str]]] = {u: [] for u in UNIVERSOS}
    especialista = recorte.especialista
    if perfil_id in ("admin", "gestao_gg"):
        escopos = {u: [("gg", TODAS)] for u in UNIVERSOS}
        especialista = True if perfil_id == "admin" else especialista
    elif perfil_id == "manutencao":
        linhas = _gerencias("gerencia", recorte.gerencias)
        escopos = {**vazio, "opex_sustaining": list(linhas), "capex_sustaining": list(linhas)}
        especialista = False
    elif perfil_id == "obras":
        if not recorte.gerencias_obras and not recorte.projetos:
            linhas = [("gg", TODAS)]
        else:
            linhas = [("gerencia_obras", v) for v in sorted(set(recorte.gerencias_obras))]
            linhas += [("elemento_pep", v) for v in sorted(set(recorte.projetos))]
        escopos = {**vazio, "capex_obras": linhas}
    else:  # sem_acesso
        escopos = dict(vazio)
        especialista = False

    caps = {k: bool(capacidades.get(k, False)) for k in CAPACIDADES}
    if perfil_id == "admin":
        caps = {k: True for k in CAPACIDADES}
    paginas = {p: True for p in UNIVERSO_DA_PAGINA}
    paginas[PAGINA_ESPECIALISTA] = bool(especialista and escopos["capex_obras"])
    paginas[PAGINA_UPLOAD] = caps["permissao_upload"]
    legadas = tuple(sorted({s for subs in SUBPAGINAS_LEGADAS.values() for s in subs}))
    return Plano(papel=PERFIS[perfil_id].papel or (papel_atual or "especialista_analista"),
                 escopos=escopos, paginas=paginas, capacidades=caps, paginas_remover=legadas)


def detectar_perfil(
    usuario: dict, escopos_universo: list[dict], permissoes: list[dict],
) -> tuple[str, Recorte]:
    """Qual perfil pronto reproduz EXATAMENTE o que está gravado hoje.
    Qualquer coisa fora do molde (ex.: Gerências diferentes entre OPEX e
    CAPEX Sustaining, página de universo negada à mão, Manutenção + Obras)
    -> "personalizado" — nada se perde ao abrir a tela."""
    if usuario.get("papel") == "admin":
        return "admin", Recorte(especialista=True)
    por_uni: dict[str, set[tuple[str, str]]] = {u: set() for u in UNIVERSOS}
    for r in escopos_universo:
        if r.get("universo") in por_uni:
            por_uni[r["universo"]].add((r.get("tipo"), r.get("valor")))
    perms = {r["pagina"]: bool(r["permitido"]) for r in permissoes}
    especialista = perms.get(PAGINA_ESPECIALISTA, False)

    # Página negada à mão num universo que a pessoa TEM -> recorte fino que
    # os perfis não reproduzem. Negação em universo que ela nem tem não
    # muda nada na tela (o universo já esconde) e não conta.
    universos_com_acesso = {u for u, linhas in por_uni.items() if linhas}
    nega_pagina_de_universo = any(
        perms.get(p) is False and (req & universos_com_acesso)
        for p, req in UNIVERSO_DA_PAGINA.items() if p != PAGINA_ESPECIALISTA
    )
    if nega_pagina_de_universo:
        return "personalizado", Recorte()
    # Negação legada de sub-página (contas, centro_custo...) nega a jornada
    # inteira em runtime, mas o molde dos perfis não a reproduz (2026-10-18, N2).
    if any(perms.get(sub) is False for subs in SUBPAGINAS_LEGADAS.values() for sub in subs):
        return "personalizado", Recorte()
    # Upload negado COM a capacidade ligada: o perfil regravaria upload=capacidade
    # e liberaria a página. Sem a capacidade, upload=False é só o que montar_plano grava.
    if perms.get("upload") is False and bool(usuario.get("permissao_upload")):
        return "personalizado", Recorte()

    def eh_gg(linhas: set) -> bool:
        return any(t == "gg" for t, _ in linhas)

    opex, capex, obras = (por_uni[u] for u in UNIVERSOS)
    if not opex and not capex and not obras:
        return "sem_acesso", Recorte()
    if eh_gg(opex) and eh_gg(capex) and eh_gg(obras):
        return "gestao_gg", Recorte(especialista=especialista)
    if opex and opex == capex and not obras:
        if eh_gg(opex):
            return "manutencao", Recorte()
        if all(t == "gerencia" for t, _ in opex):
            return "manutencao", Recorte(gerencias=tuple(sorted(v for _, v in opex)))
    if obras and not opex and not capex:
        if eh_gg(obras):
            return "obras", Recorte(especialista=especialista)
        if all(t in ("gerencia_obras", "elemento_pep") for t, _ in obras):
            return "obras", Recorte(
                gerencias_obras=tuple(sorted(v for t, v in obras if t == "gerencia_obras")),
                projetos=tuple(sorted(v for t, v in obras if t == "elemento_pep")),
                especialista=especialista,
            )
    return "personalizado", Recorte()


def paginas_visiveis(plano: Plano, permissoes_legadas: dict[str, bool] | None = None) -> list[str]:
    """Páginas que a pessoa vai ver com esse plano — mesma regra do menu
    (`app._pagina_se_permitida`): página liberada E algum universo dela.
    `permissoes_legadas`: o que está gravado hoje em app.permissao_pagina;
    sub-página legada com False esconde a página-jornada (mesma regra de
    `can_acessar_pagina`). Perfil pronto passa None: ele apaga essas linhas."""
    if plano.papel == "admin":
        return [*TITULO_PAGINA]
    legadas = permissoes_legadas or {}
    universos = {u for u, linhas in plano.escopos.items() if linhas}
    out = []
    for pagina in PAGINAS_PERFIL:
        if not plano.paginas.get(pagina, False):
            continue
        if any(legadas.get(sub) is False for sub in SUBPAGINAS_LEGADAS.get(pagina, ())):
            continue
        req = UNIVERSO_DA_PAGINA.get(pagina)
        if req and not (req & universos):
            continue
        out.append(pagina)
    return out


def linhas_escopo_para_diagnostico(usuario_id: str, plano: Plano) -> list[dict]:
    """Formato de `administracao.diagnosticar_perfis` — pra checar o recorte
    contra a base ANTES de salvar."""
    return [
        {"usuario_id": usuario_id, "universo": u, "tipo": t, "valor": v}
        for u, linhas in plano.escopos.items() for t, v in linhas
    ]
