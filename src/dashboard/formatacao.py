"""Formatação de valores para exibição no painel (pt-BR). Camada de
apresentação só — os valores continuam em float em todo o resto do código
(ver CLAUDE.md: não formatar como string cedo demais)."""
from __future__ import annotations

import re

import pandas as pd

_PADRAO_PACOTE = re.compile(r"^([A-Za-z]+)(\d+)$")


def mapa_nomes_pacote(con) -> dict[str, str]:
    """pacote_id -> nome_pacote, de dim_pacote. Painel executivo não deve
    mostrar só o código (ex.: "PM03") — pedido do usuário em 2026-08-10."""
    df = con.execute("SELECT pacote_id, nome_pacote FROM dim_pacote").df()
    return dict(zip(df["pacote_id"], df["nome_pacote"].fillna("")))


def fmt_pacote(pacote_id: str | None, nome_pacote: str | None = None) -> str:
    """"PM03" -> "PM 03 - MATERIAIS E SERVIÇOS DE MALHA". Sem nome
    conhecido (ou nome igual ao próprio código, ex. "PASSIVO"), mostra só o
    código espaçado. Código fora do padrão letra+número (raro) fica como
    veio, sem inventar formatação."""
    if not pacote_id:
        return "—"
    codigo = str(pacote_id).strip()
    m = _PADRAO_PACOTE.match(codigo)
    codigo_fmt = f"{m.group(1)} {m.group(2)}" if m else codigo
    nome = (nome_pacote or "").strip()
    if nome and nome.upper() != codigo.upper():
        return f"{codigo_fmt} - {nome}"
    return codigo_fmt


def fmt_reais(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    texto = f"{abs(valor):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {texto}"


def fmt_reais_abrev(valor: float | None) -> str:
    """Versão arredondada/abreviada de `fmt_reais` — R$ 91,98 MM / R$ 850
    mil / R$ 320 — pra rótulo de gráfico e card, onde o valor cheio (R$
    91.981.280,00) polui a leitura. Nunca usar pra reconciliação/exportação
    (isso continua com o float exato ou `fmt_reais`) — é só camada de
    apresentação onde o objetivo é "bater o olho", não auditar o centavo."""
    if valor is None or pd.isna(valor):
        return "—"
    sinal = "-" if valor < 0 else ""
    absoluto = abs(valor)
    if absoluto >= 1_000_000_000:
        numero, sufixo, casas = absoluto / 1_000_000_000, " BI", 1
    elif absoluto >= 1_000_000:
        numero, sufixo, casas = absoluto / 1_000_000, " MM", 1
    elif absoluto >= 1_000:
        numero, sufixo, casas = absoluto / 1_000, " mil", 0
    else:
        numero, sufixo, casas = absoluto, "", 0
    texto = f"{numero:,.{casas}f}".replace(".", ",")
    return f"{sinal}R$ {texto}{sufixo}"


def escapar_cifrao_md(texto: str) -> str:
    """Escapa "$" antes de mandar um texto pro `st.markdown`/`st.caption` —
    o Streamlit interpreta qualquer PAR de "$" numa mesma chamada como
    LaTeX (MathJax): uma frase com 2 valores em Real ("R$ 45,0 MM ...
    Realizado R$ 35 mil") vira uma caixa de fórmula ilegível em vez de 2
    valores normais (bug real reportado pelo usuário em 2026-08-13, com
    print, na "Visão Gerências Locais" do Resumo Executivo). Usar só em
    texto que vai pro `st.markdown`/`st.caption`/`st.write` — nunca no
    `text=` do Plotly nem no `.format()` do pandas Styler/`st.dataframe`,
    que não interpretam markdown e mostrariam a barra invertida literal."""
    return texto.replace("$", r"\$")


def fmt_pct(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    if valor == 0:
        valor = 0.0  # normaliza -0.0 (ex.: 0 / delta_negativo) pra não mostrar "-0,0%"
    return f"{valor * 100:,.1f}%".replace(".", ",")


# Paleta restrita ao que o st.markdown ":cor[texto]" aceita (não é CSS
# livre) — mesma limitação já documentada em nivel1_diretoria.py.
_CORES_SEMAFORO_MD = {
    "Verde": "green", "Amarelo": "orange", "Vermelho": "red",
    "Cinza": "gray", "Roxo": "violet",
}
_EMOJI_SEMAFORO = {
    "Verde": "🟢", "Amarelo": "🟡", "Vermelho": "🔴", "Cinza": "⚪", "Roxo": "🟣",
}


def fmt_semaforo(status: str) -> str:
    """Badge markdown do status do semáforo CAPEX (ver
    src/engine/semaforo.py) — pronto pra colar num st.markdown."""
    emoji = _EMOJI_SEMAFORO.get(status, "")
    cor = _CORES_SEMAFORO_MD.get(status, "gray")
    return f"{emoji} :{cor}[**{status}**]"
