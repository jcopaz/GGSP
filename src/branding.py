"""Elementos visuais de marca do Fin360 — vídeo de logo em loop.

Usado tanto na tela de login (src/auth/login.py) quanto na sidebar
(src/dashboard/app.py) — muda aqui, muda nos dois lugares.

Depende de `enableStaticServing = true` em `.streamlit/config.toml` e do
arquivo em `static/fin360.mp4` (servido pelo Streamlit em `app/static/...`).
"""
from __future__ import annotations

import streamlit as st

LOGO_VIDEO_URL = "app/static/fin360.mp4"


def render_logo_video(width: int = 200) -> None:
    st.html(f"""
    <div style="text-align:center;">
        <video autoplay loop muted playsinline
            style="width:{width}px;max-width:100%;display:inline-block;">
            <source src="{LOGO_VIDEO_URL}" type="video/mp4">
        </video>
    </div>
    """)
