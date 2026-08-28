"""Auditoria funcional best-effort. Falha de log nunca quebra a ação principal.

Grava em `app.log_auditoria` (schema em config/schema_postgres.sql) — não
`app.log_atividade`: o pacote de melhorias v3.4.0 propunha essa segunda
tabela, mas é redundante com `log_auditoria` (já existe, mesmas colunas,
mesmo propósito) — reaproveitada em vez de duplicada, decisão registrada em
docs/06-administracao-auditoria-e-projecao.md."""
from __future__ import annotations
import hashlib, json
import streamlit as st
from src.auth.db import executar
from src.auth.session import get_id

def registrar_atividade(acao: str, recurso: str, detalhe: dict | None = None) -> None:
    try:
        executar("insert into app.log_auditoria (usuario_id, acao, recurso, detalhe) values (%s,%s,%s,%s)", (get_id(), acao, recurso, json.dumps(detalhe or {}, ensure_ascii=False)))
    except Exception:
        pass

def registrar_visualizacao_pagina(chave: str) -> None:
    marcador = f"_audit_page_{chave}"
    if not st.session_state.get(marcador):
        registrar_atividade("visualizar_pagina", chave)
        st.session_state[marcador] = True

def registrar_exportacao(nome: str, conteudo: bytes, filtros: dict | None = None) -> None:
    try:
        sha = hashlib.sha256(conteudo).hexdigest()
        executar("insert into app.artefato_exportado (usuario_id,nome_arquivo,conteudo,tamanho_bytes,sha256,filtros) values (%s,%s,%s,%s,%s,%s)", (get_id(), nome, conteudo, len(conteudo), sha, json.dumps(filtros or {}, ensure_ascii=False)))
        registrar_atividade("exportar_dados", nome, {"sha256": sha, "tamanho_bytes": len(conteudo)})
    except Exception:
        pass
