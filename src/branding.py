"""Elementos visuais de marca do Fin360 — vídeo de logo em loop.

Usado tanto na tela de login (src/auth/login.py) quanto na sidebar
(src/dashboard/app.py) — muda aqui, muda nos dois lugares.

Depende de `enableStaticServing = true` em `.streamlit/config.toml` e de um
arquivo `static/fin360.mp4` na mesma pasta do script principal (Streamlit
serve sempre `<pasta do script principal>/static/`, nunca outra — e expõe
em `app/static/...`, independente de onde a pasta física está).

**Mudou em 2026-09-01** (`app.py` passou de `src/dashboard/app.py` pra raiz
do repo, arquitetura de publicação): o "script principal" agora é a raiz,
então a pasta que o Streamlit realmente serve é `static/` na RAIZ, não mais
`src/dashboard/static/`. Por isso `static/fin360.mp4` (raiz) é uma cópia
exata de `src/dashboard/static/fin360.mp4` — a segunda continua sendo a
localização "oficial"/documentada do arquivo (README.md, `st.logo()` na
sidebar lê direto daqui via caminho de arquivo, não via URL), a primeira
existe só porque o Streamlit exige isso pra servir a URL do vídeo do Login.
Se o vídeo for atualizado no futuro, atualizar as DUAS cópias (ou apagar
`static/` da raiz — nesse caso o Login cai sozinho no fallback de imagem
estática, ver `render_logo_video`).

Se o deploy no Streamlit Cloud der `ImportError: cannot import name
'inject_shell_css'` mesmo depois de um Reboot, é cache do próprio
Streamlit Cloud, não deste arquivo (conferido: repositório remoto sempre
consistente) — ver docs/04-licoes-aprendidas.md, item 21.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

LOGO_VIDEO_URL = "app/static/fin360.mp4"

# Caminho real em disco do vídeo/logo estática (independe de onde o script
# principal está sendo executado — ver render_logo_video). `static/` mora
# em src/dashboard/static/ (arquitetura fixada do projeto); só o vídeo
# depende do mecanismo de static serving do Streamlit (LOGO_VIDEO_URL
# acima), que só funciona quando o arquivo existe fisicamente ao lado do
# script principal — ver nota em `static/` (raiz) sobre a cópia espelhada
# de fin360.mp4 desde que `app.py` passou a viver na raiz.
_STATIC_DIR = Path(__file__).resolve().parent / "dashboard" / "static"
_LOGO_VIDEO_PATH = _STATIC_DIR / "fin360.mp4"
_LOGO_PNG_PATH = _STATIC_DIR / "fin360_logo.png"


def inject_shell_css() -> None:
    """Casca visual do painel inteiro (fundo, sidebar, tipografia).

    Chamar 1x, logo após o gate de login (`init_session()`/`is_logged_in()`
    em app.py) — antes de qualquer conteúdo de página. A tela de LOGIN tem
    CSS próprio (`_inject_login_css` em src/auth/login.py) e nunca coexiste
    com este.

    **Sidebar clara + acento DOURADO** (`--f360-gold: #c9932f`). Foi a
    versão de 6.2.0–6.2.2; o 6.3.0 trocou o acento pra navy junto com o
    `primaryColor` só pra resolver o contorno da tag do multiselect — mas
    o 6.4.0/6.5.0 passaram a estilizar a tag e os ícones internos do
    BaseWeb explicitamente (fundo/borda/`×` controlados), então o dourado
    voltou sem reabrir aquele problema. `primaryColor` fica navy no
    `.streamlit/config.toml` (serve o resto do app — checkbox, slider,
    tabs); o dourado é 100% CSS escopado em `[data-testid="stSidebar"]`.

    **6.5.0 — passada minuciosa na sidebar:**

    - Acento dourado de volta: item de nav ativo, anel de foco do
      multiselect, borda de hover dos botões, tag/chip.

    **2026-09-01 — tag de filtro:** o chip do multiselect passou de
    dourado suave + texto escuro para **dourado sólido (`--f360-gold`) +
    texto e "×" brancos** (pedido do usuário). Único ponto em que o
    dourado vira fundo cheio.
    - **Logo circular robusta**: o `st.logo()` do Streamlit 1.57 embrulha
      o `<img>` num `<div>` na página default e num
      `<button data-testid="stLogoLink">` nas demais — o seletor antigo
      (`stSidebarHeader > div`) só pegava o `<div>`, então a logo
      "voltava a ficar quadrada" ao navegar pra fora da home. Agora os 3
      invólucros (div/a/button) recebem a moldura circular, e o
      `stSidebarCollapseButton` é excluído. Mesma medida/sombra do
      círculo da tela de login (`render_logo_video`, 112px). SEM
      `transform:scale` — o crop 1:1 + zoom 1.7x já vem gravado em cada
      frame do `fin360_logo.gif` (75 frames, ver docs/04-licoes).
    - Botão "Aplicar filtros" com o mesmo gradiente navy do botão
      "Entrar" da tela de login.
    - Colunas da sidebar não quebram mais (Aplicar | Limpar lado a lado);
      scrollbar fina; ritmo dos grupos de filtro revisto.

    Nota de fragilidade: `a[aria-current="page"]` (item de nav ativo) e os
    `data-testid` do `st.logo()` não são contrato público do Streamlit —
    revalidar visualmente depois de todo upgrade de versão.
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
            /* Acento da marca — dourado. Realce (nav ativo / foco / hover)
            e fundo cheio da tag de filtro selecionada (2026-09-01), nunca
            uma superfície grande. */
            --f360-gold: #c9932f;
            --f360-gold-soft: rgba(201, 147, 47, 0.13);
            --f360-gold-soft-hover: rgba(201, 147, 47, 0.22);
            --f360-gold-line: rgba(201, 147, 47, 0.42);
            /* Navy da tela de login — botão primário da sidebar reusa. */
            --f360-navy-a: #0f2f52;
            --f360-navy-b: #1d5488;
            /* Compat: alguns pontos ainda referenciam --f360-accent. */
            --f360-accent: var(--f360-gold);
            --f360-accent-soft: var(--f360-gold-soft);
            --f360-accent-soft-hover: var(--f360-gold-soft-hover);
            --f360-banner-from: #1c3250;
            --f360-banner-to: #16283f;
            --f360-banner-title: #e0ac52;
            --f360-banner-sub: #c3d0e6;
            --f360-content-max: 1500px;
        }

        html, body, [class*="css"] {
            font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
        }

        h1, h2, h3 {
            font-family: "Fraunces", Georgia, "Times New Roman", serif !important;
            letter-spacing: -0.01em;
        }

        /* ===== Layout e reflow do conteúdo (6.4.0) ===== */
        [data-testid="stMainBlockContainer"] {
            max-width: var(--f360-content-max);
            margin-inline: auto;
            padding-inline: clamp(1rem, 3vw, 3rem);
        }
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap;
            align-items: stretch;
        }
        [data-testid="stColumn"], [data-testid="column"] {
            min-width: min(100%, 260px);
        }
        [data-testid="stColumn"] > div { min-width: 0; }
        [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] * {
            overflow-wrap: break-word;
        }
        [data-testid="stMainBlockContainer"] img { max-width: 100%; height: auto; }
        [data-testid="stMainBlockContainer"] table { max-width: 100%; }

        /* Divisória do bloco "card-resumo | visual" (src/dashboard/layout.py). */
        [class*="st-key-f360-visualcol-"] {
            border-left: 1px solid var(--f360-sidebar-line);
            padding-left: 1.2rem;
        }
        @media (max-width: 900px) {
            [class*="st-key-f360-visualcol-"] { border-left: none; padding-left: 0; }
        }

        /* Cabeçalho de grupo de filtro na sidebar. */
        .f360-filtro-grupo {
            font-size: 0.7rem; font-weight: 700; letter-spacing: 0.09em;
            text-transform: uppercase; color: var(--f360-sidebar-ink-muted);
            margin: 1.35rem 0 0.4rem; padding-top: 0.6rem;
            border-top: 1px solid var(--f360-sidebar-line);
        }
        .f360-filtro-grupo.is-first { border-top: none; padding-top: 0; margin-top: 0.5rem; }

        /* Chip de "filtros ativos" no topo das páginas (conteúdo, não sidebar). */
        .f360-badge-filtros {
            display: inline-block; font-size: 0.78rem; line-height: 1.5;
            color: var(--f360-sidebar-ink-muted);
            background: #f5f7fb; border: 1px solid #e3e8f0;
            border-radius: 999px; padding: 0.15rem 0.8rem; margin-bottom: 0.9rem;
        }

        /* ===== Sidebar: fundo, texto, scrollbar ===== */
        [data-testid="stSidebar"] {
            background: linear-gradient(175deg, var(--f360-sidebar-bg-2) 0%, var(--f360-sidebar-bg) 55%) !important;
        }
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
        [data-testid="stSidebar"] [data-testid="stTooltipIcon"] { display: none !important; }
        [data-testid="stSidebar"] hr {
            border-color: var(--f360-sidebar-line) !important;
            margin: 0.9rem 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--f360-sidebar-ink-muted) !important; }
        /* Scrollbar fina e discreta. */
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            scrollbar-width: thin;
            scrollbar-color: var(--f360-sidebar-line) transparent;
        }
        [data-testid="stSidebar"] ::-webkit-scrollbar { width: 8px; }
        [data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
            background: var(--f360-sidebar-line); border-radius: 8px;
        }
        [data-testid="stSidebar"] ::-webkit-scrollbar-track { background: transparent; }
        /* Colunas dentro da sidebar (linha "Aplicar | Limpar") não quebram —
        a regra global de reflow acima é só pro conteúdo principal. */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: 0.5rem; }
        [data-testid="stSidebar"] [data-testid="stColumn"] { min-width: 0 !important; }

        /* ===== Botões da sidebar (só os st.button/form reais) ===== */
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button {
            background: rgba(22, 40, 63, 0.04) !important;
            border: 1px solid var(--f360-sidebar-line) !important;
            border-radius: 9px !important;
            color: var(--f360-sidebar-ink) !important;
            font-weight: 500 !important;
            transition: border-color 120ms ease, background 120ms ease;
        }
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button:hover {
            background: var(--f360-gold-soft) !important;
            border-color: var(--f360-gold) !important;
            color: var(--f360-sidebar-ink) !important;
        }
        /* "Aplicar filtros" — mesmo gradiente navy do "Entrar" do login. */
        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, var(--f360-navy-a) 0%, var(--f360-navy-b) 100%) !important;
            color: #ffffff !important;
            font-weight: 600 !important;
            border: none !important;
            border-radius: 10px !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
            filter: brightness(1.08);
        }
        [data-testid="stSidebar"] [data-testid="stCheckbox"] label span {
            border-color: var(--f360-sidebar-line) !important;
        }

        /* ===== Multiselect / selectbox da sidebar ===== */
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            border: 1px solid var(--f360-sidebar-line) !important;
            border-radius: 9px !important;
            box-shadow: none !important;
            transition: border-color 120ms ease, box-shadow 120ms ease;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div:hover {
            border-color: var(--f360-gold-line) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div:focus-within {
            border-color: var(--f360-gold) !important;
            box-shadow: 0 0 0 3px var(--f360-gold-soft) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] input { color: var(--f360-sidebar-ink) !important; }
        [data-testid="stSidebar"] [data-baseweb="select"] input::placeholder {
            color: var(--f360-sidebar-ink-muted) !important;
            font-size: 0.82rem !important;
        }

        /* Tag / chip: dourado SÓLIDO com texto e "×" brancos (pedido do
        usuário 2026-09-01 — "fundo do texto dos filtros dourado, letras
        brancas"). É o único ponto em que --f360-gold vira fundo cheio;
        continua sendo um elemento pequeno (o valor selecionado), não uma
        superfície grande. */
        [data-testid="stSidebar"] [data-baseweb="tag"] {
            background: var(--f360-gold) !important;
            border: 1px solid var(--f360-gold) !important;
            border-radius: 7px !important;
            color: #ffffff !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            margin: 2px !important;
            padding: 1px 4px 1px 7px !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] span { color: #ffffff !important; }

        /* Reset dos botõezinhos internos do BaseWeb (× da tag, limpar-tudo,
        seta) — sem fundo/borda/caixa; deixa o BaseWeb só desenhar o ícone.
        Escopado ao multiselect: NÃO é a regra global de `button` que
        vazava e criava o contorno quadrado (essa é a `.stButton` acima). */
        [data-testid="stSidebar"] [data-baseweb="tag"] [role="button"],
        [data-testid="stSidebar"] [data-baseweb="tag"] button,
        [data-testid="stSidebar"] [data-baseweb="select"] [role="button"],
        [data-testid="stSidebar"] [data-baseweb="select"] button {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] [role="button"]:hover,
        [data-testid="stSidebar"] [data-baseweb="tag"] button:hover {
            background: rgba(255, 255, 255, 0.25) !important;
            border-radius: 4px !important;
        }
        /* "×" da tag: branco sobre o dourado sólido. */
        [data-testid="stSidebar"] [data-baseweb="tag"] svg {
            fill: rgba(255, 255, 255, 0.9) !important;
            color: rgba(255, 255, 255, 0.9) !important;
            width: 13px !important; height: 13px !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"]:hover svg {
            fill: #ffffff !important;
            color: #ffffff !important;
        }
        /* Seta ⌄ / limpar-tudo do select: legível (não miniatura). */
        [data-testid="stSidebar"] [data-baseweb="select"] > div > div:last-child svg {
            fill: var(--f360-sidebar-ink-muted) !important;
            color: var(--f360-sidebar-ink-muted) !important;
        }

        /* ===== Logo animada na sidebar (st.logo) — círculo igual ao login =====
        🔒 Delicado: custou ~8 rodadas. O `st.logo()` do Streamlit 1.57
        embrulha o <img.stLogo> em:
          - <div>                              na página default
          - <button data-testid="stLogoLink">  nas outras (app multipágina)
          - <a data-testid="stLogoLink">       se houvesse link (não é o caso)
        Os 3 recebem a moldura; `stSidebarCollapseButton` (irmão) fica de
        fora. Medida/sombra iguais ao círculo de `render_logo_video()`
        (login, 112px). SEM transform:scale — o zoom já vem no gif. */
        [data-testid="stSidebarHeader"] {
            position: relative !important;
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            margin-bottom: 1.15rem !important;
            padding-bottom: 0.7rem !important;
            border-bottom: 1px solid var(--f360-sidebar-line);
            flex: 1 1 auto !important;
            width: 100% !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        [data-testid="stSidebarHeader"] > div:not([data-testid="stSidebarCollapseButton"]),
        [data-testid="stSidebarHeader"] > a[data-testid="stLogoLink"],
        [data-testid="stSidebarHeader"] > button[data-testid="stLogoLink"] {
            width: 112px !important;
            height: 112px !important;
            min-width: 112px !important;
            flex: 0 0 112px !important;
            margin: 0 auto !important;
            padding: 0 !important;
            border: none !important;
            outline: none !important;
            border-radius: 50% !important;
            overflow: hidden !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: transparent !important;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.18) !important;
            cursor: pointer;
        }
        [data-testid="stSidebarHeader"] [data-testid="stSidebarLogo"],
        [data-testid="stSidebarHeader"] img.stLogo {
            width: 100% !important;
            height: 100% !important;
            min-width: 100% !important;
            max-width: none !important;
            margin: 0 !important;
            object-fit: cover !important;
            object-position: center !important;
        }
        /* Botão de colapsar (« ) — tirado do fluxo pro canto sup. direito,
        pra logo centralizar de verdade na largura inteira do header (e
        pra moldura circular nunca pegá-lo). Fica sobre a área do header,
        aparece no hover como já é padrão do Streamlit. */
        [data-testid="stSidebarCollapseButton"] {
            position: absolute !important;
            top: 0.35rem !important;
            right: 0.15rem !important;
            z-index: 3 !important;
            flex: 0 0 auto !important;
            width: auto !important; height: auto !important;
            border-radius: 6px !important;
            box-shadow: none !important;
            background: transparent !important;
        }

        /* ===== Item de navegação ativo (st.navigation) — realce dourado ===== */
        [data-testid="stSidebar"] a[aria-current="page"] {
            background: var(--f360-gold-soft) !important;
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
    """Card em gradiente pro cabeçalho de página — substitui `st.header()`
    + `st.caption()` longo soltos (pedido do usuário em 2026-08-28, mesmo
    formato de banner dos outros apps dele). Cores via tokens `--f360-*`
    (tokenizado em 6.4.0). `subtitulo` deve ser curto (1 linha) — fonte
    de dado / aviso de filtro da página, não o parágrafo inteiro."""
    sub_html = (
        f'<div style="color:var(--f360-banner-sub);font-size:0.85rem;margin-top:0.35rem;">{subtitulo}</div>'
        if subtitulo else ""
    )
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, var(--f360-banner-from) 0%, var(--f360-banner-to) 100%);
            border-radius: 14px; padding: 1.15rem 1.5rem; margin-bottom: 1.3rem;
            box-shadow: 0 8px 22px rgba(15,34,64,0.16);
        ">
            <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">
                <span style="font-size:1.25rem;">{icone}</span>
                <span style="color:var(--f360-banner-title);font-size:1.3rem;font-weight:600;
                    font-family:'Fraunces',Georgia,serif;">{titulo}</span>
            </div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_logo_video(size: int = 110) -> None:
    """Vídeo em moldura circular (tela de login). O arquivo fonte tem uma
    margem escura ao redor da marca — `overflow:hidden` + `transform:scale`
    recortam essa margem e mostram só o círculo dourado, sem caixa preta
    solta. (Na sidebar o equivalente é `st.logo()` + o CSS de
    `inject_shell_css`, que NÃO usa scale porque lá o zoom já vem no gif.)

    Fallback técnico (2026-09-01): com `app.py` na raiz, o mecanismo de
    static serving do Streamlit passou a procurar `static/` ao lado da
    raiz, não mais de `src/dashboard/` — por isso existe uma cópia de
    `fin360.mp4` também em `static/` (raiz do repo, ver comentário lá) só
    pra essa URL continuar resolvendo. Se mesmo assim o arquivo não
    existir em disco (ex.: clone sem o binário), cai pra `fin360_logo.png`
    (mesma moldura, mesmo tamanho/sombra, sem `transform:scale` — o PNG já
    vem enquadrado, mesmo tratamento que `icon_image` já recebe no
    sidebar) embutido como data URI. Nenhuma mudança de layout/cor/texto/
    fluxo do Login: só o conteúdo dentro da mesma moldura muda, e só
    quando o vídeo realmente não está presente."""
    if not _LOGO_VIDEO_PATH.exists() and _LOGO_PNG_PATH.exists():
        _logo_b64 = base64.b64encode(_LOGO_PNG_PATH.read_bytes()).decode("ascii")
        st.markdown(
            f"""
            <div style="
                width:{size}px; height:{size}px; margin:0 auto;
                border-radius:50%; overflow:hidden;
                box-shadow:0 6px 18px rgba(15,23,42,0.18);
            ">
                <img src="data:image/png;base64,{_logo_b64}"
                    style="width:100%;height:100%;object-fit:cover;">
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

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
