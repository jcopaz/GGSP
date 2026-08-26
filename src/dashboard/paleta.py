"""Paleta de cores central do painel — cada cor definida 1x só, importada
por todo gráfico/card que precisar dela.

**Achado real da auditoria de UX de 2026-08-13**: antes deste módulo,
`#1f3864` (azul) e `#ffc000` (dourado) — as cores de identidade do
painel — eram redefinidas como constante local em 6+ arquivos
(`_COR_ORCADO`, `_COR_REAL`, `_COR_CLASSIFICACAO`, `_COR_COMPOSICAO`...).
Pior: "vermelho de estouro" tinha *duas* definições diferentes ao mesmo
tempo — a palavra-chave CSS `crimson` (≈ `#DC143C`) nos gráficos de barra
de Delta, e o hex `#a8071a` (mais escuro) só no mapa de calor — e o par
Orçado/Realizado da "Visão Gerências Locais" (resumo_executivo.py) usava
azul-claro/azul-escuro, ao contrário do resto do painel (azul-escuro/
dourado). Consolidado aqui, sem mudar a essência de nenhuma paleta — só
fechando as divergências achadas.
"""
from __future__ import annotations

# ---- Orçado x Realizado — identidade do painel, usada em qualquer
# gráfico que compare os dois lado a lado. ----
COR_ORCADO = "#1f3864"
COR_REALIZADO = "#ffc000"

# ---- Estouro / economia (Delta positivo/negativo) — mesmo tom em
# qualquer gráfico, do mapa de calor ao ranking de pacotes. Valor
# alinhado ao que já existia no mapa de calor (`_RAMPA_VERMELHO`/
# `_RAMPA_VERDE` em mapa_calor_gerencia_pacote.py) — os outros gráficos
# usavam `crimson`/`seagreen` (CSS), visualmente próximo mas não
# idêntico; agora é o mesmo hex em todo lugar. ----
COR_ESTOURO = "#a8071a"
COR_ECONOMIA = "#237804"

# ---- Neutro (fallback, categoria sem cor própria) e Forecast (linha de
# projeção pontilhada — não é Orçado nem Realizado, cinza de propósito). ----
COR_NEUTRO = "#a6a6a6"
COR_FORECAST = "#7f7f7f"

# ---- Padrão MRS pro universo CAPEX Obras (2026-08-19, definido pelo
# usuário: "Cor Azul = Orçado, Cor Amarela = Forecast") — usado em
# `pce_especialista.py` e demais análises CAPEX que comparem Orçado x
# Forecast. Reaproveita o mesmo hex de `COR_REALIZADO` (mesmo par
# visual azul/dourado do resto do painel); é um nome próprio, não um
# alias solto, porque aqui o "amarelo" representa Forecast, não
# Realizado — não confundir com `COR_FORECAST` acima (cinza pontilhado),
# que é a linha de projeção do Forecast oficial do PMO dentro do
# universo OPEX (tendencia.py), onde Orçado E Realizado já ocupam
# azul/amarelo e o Forecast é um 3º traço auxiliar, não um dos 2 lados
# do par. ----
COR_CAPEX_FORECAST = COR_REALIZADO

# ---- Componentes CAPEX (Via/EE) e Região (SP/VP) — eixo categórico
# distinto de Orçado/Realizado; reaproveita a dupla navy/azul-claro pra
# ficar na família visual do painel sem colidir com o par Orçado/
# Realizado (nenhum gráfico mostra os dois pares ao mesmo tempo). ----
COR_CAPEX_VIA = "#1f3864"
COR_CAPEX_EE = "#8faadc"
COR_REGIAO_SP = "#1f3864"
COR_REGIAO_VP = "#8faadc"

# ---- Classificação Contábil (CAPEX/OPEX) — badge e gráfico de
# composição, eixo categórico próprio. ----
COR_CAPEX = "#1f3864"
COR_OPEX = "#ffc000"

# ---- Faixas de Aderência (semáforo 95-105%/90-95%+105-110%/fora) ----
COR_ADERENCIA_OK = "#237804"
COR_ADERENCIA_ATENCAO = "#b8730a"
COR_ADERENCIA_FORA = "#a8071a"


def hex_para_rgb(cor_hex: str) -> tuple[int, int, int]:
    """"#a8071a" -> (168, 7, 26) — usado onde a cor precisa virar tupla RGB
    (ex.: rampa de gradiente do mapa de calor), pra derivar de uma cor já
    definida aqui em vez de duplicar o valor como tupla solta."""
    cor_hex = cor_hex.lstrip("#")
    return tuple(int(cor_hex[i : i + 2], 16) for i in (0, 2, 4))
