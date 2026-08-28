# Changelog — Fin360 (Painel Orçamento GGSP)

Versionamento SemVer (ver `src/versao.py`): MAJOR = tela nova/schema/
segurança/integridade de dado; MINOR = funcionalidade nova sem quebrar
nada; PATCH = correção de bug. Bump a cada commit relevante.

## 3.2.0 — 2026-08-28

- **Logo da sidebar via `st.logo()`** — substitui a tentativa de CSS
  (que não funcionava: o menu de `st.navigation()` fixa a própria
  posição, independente da ordem de chamada no script). Frame estático
  extraído de `fin360.mp4` (`src/dashboard/static/fin360_logo.png`) —
  `st.logo()` só aceita imagem, não vídeo.
- **Tema próprio no `config.toml`** (`primaryColor` dourado): corrige o
  vermelho de fábrica do Streamlit em widgets nativos (tags de
  multiselect, botão "Aplicar filtros") que ficava ilegível contra a
  sidebar navy. Fundo do conteúdo principal voltou a branco
  (`backgroundColor`), revertendo o cinza-azulado testado antes.
- Filtro de Período (Ano/Trimestre/Mês) não fica mais dentro de um
  expander recolhido — estático, sempre visível.
- **Novo `render_page_banner()`** (`src/branding.py`): card em gradiente
  navy/dourado pro cabeçalho de página (ícone + título + subtítulo
  curto), substituindo `st.header()` + parágrafo longo de legenda.
  Aplicado em "CAPEX Obras — Especialista" e "Contas" (CAPEX) nesta
  rodada — mesmo padrão de banner usado em outros apps do usuário,
  personalizado pra identidade do Fin360.
- Testado via AppTest (app.py inteiro + os 2 banners novos contra o
  warehouse local real) antes de publicar.

## 3.1.2 — 2026-08-28

- Removido o `st.title` redundante do topo de toda página (pedido do
  usuário: "reduza o texto, deixe só o essencial") — a marca já fica
  fixa na sidebar, cada página já tem seu próprio `st.header` curto.
- "Nível 4 — Contas (CAPEX)" encurtado pra "Contas", legenda longa
  reduzida a uma linha.
- Sidebar reestruturada: bloco de marca (logo/Fin360/usuário/Sair) no
  topo, rodapé fixo (só "v{versão}" + "Desenvolvido por Julio Paz")
  depois de toda a navegação — chamado depois de `pg.run()` de propósito.
- Tentativa de reordenar a logo pra cima do menu de navegação via CSS
  (`order` em flexbox) — **não verificado visualmente** (sem navegador
  neste ambiente), pode precisar de ajuste depois de olhar ao vivo.
- Testado via `AppTest` rodando `app.py` inteiro de ponta a ponta antes
  de publicar (sem exceção).

## 3.1.1 — 2026-08-28

- Keep-awake do fin360.streamlit.app via GitHub Actions (ping a cada 30
  min, `.github/workflows/keep-awake.yml`) — evita o app dormir por
  inatividade no plano free do Streamlit Community Cloud.
- Registrado: o "Reboot app" manual às vezes é necessário mesmo com push
  novo — o redeploy automático pode ficar com arquivo desatualizado em
  cache (visto em produção 2026-08-28, `ImportError` de `inject_shell_css`
  mesmo com o repositório remoto 100% consistente).

## 3.1.0 — 2026-08-27

- **Casca visual nova** (aprovada pelo usuário): sidebar navy sólido com
  indicador dourado só no item de navegação ativo (marca vira parte da
  navegação, não só do login); fundo do conteúdo em cinza-azulado; tipografia
  `Fraunces` (títulos) + `IBM Plex Sans` (interface) + `IBM Plex Mono`
  (número) em todo o painel — `src/branding.py::inject_shell_css()`.
- **Card de GG (Nível 1) redesenhado**: hierarquia rótulo → Delta grande
  em monoespaçada → chip de status, em vez da tabela markdown antiga.
  Chip reaproveita as cores reais do semáforo (`paleta.py`:
  `COR_ADERENCIA_OK/ATENCAO/FORA`, novo `COR_ROXO`) — nova função
  `fmt_semaforo_chip()` em `formatacao.py`. Paleta de gráfico intocada.
- Testado via `AppTest` (render sem exceção, inclusive caso limite sem
  orçamento/aderência indefinida) antes de publicar.

## 3.0.1 — 2026-08-27

- Tela de login: "Fin360" e "Acesso Restrito" (removida a menção à GG,
  pedido do usuário) centralizados abaixo da logo, versão centralizada
  abaixo disso. Assinatura "Desenvolvimento: Julio Paz" no rodapé.
- Sidebar: logo + "Fin360" + versão centralizados no topo (acima do
  bloco "Plano de Manutenção"), separados por divisor do bloco de
  identidade/logout do usuário logado.

## 3.0.0 — 2026-08-27

- **`fact_pce_realizado` deixa de depender de "PCE Base Luiz.xlsx"**
  (planilha curada manualmente) — agora derivada em código do CJI3 +
  Catálogo CAPEX Obras (nova tabela De/Para `Objeto → Classificação`,
  `config/catalogo_objeto_classificacao.csv`, achado empírico: 100%
  determinístico no dado real). Zona de upload `pce_realizado` removida
  — menos uma planilha manual na rotina. Validado contra dado real: mesmo
  total exato do CJI3, sem duplicar/perder valor. Ver
  `docs/04-licoes-aprendidas.md`, item 20. Mudança de integridade de
  dado (como um número central é calculado) — bump MAJOR pela própria
  regra de versionamento do projeto.

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
