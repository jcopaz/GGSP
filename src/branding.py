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

    Chamar 1x, logo após o gate de login (`init_session()`/`is_logged_in()`
    em app.py) — antes de qualquer conteúdo de página. A tela de LOGIN tem
    CSS próprio (`_inject_login_css` em src/auth/login.py) e nunca coexiste
    com este.

    Histórico do fundo da sidebar: navy sólido (aprovado 2026-08-27) →
    cinza-azulado claro (2026-08-29), depois que os ícones internos do
    BaseWeb (seta/×) não deram contraste contra o navy mesmo após várias
    rodadas de CSS. `primaryColor` foi de dourado pra navy `#1e3a5f` no
    mesmo dia (igual ao MRS Sentinel), pra dar contraste natural ao "×"
    branco que o BaseWeb desenha por cima da tag.

    **6.4.0 — design do filtro + consistência entre telas/monitores:**

    - **Chip ("tag") do multiselect em navy SUAVE** (`--f360-accent-soft`,
      translúcido) no lugar do navy sólido que o `primaryColor` do BaseWeb
      pinta por padrão — o bloco escuro brigava com a sidebar clara.
      `primaryColor` fica igual (navy) porque ainda serve o resto do app.
      Refinado a partir de sugestão externa (Gemini): chip ganha borda
      sutil + texto `#16283f`; reset explícito de fundo/borda/sombra nos
      botõezinhos internos do BaseWeb (× da tag, seta, limpar-tudo), mas
      ESCOPADO só ao multiselect — não é mais a regra global de `button`
      que vazava e desenhava o contorno quadrado (essa virou
      `.stButton`/`stFormSubmitButton`). Removido o reset
      `[data-baseweb] * { color: initial }`.
    - **`max-width: 1500px` centralizado** no `.block-container` — sem
      isso cada monitor renderizava outra proporção.
    - **Colunas com `flex-wrap` + `min-width`** — quando o espaço aperta
      (tela menor, sidebar aberto num notebook) elas empilham limpo em
      vez de esmagar/sobrepor. Substitui a coluna-fantasma de proporção
      0.04 usada como divisória vertical (ver `src/dashboard/layout.py`).
    - Classes utilitárias: `.f360-filtro-grupo` (cabeçalho de grupo de
      filtro), `.f360-badge-filtros` (chip de filtros ativos), e o alvo
      `[class*="st-key-f360-visualcol-"]` (divisória do bloco resumo|visual).
    - Banner de página (`render_page_banner`) tokenizado — mesmo visual.

    Nota de fragilidade: o seletor do item ativo da navegação
    (`a[aria-current="page"]`) segue o padrão de acessibilidade mais comum
    pra "link da página atual", mas o Streamlit não documenta esse
    contrato — se uma versão futura mudar o marcador, o indicador (barra +
    fundo) do item ativo para de aparecer (cosmético). Confirmar
    visualmente depois de qualquer upgrade de Streamlit.
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
            --f360-accent: #1e3a5f;
            /* Navy translúcido refinado */
            --f360-accent-soft: rgba(30, 58, 95, 0.08);
            --f360-accent-soft-hover: rgba(30, 58, 95, 0.15);
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

        /* ---- Layout e Reflow do Conteúdo ---- */
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

        /* Divisória do bloco resumo | visual */
        [class*="st-key-f360-visualcol-"] {
            border-left: 1px solid var(--f360-sidebar-line);
            padding-left: 1.2rem;
        }
        @media (max-width: 900px) {
            [class*="st-key-f360-visualcol-"] { border-left: none; padding-left: 0; }
        }

        /* Cabeçalho de grupo de filtro na sidebar */
        .f360-filtro-grupo {
            font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
            text-transform: uppercase; color: var(--f360-sidebar-ink-muted);
            margin: 1.1rem 0 0.2rem; padding-top: 0.75rem;
            border-top: 1px solid var(--f360-sidebar-line);
        }
        .f360-filtro-grupo.is-first { border-top: none; padding-top: 0; margin-top: 0.3rem; }

        /* Badge de filtros ativos no topo das páginas */
        .f360-badge-filtros {
            display: inline-block; font-size: 0.78rem; line-height: 1.5;
            color: var(--f360-sidebar-ink);
            background: var(--f360-accent-soft); border: 1px solid var(--f360-sidebar-line);
            border-radius: 999px; padding: 0.15rem 0.75rem; margin-bottom: 0.9rem;
        }

        /* ---- Sidebar Fundo e Textos ---- */
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
        [data-testid="stSidebar"] hr { border-color: var(--f360-sidebar-line) !important; }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--f360-sidebar-ink-muted) !important; }

        /* ---- Botões REAIS da Sidebar (Isolados) ---- */
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button {
            background: var(--f360-accent-soft) !important;
            border: 1px solid var(--f360-sidebar-line) !important;
            border-radius: 8px !important;
            color: var(--f360-sidebar-ink) !important;
            font-weight: 500 !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button:hover {
            background: var(--f360-accent-soft-hover) !important;
            border-color: var(--f360-accent) !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background: var(--f360-accent) !important;
            color: #ffffff !important;
            font-weight: 600 !important;
            border-color: var(--f360-accent) !important;
        }
        [data-testid="stSidebar"] [data-testid="stCheckbox"] label span {
            border-color: var(--f360-sidebar-line) !important;
        }

        /* ---- Caixa Externa do Multiselect / Selectbox ---- */
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            border: 1px solid var(--f360-sidebar-line) !important;
            border-radius: 8px !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div:focus-within {
            border-color: var(--f360-accent) !important;
            box-shadow: 0 0 0 1px var(--f360-accent) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] input {
            color: var(--f360-sidebar-ink) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] input::placeholder {
            color: var(--f360-sidebar-ink-muted) !important;
            font-size: 0.82rem !important;
        }

        /* ---- Chips / Tags Selecionadas (Leves e Nítidas) ---- */
        [data-testid="stSidebar"] [data-baseweb="tag"],
        [data-testid="stSidebar"] div[data-baseweb="tag"],
        [data-testid="stSidebar"] span[data-baseweb="tag"] {
            background-color: var(--f360-accent-soft) !important;
            background: var(--f360-accent-soft) !important;
            border: 1px solid rgba(30, 58, 95, 0.18) !important;
            border-radius: 6px !important;
            color: #16283f !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            margin: 2px !important;
            padding: 1px 6px !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] span {
            color: #16283f !important;
        }

        /* ---- Reset Total de Contornos e Caixas nos Ícones do BaseWeb ---- */
        [data-testid="stSidebar"] [data-baseweb="tag"] [role="button"],
        [data-testid="stSidebar"] [data-baseweb="tag"] button,
        [data-testid="stSidebar"] [data-baseweb="select"] [role="button"],
        [data-testid="stSidebar"] [data-baseweb="select"] button,
        [data-testid="stSidebar"] [data-baseweb="select"] div[aria-hidden="true"] {
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
            padding: 0 2px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            cursor: pointer !important;
        }

        /* Hover sutil exclusivo no '×' do chip */
        [data-testid="stSidebar"] [data-baseweb="tag"] [role="button"]:hover,
        [data-testid="stSidebar"] [data-baseweb="tag"] button:hover {
            background: rgba(30, 58, 95, 0.14) !important;
            background-color: rgba(30, 58, 95, 0.14) !important;
            border-radius: 4px !important;
        }

        /* Ícones Vetoriais Limpos */
        [data-testid="stSidebar"] [data-baseweb="tag"] svg,
        [data-testid="stSidebar"] [data-baseweb="select"] svg {
            fill: var(--f360-sidebar-ink-muted) !important;
            color: var(--f360-sidebar-ink-muted) !important;
            stroke: currentColor !important;
            width: 12px !important;
            height: 12px !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"]:hover svg {
            fill: var(--f360-sidebar-ink) !important;
            color: var(--f360-sidebar-ink) !important;
        }

        /* ---- Logo animada na sidebar (st.logo) — 🔒 NÃO MEXER ----
        Custou ~8 rodadas acertar tamanho + loop + centralização. Regras
        abaixo replicam a técnica de 2 nós de `render_logo_video()`:
        `stSidebarHeader` cresce (`flex:1; width:100%`) pra ocupar o
        espaço ao lado do botão de colapsar, só assim o
        `justify-content:center` centraliza em relação à sidebar inteira;
        o `<div>` interno é a MOLDURA (círculo 110px, `overflow:hidden`);
        o `<img>` é o CONTEÚDO. */
        [data-testid="stSidebarHeader"] {
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            margin-bottom: 1.1rem !important;
            padding-bottom: 0.6rem !important;
            border-bottom: 1px solid var(--f360-sidebar-line);
            flex: 1 1 auto !important;
            width: 100% !important;
            display: flex !important;
            justify-content: center !important;
        }
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
        /* SEM transform:scale aqui: o crop 1:1 + zoom 1.7x já vem
        pré-aplicado em cada frame do `fin360_logo.gif` regenerado —
        replicar via CSS duplica o zoom e mostra só o centro morto do
        frame (círculo preto). Só `object-fit:cover` pra preencher a
        moldura. Ver docs/04-licoes-aprendidas.md. */
        [data-testid="stSidebarLogo"],
        img.stLogo {
            width: 100% !important;
            height: 100% !important;
            max-width: none !important;
            object-fit: cover !important;
        }

        /* Item de navegação ativo */
        [data-testid="stSidebar"] a[aria-current="page"] {
            background: rgba(30, 58, 95, 0.12) !important;
            border-radius: 8px;
            font-weight: 600 !important;
        }
        [data-testid="stSidebar"] a[aria-current="page"]::before {
            content: "";
            position: absolute;
            left: -0.4rem; top: 15%; bottom: 15%; width: 3px;
            background: var(--f360-accent);
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
    `inject_shell_css`, que NÃO usa scale porque lá o zoom já vem no gif.)"""
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
