# 10 — Revisão de Cibersegurança do Fin360

**Data:** 2026-09-07 · **Escopo:** `src/auth/*`, `config/schema_postgres.sql`,
`app.py` (gate de sessão), pipeline de upload, dependências.
**Método:** leitura de código + `bandit` (SAST) + `detect-secrets` +
`pip list --outdated` + revisão manual de CVE. `pip-audit` **não roda neste
ambiente** (proxy da MRS intercepta TLS — `SSLCertVerificationError`); precisa
rodar em CI (GitHub Actions) ou rede sem proxy.

---

## 1. Sumário executivo

O núcleo de autenticação **já segue boa prática**: bcrypt com salt por
usuário, sem senha em texto plano, SQL 100% parametrizado, XSS mitigado com
`html.escape` nas árvores HTML, mensagens de erro genéricas (sem enumeração
de conta), segredos fora do git.

**Nenhum achado ALTO/crítico.** Os gaps são de *defesa em profundidade* e
*higiene operacional*:

| # | Achado | Severidade | Status |
|---|---|---|---|
| A1 | Sem rate limit / lockout no login (tentativas ilimitadas) | **Média-Alta** | **corrigido em 10.0.0** (ver §4) |
| A2 | `ORCAMENTO_SKIP_LOGIN=1` = bypass total de auth por env var, sem trava dura | Média | aberto (P0) |
| A3 | Sem RLS no Postgres (gate só em Python) | Média | aberto (P2) |
| A4 | Segredos (`secrets.toml`) em texto plano em disco, sem vault/rotação | Média | aberto (P1) |
| A5 | `pip-audit` não roda no ambiente → sem varredura de CVE de dependência | Média | aberto (P0 — mover p/ CI) |
| A6 | `render_page_banner()` injeta `titulo`/`subtitulo` sem escapar (hoje só literais) | Baixa | aberto (P1) |
| A7 | `bandit` B608 x70 (f-string em SQL) — falso-positivo do padrão de query-builder | Baixa (informativo) | documentar convenção |
| A8 | `bandit` B110 x6 (`try/except/pass` em auditoria best-effort) | Baixa | aceitável, estreitar exceção |
| A9 | `psycopg2-binary` em produção (bundla libpq/OpenSSL própria, pode atrasar patch) | Baixa | avaliar `psycopg2` fonte |
| A10 | `Fin360_projeto_completo_reenvio/` = clone do projeto no working tree (gitignored) | Baixa | apagar quando não precisar mais |
| A11 | `enableStaticServing = true` — qualquer arquivo em `static/` é público sem auth | Baixa | manter `static/` só com asset de marca |

---

## 2. O que está correto (não regredir)

- **Hash de senha:** `src/auth/senha.py` — `bcrypt.hashpw(…, bcrypt.gensalt())`
  + `bcrypt.checkpw` (comparação em tempo constante). `senha_hash text not null`
  no schema, comentário explícito "nunca gravar/logar senha em texto plano".
  Já houve revisão automática anterior que removeu senha-padrão hardcoded
  (`Fin360@123`, HIGH).
- **SQL Injection:** Neon via `%s` (`src/auth/queries.py`, `admin_queries.py`);
  DuckDB via placeholder `?` + lista de params (`src/dashboard/filtros.py` e
  motores). Identificadores em f-string (`dims`, `coluna`, `tabela`) são
  **literais de código**, nunca entrada de usuário.
- **XSS:** Streamlit escapa por padrão. Onde há `unsafe_allow_html=True` com
  dado de planilha (`arvore_html.py`, heatmaps) → `html.escape()` em todo
  rótulo/valor.
- **Enumeração de conta:** login e "esqueci a senha" devolvem a mesma
  mensagem exista ou não a conta.
- **Segredos:** `postgres_url` + SMTP em `st.secrets` (`.streamlit/secrets.toml`),
  **gitignored e nunca rastreado** (confirmado: só `secrets.toml.example`
  entrou no git, é placeholder). Nunca vão ao browser (app 100% server-side).
- **Transporte:** Neon exige TLS; connection string usa `sslmode=require`.
- **Sessão:** server-side (`st.session_state`), sem cookie/JWT próprio exposto.
- **Auditoria:** `app.log_auditoria` grava login / troca de senha / reset.
- **1º acesso:** troca de senha obrigatória, senha temporária única
  (`secrets.choice`), mínimo 8 caracteres.
