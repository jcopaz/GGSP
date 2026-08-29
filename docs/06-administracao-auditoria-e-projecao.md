# 06 — Administração, auditoria e projeção por ritmo

Integração do pacote de melhorias v3.4.0 (trazido pelo usuário em
2026-08-28) ao repositório principal — arquivo por arquivo, não substituição
em bloco. Este doc registra o que ficou, o que foi corrigido, e o que ainda
falta pra funcionar de ponta a ponta.

## Projeção OPEX

Página nova em "Plano de Manutenção" (`src/dashboard/projecao_opex.py`,
`render_page_banner("📈", "Projeção OPEX", ...)`), 3 abas: Despesas Gerais
(PD), Despesas Pessoais (PP), Manutenção (PM).

**Não substitui o Forecast PMO** (`tendencia.py::dados_tendencia`, coluna
`tendencia_acumulada`) — esse continua com a fórmula original intocada
(redistribui o saldo do desvio pelos meses restantes, sempre fecha
dezembro exatamente no Orçado Anual, por construção).

A nova curva (`projecao_ritmo_acumulada`, mesmo módulo) é conceitualmente
diferente: identifica o último mês com Realizado, calcula a média mensal
sobre os meses efetivamente considerados, e projeta essa média pros meses
restantes — **não força nenhuma convergência**, pode fechar acima
(vermelho, `COR_ESTOURO`) ou abaixo (verde, `COR_ECONOMIA`) do Orçado.
Sem nenhum mês com Realizado, a coluna fica vazia (nunca projeta em cima
de nada). Testado manualmente contra o dado real das 3 famílias antes de
publicar (ver CHANGELOG 3.4.0).

O módulo `projecao_opex.py` já tinha sido copiado pro repositório antes
desta integração, mas dependia de uma coluna que nunca tinha sido
implementada em `tendencia.py` — quebraria com `KeyError`. Implementado
nesta rodada.

## Administração

Página nova, exclusiva do papel `admin` (`src/dashboard/administracao.py`,
`require_admin()` logo no início — revalida mesmo se alguém chegar direto
na função). Reúne 4 abas: Usuários (criar/editar, papel, ativo,
permissões operacionais), Permissões e escopos (visão de página por
usuário + cadastro de escopo de dado), Auditoria (histórico de atividade),
Uploads e exportações (histórico versionado + reversão + cópias
auditadas de exportação).

**Escopos de dado (Projeto/Elemento PEP/PEP Filho/Gerência/Coordenação/
Centro de Custo/Pacote) são só cadastro e consulta** — nenhuma página do
painel aplica isso em filtro de query ainda, de propósito (aplicar sem
validar contra o schema real de cada uma arrisca alterar total/
reconciliação, ver regra do pedido original de integração). Fica marcado
aqui como pendência explícita, não escondido.

## Permissão por página (RBAC de navegação)

`src/auth/permissions.py::can_acessar_pagina(pagina)` — admin sempre
acessa tudo; usuário sem override em `app.permissao_pagina` é permitido
por padrão (compatibilidade com quem já existia antes desta tabela).

Em `app.py`, `_pagina_se_permitida()`/`_somente_paginas()` fazem 2 coisas
ao mesmo tempo pra cada página da navegação: (1) escondem do menu se
`can_acessar_pagina` negar, e (2) embrulham a função da página
(`_com_guard_pagina`) pra revalidar a MESMA checagem antes de renderizar
— não confia só em esconder do menu. `chave` de cada página usa os mesmos
identificadores de `PAGINAS` em `administracao.py`; mudar um sem o outro
quebra o editor de permissões (mostraria/salvaria uma chave que a
navegação não reconhece).

A seção "Administração" do menu **não passa por `can_acessar_pagina`** —
checa `is_admin()` direto, hardcoded. Não pode ser liberada por engano
via uma linha errada em `app.permissao_pagina`.

**Correção de segurança sobre o design recebido**: a versão original de
`can_acessar_pagina` (vinda do pacote de melhorias) devolvia `True` se a
consulta ao Postgres falhasse — fail **aberto** (banco caiu, todo mundo
vê tudo). Corrigido pra fail **closed** (nega por padrão), consistente
com o resto do projeto (`require_upload` etc.).

`ORCAMENTO_SKIP_LOGIN=1` (bypass de login só local, ver `docs/05`) libera
tudo em `can_acessar_pagina` também — sem essa saída, o próprio flag de
teste local ficava inútil (sem usuário real de sessão, toda página seria
negada). Nunca fica ligado no deploy.

## Auditoria

