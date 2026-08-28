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

PAGINAS = ["resumo_executivo","painel_executivo","visao_opex","capex_manutencao","visao_manutencao","projecao_opex","contas","centro_custo","rastreabilidade_sap","capex_resumo","capex_painel","capex_contas","capex_rastreabilidade","pce_especialista","upload","administracao"]

# Tipos de escopo com uma dimensão real no warehouse pra virar dropdown —
# os demais (projeto/elemento_pep/pep_filho) continuam texto livre porque
# não existe uma lista fechada confiável pra eles ainda (pep_filho nem é
# um campo que a fonte de dado tem hoje — não inventar).
_TIPOS_ESCOPO_SELECIONAVEL = {"gerencia", "pacote", "centro_custo", "coordenacao"}
TIPOS_ESCOPO = ["projeto", "elemento_pep", "pep_filho", "gerencia", "coordenacao", "centro_custo", "pacote"]

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


def _listar_coordenacoes(con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    if con is None:
        return []
    try:
        df = con.execute(
            "SELECT DISTINCT coordenacao FROM fact_realizado "
            "WHERE coordenacao IS NOT NULL ORDER BY coordenacao"
        ).df()
        return [(v, v) for v in df["coordenacao"]]
    except Exception:
        return []


def _opcoes_escopo(tipo: str, con: duckdb.DuckDBPyConnection | None) -> list[tuple[str, str]]:
    return {
        "gerencia": _listar_gerencias,
        "pacote": _listar_pacotes,
        "centro_custo": _listar_centros_custo,
        "coordenacao": _listar_coordenacoes,
    }.get(tipo, lambda _c: [])(con)


def render_administracao(con: duckdb.DuckDBPyConnection | None = None) -> None:
    """`con`: conexão de leitura do warehouse DuckDB LOCAL (não o Neon) —
    só usada pra popular os dropdowns de Gerência/Pacote/Centro de Custo/
    Coordenação com valor real, em vez de texto livre digitado (pedido do
    usuário em 2026-08-28). `None` (ex.: base ainda não processada) cai
    de volta pra texto livre nesses campos, sem quebrar a página."""
    require_admin()
    render_page_banner("🛡️", "Administração", "Usuários, acessos, escopos e rastreabilidade em um só lugar.")
    if con is None:
        st.caption("⚠️ Base local ainda não processada — Gerência/Pacote/Centro de Custo/Coordenação aparecem como texto livre até reprocessar (Dados → Upload de Dados).")
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

            st.markdown("**Escopos de dados**")
            tipo = st.selectbox("Tipo", TIPOS_ESCOPO, key="admin-escopo-tipo")
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
