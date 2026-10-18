"""Administração de usuários, escopos e auditoria do Fin360."""
from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import psycopg2
import streamlit as st

from src.branding import render_page_banner
from src.auth.perfis import (
    CAPACIDADES, PERFIS, TITULO_PAGINA, Recorte, detectar_perfil,
    Plano, linhas_escopo_para_diagnostico, montar_plano, paginas_visiveis,
)
from src.auth.permissions import _PAGINAS_ALLOW_EXPLICITO, require_admin
from src.auth.session import get_id
from src.auth.queries import criar_usuario
from src.auth.senha import gerar_hash, gerar_senha_temporaria
from src.auth.admin_queries import *
from src.auth.audit import registrar_atividade
from src.config import carregar_config
from src.ingestion.arquivo_bruto import restaurar_versao_arquivo
from src.model.build_star_schema import build_star_schema

# "visao_opex"/"capex_manutencao" viraram 1 chave só ("opex_capex_manutencao")
# em 2026-08-29; "resumo_executivo"/"painel_executivo"/"projecao_opex"
# viraram "manutencao_resumo" na Etapa 3 da Visão Ideal (2026-09-05, ver
# app.py::pagina_manutencao_resumo). Linhas antigas em app.permissao_pagina
# com as chaves substituídas ficam órfãs (inofensivas — não são mais lidas
# por can_acessar_pagina, exceto pelo _JORNADA_HERDA_DENY, que usa um
# `permitido=false` antigo pra negar a jornada nova). Não precisa migração.
PAGINAS = ["manutencao_resumo","manutencao_analise_financeira","rastreabilidade_sap","obras_resumo","capex_contas","capex_rastreabilidade","pce_especialista","upload","administracao"]

# Tipos de escopo com uma dimensão real no warehouse pra virar dropdown.
# Revisado 2026-08-29 a pedido do usuário:
# - "coordenacao" removido da lista — Centro de Custo já cobre a mesma
#   granularidade (cada Gerência/Coordenação tem um Centro de Custo),
#   então mantinhamos duas listas pro mesmo recorte de negócio sem
#   necessidade.
# - "elemento_pep"/"pep_filho" (universo CAPEX Obras) deixam de ser texto
#   livre: a suposição anterior ("pep_filho nem é campo que a fonte tem
#   hoje") estava ERRADA — existe sim, é a coluna "Título" do "Catalago
#   CAPEX Obras.xlsx" (aba Auxiliar), confirmado no dado real (2795
#   linhas, 95 Elemento PEP, "Título" nunca nulo e nunca repetido entre
#   Elemento PEP diferentes). Ver `dim_catalogo_capex_obras`
#   (build_star_schema.py) e docs/04-licoes-aprendidas.md.
# - "projeto" continua texto livre — não faz parte do universo CAPEX
#   Obras descrito pelo usuário, sem catálogo fechado identificado.
# - NOVO tipo "gerencia_obras", separado de "gerencia": conferido no dado
#   real (2026-08-29) que são DUAS taxonomias diferentes, sem ID em
#   comum — "gerencia" é o órgão SAP de Manutenção/OPEX (`dim_gerencia`,
#   ex. "GER ENGENHARIA EMPREEND (SP)"); "gerencia_obras" é o recorte
#   regional do Catálogo CAPEX Obras (só 5 valores: Baixada Santista,
#   Corredor São Paulo, Expansão, Mobilidade Urbana, Obras Ferroviárias
#   — sem código próprio, só o nome). O exemplo do usuário
#   ("Tipo: Gerência → Baixada Santista") é este segundo tipo, não o
#   primeiro — misturar os dois num "gerencia" só ia esconder que são
#   catálogos diferentes.
#
# Semântica de negócio do CAPEX Obras (cascata, confirmada pelo usuário
# 2026-08-29 — só o CADASTRO do escopo está pronto aqui; a APLICAÇÃO
# desse filtro nas telas do painel ainda não existe, ver nota em
# render_administracao):
#   Gerência (Obras) ⊃ todos os Elemento PEP e PEP Filho daquela região
#   Elemento PEP     ⊃ todos os PEP Filho (etapas) daquele projeto
#   PEP Filho        = só aquela etapa/subconta específica
_TIPOS_ESCOPO_SELECIONAVEL = {"gerencia", "gerencia_obras", "pacote", "centro_custo", "elemento_pep", "pep_filho"}
TIPOS_ESCOPO = ["gerencia", "gerencia_obras", "elemento_pep", "pep_filho", "centro_custo", "pacote", "projeto"]
_ROTULO_TIPO_ESCOPO = {
    "gerencia": "Gerência (Manutenção/OPEX)",
    "gerencia_obras": "Gerência (CAPEX Obras)",
    "elemento_pep": "PEP (Elemento PEP)",
    "pep_filho": "PEP Filho",
    "centro_custo": "Centro de Custo",
    "pacote": "Pacote",
    "projeto": "Projeto",
}

_FUSO_BR = ZoneInfo("America/Sao_Paulo")


def _fmt_hora_br(valor) -> str:
    """`timestamptz` do Postgres pro fuso de Brasília/SP — pedido do
    usuário em 2026-08-28: auditoria tem que refletir hora local, não UTC.
    psycopg2 devolve `timestamptz` já como datetime; se vier sem tzinfo
    (alguns drivers/config devolvem naive), assume UTC antes de converter
    (é o que o Postgres guarda por baixo) — nunca assume já estar em BR."""
    if valor is None or pd.isna(valor):
        return ""
    if getattr(valor, "tzinfo", None) is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(_FUSO_BR).strftime("%d/%m/%Y %H:%M")


