-- Schema de segurança e negócio do Painel Orçamento GGSP — Neon Postgres.
--
-- Rode este script inteiro no console SQL do Neon (Dashboard > seu projeto >
-- SQL Editor) ou via `psql "$POSTGRES_URL" -f config/schema_postgres.sql`.
-- Idempotente (pode rodar de novo sem duplicar nada).
--
-- Este banco guarda SÓ o que precisa sobreviver entre reprocessamentos do
-- painel: usuários, justificativas, delegação e auditoria. O warehouse
-- analítico (dim_*/fact_orcamento/fact_realizado/...) continua em DuckDB
-- local, gerado do zero a cada upload por build_star_schema.py — não entra
-- aqui (decisão de 2026-08-26: não existe "histórico de base" a preservar,
-- e exportação sempre sai da base recém-processada).
--
-- Sem Row Level Security: o painel Streamlit fala com este banco usando uma
-- única connection string, server-side (nunca exposta ao navegador) — quem
-- decide "pode ou não" é o código Python (src/auth/permissions.py), não uma
-- policy de banco por usuário autenticado (não há client per-user aqui,
-- diferente de um app que fala direto com o Postgres do navegador).

create schema if not exists app;

-- ---------------------------------------------------------------------------
-- app.usuario
-- Login e RBAC próprios (sem depender de nenhum provedor de auth externo).
-- Senha nunca em texto plano — só o hash bcrypt.
-- ---------------------------------------------------------------------------
create table if not exists app.usuario (
    id uuid primary key default gen_random_uuid(),
    matricula text unique,
    email text unique,
    senha_hash text not null,
    nome_completo text not null,
    papel text not null check (papel in ('gg', 'gerente', 'especialista_analista', 'admin')),
    gg_id text,
    gerencia_id text,
    ativo boolean not null default true,
    permissao_upload boolean not null default false,
    permissao_exportacao boolean not null default true,
    permissao_justificativa_macro boolean not null default false,
    permissao_justificativa_micro boolean not null default false,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    ultimo_login timestamptz,
    -- Adicionado 2026-08-28: usuário criado pela Administração sempre com
    -- senha temporária única e essa flag ligada — obriga trocar no
    -- primeiro login antes de ver qualquer página (ver src/auth/login.py).
    precisa_trocar_senha boolean not null default false,

    constraint chk_login_tem_identificador check (matricula is not null or email is not null)
);

comment on table app.usuario is
    'Login e RBAC próprios do painel. senha_hash é sempre bcrypt — nunca gravar/logar senha em texto plano. Usuário inativo (ativo=false) não deve acessar nada — checar sempre no app.';

-- app.usuario já existe em produção — "create table if not exists" acima
-- não adiciona coluna nova numa tabela que já existe. ALTER explícito,
-- idempotente (ADD COLUMN IF NOT EXISTS é sintaxe nativa do Postgres).
alter table app.usuario add column if not exists precisa_trocar_senha boolean not null default false;

-- ---------------------------------------------------------------------------
-- app.fact_explicacao_log
-- Log append-only da justificativa de causa (Macro=Pacote / Micro=Conta ou
-- Centro de Custo) — ver docs/03-processo-justificativas-causas.md, seção 2.2.
-- Regra de ouro: NUNCA fazer UPDATE de valor/descrição numa linha existente.
-- Toda edição insere uma linha nova com versao+1 e vigente=true; a versão
-- anterior vira vigente=false (única exceção de UPDATE permitida, feita pela
-- aplicação na mesma transação do INSERT novo).
-- ---------------------------------------------------------------------------
create table if not exists app.fact_explicacao_log (
    id bigserial primary key,
    explicacao_id uuid not null,
    versao int not null,
    vigente boolean not null default true,
    gg_id text not null,
    pacote_id text not null,
    conta_interna_id text,
    centro_custo_id text,
    nivel text not null check (nivel in ('macro', 'micro')),
    ano int not null,
    mes int not null check (mes between 1 and 12),
    categoria text not null,
    valor_explicado numeric not null,
    descricao text not null,
    refs_micro text[],
    autor_id uuid not null references app.usuario (id),
    autor_nome text not null,
    autor_gerencia text not null,
    criado_em timestamptz not null default now(),
    substitui_id uuid,
    motivo_edicao text,
    status_ciclo text not null default 'rascunho' check (status_ciclo in ('rascunho', 'consolidado')),
    origem text not null default 'dashboard' check (origem in ('dashboard', 'importacao_legado')),

    -- nível micro exige exatamente 1 dos 2 campos; nível macro exige nenhum.
    constraint chk_nivel_campos check (
        (nivel = 'macro' and conta_interna_id is null and centro_custo_id is null)
        or
        (nivel = 'micro' and (
            (conta_interna_id is not null and centro_custo_id is null)
            or
            (conta_interna_id is null and centro_custo_id is not null)
        ))
    ),
    constraint chk_categoria_nao_e_calculada check (categoria <> 'Não Justificado')
);

