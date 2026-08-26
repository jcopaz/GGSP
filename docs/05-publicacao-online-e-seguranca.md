# 05 — Publicação Online, Segurança e Camadas Futuras

**Status: Camada 1 (fundação de dados) em preparação — script pronto,
aguardando você criar o projeto Neon.** Ver plano completo aprovado em
2026-08-26 (login, RBAC, gestão de usuários, captura de justificativas,
deploy) — arquitetura de 5 camadas, entregues em micro-sessões.

**Atualizado em 2026-08-26 (2ª revisão)**: a versão original deste documento
usava Supabase; foi abandonada porque a conta já tinha os 2 projetos free do
Supabase ocupados (o limite é por conta, não por Organization) e porque o
MRS Sentinel (fonte do "padrão de login" que a gente queria copiar) também
roda sobre Supabase — copiar o padrão dele não removia a dependência. Decisão
final: **Neon Postgres** (sem limite de projeto por conta, sem expiração
como o Render free) + **autenticação própria** (bcrypt), reaproveitando só as
partes do MRS Sentinel que já são independentes de backend (sessão,
permissões, envio de e-mail via Brevo). Detalhe completo em
"Histórico de decisão" no plano.

Outra simplificação da mesma rodada: o **warehouse não entra no Postgres**.
O pipeline (`build_star_schema.py`) já reconstrói tudo do zero a cada upload
— não existe histórico de base a preservar, e exportação sempre sai da base
recém-processada. Só o que precisa sobreviver entre reprocessamentos vai pro
banco: usuário, justificativa, delegação, auditoria.

## Por que isso agora

O painel roda hoje 100% local: sem git, sem login, dado analítico em arquivo
DuckDB (`data/warehouse/painel.duckdb`). Publicar online para
especialistas/analistas acessarem exige uma camada de segurança que
simplesmente não existe ainda — o painel mostra valores de Orçado/Realizado
por Gerência/Pacote/Conta, dado sensível da MRS.

## Passo a passo — criar o projeto Neon (você faz, uma vez)

1. Acesse https://neon.tech e crie uma conta (pode logar com GitHub/Google
   ou e-mail).
2. **Create a project** — nome (ex. `orcamento-ggsp`), região mais próxima
   do Brasil disponível (`AWS South America (São Paulo)` se aparecer, senão
   `AWS US East` é a alternativa mais comum).
3. Espere provisionar (segundos, é bem mais rápido que Supabase).
4. No dashboard do projeto, vá em **SQL Editor** (ou **Console**), cole o
   conteúdo inteiro de
   [`config/schema_postgres.sql`](../config/schema_postgres.sql) e rode.
   Isso cria o schema `app` com as 4 tabelas: `usuario`,
   `fact_explicacao_log`, `delegacao_justificativa`, `log_auditoria`.
5. Vá em **Connection Details** (ou **Dashboard > Connect**), copie a
   **Connection string** (formato
   `postgresql://usuario:senha@ep-xxxx....neon.tech/neondb?sslmode=require`).
6. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`
   (mesma pasta) e cole a connection string em `postgres_url`. **Não me
   envie esse valor pelo chat** — preencha direto no arquivo local.
7. (Pode ficar para a Camada 2) Preencha também a seção `[smtp]` com uma
   credencial SMTP da Brevo — pode reaproveitar a mesma do MRS Sentinel ou
   gerar uma nova em app.brevo.com > SMTP & API > SMTP.

Quando isso estiver feito, me avise para eu criar o primeiro usuário Admin
(script único, roda uma vez) e seguirmos para a Camada 2 (tela de login).

## Onde isso se encaixa no plano completo

| Camada | O quê | Status |
|---|---|---|
| 1. Fundação de dados | Schema Neon (usuário/RBAC, justificativas, delegação, auditoria) | Script pronto (`config/schema_postgres.sql`); aguardando você criar o projeto |
| 2. Autenticação | Login próprio (bcrypt), gate de sessão no `app.py`, reset de senha via Brevo | Não iniciado |
| 3. RBAC + Gestão de Usuários | Papéis, permissões granulares, tela de administração de usuários | Não iniciado |
| 4. Captura de Justificativas | Materializa `docs/03-processo-justificativas-causas.md`: Fila de Pendências, Input Macro/Micro, auditoria, tooltips | Não iniciado |
| 5. Deploy | `git init`, repo privado, Streamlit Community Cloud | Não iniciado |

## Decisões de segurança já fechadas

- **Senha nunca em texto plano**: só hash bcrypt em `app.usuario.senha_hash`.
- **`postgres_url` só existe no servidor** (`st.secrets`, nunca no
  navegador) — o painel Streamlit roda 100% server-side em Python.
- **Fail closed por padrão**: usuário inativo nunca acessa nada; sem
  permissão explícita = sem acesso, checado em código Python antes de
  renderizar qualquer página (sem Row Level Security no banco — não há
  client per-usuário direto no Postgres aqui, então a linha de frente é o
  código, mesma escolha já validada em produção pelo MRS Sentinel).
- **Justificativa é log append-only**: nunca `UPDATE` num registro
  existente, toda edição é uma nova versão.
- **Warehouse fica fora do Postgres**: `dim_*`/`fact_orcamento`/
  `fact_realizado`/etc. continuam em DuckDB local, recriados do zero a cada
  upload — sem risco de misturar com dado que precisa persistir (usuário,
  justificativa).
- **Reset de senha**: gera senha temporária no servidor, grava o hash bcrypt
  direto no Postgres, envia por e-mail via SMTP da Brevo — nunca revela se
  um e-mail/matrícula existe na mensagem de erro.
