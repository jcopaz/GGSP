"""Administração de usuários, escopos e auditoria do Fin360."""
from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import streamlit as st

from src.branding import render_page_banner
from src.auth.permissions import require_admin
from src.auth.queries import criar_usuario
from src.auth.senha import gerar_hash, gerar_senha_temporaria
from src.auth.admin_queries import *
from src.auth.audit import registrar_atividade
from src.config import carregar_config
from src.ingestion.arquivo_bruto import restaurar_versao_arquivo
from src.model.build_star_schema import build_star_schema

# "visao_opex"/"capex_manutencao" viraram 1 chave só ("opex_capex_manutencao")
# em 2026-08-29 — ver app.py::pagina_opex_capex_manutencao. Qualquer linha
# antiga em app.permissao_pagina com essas 2 chaves fica órfã (inofensiva,
# só não é mais lida por can_acessar_pagina) — não precisa migração.
PAGINAS = ["resumo_executivo","painel_executivo","opex_capex_manutencao","visao_manutencao","projecao_opex","contas","centro_custo","rastreabilidade_sap","capex_resumo","capex_painel","capex_contas","capex_rastreabilidade","pce_especialista","upload","administracao"]

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


def _render_acesso_por_universo(u: dict, con: duckdb.DuckDBPyConnection | None) -> None:
    """1ª camada (vê o universo?) + 2ª camada (GG inteira x Gerências) do
    RBAC de escopo — grava em `app.escopo_acesso` com `universo` + a
    permissão de página `pce_especialista` (opção B, docs/08 §10).
    Enforcement nas telas do painel = Fase RBAC-A.2, ainda não ligado."""
    uid = str(u["id"])
    try:
        atuais = listar_escopos_universo(u["id"])
    except Exception:
        atuais = []
    por_uni: dict[str, list[dict]] = {}
    for r in atuais:
        por_uni.setdefault(r["universo"], []).append(r)

    st.markdown("**Acesso por universo financeiro**")
    st.caption(
        "1ª camada: quais universos a pessoa vê. 2ª camada: GG inteira ou "
        "Gerências específicas. `admin` vê tudo; papel `gg` também passa por "
        "aqui. Enforcement nas telas ainda não está ligado (Fase RBAC-A.2) — "
        "aqui só se cadastra a intenção."
    )

    gers_sust = _listar_gerencias(con)
    gers_obras = _listar_gerencias_obras(con)
    projetos = _listar_elemento_pep(con)
    esp_atual = {r["pagina"]: r["permitido"] for r in listar_permissoes(u["id"])}.get("pce_especialista", False)

    plano: dict[str, list[tuple[str, str, str]]] = {}
    ve_especialista = bool(esp_atual)
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
            if universo == "capex_obras":
                marcado = st.checkbox(
                    "Vê a tela CAPEX Obras — Especialista (planejamento PCE)",
                    value=bool(esp_atual), disabled=not on,
                    key=f"uni-{uid}-{universo}-esp",
                    help="Tela densa de planejamento (13 versões, forecasts, FEL). Opção B do docs/08 §10.",
                )
                ve_especialista = bool(on and marcado)
            plano[universo] = linhas_novas

    if st.button("Salvar acessos por universo", type="primary", key=f"uni-{uid}-salvar"):
        try:
            for universo, linhas_novas in plano.items():
                substituir_escopo_universo(u["id"], universo, linhas_novas)
            salvar_permissao(u["id"], "pce_especialista", ve_especialista)
            registrar_atividade("delegar_escopo_universo", "administracao", {
                "usuario_id": uid,
                "resumo": {k: [f"{t}:{v}" for t, v, _ in vs] for k, vs in plano.items()},
                "pce_especialista": ve_especialista,
            })
            st.success("Acessos por universo salvos. O efeito aparece no próximo login da pessoa.")
        except Exception as exc:
            st.error(
                f"Não consegui salvar — a migração do `docs/08` (coluna "
                f"`universo` em `app.escopo_acesso`) já rodou no Neon? Detalhe: {exc}"
            )


