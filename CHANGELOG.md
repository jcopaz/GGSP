# Changelog — Fin360 (Painel Orçamento GGSP)

Versionamento SemVer (ver `src/versao.py`): MAJOR = tela nova/schema/
segurança/integridade de dado; MINOR = funcionalidade nova sem quebrar
nada; PATCH = correção de bug. Bump a cada commit relevante.

## 2.0.2 — 2026-08-27

- Corrige `duckdb.CatalogException` na página "CAPEX Obras — Especialista":
  `fact_pce_realizado` (fonte "PCE Base Luiz.xlsx") não tinha zona de
  upload própria — nova zona "Sob demanda" em `TIPOS_ARQUIVO`, mais guard
  defensivo em `pce_especialista.py` (devolve 0/vazio se a tabela ainda
  não existir, em vez de quebrar). Ver `docs/04-licoes-aprendidas.md`,
  item 19.

## 2.0.1 — 2026-08-27

- Redesenho da tela de login: card branco centralizado sobre fundo neutro,
  logo em moldura circular (recorta a margem escura do vídeo fonte via
  `transform: scale`), tipografia e botão com a cor da marca (azul-marinho
  Fin360). Mesma moldura circular aplicada ao logo da sidebar.

## 2.0.0 — 2026-08-27

- Tela de login centralizada (CSS) e vídeo de logo corrigido — `static/`
  precisa estar em `src/dashboard/static/` (mesma pasta do script
  principal), não na raiz do repositório; movido de lugar.
- **Nova tabela no schema Postgres**: `app.arquivo_bruto` — guarda o
  último arquivo bruto de cada tipo enviado no Upload de Dados. O painel
  agora se restaura sozinho depois de um reboot do Streamlit Cloud (disco
  efêmero apagado): `_garantir_base_pronta()` restaura os arquivos do
  Neon e reprocessa a base automaticamente, sem precisar reenviar arquivo
  que não mudou. Upload manual só é necessário quando há arquivo novo de
  verdade. **Requer rodar de novo `config/schema_postgres.sql` no Neon**
  (idempotente — só cria a tabela nova, não afeta as existentes).

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
