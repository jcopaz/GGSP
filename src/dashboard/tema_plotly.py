"""Template Plotly próprio do painel — achado #1 da auditoria de UX de
2026-08-13: nenhum gráfico do dashboard usava `template=`, então todos
caíam no tema default do Plotly (fundo branco puro, grid genérico, fonte
"Arial" do próprio Plotly.js — nunca a mesma fonte da interface Streamlit
ao redor). Registrado 1x aqui e aplicado a TODO gráfico automaticamente
via `pio.templates.default` — não precisa passar `template=` em cada
`update_layout`.

Fundo transparente (`paper_bgcolor`/`plot_bgcolor`) de propósito: o
gráfico herda a cor de fundo do container Streamlit em vez de desenhar um
retângulo branco por cima — efeito "gráfico faz parte da página", não
"gráfico colado em cima dela". Só light mode: o painel inteiro (cards,
tabelas) não tem suporte a tema escuro do Streamlit ainda — decisão de
escopo, não esquecimento (ver `st.set_page_config` em app.py, sem
`theme=` definido).

Importa este módulo (efeito colateral: registra e ativa o template) de
`grafico_interativo.py`, que por sua vez é importado por todo arquivo que
cria gráfico Plotly no painel — garante que o template já está ativo
antes de qualquer `go.Figure()` ser renderizado, não precisa de outro
ponto de import explícito.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from src.dashboard.paleta import (
    COR_ECONOMIA, COR_ESTOURO, COR_FORECAST, COR_NEUTRO, COR_ORCADO, COR_REALIZADO,
)

NOME_TEMA = "mrs_gg_infra"

_FONTE = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, '
    '"Helvetica Neue", Arial, sans-serif'
)
_COR_TEXTO = "#2c3441"
_COR_GRADE = "#e9ecf3"
_COR_EIXO = "#d7dce8"

_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        font={"family": _FONTE, "size": 12, "color": _COR_TEXTO},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[COR_ORCADO, COR_REALIZADO, COR_ESTOURO, COR_ECONOMIA, COR_NEUTRO, COR_FORECAST],
        title={"font": {"size": 15, "color": "#16213a"}, "x": 0.01, "xanchor": "left"},
        xaxis={
            "gridcolor": _COR_GRADE, "zerolinecolor": _COR_EIXO, "linecolor": _COR_EIXO,
            "showline": True, "ticks": "outside", "tickcolor": _COR_EIXO,
        },
        yaxis={
            "gridcolor": _COR_GRADE, "zerolinecolor": _COR_EIXO, "linecolor": _COR_EIXO,
            "ticks": "outside", "tickcolor": _COR_EIXO,
        },
        legend={"font": {"size": 11.5}},
        hoverlabel={"font": {"family": _FONTE, "size": 12}, "bgcolor": "white", "bordercolor": _COR_EIXO},
        margin={"t": 60, "b": 40, "l": 40, "r": 30},
    )
)

pio.templates[NOME_TEMA] = _TEMPLATE
pio.templates.default = NOME_TEMA
