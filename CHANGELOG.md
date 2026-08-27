# Changelog — Fin360 (Painel Orçamento GGSP)

Versionamento SemVer (ver `src/versao.py`): MAJOR = tela nova/schema/
segurança/integridade de dado; MINOR = funcionalidade nova sem quebrar
nada; PATCH = correção de bug. Bump a cada commit relevante.

## 1.0.0 — 2026-08-27

Primeira versão publicada online (antes só rodava local, sem controle
de versão).

- Login próprio (bcrypt + Neon Postgres), gate de sessão obrigatório em
  todas as páginas.
- Fundação de RBAC (papéis, permissões granulares — `src/auth/`).
- Schema de justificativas/delegação/auditoria preparado no Postgres
  (`config/schema_postgres.sql`), pronto para a Camada 4 (captura de
  justificativas).
- Deploy no Streamlit Community Cloud (`fin360.streamlit.app`).
- Identidade visual "Fin360": logo em vídeo (login + sidebar), nome
  padrão em toda a interface.
- Correções de "dia zero" encontradas no primeiro deploy real (ver
  `docs/04-licoes-aprendidas.md`, itens 16-18): sys.path na raiz do
  projeto, aviso claro quando faltam arquivos obrigatórios no upload,
  CSV de explicações ausente tratado como "sem justificativa ainda".
