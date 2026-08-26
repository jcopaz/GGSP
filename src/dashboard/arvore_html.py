"""Helpers compartilhados pelas árvores HTML colapsáveis (<details>/<summary>
nativos do navegador, sem dependência de componente externo) usadas no
Nível 4 (Contas) e no Nível 5 (Centro de Custo), e reaproveitadas na Visão
Manutenção — mesmo estilo visual "Visão acumulado" do Power BI de
referência trazido pelo usuário em 2026-08-06.

Extraído de nivel4_contas.py em 2026-08-06 (a pedido do usuário: "ficou
muito bom o Nível 4, faça a mesma coisa no Nível 5") para não duplicar
CSS/HTML entre os dois níveis e a Visão Manutenção.
"""
from __future__ import annotations

import html as _html

from src.dashboard.formatacao import fmt_pct, fmt_reais_abrev

# Rótulos de Família de Pacote — vêm de DRE_FINAL observado nos dados reais
# (DRE011132-MANUTENÇÃO, DRE011133-DESPESAS GERAIS, DRE011131-PESSOAL), não
# é chute (ver histórico em nivel4_contas.py).
NOME_FAMILIA = {
    "PM": "Manutenção",
    "PD": "Despesas Gerais",
    "PP": "Pessoal",
    "PASSIVO": "Passivo",
}

CSS_ARVORE = """
<style>
.pnl-arvore { font-family: -apple-system, sans-serif; font-size: 13px; }
.pnl-arvore details { margin-bottom: 2px; }
.pnl-arvore summary { cursor: pointer; list-style: none; padding: 6px 8px; border-radius: 4px; }
.pnl-arvore summary::-webkit-details-marker { display: none; }
.pnl-arvore summary::before { content: "▶ "; font-size: 10px; }
.pnl-arvore details[open] > summary::before { content: "▼ "; }
.pnl-linha { display: grid; grid-template-columns: 1fr 130px 130px 130px 90px; gap: 4px; align-items: center; }
.pnl-linha-simples { display: grid; grid-template-columns: 1fr 140px; gap: 4px; align-items: center; padding: 3px 8px 3px 28px; }
.pnl-linha-simples:nth-child(odd) { background: rgba(127,127,127,0.05); }
.pnl-folha { padding: 3px 8px 3px 28px; }
.pnl-folha:nth-child(odd) { background: rgba(127,127,127,0.05); }
.pnl-nivel1 > summary { background: #1f3864; color: white; font-weight: 600; }
.pnl-nivel1 { margin-top: 8px; }
.pnl-nivel2 > summary { background: rgba(31,56,100,0.10); font-weight: 600; }
.pnl-nivel3 > summary { background: transparent; font-weight: 500; font-size: 12px; color: #555; padding-left: 20px; }
.pnl-num { text-align: right; font-variant-numeric: tabular-nums; }
.pnl-hdr { display: grid; grid-template-columns: 1fr 130px 130px 130px 90px; gap: 4px; font-weight: 600; font-size: 11px; color: #666; padding: 4px 8px; border-bottom: 1px solid #ddd; }
</style>
"""


def esc(valor) -> str:
    return _html.escape(str(valor))


def linha_resumo(rotulo: str, orcado: float, realizado: float, delta: float, classe_extra: str = "") -> str:
    """1 linha de 5 colunas (rótulo, Orçado, Real, Var. fin, Adr fin) — usada
    tanto em <summary> (níveis colapsáveis) quanto como linha-folha simples
    (`classe_extra="pnl-folha"`, ex.: Centro de Custo no Nível 5)."""
    aderencia = fmt_pct((realizado / orcado) if orcado else None)
    cor_delta = "crimson" if delta > 0 else "seagreen" if delta < 0 else "inherit"
    classe = f"pnl-linha {classe_extra}".strip()
    return (
        f'<div class="{classe}">'
        f"<span>{esc(rotulo)}</span>"
        f'<span class="pnl-num">{esc(fmt_reais_abrev(orcado))}</span>'
        f'<span class="pnl-num">{esc(fmt_reais_abrev(realizado))}</span>'
        f'<span class="pnl-num" style="color:{cor_delta}">{esc(fmt_reais_abrev(delta))}</span>'
        f'<span class="pnl-num">{esc(aderencia)}</span>'
        "</div>"
    )


def cabecalho_arvore(rotulo_primeira_coluna: str) -> str:
    return (
        f'<div class="pnl-hdr"><span>{esc(rotulo_primeira_coluna)}</span>'
        '<span class="pnl-num">Orçado</span><span class="pnl-num">Real</span>'
        '<span class="pnl-num">Var. fin</span><span class="pnl-num">Adr fin</span></div>'
    )


def subarvore(titulo: str, linhas_html: list[str]) -> str:
    """Grupo colapsável de linhas-folha simples, com contagem no título
    (ex.: as duas subárvores de Conta do Nível 4 — Orçamento x Realizado)."""
    if not linhas_html:
        return ""
    return (
        f'<details class="pnl-nivel3"><summary>{esc(titulo)} ({len(linhas_html)})</summary>'
        + "".join(linhas_html)
        + "</details>"
    )
