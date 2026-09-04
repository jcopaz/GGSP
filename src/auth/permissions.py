"""Verificação de permissões (RBAC) — padrão de guards portado de
MRS Sentinel/Sentinel/auth/permissions.py, adaptado ao domínio do Orçamento.

Matriz de papéis (ver docs/03-processo-justificativas-causas.md, seção 3.1,
e docs/05-publicacao-online-e-seguranca.md):

    Ação                     | Admin | GG | Gerente          | Especialista/Analista
    Ver visão executiva      | sim   | sim| escopo (gerência) | escopo (gerência)
    Fazer upload             | sim   | não| não               | se permissao_upload
    Justificar Macro (Pacote)| sim   | não| não (só ciência)  | se permissao_justificativa_macro
    Justificar Micro (Conta) | sim   | não| não (só ciência)  | se permissao_justificativa_micro
    Exportar dado            | sim   | se permissao_exportacao (default true, todo papel)
    Gerir usuários           | sim   | não| não               | não

Como o painel inteiro já é escopado a uma única GG (GGG_0054, ver
config/settings.yaml), o recorte que importa no dia a dia é `gerencia_id`
(a Gerência dentro dessa GG — Malha SP/VP etc.), não `gg_id`.
"""
from __future__ import annotations

import os

import streamlit as st

from src.auth.session import get_papel, get_usuario, is_logged_in


def is_admin() -> bool:
    return get_papel() == "admin"


def is_gg() -> bool:
    return get_papel() == "gg"


def is_gerente() -> bool:
    return get_papel() == "gerente"


def is_especialista_analista() -> bool:
    return get_papel() == "especialista_analista"


def can_ver_gerencia(gerencia_alvo: str | None) -> bool:
    """Admin e GG veem qualquer Gerência dentro do escopo da GG. Gerente e
    Especialista/Analista só veem a própria."""
    papel = get_papel()
    if papel in ("admin", "gg"):
        return True
    u = get_usuario()
    return bool(u) and u.get("gerencia_id") == gerencia_alvo


def can_fazer_upload() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_upload", False)


def can_exportar() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_exportacao", True)


def can_justificar_macro() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_justificativa_macro", False)


def can_justificar_micro() -> bool:
    if is_admin():
        return True
    u = get_usuario()
    return bool(u) and u.get("permissao_justificativa_micro", False)


def can_administrar_usuarios() -> bool:
    return is_admin()


# ---------------------------------------------------------------------------
# Guards de tela — usar st.stop() no topo de módulos/páginas protegidas.
# ---------------------------------------------------------------------------

def require_login() -> None:
    if not is_logged_in():
        st.error("🔒 Acesso restrito. Faça login para continuar.")
        st.stop()


def require_admin() -> None:
    require_login()
    if not is_admin():
        st.error("🚫 Esta área é restrita a administradores.")
        st.stop()


def require_upload() -> None:
    require_login()
    if not can_fazer_upload():
        st.error("🚫 Você não tem permissão para fazer upload de dados.")
        st.stop()


def require_justificativa_macro() -> None:
    require_login()
    if not can_justificar_macro():
        st.error("🚫 Você não tem permissão para justificar no nível Pacote.")
        st.stop()


def require_justificativa_micro() -> None:
    require_login()
    if not can_justificar_micro():
        st.error("🚫 Você não tem permissão para justificar no nível Conta/Centro de Custo.")
        st.stop()


def _permissoes_pagina_cache(usuario_id: str) -> dict[str, bool]:
    """Busca `app.permissao_pagina` inteira do usuário **1x por sessão**,
    guardada em `st.session_state` — não 1x por página.

    Achado em 2026-08-28 (causa provável de "trocar de página derruba
    pra tela de login"): `can_acessar_pagina` é chamada pra CADA página
    da navegação, EM TODO rerun do Streamlit (o menu inteiro é
    reconstruído a cada clique) — sem cache, isso virava até ~15 conexões
    novas ao Neon por interação (`conectar()` não usa pool, cada chamada
    abre/fecha a própria conexão). Lento o bastante pra estourar timeout
    de infraestrutura no meio do caminho, derrubando a sessão sem a
    permissão em si ter sido negada.

    Cache não invalida sozinho durante a sessão — se um admin mudar a
    permissão de alguém que já está logado, só pega efeito no próximo
    login dessa pessoa. Comportamento aceito de propósito (trade-off
    padrão de cache de permissão), não bug."""
    chave = "_permissoes_pagina_cache"
    if chave not in st.session_state:
        from src.auth.db import buscar_todos

        linhas = buscar_todos(
            "select pagina, permitido from app.permissao_pagina where usuario_id = %s",
            (usuario_id,),
        )
        st.session_state[chave] = {l["pagina"]: bool(l["permitido"]) for l in linhas}
    return st.session_state[chave]


