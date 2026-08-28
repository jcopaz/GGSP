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
    """Casca visual do painel inteiro (fundo, sidebar, tipografia) —
    aprovada pelo usuário em 2026-08-27 (ver artefato de proposta). A
    paleta de gráfico (`paleta.py`) não é tocada aqui, só o "entorno":

    - Sidebar vira navy sólido (identidade de marca), texto claro.
    - Fundo do conteúdo principal em cinza-azulado (mesmo tom da tela de
      login), cards continuam brancos.
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
            --f360-sidebar-bg: #16283f;
            --f360-sidebar-bg-2: #1c3250;
            --f360-sidebar-ink: #e9edf5;
            --f360-sidebar-ink-muted: #8ea0bf;
            --f360-sidebar-line: #2a3e5c;
            --f360-gold: #c9932f;
            --f360-bg: #eef1f6;
        }

        html, body, [class*="css"] {
            font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
        }

        h1, h2, h3 {
            font-family: "Fraunces", Georgia, "Times New Roman", serif !important;
            letter-spacing: -0.01em;
        }

        [data-testid="stAppViewContainer"], .stApp {
            background: var(--f360-bg) !important;
        }

        /* ---- Sidebar: vira a marca ---- */
        [data-testid="stSidebar"] {
            background: linear-gradient(175deg, var(--f360-sidebar-bg-2) 0%, var(--f360-sidebar-bg) 55%) !important;
        }
        [data-testid="stSidebar"] * { color: var(--f360-sidebar-ink); }
        [data-testid="stSidebar"] hr { border-color: var(--f360-sidebar-line) !important; }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--f360-sidebar-ink-muted) !important; }
        [data-testid="stSidebar"] button {
            background: rgba(255,255,255,0.06) !important;
            border: 1px solid var(--f360-sidebar-line) !important;
            color: var(--f360-sidebar-ink) !important;
        }
        [data-testid="stSidebar"] button:hover {
            background: rgba(255,255,255,0.12) !important;
            border-color: var(--f360-gold) !important;
        }
        [data-testid="stSidebar"] [data-testid="stCheckbox"] label span {
            border-color: var(--f360-sidebar-line) !important;
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
