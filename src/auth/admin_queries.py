"""Consultas da Administração. Todas as mutações são auditáveis."""
from __future__ import annotations
from src.auth.db import buscar_todos, buscar_um, executar

def listar_usuarios():
    return buscar_todos("select id,matricula,email,nome_completo,papel,gg_id,gerencia_id,ativo,permissao_upload,permissao_exportacao,permissao_justificativa_macro,permissao_justificativa_micro,ultimo_login,criado_em,atualizado_em from app.usuario order by nome_completo")
def obter_usuario(usuario_id):
    return buscar_um("select * from app.usuario where id=%s", (usuario_id,))
def atualizar_usuario(usuario_id, **campos):
    permitidos={"nome_completo","matricula","email","papel","gg_id","gerencia_id","ativo","permissao_upload","permissao_exportacao","permissao_justificativa_macro","permissao_justificativa_micro"}
    itens=[(k,v) for k,v in campos.items() if k in permitidos]
    if not itens: return
    sql=", ".join(f"{k}=%s" for k,_ in itens)+", atualizado_em=now()"
    executar(f"update app.usuario set {sql} where id=%s", tuple(v for _,v in itens)+(usuario_id,))
def listar_permissoes(usuario_id):
    return buscar_todos("select pagina, permitido from app.permissao_pagina where usuario_id=%s order by pagina",(usuario_id,))
def salvar_permissao(usuario_id,pagina,permitido):
    executar("insert into app.permissao_pagina(usuario_id,pagina,permitido) values(%s,%s,%s) on conflict(usuario_id,pagina) do update set permitido=excluded.permitido",(usuario_id,pagina,permitido))
def listar_escopos(usuario_id):
    return buscar_todos("select id,tipo,valor,descricao,ativo from app.escopo_acesso where usuario_id=%s order by tipo,valor",(usuario_id,))
def adicionar_escopo(usuario_id,tipo,valor,descricao=''):
    executar("insert into app.escopo_acesso(usuario_id,tipo,valor,descricao) values(%s,%s,%s,%s) on conflict(usuario_id,tipo,valor) do update set descricao=excluded.descricao,ativo=true",(usuario_id,tipo,valor,descricao))
def desativar_escopo(escopo_id): executar("update app.escopo_acesso set ativo=false where id=%s",(escopo_id,))
def listar_atividades(limite=500):
    # app.log_auditoria (não log_atividade — reaproveitada, ver audit.py).
    return buscar_todos("select l.criado_em,u.nome_completo,u.matricula,l.acao,l.recurso,l.detalhe from app.log_auditoria l left join app.usuario u on u.id=l.usuario_id order by l.criado_em desc limit %s",(limite,))
def listar_exportacoes(limite=200):
    return buscar_todos("select e.id,e.criado_em,u.nome_completo,e.nome_arquivo,e.tamanho_bytes,e.sha256,e.filtros from app.artefato_exportado e left join app.usuario u on u.id=e.usuario_id order by e.criado_em desc limit %s",(limite,))
def obter_exportacao(exportacao_id): return buscar_um("select nome_arquivo,conteudo from app.artefato_exportado where id=%s",(exportacao_id,))
def listar_versoes_upload(limite=200):
    return buscar_todos("select v.id,v.tipo,v.nome_original,v.tamanho_bytes,v.enviado_em,u.nome_completo,v.ativo from app.arquivo_bruto_versao v left join app.usuario u on u.id=v.enviado_por order by v.enviado_em desc limit %s",(limite,))
