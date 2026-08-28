"""Administração de usuários, escopos e auditoria do Fin360."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from src.branding import render_page_banner
from src.auth.permissions import require_admin
from src.auth.queries import criar_usuario
from src.auth.senha import gerar_hash
from src.auth.admin_queries import *
from src.auth.audit import registrar_atividade
from src.config import carregar_config
from src.ingestion.arquivo_bruto import restaurar_versao_arquivo
from src.model.build_star_schema import build_star_schema

PAGINAS=["resumo_executivo","painel_executivo","visao_opex","capex_manutencao","visao_manutencao","projecao_opex","contas","centro_custo","rastreabilidade_sap","capex_resumo","capex_painel","capex_contas","capex_rastreabilidade","pce_especialista","upload","administracao"]
TIPOS_ESCOPO=["projeto","elemento_pep","pep_filho","gerencia","coordenacao","centro_custo","pacote"]

def render_administracao() -> None:
    require_admin()
    render_page_banner("🛡️","Administração","Usuários, acessos, escopos e rastreabilidade em um só lugar.")
    t1,t2,t3,t4=st.tabs(["Usuários","Permissões e escopos","Auditoria","Uploads e exportações"] )
    with t1:
        with st.expander("Criar usuário", expanded=False):
            with st.form("admin-criar-usuario"):
                c1,c2=st.columns(2); nome=c1.text_input("Nome completo"); matricula=c2.text_input("Matrícula")
                email=c1.text_input("E-mail"); papel=c2.selectbox("Papel",["gg","gerente","especialista_analista","admin"])
                gg=c1.text_input("GG",value="GGG_0054"); ger=c2.text_input("Gerência ID")
                senha=st.text_input("Senha inicial",type="password")
                if st.form_submit_button("Criar usuário",type="primary"):
                    criar_usuario(nome_completo=nome,papel=papel,senha_hash=gerar_hash(senha),matricula=matricula or None,email=email or None,gg_id=gg or None,gerencia_id=ger or None)
                    registrar_atividade("criar_usuario","administracao",{"matricula":matricula,"papel":papel}); st.success("Usuário criado.")
        usuarios=listar_usuarios(); st.dataframe(pd.DataFrame(usuarios),hide_index=True,use_container_width=True)
        if usuarios:
            nomes={f"{u['nome_completo']} · {u.get('matricula') or u.get('email')}":u for u in usuarios}; sel=st.selectbox("Editar usuário",list(nomes)); u=nomes[sel]
            with st.form("admin-editar-usuario"):
                ativo=st.checkbox("Ativo",value=bool(u.get("ativo"))); papel=st.selectbox("Papel",["gg","gerente","especialista_analista","admin"],index=["gg","gerente","especialista_analista","admin"].index(u["papel"]))
                c1,c2,c3,c4=st.columns(4); up=c1.checkbox("Upload",value=bool(u.get("permissao_upload"))); ex=c2.checkbox("Download/exportação",value=bool(u.get("permissao_exportacao"))); ma=c3.checkbox("Justificativa macro",value=bool(u.get("permissao_justificativa_macro"))); mi=c4.checkbox("Justificativa micro",value=bool(u.get("permissao_justificativa_micro")))
                if st.form_submit_button("Salvar alterações"):
                    atualizar_usuario(u["id"],ativo=ativo,papel=papel,permissao_upload=up,permissao_exportacao=ex,permissao_justificativa_macro=ma,permissao_justificativa_micro=mi); registrar_atividade("editar_usuario","administracao",{"usuario_id":str(u["id"])}); st.success("Alterações salvas.")
    with t2:
        usuarios=listar_usuarios();
        if usuarios:
            nomes={f"{u['nome_completo']} · {u.get('matricula') or u.get('email')}":u for u in usuarios}; u=nomes[st.selectbox("Usuário",list(nomes),key="admin-escopo-user")]
            atuais={r["pagina"]:r["permitido"] for r in listar_permissoes(u["id"])}
            st.markdown("**Visão de páginas**")
            cols=st.columns(3)
            escolhas={p:cols[i%3].checkbox(p.replace("_"," ").title(),value=atuais.get(p,True),key=f"perm-{u['id']}-{p}") for i,p in enumerate(PAGINAS)}
            if st.button("Salvar páginas"):
                for pg,val in escolhas.items(): salvar_permissao(u["id"],pg,val)
                registrar_atividade("alterar_permissoes_pagina","administracao",{"usuario_id":str(u["id"])}); st.success("Permissões salvas.")
            st.markdown("**Escopos de dados**")
            c1,c2,c3=st.columns(3); tipo=c1.selectbox("Tipo",TIPOS_ESCOPO); valor=c2.text_input("Código/valor exato"); desc=c3.text_input("Descrição")
            if st.button("Adicionar escopo") and valor:
                adicionar_escopo(u["id"],tipo,valor,desc); registrar_atividade("adicionar_escopo","administracao",{"usuario_id":str(u["id"]),"tipo":tipo,"valor":valor}); st.success("Escopo adicionado.")
            st.dataframe(pd.DataFrame(listar_escopos(u["id"])),hide_index=True,use_container_width=True)
    with t3:
        st.dataframe(pd.DataFrame(listar_atividades()),hide_index=True,use_container_width=True,height=520)
    with t4:
        st.markdown("**Histórico versionado de uploads**")
        versoes=listar_versoes_upload(); st.dataframe(pd.DataFrame(versoes),hide_index=True,use_container_width=True)
        if versoes:
            opv={f"{v['enviado_em']} · {v['tipo']} · {v['nome_original']}":v for v in versoes}
            v=opv[st.selectbox("Versão para restaurar",list(opv))]
            if st.button("Restaurar esta versão e reprocessar",type="primary"):
                cfg=carregar_config(); caminho=cfg["caminhos"].get(v["tipo"])
                if not caminho: st.error("Tipo sem caminho configurado em settings.yaml.")
                elif restaurar_versao_arquivo(v["id"],caminho):
                    build_star_schema(); registrar_atividade("reverter_upload","administracao",{"versao_id":str(v["id"]),"tipo":v["tipo"]}); st.success("Versão restaurada e base reprocessada.")
        st.markdown("**Cópias das exportações**"); exps=listar_exportacoes(); st.dataframe(pd.DataFrame(exps),hide_index=True,use_container_width=True)
        if exps:
            op={f"{e['criado_em']} · {e['nome_arquivo']} · {e.get('nome_completo') or 'Usuário'}":e for e in exps}; e=op[st.selectbox("Baixar cópia auditada",list(op))]; bruto=obter_exportacao(e["id"]); st.download_button("Baixar cópia",bytes(bruto["conteudo"]),file_name=bruto["nome_arquivo"])