`app.log_auditoria` — **não** `app.log_atividade`: o pacote de melhorias
propunha uma tabela nova pra isso, mas é redundante com `log_auditoria`
(já existia desde a Camada 1, mesmas colunas, mesmo propósito) —
reaproveitada em vez de duplicada. `src/auth/audit.py::registrar_atividade`
grava ali; `registrar_visualizacao_pagina` (1x por página por sessão) e
`registrar_exportacao` (grava cópia auditada + entrada de log) usam a
mesma função por baixo. Tudo best-effort — falha de log nunca derruba a
ação principal (`try/except: pass`).

**Achado de performance/robustez**: `src/auth/db.py::conectar()` não
tinha timeout de conexão — numa rede que bloqueia a porta em silêncio
(não recusa, só some, ver `docs/05`), uma chamada de auditoria (agora
disparada a cada visualização de página) travava a página inteira
esperando o timeout padrão do sistema operacional (pode passar de 1
minuto). Corrigido com `connect_timeout=8` — tolera o "scale to zero" do
Neon free (cold start) sem deixar a UI pendurada se o banco estiver mesmo
inalcançável.

## Upload versionado

`app.arquivo_bruto` (já existia, Camada 1) continua guardando só a
**última** versão de cada tipo — é o que o auto-restore de reboot usa
(`_garantir_base_pronta` em `app.py`). `app.arquivo_bruto_versao` (nova)
guarda o **histórico completo** — cada upload soma uma linha, nunca
sobrescreve (`src/ingestion/arquivo_bruto.py::salvar_versao_arquivo`,
chamada junto de `salvar_arquivo_bruto` no mesmo upload, nunca sozinha).
`restaurar_versao_arquivo` (Administração → reverter) sobrescreve o
arquivo local incondicionalmente e também atualiza `arquivo_bruto` (senão
o próximo reboot restauraria a versão errada).

## Exportações

`registrar_exportacao()` existe e funciona, mas **nenhum `st.download_button`
de exportação real foi encontrado no resto do painel** (só o da própria
tela de Administração, pra baixar cópia auditada) — não há, hoje, nenhuma
tela de exportação de CSV/XLSX pra centralizar. Fica registrado como
"infraestrutura pronta, sem consumidor ainda", não como pendência
escondida.

## Senha temporária única + troca obrigatória (2026-08-28, revisado 2026-08-28)

Todo usuário criado pela Administração recebe uma senha temporária
**única e aleatória**, gerada na hora (`src/auth/senha.py::
gerar_senha_temporaria()`, mesma função já usada no reset autoatendido),
mostrada **uma única vez** na tela pra quem criou (`st.code`, sem ficar
gravada em texto plano em lugar nenhum) — quem cria repassa com segurança
pra pessoa. A coluna `app.usuario.precisa_trocar_senha` (migração abaixo)
começa `true`. No próximo login, `app.py` intercepta logo após o gate de
sessão — antes de qualquer página, inclusive antes da casca visual — e
mostra `render_trocar_senha_obrigatoria()` (`src/auth/login.py`): só sai
dali depois de definir uma senha própria (mínimo 8 caracteres).
`scripts/criar_usuario_admin.py` (bootstrap manual, senha digitada na
hora) não ativa a flag — só a criação pela Administração.

Revisão do mesmo dia: a versão original usava uma senha padrão fixa
(`Fin360@123`, literal no código, igual pra todo usuário novo) — achado de
revisão de segurança automática, HIGH, "Hardcoded Credentials / Shared
Default Password" (uma senha vazada expõe todas as contas ainda não
trocadas, e o literal fica visível pra qualquer um com acesso ao
repositório). Substituída por senha temporária única por usuário no mesmo
dia, antes de qualquer deploy com a versão fixa.

## Campos selecionáveis (Gerência/Escopos) (2026-08-28, ampliado 2026-08-29)

O formulário de criar usuário e a aba de Escopos de dados buscam valor
real do **warehouse DuckDB local** (não o Neon) pra virar dropdown/
multiseleção, em vez de texto livre. Escopos selecionáveis usam
`st.multiselect` — dá pra adicionar um, vários ou todos de uma vez, 1
linha em `app.escopo_acesso` por valor selecionado.

Tipos de escopo hoje (`src/dashboard/administracao.py::TIPOS_ESCOPO`):