def can_acessar_pagina(pagina: str) -> bool:
    """Permissão por página (app.permissao_pagina) — adicionado em
    2026-08-28 (integração v3.4.0). Admin sempre acessa tudo. Usuário sem
    linha própria pra essa página é permitido por padrão (compatibilidade
    com quem já existia antes desta tabela).

    **Correção de segurança sobre o design original recebido**: se a
    consulta ao Postgres falhar (indisponibilidade, rede), o pacote de
    melhorias trazido pelo usuário devolvia `True` (fail **aberto** —
    todo mundo vê tudo se o banco cair). Isso contradiz o resto do
    projeto, que usa fail closed em ação crítica (ver `require_upload`
    etc. acima). Aqui devolve `False` na falha — nega por padrão, não
    libera. Registrado como decisão em
    docs/06-administracao-auditoria-e-projecao.md.

    `ORCAMENTO_SKIP_LOGIN=1` (bypass de login só local, ver app.py) libera
    tudo aqui também — sem essa saída, o próprio flag de teste local
    ficava inútil: sem usuário real de sessão, toda página seria negada
    (fail closed corretamente, mas contra o propósito do flag, que é
    "sem Neon, mas ainda dá pra olhar o painel"). Nunca fica ligado no
    deploy (mesmo aviso já existente no app.py).

    **`_PAGINAS_ALLOW_EXPLICITO`** (2026-09-04, docs/08 §10 opção B):
    páginas nesse conjunto invertem o default — exigem uma linha
    `permitido=true` explícita em `app.permissao_pagina`. Hoje só
    `pce_especialista` (CAPEX Obras — Especialista, tela densa de
    planejamento). Admin e SKIP_LOGIN continuam vendo."""
    if os.environ.get("ORCAMENTO_SKIP_LOGIN") == "1":
        return True
    if is_admin():
        return True
    u = get_usuario()
    if not u:
        return False
    try:
        permissoes = _permissoes_pagina_cache(u["id"])
        default = pagina not in _PAGINAS_ALLOW_EXPLICITO
        return permissoes.get(pagina, default)
    except Exception:
        return False


def require_acesso_pagina(pagina: str) -> None:
    require_login()
    if not can_acessar_pagina(pagina):
        st.error("🚫 Você não tem permissão para acessar esta página.")
        st.stop()


# ---------------------------------------------------------------------------
# RBAC de escopo por universo financeiro (ver docs/08-rbac-escopo-por-
# universo.md). Duas camadas:
#   1) universo   — pode ver opex_sustaining / capex_sustaining / capex_obras
#   2) escopo     — dentro do universo: GG inteira OU lista de Gerências /
#                   Projetos / Elementos PEP
#
# Fase RBAC-A.1 (2026-09-02): schema + estes helpers + tela de delegação.
# NENHUMA página do painel ainda chama `escopo_universo` pra filtrar dado —
# o enforcement entra página a página na Fase RBAC-A.2, com regressão
# numérica em cada uma (a lição de docs/06 pesa: aplicar escopo sem
# validar contra o schema real de cada consulta arrisca mudar total /
# reconciliação).
# ---------------------------------------------------------------------------

UNIVERSOS = ("opex_sustaining", "capex_sustaining", "capex_obras")

# Páginas que exigem allow EXPLÍCITO em app.permissao_pagina (o default das
# demais é "liberado se não houver linha"). `pce_especialista` (CAPEX Obras
# — Especialista) é tela de planejamento densa (13 versões, forecasts,
# FEL), público diferente da execução CJI3/CJI4 — decisão do usuário
# 2026-09-02, docs/08 §10 opção B. Registrado aqui; o `can_acessar_pagina`
# só passa a usar isso na Fase RBAC-A.2 (não mexe no comportamento atual).
_PAGINAS_ALLOW_EXPLICITO = {"pce_especialista"}


def _escopos_cache(usuario_id: str) -> list[dict]:
    """Todas as linhas de `app.escopo_acesso` do usuário COM universo
    preenchido (as legadas, universo NULL, ficam de fora do enforcement
    novo de propósito) — 1x por sessão, mesmo padrão de
    `_permissoes_pagina_cache`. Não invalida sozinho durante a sessão: se
    o admin mudar o escopo de alguém logado, pega efeito no próximo login
    dessa pessoa (trade-off aceito, igual permissão de página)."""
    chave = "_escopos_acesso_cache"
    if chave not in st.session_state:
        from src.auth.db import buscar_todos

        st.session_state[chave] = buscar_todos(
            "select universo, tipo, valor from app.escopo_acesso "
            "where usuario_id = %s and ativo = true and universo is not null",
            (usuario_id,),
        )
    return st.session_state[chave]


def _resolver_universos_permitidos(linhas: list[dict], eh_admin: bool, tem_usuario: bool) -> set[str]:
    # `not tem_usuario` = contexto sem sessão (script/teste). O recorte de
    # escopo só narra um usuário AUTENTICADO não-admin — quem decide "pode
    # abrir esta página" é o guard de página (`require_acesso_pagina`), que
    # já fail-closa sem usuário. Aqui, sem usuário -> no-op (vê tudo).
    if eh_admin or not tem_usuario:
        return set(UNIVERSOS)
    return {r["universo"] for r in linhas if r.get("universo") in UNIVERSOS}


