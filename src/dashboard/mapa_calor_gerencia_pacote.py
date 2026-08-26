"""Mapa de calor Gerência x Pacote, dentro do Painel Executivo — pedido do
usuário em 2026-08-11: "como executivo, ver de cara onde está o problema",
cruzando as duas dimensões (Gerência do organograma, Pacote orçamentário)
numa grade só, com destaque pulsante nos Pacotes estourados.

HTML/CSS puro (não Plotly) — a animação "pulsante" pedida é CSS
(`@keyframes`), que o Plotly não tem como fazer nativamente. Mesmo caminho
já usado pela árvore colapsável do Nível 4/5 (`arvore_html.py`).

Cor da célula = Delta (vermelho estouro / verde economia), intensidade
proporcional ao maior |Delta| da própria grade (contraste local, não uma
escala fixa). Pisca só quando o Delta é estouro **e** ultrapassa o mesmo
threshold de materialidade já usado no nível Macro (R$100 mil — ver
docs/03-processo-justificativas-causas.md, seção 3.3) — sem isso, qualquer
estouro de R$500 já piscaria, virando ruído visual em vez de destaque.

**Visual "premium" (gradiente + sombra), pedido do usuário em 2026-08-11**:
cada célula preenchida usa um gradiente diagonal de 2 tons (não cor
chapada) na mesma família do diverging vermelho/verde, com a cor da letra
escolhida por luminância percebida do gradiente (não um corte fixo de
intensidade) — garante contraste em qualquer ponto da escala, inclusive
nas células que também estão piscando. Paleta inspirada nas rampas
vermelho/verde do tema padrão do Apache ECharts (tons vivos, não
pasteis) — avaliado como referência de "visual premium" pelo usuário, mas
a grade continua HTML/CSS puro (não um widget ECharts de verdade): o
componente ECharts de heatmap não tem como fazer a borda pulsante nativa
que já validamos aqui (ver parágrafo acima), então a troca perderia a
funcionalidade em troca só da biblioteca.
"""
from __future__ import annotations

import html as _html

import duckdb
import pandas as pd
import streamlit as st

from src.dashboard.filtros import clausula_periodo
from src.dashboard.formatacao import fmt_pacote, fmt_reais_abrev, mapa_nomes_pacote
from src.dashboard.nivel2_gg import _pacotes_do_gg
from src.dashboard.paleta import COR_ECONOMIA, COR_ESTOURO, hex_para_rgb

LIMIAR_PULSO = 100_000.0

_RGB_ESTOURO = ",".join(str(c) for c in hex_para_rgb(COR_ESTOURO))

CSS_MAPA_CALOR = f"""
<style>
.pnl-heatmap-wrap {{ overflow-x: auto; font-family: -apple-system, sans-serif; font-size: 12px; padding: 2px 0 6px; }}
.pnl-heatmap {{ border-collapse: separate; border-spacing: 3px; }}
.pnl-heatmap th, .pnl-heatmap td {{ padding: 8px 10px; text-align: center; white-space: nowrap; }}
.pnl-heatmap th {{ font-weight: 600; color: #555; font-size: 11px; border-bottom: 1px solid #ddd; }}
.pnl-heatmap th.pnl-hm-rotulo, .pnl-heatmap td.pnl-hm-rotulo {{
  text-align: left; position: sticky; left: 0; background: white; font-weight: 600;
}}
.pnl-heatmap td.pnl-hm-valor {{
  border-radius: 6px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 1px 2px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.30);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.pnl-heatmap td.pnl-hm-valor:hover {{
  transform: scale(1.07);
  box-shadow: 0 5px 12px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.35);
  position: relative;
  z-index: 2;
}}
.pnl-heatmap td.pnl-hm-vazio {{ color: #bbb; border-radius: 6px; }}
@keyframes pnl-hm-pulso {{
  0%   {{ box-shadow: 0 0 0 0 rgba({_RGB_ESTOURO},0.55), inset 0 1px 0 rgba(255,255,255,0.30); }}
  70%  {{ box-shadow: 0 0 0 10px rgba({_RGB_ESTOURO},0), inset 0 1px 0 rgba(255,255,255,0.30); }}
  100% {{ box-shadow: 0 0 0 0 rgba({_RGB_ESTOURO},0), inset 0 1px 0 rgba(255,255,255,0.30); }}
}}
.pnl-heatmap td.pnl-hm-pulsa {{
  animation: pnl-hm-pulso 1.6s infinite;
  border: 2px solid {COR_ESTOURO};
  font-weight: 700;
}}
</style>
"""