create index if not exists idx_explicacao_vigente
    on app.fact_explicacao_log (explicacao_id, vigente)
    where vigente = true;

create index if not exists idx_explicacao_pacote_periodo
    on app.fact_explicacao_log (pacote_id, ano, mes)
    where vigente = true;

comment on table app.fact_explicacao_log is
    'Log append-only de justificativa de causa. Nunca fazer UPDATE de valor/descrição numa linha existente — sempre INSERT de nova versão. O motor de cálculo (calcular_explicacao) só soma vigente=true.';

-- ---------------------------------------------------------------------------
-- app.delegacao_justificativa
-- Preparação para a delegação futura: um Gerente delega a um Especialista/
-- Analista a responsabilidade de justificar um recorte específico (Pacote OU
-- Conta OU Centro de Custo). Schema nasce agora; a tela de delegação (UI)
-- fica para uma entrega futura — não implementar UI ainda.
-- ---------------------------------------------------------------------------
create table if not exists app.delegacao_justificativa (
    id uuid primary key default gen_random_uuid(),
    gerente_id uuid not null references app.usuario (id),
    especialista_id uuid not null references app.usuario (id),
    pacote_id text,
    conta_interna_id text,
    centro_custo_id text,
    vigencia_inicio date not null default current_date,
    vigencia_fim date,
    ativo boolean not null default true,
    criado_em timestamptz not null default now(),

    constraint chk_delegacao_tem_escopo check (
        pacote_id is not null or conta_interna_id is not null or centro_custo_id is not null
    )
);

comment on table app.delegacao_justificativa is
    'Preparação para delegação de responsáveis por justificativa (Gerente -> Especialista/Analista). Schema criado agora; UI de delegação é entrega futura.';

-- ---------------------------------------------------------------------------
-- app.log_auditoria
-- Toda mutação relevante (upload, gestão de usuário, justificativa) grava
-- aqui: quem, quando, o quê. Nunca apagar linhas desta tabela pela aplicação.
-- ---------------------------------------------------------------------------
create table if not exists app.log_auditoria (
    id bigserial primary key,
    usuario_id uuid references app.usuario (id),
    acao text not null,
    recurso text not null,
    detalhe jsonb,
    criado_em timestamptz not null default now()
);

comment on table app.log_auditoria is
    'Log de auditoria append-only: toda mutação (upload, gestão de usuário, justificativa) grava aqui. Nunca editar/apagar por aqui.';

-- ---------------------------------------------------------------------------
-- app.arquivo_bruto
-- Cópia de segurança dos arquivos brutos de upload (data/raw/), um por
-- "tipo" (mesmas chaves de TIPOS_ARQUIVO em app.py: base_zero, realizado,
-- cji4_capex_obras etc.) — sempre o ÚLTIMO enviado, sobrescrito a cada novo
-- upload (on conflict). Existe porque o disco do Streamlit Community Cloud
-- não é garantido entre reboots (ver docs/05); com isso, o painel consegue
-- se restaurar sozinho sem precisar reenviar arquivo que não mudou —
-- upload manual só é necessário quando há um arquivo novo de verdade.
-- ---------------------------------------------------------------------------
create table if not exists app.arquivo_bruto (
    tipo text primary key,
    nome_original text not null,
    conteudo bytea not null,
    tamanho_bytes int not null,
    enviado_por uuid references app.usuario (id),
    enviado_em timestamptz not null default now()
);

comment on table app.arquivo_bruto is
    'Backup do último arquivo bruto de cada tipo enviado via Upload de Dados — permite restaurar data/raw/ automaticamente após um reboot do Streamlit Cloud, sem reenviar arquivo que não mudou.';

-- =============================================================================
-- Extensão 2026-08-28: Administração (permissão por página, escopos, upload
-- versionado, exportação auditada). Integração do pacote de melhorias v3.4.0
-- trazido pelo usuário — 4 tabelas novas, não 5: o pacote propunha
-- `app.log_atividade`, redundante com `app.log_auditoria` já existente acima
-- (mesmas colunas, mesmo propósito) — reaproveitada em vez de duplicada.
-- Idempotente, não toca nas tabelas já criadas acima.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- app.permissao_pagina
-- Override por usuário de quais páginas ele vê — chave (`pagina`) usa os
-- mesmos identificadores da navegação em app.py (ver PAGINAS em
-- src/dashboard/administracao.py). Sem linha para um (usuario_id, pagina),
-- o acesso é permitido por padrão — mantém compatibilidade com usuário já
-- existente antes desta tabela existir (ver `can_acessar_pagina` em
-- src/auth/permissions.py). Admin sempre acessa tudo, independente do que
-- estiver aqui (checado em código, não precisa de linha própria).
-- ---------------------------------------------------------------------------
create table if not exists app.permissao_pagina (
    usuario_id uuid not null references app.usuario (id) on delete cascade,
    pagina text not null,
    permitido boolean not null default true,
    atualizado_em timestamptz not null default now(),
    primary key (usuario_id, pagina)
);