| Tipo (interno) | Rótulo na tela | Fonte real | Exemplo |
|---|---|---|---|
| `gerencia` | Gerência (Manutenção/OPEX) | `dim_gerencia` | `GGE_0161 — GER ENGENHARIA EMPREEND (SP)` |
| `gerencia_obras` | Gerência (CAPEX Obras) | `dim_catalogo_capex_obras.gerencia_obras` | `Baixada Santista` |
| `elemento_pep` | PEP (Elemento PEP) | `dim_catalogo_capex_obras.e_pep_projeto` | `DM/21973 — Pátio Regulador Jurubatuba` |
| `pep_filho` | PEP Filho | `dim_catalogo_capex_obras.titulo_etapa` | `DM/21973C-04 — Projeto básico` |
| `centro_custo` | Centro de Custo | `fact_realizado` | `código — nome da área` |
| `pacote` | Pacote | `dim_pacote` | `código — nome do pacote` |
| `projeto` | Projeto | — (texto livre) | sem catálogo fechado identificado |

**`gerencia` × `gerencia_obras` são duas taxonomias diferentes, sem código
em comum** — achado 2026-08-29, ver `docs/04-licoes-aprendidas.md` item
22. Não confundir ao ler `app.escopo_acesso`: um usuário pode ter escopo
nas duas ao mesmo tempo, cada um restringindo um universo de dado
diferente (Manutenção/OPEX vs. CAPEX Obras).

**Cascata de negócio do CAPEX Obras** (confirmada pelo usuário
2026-08-29): Gerência (Obras) ⊃ todos os Elemento PEP e PEP Filho daquela
região; Elemento PEP ⊃ todos os PEP Filho (etapas) daquele projeto; PEP
Filho é a etapa/subconta específica. **Essa cascata ainda não é
aplicada em nenhuma tela** — só o cadastro do escopo está pronto (mesmo
status de "infraestrutura pronta, sem consumidor ainda" das seções
acima). Quando a aplicação for construída, ela precisa resolver essa
cascata (um escopo de `gerencia_obras="Baixada Santista"` implica acesso
a todo `elemento_pep`/`pep_filho` daquela Gerência, sem precisar cadastrar
cada um), não tratar os 3 tipos como listas soltas e independentes.

`coordenacao` foi removido da lista de tipos selecionáveis em 2026-08-29
(Centro de Custo já cobre a mesma granularidade — cada Gerência/
Coordenação tem um Centro de Custo) — o valor continua aceito pelo CHECK
do Postgres (`config/schema_postgres.sql`), só não aparece mais como
opção na tela, pra não quebrar nenhuma linha eventualmente já cadastrada
com esse tipo.

`projeto` continua texto livre — não existe uma lista fechada confiável
pra ele na fonte de dado ainda.

`dim_catalogo_capex_obras` (nova, `build_star_schema.py`) materializa o
"Catalago CAPEX Obras.xlsx" (aba Auxiliar) com granularidade completa —
até 2026-08-29 ele só existia como DataFrame transiente, sempre
deduplicado 1 linha por projeto antes de virar `fact_cji3_capex_obras`/
`fact_cji4_capex_obras`/`fact_pce_realizado` (essas 3 tabelas continuam
sem alteração, mesma dedução de antes — a nova dimensão é aditiva, não
substitui nada). Requer reprocessar a base (Upload → Reprocessar) pra
existir num ambiente que ainda não tem essa tabela.

**Requer rodar `config/schema_postgres.sql` de novo no Neon** — o CHECK
de `app.escopo_acesso.tipo` precisa aceitar `'gerencia_obras'` (migração
via `alter table ... drop constraint / add constraint`, idempotente).

`render_administracao()` agora recebe a conexão DuckDB como parâmetro
opcional (`pagina_administracao()` em `app.py` abre se a base estiver
processada); sem base pronta, cai pra texto livre nesses campos sem
quebrar o resto da página.

## Fuso horário (2026-08-28)

Toda data/hora exibida na Administração (Auditoria, histórico de upload,
exportações) converte de `timestamptz` (Postgres, UTC internamente) pra
`America/Sao_Paulo` antes de mostrar (`administracao.py::_fmt_hora_br`).

## Migração pendente (ação do usuário)

Rodar `config/schema_postgres.sql` inteiro no SQL Editor do Neon — é
idempotente, pode rodar de novo sem duplicar nada, e não toca nas tabelas
já existentes (`usuario`, `fact_explicacao_log`, `delegacao_justificativa`,
`log_auditoria`, `arquivo_bruto`). Sem isso, a tela de Administração
quebra ao abrir (tabela inexistente) — código já testado até o ponto de
conexão real (ver CHANGELOG 3.4.x), só falta o schema existir de verdade
no banco.