def dados_heatmap_gerencia_pacote(con: duckdb.DuckDBPyConnection, gg_id: str) -> pd.DataFrame:
    """1 linha por (Gerência, Pacote) com Orçado/Real/Delta — grão fino
    pro mapa de calor. Mesmo bucket "Não atribuído" do resto da visão por
    Gerência (`nivel2_gg.dados_gerencia_gg`) — no Orçado já não sobra
    nada aí desde 2026-08-17 (CAPEX atribuído por região SP/VP via
    `_GERENCIA_ID_POR_REGIAO_BASE_ZERO`, e o resto vira CGG050/"GG
    direto" via `_GERENCIA_ID_GG_DIRETO`, ambos em build_star_schema.py);
    só sobra "Não atribuído" de verdade no Realizado, pra linhas sem
    Gerência na hierarquia SAP. Filtro de Período (Ano/Trimestre/Mês)
    aplicado desde 2026-08-11."""
    pacotes = _pacotes_do_gg(con, gg_id)
    where_periodo, params_periodo = clausula_periodo()
    if pacotes is None:
        where_orc, params_orc = "WHERE 1=1", []
        where_real, params_real = "WHERE 1=1", []
    else:
        marcadores = ", ".join("?" * len(pacotes)) if pacotes else "NULL"
        where_orc, params_orc = f"WHERE pacote_id IN ({marcadores})", list(pacotes)
        where_real, params_real = f"WHERE pacote_id IN ({marcadores})", list(pacotes)
    where_orc += where_periodo
    params_orc += params_periodo
    where_real += where_periodo
    params_real += params_periodo

    df_orc = con.execute(
        f"SELECT COALESCE(gerencia_id, '') AS gerencia_id, pacote_id, "
        f"SUM(valor_orcado) AS orcado FROM fact_orcamento {where_orc} GROUP BY 1, 2",
        params_orc,
    ).df()
    df_real = con.execute(
        f"SELECT COALESCE(gerencia_id, '') AS gerencia_id, pacote_id, "
        f"MAX(NULLIF(gerencia_nome, '')) AS gerencia_nome, "
        f"SUM(valor_realizado) AS realizado FROM fact_realizado {where_real} GROUP BY 1, 2",
        params_real,
    ).df()

    df = df_orc.merge(df_real, on=["gerencia_id", "pacote_id"], how="outer")
    df["orcado"] = df["orcado"].fillna(0.0)
    df["realizado"] = df["realizado"].fillna(0.0)
    # `gerencia_nome` acima só vem do Realizado — completa via dim_gerencia
    # pra Gerências que só existem no Orçado (ex.: CGG050/"GG direto").
    df_dim_gerencia = con.execute("SELECT gerencia_id, gerencia_nome AS nome_dim FROM dim_gerencia").df()
    df = df.merge(df_dim_gerencia, on="gerencia_id", how="left")
    df["gerencia_nome"] = df["gerencia_nome"].fillna(df["nome_dim"]).fillna("")
    df = df.drop(columns=["nome_dim"])
    df["delta_total"] = df["realizado"] - df["orcado"]
    df["gerencia_rotulo"] = df.apply(
        lambda r: (r["gerencia_nome"] or r["gerencia_id"]) if r["gerencia_id"] else "Não atribuído",
        axis=1,
    )
    return df