- **Fail-closed:** usuário `ativo=false` não acessa nada; sem permissão
  explícita = sem acesso, checado em Python antes de renderizar.

---

## 3. Resultado das ferramentas

### 3.1 bandit 1.9.4 (`bandit -r src app.py`)

```
Total lines of code: 9653
High: 0   Medium: 70   Low: 6
```

- **B608 hardcoded_sql_expressions (Medium × 70)** — todo o núcleo de
  query-builder (`delta_calculator`, `fila_pendencias`, `filtros`, níveis).
  Revisado 1 a 1: interpolam **nome de tabela/coluna e fragmento `WHERE`
  pré-montado que já usa `?`+params**. Sem concatenação de entrada de
  usuário. **Falso-positivo do estilo.** Ação: convenção documentada
  (§5) + `# nosec B608` com justificativa nas linhas, OU baseline do bandit.
- **B110 try_except_pass (Low × 6)** — `app.py:289`, `auth/audit.py:17,31`,
  `auth/login.py:98,193`, `auth/recuperar_senha.py:98`. São os blocos
  best-effort ("auditoria nunca derruba a ação principal"). Legítimos;
  melhorar estreitando o `except` e logando em nível debug.

### 3.2 detect-secrets 1.5.0 (`scan --all-files`)

| Arquivo | Achado | Veredito |
|---|---|---|
| `.streamlit/secrets.toml:10,20` | Basic Auth + Base64 alta entropia | **segredo real, mas NÃO rastreado no git** — só disco local. OK p/ dev; ver §4 (A4). |
| `.streamlit/secrets.toml.example` (+ `.txt`, + clone) | Basic Auth placeholder | placeholder, inofensivo. |
| `docs/05-…:48` | Basic Auth placeholder | idem. |
| `.pytest_cache/CACHEDIR.TAG` | Hex alta entropia | falso-positivo (marcador padrão). |

**Histórico do git limpo:** `git log --all --diff-filter=A` só mostra
`secrets.toml.example` — nenhum segredo real jamais commitado.

### 3.3 Dependências (`pip list --outdated` — pip funciona, pip-audit não)

| Pacote | Instalado | Última | Nota de CVE (revisão manual, base jan/2026) |
|---|---|---|---|
| streamlit | 1.57.0 | 1.63.0 | sem CVE crítico conhecido na 1.57; bump recomendado. |
| tornado | 6.5.5 | 6.5.8 | DoS multipart (CVE-2025-47287) corrigido na 6.5.0 → 6.5.5 já cobre; bump é higiene. |
| jinja2 | 3.1.6 | 3.1.6 | 3.1.6 corrige o sandbox escape CVE-2025-27516 → **já patched**. |
| urllib3 | 2.7.0 | — | redirect CVE-2025-50181/50182 corrigido na 2.5.0 → coberto. |
| pyarrow | 24.0.0 | 25.0.1 | RCE de deserialização (CVE-2023-47248) corrigido na 14.0.1 → coberto. |
| pandas | 3.0.3 | 3.0.5 | sem crítico conhecido. |
| numpy | 2.4.6 | 2.5.3 | sem crítico conhecido. |
| psycopg2-binary | 2.9.12 | — | ver A9 — em produção preferir `psycopg2` (fonte) ou `psycopg[binary]` v3. |
| openpyxl / pyxlsb | 3.1.5 / 1.0.10 | — | parseiam Excel de upload — superfície de XML/zip bomb; upload é gated por `permissao_upload`. |

**Ação obrigatória (A5):** `pip-audit -r requirements.txt` num job de CI
(GitHub Actions `pip-audit` ou `pypa/gh-action-pip-audit`) — é onde a
varredura de CVE tem que viver, já que o ambiente de dev não alcança a base
de vulnerabilidade.

---

## 4. Correção A1 — rate limit de login (entregue em 10.0.0)

**Problema:** `_autenticar` (`src/auth/login.py`) aceitava tentativas
ilimitadas. O único freio era um cooldown de 60 s **client-side**
(`st.session_state`) no "esqueci a senha" — burlável recarregando a aba.

**Solução:**