def _resolver_escopo_universo(
    universo: str, linhas: list[dict], eh_admin: bool, tem_usuario: bool
) -> tuple[bool, bool, list[str]]:
    """(tem_acesso, tudo, alvos). Função pura — testável sem Streamlit.
    `not tem_usuario` = contexto sem sessão (script/teste) -> no-op
    (`True, True, []`), o guard de página é quem fail-closa sem usuário."""
    if eh_admin or not tem_usuario:
        return True, True, []
    rel = [r for r in linhas if r.get("universo") == universo]
    if not rel:
        return False, False, []
    if any(r.get("tipo") == "gg" for r in rel):
        return True, True, []
    alvos = sorted({r["valor"] for r in rel if r.get("valor")})
    return bool(alvos), False, alvos


def _resolver_alvos_por_tipo(
    universo: str, linhas: list[dict], eh_admin: bool, tem_usuario: bool
) -> dict[str, list[str]]:
    """{tipo: [valores]} do usuário nesse universo. `{"gg": ["(todas)"]}`
    = vê o universo inteiro (admin ou linha tipo 'gg'). `{}` = sem grant.
    Usado por `capex_obras`, onde os alvos podem ser de 2 tipos ao mesmo
    tempo (`gerencia_obras` + `elemento_pep`) — `escopo_universo` achata
    tudo numa lista só e não serve pra montar o WHERE."""
    # `not tem_usuario` (script/teste) -> no-op, igual `_resolver_escopo_universo`.
    if eh_admin or not tem_usuario:
        return {"gg": ["(todas)"]}
    rel = [r for r in linhas if r.get("universo") == universo]
    if any(r.get("tipo") == "gg" for r in rel):
        return {"gg": ["(todas)"]}
    out: dict[str, list[str]] = {}
    for r in rel:
        tipo, valor = r.get("tipo"), r.get("valor")
        if tipo and valor:
            out.setdefault(tipo, []).append(valor)
    return {k: sorted(set(v)) for k, v in out.items()}


def escopo_alvos_por_tipo(universo: str, usuario: dict | None = None) -> dict[str, list[str]]:
    """Ver `_resolver_alvos_por_tipo`. `admin` / `ORCAMENTO_SKIP_LOGIN=1` ->
    `{"gg": ["(todas)"]}`. Fail closed: erro -> `{}`."""
    if os.environ.get("ORCAMENTO_SKIP_LOGIN") == "1":
        return {"gg": ["(todas)"]}
    try:
        u = usuario or get_usuario()
        linhas = _escopos_cache(u["id"]) if u else []
        return _resolver_alvos_por_tipo(universo, linhas, is_admin(), bool(u))
    except Exception:
        return {}


def universos_permitidos(usuario: dict | None = None) -> set[str]:
    """1ª camada: universos financeiros que o usuário pode ver. `admin` e
    `ORCAMENTO_SKIP_LOGIN=1` veem os 3; `gg` NÃO é bypass. Fail closed:
    qualquer erro (banco fora, sessão inexistente) -> conjunto vazio."""
    if os.environ.get("ORCAMENTO_SKIP_LOGIN") == "1":
        return set(UNIVERSOS)
    try:
        u = usuario or get_usuario()
        linhas = _escopos_cache(u["id"]) if u else []
        return _resolver_universos_permitidos(linhas, is_admin(), bool(u))
    except Exception:
        return set()


def require_universo(universo: str) -> None:
    """Barra a página se o usuário não tem acesso ao universo financeiro
    (1ª camada do RBAC de escopo — docs/08). Usar no topo da função da
    página/painel, depois do `render_page_banner`. Admin / SKIP_LOGIN
    passam. Fase RBAC-A.2."""
    tem_acesso, _tudo, _alvos = escopo_universo(universo)
    if not tem_acesso:
        st.error(
            "🚫 Você não tem acesso a este universo financeiro. "
            "Fale com o administrador para liberar."
        )
        st.stop()


def escopo_universo(universo: str, usuario: dict | None = None) -> tuple[bool, bool, list[str]]:
    """2ª camada: `(tem_acesso, tudo, alvos)` do usuário nesse universo.
    - tem_acesso=False -> sem grant, não vê nada nesse universo
    - tudo=True        -> nível 'gg', vê o universo inteiro
    - alvos=[...]      -> recorte: gerencia_id / gerencia_obras /
                          e_pep_projeto / elemento_pep (união das linhas)
    `admin` / `ORCAMENTO_SKIP_LOGIN=1` -> (True, True, []). Fail closed."""
    if os.environ.get("ORCAMENTO_SKIP_LOGIN") == "1":
        return True, True, []
    try:
        u = usuario or get_usuario()
        linhas = _escopos_cache(u["id"]) if u else []
        return _resolver_escopo_universo(universo, linhas, is_admin(), bool(u))
    except Exception:
        return False, False, []
