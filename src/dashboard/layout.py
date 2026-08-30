"""Blocos de layout compartilhados do painel — extraídos em 6.4.0
(passada de design UI/UX).

`bloco_resumo_visual` substitui o padrão que estava copiado literalmente
em 8 páginas:

    col_card, col_linha, col_graf = st.columns([1, 0.04, 3], gap="medium")
    with col_card:
        _render_card(...)
    with col_linha:
        st.markdown(
            "<div style='border-left: 1px solid #ccc; height: 100%; "
            "min-height: 420px; margin: 0 auto;'></div>",
            unsafe_allow_html=True,
        )
    with col_graf:
        st.plotly_chart(...)

Problema: a coluna-fantasma de proporção 0.04, com um `<div>` de altura
fixa (420–560px) dentro, virava um traço vertical solto no meio da tela
quando as colunas quebravam — o que acontecia sempre que o espaço
apertava (tela menor, ou sidebar aberto num notebook). O card e o
gráfico também encavalavam.

Agora são 2 colunas `[1, 3]`. A divisória é a borda esquerda do
`st.container(key=...)` do lado direito, via CSS em
`branding.inject_shell_css` (`[class*="st-key-f360-visualcol-"]`), que
some sozinha abaixo de 900px — empilhamento limpo, sem traço solto.
"""
from __future__ import annotations

from collections.abc import Callable

import streamlit as st

LEGENDA_SEMAFORO = (
    "🟢 95–105% · 🟡 90–95%/105–110% · 🔴 fora da faixa · ⚪ sem dado · "
    "🟣 delta relevante sem justificativa (sobrepõe a faixa de aderência)"
)

# Explicação da linha de Forecast — estava copiada quase igual embaixo de
# 4 gráficos de Tendência (resumo executivo, Nível 2, Nível 4, Nível 5).
_NOTA_FORECAST = (
    "Linha pontilhada = Forecast: saldo do desvio até o mês de referência "
    "redistribuído nos meses restantes, fechando no Orçado Anual em "
    "dezembro (fórmula do PMO)."
)
_NOTA_FORECAST_RECORTE = (
    " Segue o mesmo recorte de filtros aplicado acima "
    "(Pacote/Centro de Custo/PEP/Classificação/Coordenação/Gerência/Período)."
)


def bloco_resumo_visual(
    render_resumo: Callable[[], None],
    render_visual: Callable[[], None],
    *,
    key: str,
    proporcao: tuple[float, float] = (1.0, 3.0),
    gap: str = "medium",
) -> None:
    """"Card-resumo | divisória | visual principal" — layout padrão do
    topo de quase toda página do painel.

    - `render_resumo`: desenha o card da esquerda (recebe a coluna já
      ativa como contexto — só chamar `st.*` lá dentro).
    - `render_visual`: desenha o gráfico/tabela da direita.
    - `key`: sufixo único por página (ex.: `"n4"`, `"capex-resumo"`) —
      compõe a classe `st-key-f360-visualcol-<key>` que o CSS usa pra
      desenhar a borda divisória.
    """
    col_resumo, col_visual = st.columns(list(proporcao), gap=gap)
    with col_resumo:
        render_resumo()
    with col_visual:
        with st.container(key=f"f360-visualcol-{key}"):
            render_visual()


def legenda_semaforo() -> None:
    """`st.caption` da legenda do semáforo de aderência — mesma string
    estava copiada em 3+ páginas antes de 6.4.0."""
    st.caption(LEGENDA_SEMAFORO)


def nota_forecast(*, com_recorte: bool = False) -> None:
    """`st.caption` padrão embaixo de um gráfico de Tendência — texto
    unificado em 6.4.0 (estava copiado quase igual em 4 páginas).
    `com_recorte=True` acrescenta a frase de "segue os filtros do topo"
    (Nível 4/5)."""
    texto = _NOTA_FORECAST + (_NOTA_FORECAST_RECORTE if com_recorte else "")
    st.caption(texto)


def badge_filtros_ativos(resumo: str) -> None:
    """Chip discreto com o recorte de filtro atual, no topo da página —
    no lugar do `st.info` full-width, que gritava em toda página
    (6.4.0). `resumo` já vem pronto de
    `filtros.resumo_filtros_ativos()`."""
    st.markdown(
        f'<div class="f360-badge-filtros">🔎 Filtros ativos &nbsp;·&nbsp; {resumo}</div>',
        unsafe_allow_html=True,
    )