def _com_hora_br(df: pd.DataFrame, coluna: str = "criado_em") -> pd.DataFrame:
    if df.empty or coluna not in df.columns:
        return df
    df = df.copy()
    df[coluna] = df[coluna].map(_fmt_hora_br)
    return df


def _listar_gerencias(con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    if con is None:
        return []
    try:
        df = con.execute(
            "SELECT DISTINCT gerencia_id, gerencia_nome FROM dim_gerencia "
            "WHERE gerencia_id IS NOT NULL ORDER BY gerencia_nome"
        ).df()
        return list(zip(df["gerencia_id"], df["gerencia_nome"].fillna("")))
    except Exception:
        return []


def _listar_pacotes(con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    if con is None:
        return []
    try:
        df = con.execute(
            "SELECT DISTINCT pacote_id, nome_pacote FROM dim_pacote "
            "WHERE pacote_id IS NOT NULL ORDER BY pacote_id"
        ).df()
        return list(zip(df["pacote_id"], df["nome_pacote"].fillna("")))
    except Exception:
        return []


def _listar_centros_custo(con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    if con is None:
        return []
    try:
        df = con.execute(
            "SELECT DISTINCT centro_custo_id, centro_custo_nome FROM fact_realizado "
            "WHERE centro_custo_id IS NOT NULL ORDER BY centro_custo_id"
        ).df()
        return list(zip(df["centro_custo_id"], df["centro_custo_nome"].fillna("")))
    except Exception:
        return []


def _listar_gerencias_obras(con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    """Gerência do universo CAPEX Obras (recorte regional, ex. "Baixada
    Santista") — catálogo próprio, sem código, só nome. NÃO é a mesma
    lista de `_listar_gerencias` (órgão SAP de Manutenção/OPEX)."""
    if con is None:
        return []
    try:
        df = con.execute(
            "SELECT DISTINCT gerencia_obras FROM dim_catalogo_capex_obras "
            "WHERE gerencia_obras IS NOT NULL ORDER BY gerencia_obras"
        ).df()
        return [(v, v) for v in df["gerencia_obras"]]
    except Exception:
        return []


def _listar_elemento_pep(con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    """"PEP" no vocabulário do usuário — 1 linha por Elemento PEP (projeto),
    ex.: `("DM/21973", "Pátio Regulador Jurubatuba")`. Escopo nesse tipo
    abrange (em cascata, quando a aplicação do filtro existir — ver nota
    em render_administracao) todos os PEP Filho daquele projeto."""
    if con is None:
        return []
    try:
        df = con.execute(
            "SELECT DISTINCT e_pep_projeto, nome_empreendimento "
            "FROM dim_catalogo_capex_obras "
            "WHERE e_pep_projeto IS NOT NULL ORDER BY e_pep_projeto"
        ).df()
        return list(zip(df["e_pep_projeto"], df["nome_empreendimento"].fillna("")))
    except Exception:
        return []


def _listar_pep_filho(con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    """"PEP Filho" — a etapa/subconta específica do cronograma, ex.:
    `("DM/21973C-04", "Projeto básico")`. Confirmado no dado real
    (2026-08-29): "Título" nunca se repete entre Elemento PEP diferentes,
    então o código sozinho já identifica a etapa sem ambiguidade."""
    if con is None:
        return []
    try:
        df = con.execute(
            "SELECT DISTINCT titulo_etapa, descricao_etapa "
            "FROM dim_catalogo_capex_obras "
            "WHERE titulo_etapa IS NOT NULL ORDER BY titulo_etapa"
        ).df()
        # `descricao_etapa` vem da fonte com espaço fixo à direita
        # (largura de coluna do Excel original) — sem strip, o rótulo do
        # multiselect ("DM/21973C-04 — Projeto básico          ") fica
        # com um rastro em branco estranho antes da próxima opção.
        return list(zip(df["titulo_etapa"], df["descricao_etapa"].fillna("").str.strip()))
    except Exception:
        return []


def _opcoes_escopo(tipo: str, con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    return {
        "gerencia": _listar_gerencias,
        "gerencia_obras": _listar_gerencias_obras,
        "pacote": _listar_pacotes,
        "centro_custo": _listar_centros_custo,
        "elemento_pep": _listar_elemento_pep,
        "pep_filho": _listar_pep_filho,
    }.get(tipo, lambda _c: [])(con)


# RBAC de escopo por universo (docs/08). Rótulos e helper da tela de
# delegação. NENHUMA página aplica isso ainda — Fase RBAC-A.2.
_UNIVERSOS_ROTULO = {
    "opex_sustaining": "OPEX Sustaining (Manutenção Corrente)",
    "capex_sustaining": "CAPEX Sustaining (Malha / Infra)",
    "capex_obras": "CAPEX Plano de Obras",
}


def _multiselect_escopo(rotulo, opcoes, linhas_uni, tipo, *, key):
    """multiselect (cód — nome) pré-marcado com o que já está gravado pra
    esse `tipo`. Devolve lista de (cód, nome). Sem base processada
    (`opcoes` vazio) cai pra text_input separado por vírgula."""
    ja = [r["valor"] for r in linhas_uni if r["tipo"] == tipo]
    if not opcoes:
        bruto = st.text_input(
            f"{rotulo} — base não processada, digite os códigos separados por vírgula",
            value=", ".join(ja), key=key + "-txt",
        )
        return [(c.strip(), "") for c in bruto.split(",") if c.strip()]
    rot = {(f"{c} — {n}" if n else c): (c, n) for c, n in opcoes}
    inv = {c: lbl for lbl, (c, _n) in rot.items()}
    default = [inv[c] for c in ja if c in inv]
    escolhidos = st.multiselect(rotulo, list(rot), default=default, key=key)
    return [rot[e] for e in escolhidos]


def _render_acesso_por_universo(
    u: dict, con: duckdb.DuckDBPyConnection | None, atuais: list[dict], perms: dict[str, bool],
) -> tuple[dict[str, list[tuple[str, str, str]]], bool, bool]:
    """1ª camada (vê o universo?) + 2ª camada (GG inteira x Gerências) do
    RBAC de escopo. Só DESENHA os controles e devolve `(escopos,
    ve_especialista, ok)` — quem grava é o botão único do modo Personalizado
    (`_render_perfil_acesso`, gravação atômica, docs/13 N3 — 2026-10-18).
    `atuais`/`perms` já vêm lidos do Neon (N1: esta função não consulta
    sozinha). `ok=False` = universo em "Gerências específicas" sem nenhuma
    escolhida (gravaria lista vazia e tiraria o universo calado)."""
    uid = str(u["id"])
    por_uni: dict[str, list[dict]] = {}
    for r in atuais:
        por_uni.setdefault(r["universo"], []).append(r)

    st.markdown("**Acesso por universo financeiro (avançado)**")
    st.caption(
        "Universo a universo: quais a pessoa vê e, em cada um, GG inteira ou "
        "Gerências específicas. As telas já aplicam esse recorte (docs/08)."
    )

    gers_sust = _listar_gerencias(con)
    gers_obras = _listar_gerencias_obras(con)
    projetos = _listar_elemento_pep(con)
    esp_atual = perms.get("pce_especialista", False)

    plano: dict[str, list[tuple[str, str, str]]] = {}
    ve_especialista = bool(esp_atual)
    ok = True
    for universo in ("opex_sustaining", "capex_sustaining", "capex_obras"):
        linhas_uni = por_uni.get(universo, [])
        tem = len(linhas_uni) > 0
        tem_gg = any(r["tipo"] == "gg" for r in linhas_uni)
        with st.container(border=True):
            on = st.checkbox(
                f"Vê {_UNIVERSOS_ROTULO[universo]}", value=tem,
                key=f"uni-{uid}-{universo}-on",
            )
            linhas_novas: list[tuple[str, str, str]] = []
            if on:
                abr = st.radio(
                    "Abrangência", ["GG inteira", "Gerências específicas"],
                    index=0 if (tem_gg or not tem) else 1,
                    horizontal=True, key=f"uni-{uid}-{universo}-abr",
                )
                if abr == "GG inteira":
                    linhas_novas.append(("gg", "(todas)", ""))
                elif universo == "capex_obras":
                    linhas_novas += [
                        ("gerencia_obras", v, n) for v, n in _multiselect_escopo(
                            "Gerências de Obras", gers_obras, linhas_uni,
                            "gerencia_obras", key=f"uni-{uid}-{universo}-ger")
                    ]
                    linhas_novas += [
                        ("elemento_pep", v, n) for v, n in _multiselect_escopo(
                            "Projetos (Elemento PEP) — opcional", projetos, linhas_uni,
                            "elemento_pep", key=f"uni-{uid}-{universo}-proj")
                    ]
                else:
                    linhas_novas += [
                        ("gerencia", v, n) for v, n in _multiselect_escopo(
                            "Gerências", gers_sust, linhas_uni,
                            "gerencia", key=f"uni-{uid}-{universo}-ger")
                    ]
                if abr != "GG inteira" and not linhas_novas:
                    ok = False
                    st.error(
                        f"{_UNIVERSOS_ROTULO[universo]}: escolha ao menos uma opção, "
                        "ou marque \"GG inteira\" (senão o universo seria removido)."
                    )
            if universo == "capex_obras":
                marcado = st.checkbox(
                    "Vê a tela CAPEX Obras — Especialista (planejamento PCE)",
                    value=bool(esp_atual), disabled=not on,
                    key=f"uni-{uid}-{universo}-esp",
                    help="Tela densa de planejamento (13 versões, forecasts, FEL). Opção B do docs/08 §10.",
                )
                ve_especialista = bool(on and marcado)
            plano[universo] = linhas_novas

    return plano, ve_especialista, ok


# Tipos que o filtro de cada universo de fato entende (filtros.py:
# clausula_escopo usa gerencia_id; clausula_escopo_obras usa gerencia_obras
# / e_pep_projeto). Escopo com outro tipo libera o menu mas filtra 0 linha.
_TIPOS_VALIDOS_UNIVERSO = {
    "opex_sustaining": {"gg", "gerencia"},
    "capex_sustaining": {"gg", "gerencia"},
    "capex_obras": {"gg", "gerencia_obras", "elemento_pep"},
}
_ROTULO_UNIVERSO = {
    "opex_sustaining": "OPEX Sustaining",
    "capex_sustaining": "CAPEX Sustaining",
    "capex_obras": "CAPEX Obras",
}


def _valores_existentes_na_base(con: duckdb.DuckDBPyConnection | None) -> dict[str, set[str]] | None:
    """{tipo: valores reais na base} pra checar escopo apontando pra código
    inexistente. None se a base não está disponível (pula essa checagem)."""
    if con is None:
        return None
    consultas = {
        "gerencia": "SELECT DISTINCT gerencia_id FROM dim_gerencia",
        "gerencia_obras": "SELECT DISTINCT gerencia_obras FROM fact_cji4_capex_obras "
                          "UNION SELECT DISTINCT gerencia_obras FROM fact_cji3_capex_obras",
        "elemento_pep": "SELECT DISTINCT e_pep_projeto FROM fact_cji4_capex_obras "
                        "UNION SELECT DISTINCT e_pep_projeto FROM fact_cji3_capex_obras",
    }
    out: dict[str, set[str]] = {}
    for tipo, sql in consultas.items():
        try:
            out[tipo] = {str(r[0]) for r in con.execute(sql).fetchall() if r[0] is not None}
        except Exception:
            pass  # tabela ausente — essa checagem é pulada pra esse tipo
    return out


def diagnosticar_perfis(
    usuarios: list[dict], escopos: list[dict], valores_base: dict[str, set[str]] | None
) -> list[dict]:
    """Função pura (testável sem Streamlit/Neon). Para cada usuário ATIVO
    não-admin, lista os motivos pelos quais ele pode abrir o app e não ver
    dado nenhum — o caso da Sandra (2026-10-04): menu lateral visível e
    tela em branco até liberar todas as camadas."""
    por_usuario: dict[str, list[dict]] = {}
    for e in escopos:
        por_usuario.setdefault(str(e["usuario_id"]), []).append(e)

    problemas: list[dict] = []
    for u in usuarios:
        if not u.get("ativo") or u.get("papel") == "admin":
            continue
        linhas = por_usuario.get(str(u["id"]), [])
        com_universo = [l for l in linhas if l.get("universo")]
        motivos: list[str] = []
        if not com_universo:
            if linhas:
                motivos.append("só tem escopos legados (sem universo) — eles não liberam nada hoje")
            else:
                motivos.append("nenhum universo liberado — vê só a tela 'Sem acesso'")
        for universo, validos in _TIPOS_VALIDOS_UNIVERSO.items():
            rel = [l for l in com_universo if l["universo"] == universo]
            if not rel or any(l["tipo"] == "gg" for l in rel):
                continue
            rotulo = _ROTULO_UNIVERSO[universo]
            invalidos = sorted({l["tipo"] for l in rel if l["tipo"] not in validos})
            if invalidos:
                motivos.append(f"{rotulo}: tipo de escopo {', '.join(invalidos)} não é filtrável nesse universo")
            if valores_base is not None:
                for l in rel:
                    tipo_ref = "gerencia" if universo != "capex_obras" else l["tipo"]
                    base = valores_base.get(tipo_ref)
                    if base is not None and l["tipo"] in validos and str(l["valor"]) not in base:
                        motivos.append(f"{rotulo}: '{l['valor']}' não existe na base atual")
        if motivos:
            problemas.append({
                "Usuário": u.get("nome_completo"),
                "Papel": u.get("papel"),
                "Problema": " · ".join(motivos),
            })
    return problemas


def _render_diagnostico_perfis(con: duckdb.DuckDBPyConnection | None) -> None:
    try:
        problemas = diagnosticar_perfis(
            listar_usuarios(), listar_escopos_todos_ativos(), _valores_existentes_na_base(con)
        )
    except Exception as exc:
        st.caption(f"⚠️ Não consegui rodar o diagnóstico de perfis: {exc}")
        return
    if not problemas:
        st.success("✅ Todos os usuários ativos têm universo e escopo que alcançam dados.")
        return
    st.warning(
        f"⚠️ {len(problemas)} usuário(s) ativo(s) podem entrar no app e não ver dado nenhum. "
        "Ajuste em **Acesso por universo** abaixo. Lembre: a mudança só vale "
        "depois que a pessoa sair e entrar de novo."
    )
    st.dataframe(pd.DataFrame(problemas), hide_index=True, use_container_width=True)


# ===== Perfil de acesso (docs/13, 2026-10-18) =====
_ORDEM_PERFIS = ("gestao_gg", "manutencao", "obras", "sem_acesso", "admin", "personalizado")


def _multiselect_codigos(rotulo: str, opcoes: list[tuple[str, str]], selecionados, *, key: str) -> list[str]:
    """multiselect "cód — nome" -> lista de códigos. Sem base processada
    (`opcoes` vazio), cai pra texto separado por vírgula."""
    if not opcoes:
        bruto = st.text_input(
            f"{rotulo} — base não processada, digite os códigos separados por vírgula",
            value=", ".join(selecionados), key=key + "-txt",
        )
        return [c.strip() for c in bruto.split(",") if c.strip()]
    rot = {(f"{c} — {n}" if n else c): c for c, n in opcoes}
    inv = {c: lbl for lbl, c in rot.items()}
    escolhidos = st.multiselect(rotulo, list(rot), default=[inv[c] for c in selecionados if c in inv], key=key)
    return [rot[e] for e in escolhidos]


def _render_paginas_avancado(u: dict, atuais: dict[str, bool]) -> dict[str, bool]:
    """Caixas por página (modo Personalizado). Só servem pra NEGAR uma
    página específica — quem libera é o universo. Só desenha e devolve as
    escolhas (o botão único está em `_render_perfil_acesso`, docs/13 N3).
    Ficam de fora `administracao`, `pce_especialista` (dono: caixa
    Especialista do universo) e `upload` (dono: capacidade Upload)."""
    st.markdown("**Páginas (avançado)**")
    st.caption("Desmarque para esconder uma página específica. Página de um universo que a pessoa não tem já fica escondida de qualquer jeito.")
    cols = st.columns(3)
    escolhas = {
        p: cols[i % 3].checkbox(
            TITULO_PAGINA.get(p, p.replace("_", " ").title()),
            value=atuais.get(p, p not in _PAGINAS_ALLOW_EXPLICITO), key=f"perm-{u['id']}-{p}",
        )
        for i, p in enumerate(p for p in PAGINAS if p not in ("administracao", "pce_especialista", "upload"))
    }
    return escolhas


def _texto_recorte(perfil: str, recorte: Recorte, nomes: dict[str, str]) -> str:
    def _n(v: str) -> str:
        return nomes.get(v) or v
    if perfil == "manutencao":
        return "Gerências: " + (", ".join(_n(g) for g in recorte.gerencias) if recorte.gerencias else "todas (GG inteira)")
    if perfil == "obras":
        partes = []
        if recorte.gerencias_obras:
            partes.append("Gerências de Obras: " + ", ".join(recorte.gerencias_obras))
        if recorte.projetos:
            partes.append("Projetos: " + ", ".join(_n(p) for p in recorte.projetos))
        return " · ".join(partes) or "todo o Plano de Obras"
    if perfil in ("gestao_gg", "admin"):
        return "GG inteira, os 3 universos"
    return "nenhum dado"


def _render_perfil_acesso(u: dict, con: duckdb.DuckDBPyConnection | None) -> None:
    """Tela única: perfil -> recorte -> capacidades -> prévia -> 1 botão.
    Grava as MESMAS linhas que o RBAC já lê (`perfis.montar_plano`), numa
    transação só (`salvar_perfil_acesso`)."""
    uid = str(u["id"])
    # N1 (docs/13, 2026-10-18): lê UMA vez e, se falhar, NÃO desenha nada —
    # tratar erro como "lista vazia" mostrava "Sem acesso" e o Salvar apagava
    # o acesso real da pessoa.
    try:
        escopos_atuais = listar_escopos_universo(u["id"])
        perms_atuais = listar_permissoes(u["id"])
    except Exception as exc:
        st.error(
            f"Não consegui ler o acesso atual de {u['nome_completo']} no banco — a tela "
            "não mostra nem salva nada, para não apagar o acesso real. "
            f"Tente de novo. Detalhe: {exc}"
        )
        return
    perms = {r["pagina"]: bool(r["permitido"]) for r in perms_atuais}
    atual, recorte_atual = detectar_perfil(u, escopos_atuais, perms_atuais)

    st.markdown("**Perfil de acesso**")
    st.caption(f"Perfil atual de {u['nome_completo']}: **{PERFIS[atual].rotulo}**")
    perfil = st.radio(
        "Perfil", _ORDEM_PERFIS, index=_ORDEM_PERFIS.index(atual),
        format_func=lambda p: PERFIS[p].rotulo, horizontal=True, key=f"perfil-{uid}",
    )
    st.caption(PERFIS[perfil].descricao)
    mesmo = perfil == atual
    rec = recorte_atual if mesmo else Recorte()

    nomes: dict[str, str] = {}
    recorte = Recorte()
    recorte_ok = True
    escopos_pers: dict[str, list[tuple[str, str, str]]] = {}
    ve_esp_pers = False
    escolhas_pers: dict[str, bool] = {}
    if perfil == "manutencao":
        gers = _listar_gerencias(con)
        nomes.update(dict(gers))
        todas = st.checkbox("Todas as Gerências (GG inteira)", value=not rec.gerencias, key=f"perfil-{uid}-man-todas")
        sel: list[str] = []
        if not todas:
            sel = _multiselect_codigos("Gerências", gers, rec.gerencias, key=f"perfil-{uid}-man-ger")
            recorte_ok = bool(sel)
        recorte = Recorte(gerencias=tuple(sel))
    elif perfil == "obras":
        gers_obras = _listar_gerencias_obras(con)
        projetos = _listar_elemento_pep(con)
        nomes.update(dict(projetos))
        todo = st.checkbox(
            "Todo o Plano de Obras", value=not (rec.gerencias_obras or rec.projetos), key=f"perfil-{uid}-obr-todo",
        )
        sel_g: list[str] = []
        sel_p: list[str] = []
        if not todo:
            sel_g = _multiselect_codigos("Gerências de Obras", gers_obras, rec.gerencias_obras, key=f"perfil-{uid}-obr-ger")
            sel_p = _multiselect_codigos("Projetos (Elemento PEP)", projetos, rec.projetos, key=f"perfil-{uid}-obr-proj")
            recorte_ok = bool(sel_g or sel_p)
        esp = st.checkbox(
            "Inclui a tela CAPEX Obras — Especialista (planejamento PCE)", value=rec.especialista,
            key=f"perfil-{uid}-obr-esp",
        )
        recorte = Recorte(gerencias_obras=tuple(sel_g), projetos=tuple(sel_p), especialista=esp)
    elif perfil == "gestao_gg":
        esp = st.checkbox(
            "Inclui a tela CAPEX Obras — Especialista (planejamento PCE)", value=rec.especialista,
            key=f"perfil-{uid}-gg-esp",
        )
        recorte = Recorte(especialista=esp)
    elif perfil == "personalizado":
        with st.container(border=True):
            st.caption(
                "Modo avançado — para quem não cabe nos perfis prontos (ex.: Manutenção e "
                "Obras ao mesmo tempo, ou Gerências diferentes entre OPEX e CAPEX)."
            )
            escopos_pers, ve_esp_pers, recorte_ok = _render_acesso_por_universo(
                u, con, escopos_atuais, perms)
            st.divider()
            escolhas_pers = _render_paginas_avancado(u, perms)
    if perfil != "personalizado" and not recorte_ok:
        st.error("Escolha ao menos uma opção, ou marque a opção \"todas\".")

    st.markdown("**Capacidades**")
    base_caps = (
        {k: bool(u.get(k)) for k in CAPACIDADES}
        if (mesmo or perfil == "personalizado") else PERFIS[perfil].capacidades_padrao
    )
    cols = st.columns(len(CAPACIDADES))
    caps = {
        k: cols[i].checkbox(rot, value=True if perfil == "admin" else base_caps.get(k, False),
                            disabled=perfil == "admin", key=f"perfil-{uid}-{perfil}-cap-{k}")
        for i, (k, rot) in enumerate(CAPACIDADES.items())
    }
    if not caps["permissao_upload"]:
        st.caption("Sem Upload, a página Dados e Qualidade não aparece.")

    proprio_admin = str(get_id() or "") == uid and perfil != "admin"
    if proprio_admin:
        st.warning("Você está editando o seu próprio acesso: sair do perfil Administrador tiraria a Administração de você. Escolha outro usuário ou mantenha Administrador.")

    if perfil == "personalizado":
        # N3: gravação única e atômica. Upload e Especialista têm dono próprio
        # (capacidade / caixa do universo), igual ao montar_plano.
        paginas_pers = {**escolhas_pers, "pce_especialista": ve_esp_pers,
                        "upload": caps["permissao_upload"]}
        plano = Plano(
            papel=u["papel"],
            escopos={uni: [(t, v) for t, v, _n in linhas] for uni, linhas in escopos_pers.items()},
            paginas=paginas_pers, capacidades=caps,
        )
        _render_previa(u, plano, perfil, Recorte(), {}, con, perms)
        if st.button("Salvar perfil de acesso", type="primary", key=f"perfil-{uid}-salvar",
                     disabled=not recorte_ok or proprio_admin):
            try:
                salvar_perfil_acesso(u["id"], u.get("papel"), caps, escopos_pers, paginas_pers)
            except Exception as exc:
                st.error(f"Não consegui salvar — nada foi alterado. Detalhe: {exc}")
                return
            registrar_atividade("salvar_perfil_acesso", "administracao", {
                "usuario_id": uid, "perfil": "personalizado", "papel": u.get("papel"),
                "escopos": {k: [f"{t}:{v}" for t, v, _n in vs] for k, vs in escopos_pers.items()},
                "paginas": paginas_pers, "capacidades": caps,
            })
            st.success("Perfil \"Personalizado\" salvo. Vale para a pessoa em até 1 minuto, sem novo login.")
        return

    plano = montar_plano(perfil, recorte, caps, u.get("papel"))
    _render_previa(u, plano, perfil, recorte, nomes, con, None)
    removidas = [s for s in plano.paginas_remover if perms.get(s) is False]
    if removidas:
        st.warning(
            f"Ao salvar, as negações antigas ({', '.join(removidas)}) deste usuário serão removidas."
        )

    if st.button("Salvar perfil de acesso", type="primary", key=f"perfil-{uid}-salvar",
                 disabled=not recorte_ok or proprio_admin):
        escopos = {
            universo: [(t, v, nomes.get(v, "")) for t, v in linhas]
            for universo, linhas in plano.escopos.items()
        }
        try:
            salvar_perfil_acesso(u["id"], plano.papel, plano.capacidades, escopos, plano.paginas,
                                 paginas_remover=plano.paginas_remover)
        except Exception as exc:
            st.error(f"Não consegui salvar — nada foi alterado. Detalhe: {exc}")
            return
        registrar_atividade("salvar_perfil_acesso", "administracao", {
            "usuario_id": uid, "perfil": perfil, "papel": plano.papel,
            "escopos": {k: [f"{t}:{v}" for t, v in vs] for k, vs in plano.escopos.items()},
            "paginas": plano.paginas, "capacidades": plano.capacidades,
            "negacoes_removidas": removidas,
        })
        st.success(f"Perfil \"{PERFIS[perfil].rotulo}\" salvo. Vale para a pessoa em até 1 minuto, sem novo login.")


def _render_previa(u, plano, perfil, recorte, nomes, con, permissoes_legadas) -> None:
    """Prévia do que a pessoa vai ver + checagem do recorte contra a base.
    `permissoes_legadas` (só no Personalizado, que não apaga negações):
    sub-página legada negada esconde a jornada (docs/13 N2)."""
    with st.container(border=True):
        st.markdown("**Prévia**")
        visiveis = paginas_visiveis(plano, permissoes_legadas)
        st.markdown(
            f"{u['nome_completo']} vai ver: "
            + (", ".join(TITULO_PAGINA.get(p, p) for p in visiveis) if visiveis else "só o aviso \"Sem acesso\"")
        )
        if perfil != "personalizado":
            st.caption("Recorte: " + _texto_recorte(perfil, recorte, nomes))
        if perfil not in ("admin", "sem_acesso"):
            problemas = diagnosticar_perfis(
                [{**u, "ativo": True, "papel": plano.papel}],
                linhas_escopo_para_diagnostico(str(u["id"]), plano),
                _valores_existentes_na_base(con),
            )
            for p in problemas:
                st.warning("⚠️ " + p["Problema"])



def _render_escopos_legados(u: dict) -> None:
    """Escopos sem universo (antes do docs/08): não liberam nem filtram
    nada. Só leitura + botão pra desativar — o cadastro novo deles saiu."""
    try:
        legados = [r for r in listar_escopos(u["id"]) if r.get("ativo")]
    except Exception as exc:
        st.warning(f"Não consegui ler os escopos legados deste usuário. Detalhe: {exc}")
        return
    if not legados:
        return
    with st.expander(f"Escopos legados sem efeito ({len(legados)})"):
        st.caption(
            "Linhas antigas, sem universo — o controle de acesso não lê estas linhas. "
            "Podem ser desativadas sem mudar nada do que a pessoa vê."
        )
        st.dataframe(pd.DataFrame(legados), hide_index=True, use_container_width=True)
        if st.button("Desativar escopos legados deste usuário", key=f"legado-{u['id']}-desativar"):
            desativar_escopos_legados(u["id"])
            registrar_atividade("desativar_escopos_legados", "administracao", {"usuario_id": str(u["id"])})
            st.success("Escopos legados desativados.")


def render_administracao(con: duckdb.DuckDBPyConnection | None = None) -> None:
    """`con`: conexão de leitura do warehouse DuckDB LOCAL (não o Neon) —
    só usada pra popular os dropdowns de Gerência/Gerência de Obras/PEP/
    PEP Filho/Centro de Custo/Pacote com valor real, em vez de texto
    livre digitado (pedido do usuário em 2026-08-28, ampliado em
    2026-08-29 com o universo CAPEX Obras). `None` (ex.: base ainda não
    processada) cai de volta pra texto livre nesses campos, sem quebrar
    a página.

    Desde 2026-10-18 (docs/13) o acesso de cada pessoa é definido numa
    tela só — aba "Perfil de acesso" (`_render_perfil_acesso`) — e vale em
    até 1 minuto, sem novo login (`permissions.revalidar_acesso_da_sessao`).
    O enforcement nas telas está ligado desde a Fase RBAC-A.2 (docs/08)."""
    require_admin()
    render_page_banner("🛡️", "Administração", "Usuários, acessos, escopos e rastreabilidade em um só lugar.")
    if con is None:
        st.caption("⚠️ Base local ainda não processada — Gerência/PEP/PEP Filho/Centro de Custo/Pacote aparecem como texto livre até reprocessar (Gestão → Dados e Qualidade).")
    t1, t2, t3, t4 = st.tabs(["Usuários", "Perfil de acesso", "Auditoria", "Uploads e exportações"])

    with t1:
        with st.expander("Criar usuário", expanded=False):
            with st.form("admin-criar-usuario"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome completo")
                matricula = c2.text_input("Matrícula")
                email = c1.text_input("E-mail")
                gg = c2.text_input("GG", value="GGG_0054")
                # docs/13: papel e Gerência saíram daqui — quem decide o que a
                # pessoa vê é o Perfil de acesso (aba ao lado). Usuário novo
                # nasce "Sem acesso" até o admin escolher o perfil.
                papel, ger = "especialista_analista", None
                st.caption("Uma senha temporária única é gerada automaticamente na criação — a pessoa é obrigada a trocá-la no primeiro login. Depois, defina o que ela vê na aba **Perfil de acesso** (até lá ela fica \"Sem acesso\").")
                if st.form_submit_button("Criar usuário", type="primary"):
                    senha_temporaria = gerar_senha_temporaria()
                    criar_usuario(
                        nome_completo=nome, papel=papel, senha_hash=gerar_hash(senha_temporaria),
                        matricula=matricula or None, email=email or None,
                        gg_id=gg or None, gerencia_id=ger or None,
                    )
                    registrar_atividade("criar_usuario", "administracao", {"matricula": matricula, "papel": papel})
                    st.success(f"Usuário {nome or matricula or email} criado.")
                    st.code(senha_temporaria, language=None)
                    st.warning("Copie a senha acima agora — ela não será exibida novamente. Repasse com segurança à pessoa; a troca é obrigatória no primeiro login.")
        usuarios = listar_usuarios()
        st.dataframe(pd.DataFrame(usuarios), hide_index=True, use_container_width=True)
        if usuarios:
            nomes = {f"{u['nome_completo']} · {u.get('matricula') or u.get('email')}": u for u in usuarios}
            sel = st.selectbox("Editar usuário", list(nomes)); u = nomes[sel]
            with st.form("admin-editar-usuario"):
                ativo = st.checkbox("Ativo", value=bool(u.get("ativo")))
                st.caption("Papel e capacidades (upload, exportação, justificativas) ficam na aba **Perfil de acesso**.")
                if st.form_submit_button("Salvar alterações"):
                    atualizar_usuario(u["id"], ativo=ativo)
                    registrar_atividade("editar_usuario", "administracao", {"usuario_id": str(u["id"]), "ativo": ativo})
                    st.success("Alterações salvas.")

            st.markdown("**Redefinir senha**")
            forcar_troca = st.checkbox("Forçar troca de senha no próximo login", value=True, key=f"admin-forcar-troca-{u['id']}")
            if st.button("Gerar nova senha temporária", key=f"admin-resetar-senha-{u['id']}"):
                senha_temporaria = gerar_senha_temporaria()
                resetar_senha_admin(u["id"], gerar_hash(senha_temporaria), forcar_troca)
                registrar_atividade("resetar_senha", "administracao", {"usuario_id": str(u["id"]), "forcar_troca": forcar_troca})
                st.success(f"Senha de {u['nome_completo']} redefinida.")
                st.code(senha_temporaria, language=None)
                st.warning("Copie a senha acima agora — ela não será exibida novamente. Repasse com segurança à pessoa; a troca é obrigatória no próximo login se a caixa acima estiver marcada.")

            with st.expander("⚠️ Excluir usuário"):
                st.caption(
                    "Exclusão é permanente e o banco bloqueia (fail closed) se este usuário já tiver login, "
                    "exportação, upload ou justificativa registrados — nesse caso, desmarque \"Ativo\" acima "
                    "em vez de excluir."
                )
                confirmar = st.checkbox(
                    f"Confirmo que quero excluir permanentemente {u['nome_completo']}",
                    key=f"admin-confirma-exclusao-{u['id']}",
                )
                if st.button("Excluir usuário", disabled=not confirmar, key=f"admin-excluir-{u['id']}"):
                    try:
                        excluir_usuario(u["id"])
                    except psycopg2.errors.ForeignKeyViolation:
                        st.error(
                            "Não foi possível excluir: este usuário tem histórico vinculado (login, exportação, "
                            "upload ou justificativa) e a exclusão físico-permanente apagaria rastro de auditoria. "
                            "Desmarque \"Ativo\" acima para desativar em vez de excluir."
                        )
                    else:
                        registrar_atividade(
                            "excluir_usuario", "administracao",
                            {"nome_completo": u["nome_completo"], "matricula": u.get("matricula"), "email": u.get("email")},
                        )
                        st.toast(f"Usuário {u['nome_completo']} excluído.")
                        st.rerun()

    with t2:
        st.markdown("**Perfis com problema**")
        _render_diagnostico_perfis(con)
        st.divider()
        usuarios = listar_usuarios()
        if usuarios:
            nomes = {f"{u['nome_completo']} · {u.get('matricula') or u.get('email')}": u for u in usuarios}
            u = nomes[st.selectbox("Usuário", list(nomes), key="admin-escopo-user")]
            _render_perfil_acesso(u, con)
            st.divider()
            _render_escopos_legados(u)

    with t3:
        st.dataframe(_com_hora_br(pd.DataFrame(listar_atividades())), hide_index=True, use_container_width=True, height=520)

    with t4:
        st.markdown("**Histórico versionado de uploads**")
        versoes = listar_versoes_upload()
        st.dataframe(_com_hora_br(pd.DataFrame(versoes), "enviado_em"), hide_index=True, use_container_width=True)
        if versoes:
            opv = {f"{_fmt_hora_br(v['enviado_em'])} · {v['tipo']} · {v['nome_original']}": v for v in versoes}
            v = opv[st.selectbox("Versão para restaurar", list(opv))]
            c_restaurar, c_baixar = st.columns(2)
            if c_restaurar.button("Restaurar esta versão e reprocessar", type="primary"):
                cfg = carregar_config(); caminho = cfg["caminhos"].get(v["tipo"])
                if not caminho:
                    st.error("Tipo sem caminho configurado em settings.yaml.")
                elif restaurar_versao_arquivo(v["id"], caminho):
                    build_star_schema()
                    registrar_atividade("reverter_upload", "administracao", {"versao_id": str(v["id"]), "tipo": v["tipo"]})
                    st.success("Versão restaurada e base reprocessada.")
            bruto_versao = obter_versao_arquivo(v["id"])
            c_baixar.download_button(
                "Baixar cópia deste arquivo bruto", bytes(bruto_versao["conteudo"]),
                file_name=bruto_versao["nome_original"],
            )
        st.markdown("**Cópias das exportações**")
        exps = listar_exportacoes()
        st.dataframe(_com_hora_br(pd.DataFrame(exps)), hide_index=True, use_container_width=True)
        if exps:
            op = {f"{_fmt_hora_br(e['criado_em'])} · {e['nome_arquivo']} · {e.get('nome_completo') or 'Usuário'}": e for e in exps}
            e = op[st.selectbox("Baixar cópia auditada", list(op))]
            bruto = obter_exportacao(e["id"])
            st.download_button("Baixar cópia", bytes(bruto["conteudo"]), file_name=bruto["nome_arquivo"])