# Rampas vermelho/verde (tons vivos, não pasteis) — mesma família de cor
# das paletas diverging padrão do ECharts, usada como referência de
# "visual premium" (pedido do usuário em 2026-08-11). Par claro/escuro por
# cor: interpolamos entre eles (não entre branco e a cor), pra sempre ter
# alguma saturação visível mesmo nas células de menor intensidade. Ponta
# escura derivada de `paleta.COR_ESTOURO`/`COR_ECONOMIA` (2026-08-13,
# achado #2 da auditoria de UX) — antes era uma tupla RGB solta, mesmo
# valor mas sem ligação com o resto do painel; agora não tem como
# divergir. Ponta clara continua local (tom claro específico deste
# gradiente, não faz parte da paleta semântica compartilhada).
_RAMPA_VERMELHO = ((255, 204, 199), hex_para_rgb(COR_ESTOURO))
_RAMPA_VERDE = ((217, 247, 190), hex_para_rgb(COR_ECONOMIA))


_TEXTO_ESCURO = (26, 26, 26)
_TEXTO_CLARO = (255, 255, 255)


def _misturar(cor_a: tuple[int, int, int], cor_b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(cor_a[i] + (cor_b[i] - cor_a[i]) * t) for i in range(3))


def _luminancia_relativa(cor: tuple[int, int, int]) -> float:
    """Luminância relativa WCAG (com correção de gama sRGB) — a fórmula
    linear simples (sem `** 2.4`) subestima o quanto tons de vermelho/verde
    de saturação média "parecem" escuros, e escolhia texto branco em
    células onde o contraste real (medido) ficava abaixo de 3:1."""
    def _linear(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (_linear(c) for c in cor)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(cor_a: tuple[int, int, int], cor_b: tuple[int, int, int]) -> float:
    la, lb = _luminancia_relativa(cor_a), _luminancia_relativa(cor_b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def _cor_celula(delta: float, max_abs: float) -> tuple[str, str]:
    """(fundo_css, cor_texto) — vermelho/verde diverging, intensidade
    proporcional ao maior |Delta| da própria grade (contraste local).

    `fundo_css` é um gradiente diagonal de 2 tons (não cor chapada) —
    visual "premium" pedido pelo usuário. `cor_texto` é escolhido pelo
    **pior caso** de contraste WCAG entre branco/escuro contra os 2 tons
    do gradiente (não a média) — com só a média, uma célula de
    intensidade média (tom claro no canto A, escuro no canto B) podia
    escolher texto branco pra ficar legível no canto B e sair ilegível
    (contraste medido ~2,4:1, abaixo até do mínimo de 3:1 pra texto
    grande) no canto A, que é mais claro."""
    if max_abs <= 0 or delta == 0:
        return "#f4f5f7", "#4b5563"

    intensidade = min(abs(delta) / max_abs, 1.0)
    clara, escura = _RAMPA_VERMELHO if delta > 0 else _RAMPA_VERDE

    # Stop A (topo-esquerda) sempre um pouco mais claro que o Stop B
    # (rodapé-direita) — dá a sensação de "brilho"/profundidade do
    # gradiente mesmo em células de baixa intensidade.
    cor_a = _misturar(clara, escura, intensidade * 0.55)
    cor_b = _misturar(clara, escura, min(intensidade * 1.15, 1.0))
    gradiente = f"linear-gradient(135deg, rgb{cor_a} 0%, rgb{cor_b} 100%)"

    pior_escuro = min(_contraste(cor_a, _TEXTO_ESCURO), _contraste(cor_b, _TEXTO_ESCURO))
    pior_claro = min(_contraste(cor_a, _TEXTO_CLARO), _contraste(cor_b, _TEXTO_CLARO))
    cor_texto = "#1a1a1a" if pior_escuro >= pior_claro else "#ffffff"
    return gradiente, cor_texto


def sombra_texto(cor_texto: str) -> str:
    """Halo (`text-shadow`) na cor oposta ao texto — reforça legibilidade
    nas células de intensidade média, onde os 2 tons do gradiente (claro
    no canto A, escuro no canto B) ficam longe o bastante um do outro pra
    nenhuma cor única de texto ter contraste bom nos 2 ao mesmo tempo
    (medido: só a escolha por pior-caso em `_cor_celula` não bastava,
    contraste mínimo ~2,85:1 na faixa de transição — abaixo do piso de
    3:1 pra texto grande da WCAG). Mesma técnica usada em rótulo sobre
    mapa/heatmap (halo), não um recurso decorativo à toa."""
    if cor_texto == "#ffffff":
        return "0 1px 2px rgba(0,0,0,0.70), 0 0 3px rgba(0,0,0,0.55)"
    return "0 1px 1px rgba(255,255,255,0.85), 0 0 3px rgba(255,255,255,0.65)"


def _html_mapa_calor(df: pd.DataFrame, nomes_pacote: dict[str, str]) -> str:
    gerencias = (
        df.groupby("gerencia_rotulo")["delta_total"].apply(lambda s: s.abs().sum())
        .sort_values(ascending=False).index.tolist()
    )
    pacotes = sorted(df["pacote_id"].unique().tolist())
    matriz = df.set_index(["gerencia_rotulo", "pacote_id"])
    max_abs = df["delta_total"].abs().max() or 0.0

    partes = [CSS_MAPA_CALOR, '<div class="pnl-heatmap-wrap"><table class="pnl-heatmap">']
    partes.append("<tr><th class='pnl-hm-rotulo'>Gerência \\ Pacote</th>")
    for pac in pacotes:
        partes.append(f"<th>{_html.escape(fmt_pacote(pac, nomes_pacote.get(pac)).split(' - ')[0])}</th>")
    partes.append("</tr>")

    for ger in gerencias:
        partes.append(f"<tr><td class='pnl-hm-rotulo'>{_html.escape(ger)}</td>")
        for pac in pacotes:
            if (ger, pac) not in matriz.index:
                partes.append("<td class='pnl-hm-vazio'>·</td>")
                continue
            linha = matriz.loc[(ger, pac)]
            delta = float(linha["delta_total"])
            orcado, realizado = float(linha["orcado"]), float(linha["realizado"])
            if orcado == 0.0 and realizado == 0.0:
                partes.append("<td class='pnl-hm-vazio'>·</td>")
                continue
            cor_fundo, cor_texto = _cor_celula(delta, max_abs)
            pulsa = " pnl-hm-pulsa" if delta > LIMIAR_PULSO else ""
            titulo = (
                f"{ger} · {fmt_pacote(pac, nomes_pacote.get(pac))}\n"
                f"Orçado: {fmt_reais_abrev(orcado)} | Realizado: {fmt_reais_abrev(realizado)} | "
                f"Delta: {fmt_reais_abrev(delta)}"
            )
            partes.append(
                f"<td class='pnl-hm-valor{pulsa}' title='{_html.escape(titulo)}' "
                f"style='background:{cor_fundo}; color:{cor_texto}; text-shadow:{sombra_texto(cor_texto)};'>"
                f"{_html.escape(fmt_reais_abrev(delta))}</td>"
            )
        partes.append("</tr>")

    partes.append("</table></div>")
    return "".join(partes)


def render_mapa_calor_gerencia_pacote(con: duckdb.DuckDBPyConnection, gg_id: str) -> None:
    df = dados_heatmap_gerencia_pacote(con, gg_id)
    if df.empty:
        return
    with st.expander("🔥 Mapa de Calor: Gerência x Pacote", expanded=False):
        st.caption(
            f"Delta (Realizado − Orçado) cruzando Gerência x Pacote. "
            f"Vermelho = estouro, verde = economia — intensidade proporcional "
            f"ao maior desvio da própria grade. Célula pulsando = estouro "
            f"acima de {fmt_reais_abrev(LIMIAR_PULSO)} (mesmo threshold de "
            f"materialidade do nível Pacote). Passe o cursor numa célula pra "
            f"ver Orçado/Realizado/Delta exatos."
        )
        st.markdown(
            _html_mapa_calor(df, mapa_nomes_pacote(con)), unsafe_allow_html=True,
        )