comment on table app.permissao_pagina is
    'Override por usuário de visibilidade de página. Sem linha = permitido (compatibilidade com usuário pré-existente). Admin ignora esta tabela, sempre acessa tudo.';

-- ---------------------------------------------------------------------------
-- app.escopo_acesso
-- Recorte de dado que um usuário pode ver (Projeto/Elemento PEP/PEP
-- Filho/Gerência/Gerência de Obras/Centro de Custo/Pacote) —
-- infraestrutura de cadastro/consulta só; NENHUMA página aplica isso em
-- filtro de consulta
-- ainda (decisão deliberada, ver docs/06-administracao-auditoria-e-
-- projecao.md — aplicar automaticamente sem validar contra o schema real
-- de cada página arrisca alterar total/reconciliação). Admin não usa
-- escopo (sempre vê tudo).
-- ---------------------------------------------------------------------------
create table if not exists app.escopo_acesso (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null references app.usuario (id) on delete cascade,
    tipo text not null check (tipo in (
        'projeto', 'elemento_pep', 'pep_filho', 'gerencia', 'gerencia_obras', 'coordenacao', 'centro_custo', 'pacote'
    )),
    valor text not null,
    descricao text,
    ativo boolean not null default true,
    criado_em timestamptz not null default now(),
    unique (usuario_id, tipo, valor)
);

comment on table app.escopo_acesso is
    'Cadastro de escopo de dado por usuário. Só cadastro/consulta por enquanto — nenhuma query de dashboard aplica isso ainda, ver docs/06.';

-- Migração 2026-08-29: adiciona 'gerencia_obras' à lista de tipos aceitos
-- (o CHECK acima só vale pra CRIAÇÃO da tabela — precisa rodar de novo
-- no Neon já existente). Nome padrão do Postgres pra CHECK inline sem
-- nome próprio é "<tabela>_<coluna>_check"; "if exists" torna seguro
-- rodar mesmo se o nome de fato divergir. 'coordenacao' continua
-- aceito no banco (não removido do CHECK) mesmo saindo da lista
-- selecionável da tela — evita quebrar qualquer linha já cadastrada
-- com esse tipo, sem precisar conferir se existe alguma.
alter table app.escopo_acesso drop constraint if exists escopo_acesso_tipo_check;
alter table app.escopo_acesso add constraint escopo_acesso_tipo_check check (tipo in (
    'projeto', 'elemento_pep', 'pep_filho', 'gerencia', 'gerencia_obras', 'coordenacao', 'centro_custo', 'pacote'
));

-- ---------------------------------------------------------------------------
-- app.artefato_exportado
-- Cópia auditada de todo arquivo exportado (CSV/XLSX/etc.) pelo painel —
-- guarda o conteúdo inteiro, não só o registro, pra permitir re-baixar a
-- cópia exata que foi exportada num momento passado.
-- ---------------------------------------------------------------------------
create table if not exists app.artefato_exportado (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid references app.usuario (id),
    nome_arquivo text not null,
    conteudo bytea not null,
    tamanho_bytes bigint not null,
    sha256 text not null,
    filtros jsonb not null default '{}'::jsonb,
    criado_em timestamptz not null default now()
);

comment on table app.artefato_exportado is
    'Cópia auditada de cada exportação feita pelo painel — conteúdo completo, não só metadado, pra re-baixar a cópia exata.';

-- ---------------------------------------------------------------------------
-- app.arquivo_bruto_versao
-- Histórico VERSIONADO dos uploads (complementa `app.arquivo_bruto`, que
-- guarda só a última versão de cada tipo pro auto-restore de reboot —
-- essa tabela continua existindo e funcionando como estava). Cada upload
-- soma uma linha nova aqui, nunca sobrescreve — permite reverter pra uma
-- versão anterior pela tela de Administração.
-- ---------------------------------------------------------------------------
create table if not exists app.arquivo_bruto_versao (
    id uuid primary key default gen_random_uuid(),
    tipo text not null,
    nome_original text not null,
    conteudo bytea not null,
    tamanho_bytes bigint not null,
    enviado_por uuid references app.usuario (id),
    enviado_em timestamptz not null default now(),
    ativo boolean not null default true
);

create index if not exists idx_arquivo_bruto_versao_tipo
    on app.arquivo_bruto_versao (tipo, enviado_em desc);

comment on table app.arquivo_bruto_versao is
    'Histórico versionado de uploads — cada envio soma uma linha, nunca sobrescreve. app.arquivo_bruto continua guardando só a última versão (auto-restore de reboot); esta tabela é pra reversão manual pela Administração.';