- Tabela `app.tentativa_login (identificador, ip, sucesso, ocorrido_em)` +
  índices por `(identificador, ocorrido_em)` e `(ip, ocorrido_em)`.
- `src/auth/ratelimit.py`:
  - `avaliar_bloqueio(tentativas, agora)` — **função pura** (testável):
    conta falhas **depois do último sucesso**, dentro de uma janela de
    15 min; a partir de **5 falhas** bloqueia por **15 min** (a contar da
    última falha). Retorna `(bloqueado, segundos_restantes)`.
  - `checar_bloqueio(identificador, ip)` / `registrar_tentativa(…)` —
    invólucros que falam com o Neon. **Falha-aberta na checagem** se o
    banco cair (não trava login legítimo) — aceitável porque sem banco o
    próprio `_autenticar` já não autentica ninguém.
- `_autenticar`: checa bloqueio (por `identificador` **e** por `ip`) antes
  do `verificar_senha`; registra toda tentativa (sucesso/falha); mensagem
  de bloqueio é neutra ("Muitas tentativas de login. Aguarde ~15 min.") —
  não confirma se a conta existe.
- IP obtido de `st.context.headers["X-Forwarded-For"]` quando atrás de
  proxy (Streamlit Cloud); `None` → limita só por `identificador`.
- `tests/rate_limit_check.py` — pytest da função pura (janela, reset por
  sucesso, expiração do bloqueio, contagem por identificador × IP).

**Retenção:** `app.tentativa_login` cresce devagar (só login); limpar linhas
> 30 dias num job de manutenção quando houver um.

---

## 5. Convenção anti-B608 (query-builder seguro)

Regra do projeto para toda query montada com f-string:

1. **Só identificadores de código** entram por interpolação — nome de
   tabela, nome de coluna, fragmento `WHERE` **que já veio de um helper de
   `filtros.py`** (e esse helper usa `?` + params).
2. **Todo valor** (inclusive de sessão / do usuário) entra **só** como `?`
   / `%s` + lista de params. Nunca em f-string.
3. Fragmentos de escopo (`clausula_escopo*`) retornam `("", [])` /
   `(" AND col IN (?,?)", [...])` — o texto é fixo, os valores viajam nos
   params.
4. Linha sinalizada pelo bandit que cumpre (1)–(3) leva
   `# nosec B608  # identificador de código, valores via params`.

---

## 6. Plano priorizado (restante)

| Prio | Item | Esforço | Achado |
|---|---|---|---|
| P0 | `pip-audit` em CI (GitHub Actions) | ~2 h | A5 |
| P0 | `SKIP_LOGIN`: abortar se `st.secrets` indicar produção; log de alerta | ~1 h | A2 |
| P1 | Pepper de senha via `st.secrets` (sem trocar bcrypt) + cost factor 12 | ~2 h | — |
| P1 | Segredos no secrets-manager da plataforma de deploy (fora do disco) | ~2 h | A4 |
| P1 | `render_page_banner` escapando + lint contra `unsafe_allow_html`+f-string de dado | ~1 h | A6 |
| P1 | `# nosec B608` + baseline do bandit no CI | ~1 h | A7 |
| P2 | RLS em `app.fact_explicacao_log` (policy por `usuario_id` via `set_config`) | ~1 dia | A3 |
| P2 | MFA TOTP opcional em `app.usuario` (`otp_secret`) | ~1 dia | — |
| P2 | Estreitar `except` dos blocos best-effort + log debug | ~2 h | A8 |
| P3 | Avaliar `psycopg2` fonte vs `-binary`; Keycloak/OIDC/Vault se a MRS pedir SSO | grande | A9 |
| — | `sslmode=verify-full` + CA do Neon | ~1 h | — |

---

## 7. Como rodar a bateria de segurança (dev)

```bash
pip install bandit detect-secrets            # pip-audit só em CI (TLS proxy)
python -m bandit -r src app.py -ll           # SAST — 0 High é o gate
python -m detect_secrets scan --all-files    # nada fora de secrets.toml (não rastreado)
python -m pytest tests/rate_limit_check.py tests/test_rbac_escopo.py -q
git log --all --diff-filter=A --name-only | grep -iE 'secret|\.env|\.pem|\.key' || echo ok
```
