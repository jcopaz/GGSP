"""Elementos visuais de marca do Fin360 — vídeo de logo em loop.

Usado tanto na tela de login (src/auth/login.py) quanto na sidebar
(src/dashboard/app.py) — muda aqui, muda nos dois lugares.

Depende de `enableStaticServing = true` em `.streamlit/config.toml` e do
arquivo em `src/dashboard/static/fin360.mp4` (Streamlit serve `static/` a
partir da pasta do script principal, não da raiz do repo — e expõe sempre
em `app/static/...`, independente de onde a pasta física está).

Se o deploy no Streamlit Cloud der `ImportError: cannot import name
'inject_shell_css'` mesmo depois de um Reboot, é cache do próprio
Streamlit Cloud, não deste arquivo (conferido: repositório remoto sempre
consistente) — ver docs/04-licoes-aprendidas.md, item 21.
"""
from __future__ import annotations

import streamlit as st

LOGO_VIDEO_URL = "app/static/fin360.mp4"


def inject_shell_css() -> None:
    """Casca visual do painel inteiro (fundo, sidebar, tipografia).

    Sidebar em navy sólido (identidade de marca) foi a versão aprovada em
    2026-08-27 — **substituída em 2026-08-29** por pedido explícito do
    usuário: os ícones internos do BaseWeb (seta de abrir opções, x de
    remover tag/limpar tudo) continuavam com contraste ruim contra o
    navy mesmo depois de 2 rodadas de correção cirúrgica (cor do ícone,
    depois fundo/borda do botão) — o usuário decidiu trocar o fundo da
    sidebar pra claro em vez de continuar caçando seletor exato do
    BaseWeb. Variáveis `--f360-sidebar-*` viraram tons claros (mesma
    função de cada uma, só valor invertido); `--f360-gold` não muda —
    accent dourado funciona em qualquer fundo.

    - Sidebar em cinza-azulado claro (mesmo tom de `secondaryBackgroundColor`
      do tema), texto escuro — texto solto E caixa de widget (multiselect/
      selectbox) ficam no mesmo mundo tonal agora, sem mais o choque
      "caixa clara ilha no meio do navy" que gerava contorno feio.
    - Fundo do conteúdo principal em branco (`.streamlit/config.toml
      [theme] backgroundColor`), cards continuam brancos.
    - Fraunces nos títulos, IBM Plex Sans na interface, IBM Plex Mono em
      número (aplicado card a card, não globalmente ainda).

    Chamar 1x, logo após o gate de login (`init_session()`/`is_logged_in()`
    em app.py) — antes de qualquer conteúdo de página.

    Nota de fragilidade: o seletor do item ativo da navegação
    (`a[aria-current="page"]`) segue o padrão de acessibilidade mais comum
    pra "link da página atual", mas o Streamlit não documenta esse
    contrato — se uma versão futura mudar o marcador, o indicador dourado
    do item ativo para de aparecer (cosmético, não quebra navegação).
    Confirmar visualmente depois de qualquer upgrade de versão do
    Streamlit.
    """
    st.markdown(
        """
        <style>
        :root {
            --f360-sidebar-bg: #eef1f6;
            --f360-sidebar-bg-2: #f8f9fc;
            --f360-sidebar-ink: #16283f;
            --f360-sidebar-ink-muted: #5b6b85;
            --f360-sidebar-line: #d8dfea;
            --f360-gold: #c9932f;
        }

        html, body, [class*="css"] {
            font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
        }

        h1, h2, h3 {
            font-family: "Fraunces", Georgia, "Times New Roman", serif !important;
            letter-spacing: -0.01em;
        }

        /* Fundo do conteúdo principal: branco, definido em
        .streamlit/config.toml ([theme] backgroundColor) — pedido do
        usuário em 2026-08-28 pra reverter do cinza-azulado testado antes.
        Não sobrescrever aqui de novo. */

        /* ---- Sidebar: cinza-azulado claro (2026-08-29, ver docstring) ---- */
        [data-testid="stSidebar"] {
            background: linear-gradient(175deg, var(--f360-sidebar-bg-2) 0%, var(--f360-sidebar-bg) 55%) !important;
        }
        /* Recolore o que fica direto em cima do fundo da sidebar (texto
        solto, título, label de widget). Antes (sidebar navy) essa regra
        também precisava de um reset separado pro interior dos widgets —
        agora que o fundo é claro dos dois lados (sidebar E caixa de
        multiselect/selectbox), texto escuro funciona igual nos dois
        contextos, então o reset abaixo virou rede de segurança
        (redundante, não removido por precaução — não custa nada manter). */
        [data-testid="stSidebar"] > div > div,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span:not([data-baseweb] *),
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
            color: var(--f360-sidebar-ink);
        }
        [data-testid="stSidebar"] [data-baseweb],
        [data-testid="stSidebar"] [data-baseweb] * {
            color: initial;
        }
        /* Ícone de ajuda ("?" de help=) escondido na sidebar — achado
        2026-08-28: renderiza mal contra o fundo em gradiente (posição
        estranha, contraste ruim), tentativa anterior de só recolorir não
        resolveu. Mais seguro esconder do que continuar adivinhando CSS
        sem conseguir ver o resultado ao vivo — o texto de ajuda em si não
        é essencial pro filtro funcionar. */
        [data-testid="stSidebar"] [data-testid="stTooltipIcon"] { display: none !important; }
        [data-testid="stSidebar"] hr { border-color: var(--f360-sidebar-line) !important; }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--f360-sidebar-ink-muted) !important; }
        /* Botão comum (secundário, ex. "Sair"/"Limpar filtros") — sutil.
        `:not([kind="primary"])` é o que faltava: sem essa exclusão, esta
        regra também achatava o botão PRIMÁRIO (ex. "Aplicar filtros",
        type="primary") pro mesmo estilo fantasma. Tinta escura (não mais
        branca) em 2026-08-29 — um véu branco translúcido só aparece
        contra fundo escuro; no fundo claro de agora, o véu precisa ser
        escuro pra continuar visível como "botão sutil". */
        [data-testid="stSidebar"] button:not([kind="primary"]) {
            background: rgba(22, 40, 63, 0.05) !important;
            border: 1px solid var(--f360-sidebar-line) !important;
            color: var(--f360-sidebar-ink) !important;
        }
        [data-testid="stSidebar"] button:not([kind="primary"]):hover {
            background: rgba(22, 40, 63, 0.10) !important;
            border-color: var(--f360-gold) !important;
        }
        /* Botão primário (ex. "Aplicar filtros") — deixa o tema global
        cuidar (primaryColor dourado, já em .streamlit/config.toml),
        só reforça contraste do texto pra garantir legibilidade em cima
        do dourado. */
        [data-testid="stSidebar"] button[kind="primary"] {
            color: #16283f !important;
            font-weight: 600 !important;
        }
        [data-testid="stSidebar"] [data-testid="stCheckbox"] label span {
            border-color: var(--f360-sidebar-line) !important;
        }
        /* Botão/ícone de abrir-fechar (ex.: seta do expander "Filtros")
        dentro de um bloco com chrome próprio ([data-baseweb]) — achado
        2026-08-28 via DevTools real (print do usuário): esse botão é
        `fill="currentColor"`, e a regra de reset acima
        (`[data-baseweb] * { color: initial }`, pensada pra caixa clara
        de multiselect/selectbox) também zera a cor dele — herda preto
        (valor inicial de `color`) sobre fundo quase transparente em
        cima do navy da sidebar: some. Reforça claro só pra button/svg,
        sem tocar no reset geral (que continua certo pras caixas de
        input). */
        [data-testid="stSidebar"] [data-baseweb] button,
        [data-testid="stSidebar"] [data-baseweb] button svg,
        [data-testid="stSidebar"] [data-baseweb] [role="button"],
        [data-testid="stSidebar"] [data-baseweb] [role="button"] svg {
            color: var(--f360-sidebar-ink) !important;
            fill: var(--f360-sidebar-ink) !important;
        }
        /* "Contorno preto" feio na seta (abrir opções) e no "x" (remover
        tag/limpar tudo) do multiselect — achado 2026-08-29 (print do
        usuário), corrigido parcialmente numa rodada anterior só pra
        <button>. Print seguinte mostrou que ainda sobra contorno + a
        seta de abrir opções aparece QUADRADA — sinal de que o controle
        real é um `[role="button"]` (div/span, comum no BaseWeb pra
        ícones clicáveis dentro de Tag/Select), não um <button> puro, e
        de que ele carrega um `border-radius` pequeno/fixo do próprio
        componente em vez de circular. Alvo ampliado pra `[role="button"]`
        também, e força `border-radius:50%` pra qualquer um desses virar
        círculo — nunca quadrado — independente do valor que o BaseWeb
        aplicar por padrão. */
        [data-testid="stSidebar"] [data-baseweb] button,
        [data-testid="stSidebar"] [data-baseweb] [role="button"] {
            background: transparent !important;
            border: none !important;
            border-radius: 50% !important;
            box-shadow: none !important;
        }

        /* Logo do st.logo() na sidebar — histórico das rodadas 1-4
        (2026-08-28/29): seletor errado, depois corte nas bordas, depois
        quadrada/descentralizada (container vs. moldura). Rodada 4 corrigiu
        a estrutura (moldura circular fixa no `<div>` que o `st.logo()` já
        gera em volta do `<img>`, replicando `render_logo_video()`), mas
        ainda aplicava `transform:scale(1.7)` no `<img>` — e o PRÓPRIO
        `fin360_logo.gif` já vinha com esse mesmo recorte/zoom pré-aplicado
        na geração do arquivo (mesma técnica usada aqui: crop central 1:1 +
        zoom 1.7x, "congelados" em cada frame do GIF). Resultado: zoom
        duplicado — a moldura circular acabava mostrando só o centro morto
        de cada frame (círculo preto sólido, sem a marca), bem diferente
        do vídeo da tela de login.

        Rodada 5 (2026-08-29, achado por inspeção direta dos frames do GIF
        e do vídeo fonte, não por tentativa): `fin360_logo.gif` foi
        REGENERADO a partir do mesmo `fin360.mp4`, com o crop 1:1 + zoom
        1.7x aplicado 1x só (na geração do arquivo — por isso o CSS abaixo
        NÃO tem mais `transform:scale`, só `object-fit:cover` pra preencher
        a moldura). De quebra, também corrigido o problema real de "loop
        diferente": o GIF antigo tinha só 38 frames (amostrados a cada
        ~11,8 frames dos 450 do vídeo) — como a animação passa por fases
        bem distintas (marca oculta → aparecendo em cor → cor cheia →
        cinza → dourado, ver docs/04-licoes-aprendidas.md), amostragem tão
        esparsa pulava fases inteiras e parecia "outra animação". Novo GIF:
        75 frames (a cada 6 frames = 200ms/frame, mesmo 1 loop de 15s do
        vídeo), 2,6 MB (era 1,4 MB —137 KB a mais por frame extra, aceito
        pelo usuário em troca de fluidez igual ao login). */
        [data-testid="stSidebarHeader"] {
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            margin-bottom: 1.1rem !important;
            padding-bottom: 0.6rem !important;
            border-bottom: 1px solid var(--f360-sidebar-line);
        }
        /* Moldura: círculo de tamanho fixo, overflow:hidden recorta tudo
        que passar da borda — exatamente o papel do <div> externo de
        render_logo_video(). */
        [data-testid="stSidebarHeader"] > div {
            width: 110px !important;
            height: 110px !important;
            margin: 0 auto !important;
            border-radius: 50% !important;
            overflow: hidden !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.28) !important;
        }
        /* Conteúdo: preenche a moldura inteira — SEM transform:scale
        aqui (rodada 5, ver histórico acima): o zoom/recorte da margem
        escura já vem pré-aplicado em cada frame do `fin360_logo.gif`
        regenerado, replicar de novo via CSS duplicava o zoom. */
        [data-testid="stSidebarLogo"],
        img.stLogo {
            width: 100% !important;
            height: 100% !important;
            max-width: none !important;
            object-fit: cover !important;
        }

        /* Item de navegação ativo (st.navigation) — ver nota de
        fragilidade no docstring de inject_shell_css(). */
        [data-testid="stSidebar"] a[aria-current="page"] {
            background: rgba(201, 147, 47, 0.14) !important;
            border-radius: 8px;
            font-weight: 600 !important;
        }
        [data-testid="stSidebar"] a[aria-current="page"]::before {
            content: "";
            position: absolute;
            left: -0.4rem; top: 15%; bottom: 15%; width: 3px;
            background: var(--f360-gold);
            border-radius: 0 3px 3px 0;
        }
        [data-testid="stSidebar"] a { position: relative; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Fraunces:opsz,wght@9..144,500;9..144,600&'
        'family=IBM+Plex+Sans:wght@400;500;600;700&'
        'family=IBM+Plex+Mono:wght@400;500;600&display=swap">',
        unsafe_allow_html=True,
    )


def render_page_banner(icone: str, titulo: str, subtitulo: str | None = None) -> None:
    """Card em gradiente pro cabeçalho de página — substitui
    `st.header()` + `st.caption()` longo soltos. Pedido do usuário em
    2026-08-28, no mesmo formato de banner usado em outros apps dele
    (ícone + título + subtítulo num card arredondado), personalizado pra
    navy/dourado do Fin360 em vez do roxo do exemplo original.

    `subtitulo` deve ser curto (1 linha) — é onde entra a fonte de dado/
    aviso de filtro próprio da página, não o parágrafo inteiro que
    existia antes."""
    sub_html = (
        f'<div style="color:#c3d0e6;font-size:0.85rem;margin-top:0.35rem;">{subtitulo}</div>'
        if subtitulo else ""
    )
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1c3250 0%, #16283f 100%);
            border-radius: 14px; padding: 1.15rem 1.5rem; margin-bottom: 1.3rem;
            box-shadow: 0 8px 22px rgba(15,34,64,0.16);
        ">
            <div style="display:flex;align-items:center;gap:0.6rem;">
                <span style="font-size:1.25rem;">{icone}</span>
                <span style="color:#e0ac52;font-size:1.3rem;font-weight:600;
                    font-family:'Fraunces',Georgia,serif;">{titulo}</span>
            </div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_logo_video(size: int = 110) -> None:
    """Vídeo em moldura circular. O arquivo fonte tem uma margem escura ao
    redor da marca — usamos overflow:hidden + transform:scale para
    recortar essa margem e mostrar só o círculo dourado, sem caixa preta
    solta."""
    st.markdown(
        f"""
        <div style="
            width:{size}px; height:{size}px; margin:0 auto;
            border-radius:50%; overflow:hidden;
            box-shadow:0 6px 18px rgba(15,23,42,0.18);
        ">
            <video autoplay loop muted playsinline
                style="width:100%;height:100%;object-fit:cover;transform:scale(1.7);">
                <source src="{LOGO_VIDEO_URL}" type="video/mp4">
            </video>
        </div>
        """,
        unsafe_allow_html=True,
    )