def render_administracao(con: duckdb.DuckDBPyConnection | None = None) -> None:
    """`con`: conexão de leitura do warehouse DuckDB LOCAL (não o Neon) —
    só usada pra popular os dropdowns de Gerência/Gerência de Obras/PEP/
    PEP Filho/Centro de Custo/Pacote com valor real, em vez de texto
    livre digitado (pedido do usuário em 2026-08-28, ampliado em
    2026-08-29 com o universo CAPEX Obras). `None` (ex.: base ainda não
    processada) cai de volta pra texto livre nesses campos, sem quebrar
    a página.

    IMPORTANTE — o que este cadastro NÃO faz (2026-08-29): salvar um
    escopo aqui (ex. Gerência de Obras = "Baixada Santista") só GRAVA a
    intenção em `app.escopo_acesso` — nenhuma página do painel hoje lê
    esse registro pra filtrar dado nenhum. A cascata de negócio (Gerência
    de Obras ⊃ Elemento PEP ⊃ PEP Filho) é a regra que VAI ser aplicada
    quando essa parte for construída, não o comportamento atual. Ver
    aviso equivalente já dado sobre Gerência/Pacote em 2026-08-28."""
    require_admin()
    render_page_banner("🛡️", "Administração", "Usuários, acessos, escopos e rastreabilidade em um só lugar.")
    if con is None:
        st.caption("⚠️ Base local ainda não processada — Gerência/PEP/PEP Filho/Centro de Custo/Pacote aparecem como texto livre até reprocessar (Gestão → Dados e Qualidade).")
    t1, t2, t3, t4 = st.tabs(["Usuários", "Permissões e escopos", "Auditoria", "Uploads e exportações"])

    with t1:
        with st.expander("Criar usuário", expanded=False):
            gerencias = _listar_gerencias(con)
            with st.form("admin-criar-usuario"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome completo")
                matricula = c2.text_input("Matrícula")
                email = c1.text_input("E-mail")
                papel = c2.selectbox("Papel", ["gg", "gerente", "especialista_analista", "admin"])
                gg = c1.text_input("GG", value="GGG_0054")
                if gerencias:
                    opcoes_ger = ["(sem Gerência específica)"] + [f"{gid} — {gnome}" for gid, gnome in gerencias]
                    escolha_ger = c2.selectbox("Gerência", opcoes_ger)
                    ger = None if escolha_ger == opcoes_ger[0] else escolha_ger.split(" — ")[0]
                else:
                    ger = c2.text_input("Gerência ID")
                st.caption("Uma senha temporária única é gerada automaticamente na criação — a pessoa é obrigada a trocá-la no primeiro login.")
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
                papel = st.selectbox("Papel", ["gg", "gerente", "especialista_analista", "admin"], index=["gg", "gerente", "especialista_analista", "admin"].index(u["papel"]))
                c1, c2, c3, c4 = st.columns(4)
                up = c1.checkbox("Upload", value=bool(u.get("permissao_upload")))
                ex = c2.checkbox("Download/exportação", value=bool(u.get("permissao_exportacao")))
                ma = c3.checkbox("Justificativa macro", value=bool(u.get("permissao_justificativa_macro")))
                mi = c4.checkbox("Justificativa micro", value=bool(u.get("permissao_justificativa_micro")))
                if st.form_submit_button("Salvar alterações"):
                    atualizar_usuario(u["id"], ativo=ativo, papel=papel, permissao_upload=up, permissao_exportacao=ex, permissao_justificativa_macro=ma, permissao_justificativa_micro=mi)
                    registrar_atividade("editar_usuario", "administracao", {"usuario_id": str(u["id"])})
                    st.success("Alterações salvas.")

    with t2:
        usuarios = listar_usuarios()
        if usuarios:
            nomes = {f"{u['nome_completo']} · {u.get('matricula') or u.get('email')}": u for u in usuarios}
            u = nomes[st.selectbox("Usuário", list(nomes), key="admin-escopo-user")]
            atuais = {r["pagina"]: r["permitido"] for r in listar_permissoes(u["id"])}
            st.markdown("**Visão de páginas**")
            cols = st.columns(3)
            escolhas = {p: cols[i % 3].checkbox(p.replace("_", " ").title(), value=atuais.get(p, True), key=f"perm-{u['id']}-{p}") for i, p in enumerate(PAGINAS)}
            if st.button("Salvar páginas"):
                for pg, val in escolhas.items():
                    salvar_permissao(u["id"], pg, val)
                registrar_atividade("alterar_permissoes_pagina", "administracao", {"usuario_id": str(u["id"])})
                st.success("Permissões salvas.")

            st.divider()
            _render_acesso_por_universo(u, con)

            st.divider()
            st.markdown("**Escopos avançados (legado)**")
            st.caption(
                "Cadastro genérico por tipo (Pacote / Centro de Custo / PEP Filho / "
                "Projeto). Grava linhas SEM universo — o RBAC de escopo por universo "
                "acima NÃO lê estas linhas. Mantido para os tipos fora do modelo de "
                "2 camadas do `docs/08`."
            )
            tipo = st.selectbox(
                "Tipo", TIPOS_ESCOPO, key="admin-escopo-tipo",
                format_func=lambda t: _ROTULO_TIPO_ESCOPO.get(t, t),
            )
            opcoes = _opcoes_escopo(tipo, con)
            if tipo in _TIPOS_ESCOPO_SELECIONAVEL and opcoes:
                rotulos = {f"{cod} — {nome}" if nome else cod: (cod, nome) for cod, nome in opcoes}
                selecionados = st.multiselect(
                    "Selecione um, vários ou todos",
                    list(rotulos),
                    key=f"admin-escopo-multi-{tipo}",
                )
                if st.button("Adicionar escopo(s) selecionado(s)") and selecionados:
                    for rotulo in selecionados:
                        cod, nome = rotulos[rotulo]
                        adicionar_escopo(u["id"], tipo, cod, nome)
                    registrar_atividade("adicionar_escopo", "administracao", {"usuario_id": str(u["id"]), "tipo": tipo, "valores": [rotulos[r][0] for r in selecionados]})
                    st.success(f"{len(selecionados)} escopo(s) adicionado(s).")
            else:
                if tipo in _TIPOS_ESCOPO_SELECIONAVEL:
                    st.caption("Base local ainda não processada — sem lista real disponível, digite manualmente.")
                else:
                    st.caption("Sem lista fechada pra este tipo na fonte de dado — texto livre.")
                c1, c2 = st.columns(2)
                valor = c1.text_input("Código/valor exato", key=f"admin-escopo-valor-{tipo}")
                desc = c2.text_input("Descrição", key=f"admin-escopo-desc-{tipo}")
                if st.button("Adicionar escopo") and valor:
                    adicionar_escopo(u["id"], tipo, valor, desc)
                    registrar_atividade("adicionar_escopo", "administracao", {"usuario_id": str(u["id"]), "tipo": tipo, "valor": valor})
                    st.success("Escopo adicionado.")
            st.dataframe(pd.DataFrame(listar_escopos(u["id"])), hide_index=True, use_container_width=True)

    with t3:
        st.dataframe(_com_hora_br(pd.DataFrame(listar_atividades())), hide_index=True, use_container_width=True, height=520)

    with t4:
        st.markdown("**Histórico versionado de uploads**")
        versoes = listar_versoes_upload()
        st.dataframe(_com_hora_br(pd.DataFrame(versoes), "enviado_em"), hide_index=True, use_container_width=True)
        if versoes:
            opv = {f"{_fmt_hora_br(v['enviado_em'])} · {v['tipo']} · {v['nome_original']}": v for v in versoes}
            v = opv[st.selectbox("Versão para restaurar", list(opv))]
            if st.button("Restaurar esta versão e reprocessar", type="primary"):
                cfg = carregar_config(); caminho = cfg["caminhos"].get(v["tipo"])
                if not caminho:
                    st.error("Tipo sem caminho configurado em settings.yaml.")
                elif restaurar_versao_arquivo(v["id"], caminho):
                    build_star_schema()
                    registrar_atividade("reverter_upload", "administracao", {"versao_id": str(v["id"]), "tipo": v["tipo"]})
                    st.success("Versão restaurada e base reprocessada.")
        st.markdown("**Cópias das exportações**")
        exps = listar_exportacoes()
        st.dataframe(_com_hora_br(pd.DataFrame(exps)), hide_index=True, use_container_width=True)
        if exps:
            op = {f"{_fmt_hora_br(e['criado_em'])} · {e['nome_arquivo']} · {e.get('nome_completo') or 'Usuário'}": e for e in exps}
            e = op[st.selectbox("Baixar cópia auditada", list(op))]
            bruto = obter_exportacao(e["id"])
            st.download_button("Baixar cópia", bytes(bruto["conteudo"]), file_name=bruto["nome_arquivo"])
