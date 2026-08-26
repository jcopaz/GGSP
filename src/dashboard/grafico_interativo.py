"""Interatividade compartilhada dos gráficos Plotly — pedido do usuário em
2026-08-11: zoom/pan sempre ligados, e alternância Barra/Linha nos
gráficos onde o eixo X é sequencial (mês) — comparação Orçado x Real por
Pacote/Conta não entra aqui de propósito: o eixo X ali é categórico (não
uma sequência), e uma linha ligando categorias sem ordem/continuidade real
é enganosa (ver dataviz skill, anti-patterns) — nesses o ganho fica só no
zoom/pan e no rótulo abreviado.

Importa `tema_plotly` só pelo efeito colateral (registra e ativa o
template visual do painel) — todo arquivo que cria gráfico já importa
`CONFIG_PLOTLY` daqui, então o template fica garantidamente ativo antes
de qualquer `go.Figure()` ser renderizado, sem precisar de outro ponto de
import explícito (ver docstring de `tema_plotly.py`).
"""
from __future__ import annotations

import plotly.graph_objects as go

from src.dashboard import tema_plotly as _tema_plotly  # noqa: F401 — registra o template (efeito colateral)

# `displaylogo=False` tira o logo da Plotly da barra de ferramentas.
# Zoom/pan/autoscale/reset já vêm ligados por padrão do Plotly — não
# precisa de opção extra pra isso, só não desligar (nunca passar
# `displayModeBar=False` nos gráficos deste painel).
CONFIG_PLOTLY = {"displaylogo": False}


def com_alternancia_barra_linha(
    categorias: list[str],
    series: list[tuple[str, list[float], str]],
    titulo: str,
    yaxis_title: str | None = None,
    traces_extras: list[go.Scatter] | None = None,
    layout_extra: dict | None = None,
    padrao: str = "barra",
) -> go.Figure:
    """Gráfico com 2 conjuntos de traces (Barra e Linha) pro mesmo dado —
    só 1 conjunto visível por vez — e botões no canto pra alternar. Uso
    pensado pra série mensal (eixo X sequencial, ex. Jan..Dez); não usar
    com eixo categórico (Pacote/Conta) — ver docstring do módulo.

    `series`: lista de (nome_da_série, valores, cor).

    `traces_extras`: traces sempre visíveis, independente do modo Barra/
    Linha (ex.: Forecast pontilhado em `tendencia.py`, Aderência no eixo
    secundário em `visao_manutencao.py`) — não entram na alternância,
    só ficam desenhados por cima nos 2 modos. Adicionado em 2026-08-13
    (achado #6 da auditoria de UX: `tendencia.figura_tendencia` e
    `visao_manutencao._grafico_mensal` reimplementavam esse padrão de
    `updatemenus` manualmente em vez de reusar este helper — as 2
    divergiam sutilmente entre si).

    `layout_extra`: kwargs extras pra `fig.update_layout` (ex.: `yaxis2`
    pro eixo secundário de Aderência, `annotations` da projeção final).

    `padrao`: `"barra"` (default) ou `"linha"` — qual dos 2 conjuntos
    começa visível/com o botão marcado como ativo. `tendencia.py` usa
    `"linha"` pra preservar o comportamento já validado com o usuário
    (Tendência sempre abre como linha); os demais chamadores usam o
    default `"barra"`.
    """
    fig = go.Figure()
    n = len(series)
    barra_visivel = padrao == "barra"

    for nome, valores, cor in series:
        fig.add_bar(name=nome, x=categorias, y=valores, marker_color=cor, visible=barra_visivel)
    for nome, valores, cor in series:
        fig.add_trace(go.Scatter(
            name=nome, x=categorias, y=valores, mode="lines+markers",
            line={"color": cor, "width": 3}, visible=not barra_visivel,
        ))
    n_extras = len(traces_extras) if traces_extras else 0
    for trace in (traces_extras or []):
        fig.add_trace(trace)

    visivel_barra = [True] * n + [False] * n + [True] * n_extras
    visivel_linha = [False] * n + [True] * n + [True] * n_extras
    fig.update_layout(
        title=titulo,
        yaxis_title=yaxis_title,
        updatemenus=[{
            "type": "buttons", "direction": "right", "showactive": True,
            "active": 0 if barra_visivel else 1,
            "x": 1, "xanchor": "right", "y": 1.18, "yanchor": "top",
            "buttons": [
                {"label": "Barra", "method": "update", "args": [{"visible": visivel_barra}]},
                {"label": "Linha", "method": "update", "args": [{"visible": visivel_linha}]},
            ],
        }],
        **(layout_extra or {}),
    )
    return fig
