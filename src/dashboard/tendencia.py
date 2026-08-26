"""Gráfico de tendência anual: Orçado (Planejado) acumulado x Realizado
acumulado x Forecast pontilhado até o fim do ano fiscal — pra ver se o
comportamento do ano vai fechar em linha com o Orçamento ou estourar.

**Fórmula do Forecast — recebida do usuário em 2026-08-12, fecha o item 2
de docs/02-perguntas-em-aberto.md (fonte do PMO, antes não recebida):**

```
saldo = Realizado_Acumulado(mês_referência) - Orçado_Acumulado(mês_referência)
Forecast_mês = Orçado_mês - (saldo / nº meses restantes), para cada mês > mês_referência
```

Ou seja: o quanto já estourou (ou economizou) até o mês de referência é
redistribuído igualmente pelos meses restantes, subtraído do Orçado
original de cada um — se estourou, os meses futuros ficam com Forecast
menor que o Orçado (compensando); se economizou, ficam maior (recuperando
o ritmo). Por construção, o Forecast Acumulado de dezembro sempre fecha
exatamente no Orçado Anual — é a "curva S" de volta ao ritmo do Orçado que
o usuário descreveu. Substitui a extrapolação mecânica (run-rate) usada
antes dessa fórmula chegar — mesmo variável interna (`tendencia_acumulada`)
por simplicidade de não quebrar quem já consome esse DataFrame, mas o
cálculo agora é este, não mais run-rate.

CLAUDE.md decide que não existe uma versão "Planejado" separada de
"Orçamento" (só Orçamento Aprovado / Base Zero) — a linha "Planejado" que o
usuário pediu é a mesma série do Orçamento, só renomeada aqui porque é como
a Diretoria já enxerga esse número nas RDGs.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go

from src.dashboard.formatacao import fmt_reais_abrev
from src.dashboard.grafico_interativo import com_alternancia_barra_linha
from src.dashboard.paleta import COR_FORECAST, COR_ORCADO, COR_REALIZADO

_NOMES_MES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
              7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def dados_tendencia(
    con: duckdb.DuckDBPyConnection,
    ano_fiscal: int,
    pacotes: list[str] | None = None,
    familia: str | None = None,
    filtro_orcado: tuple[str, list] | None = None,
    filtro_realizado: tuple[str, list] | None = None,
) -> pd.DataFrame:
    """1 linha por mês (1-12) com Orçado/Realizado acumulados + projeção.

    `pacotes`: lista de pacote_id pra filtrar (None = sem filtro).
    `familia`: familia_pacote pra filtrar (None = sem filtro). Os dois
    filtros podem ser combinados.

    `filtro_orcado`/`filtro_realizado`: fragmento SQL pronto (começando com
    " AND ") + params, no mesmo formato de `clausula_where`/
    `clausula_periodo`/`calcular_delta` — usado pelos Níveis 4/5 pra
    mostrar a tendência do recorte que estiver filtrado na sidebar
    (Pacote/Centro de Custo/PEP/Coordenação/Gerência/Classificação/Período),
    não só Pacote/Família isolados. Adicionado em 2026-08-10.
    """
    filtros_orc, params_orc = ["ano = ?"], [ano_fiscal]
    filtros_real, params_real = ["ano = ?"], [ano_fiscal]

    if familia:
        filtros_orc.append("familia_pacote = ?")
        params_orc.append(familia)
        filtros_real.append("familia_pacote = ?")
        params_real.append(familia)

    if pacotes is not None:
        marcadores = ", ".join("?" * len(pacotes)) if pacotes else "NULL"
        filtros_orc.append(f"pacote_id IN ({marcadores})")
        params_orc += pacotes
        filtros_real.append(f"pacote_id IN ({marcadores})")
        params_real += pacotes

    if filtro_orcado is not None:
        fragmento, params = filtro_orcado
        if fragmento:
            filtros_orc.append(fragmento.lstrip().removeprefix("AND ").strip())
            params_orc += params
    else:
        # Sem filtro fino da sidebar (chamada simples de Resumo Executivo/
        # Painel Executivo, só com pacotes=/familia=): Realizado só tem
        # OPEX por construção (ver build_star_schema.py) — sem essa trava
        # o Orçado somaria CAPEX também e a Tendência compararia escopos
        # diferentes (corrigido em 2026-08-11, mesmo ajuste de
        # nivel1_diretoria.py/nivel2_gg.py). Quando o caller já manda
        # `filtro_orcado` (Nível 4/5, recorte da sidebar), respeita o que
        # o usuário filtrou lá — inclusive se ele pediu CAPEX de propósito.
        filtros_orc.append("classificacao_contabil = 'OPEX'")
    if filtro_realizado is not None:
        fragmento, params = filtro_realizado
        if fragmento:
            filtros_real.append(fragmento.lstrip().removeprefix("AND ").strip())
            params_real += params

    df_orc = con.execute(
        f"SELECT mes, SUM(valor_orcado) AS orcado FROM fact_orcamento "
        f"WHERE {' AND '.join(filtros_orc)} GROUP BY mes",
        params_orc,
    ).df()
    # `HAVING ... FILTER (valor_realizado != 0) > 0` — corrigido em
    # 2026-08-11: `fact_realizado` (Consulta de Contas, ver
    # build_star_schema.py) tem linhas pré-populadas pro ano inteiro, com
    # `valor_realizado = 0` pros meses que ainda não aconteceram (achado
    # real: ~277 linhas em cada mês de Set-Dez, todas exatas 0). Sem esse
    # filtro, `GROUP BY mes` devolvia linha pra Set-Dez mesmo sem nenhuma
    # execução real, e a linha Realizado do gráfico ficava "plana com
    # marcador" até dezembro em vez de simplesmente parar no último mês
    # com dado de verdade (só a Tendência pontilhada deveria continuar
    # depois disso). `FILTER` em vez de só excluir soma=0 (`HAVING SUM !=
    # 0`) pra não esconder por engano um mês raro cuja soma líquida deu
    # zero por coincidência mas teve lançamento real.
    df_real = con.execute(
        f"SELECT mes, SUM(valor_realizado) AS realizado FROM fact_realizado "
        f"WHERE {' AND '.join(filtros_real)} GROUP BY mes "
        f"HAVING COUNT(*) FILTER (WHERE valor_realizado != 0) > 0",
        params_real,
    ).df()

    df = pd.DataFrame({"mes": range(1, 13)}).merge(df_orc, on="mes", how="left").merge(
        df_real, on="mes", how="left", suffixes=("", "_real")
    )
    df["orcado"] = df["orcado"].fillna(0.0)
    df["orcado_acumulado"] = df["orcado"].cumsum()

    # Só acumula nos meses que realmente têm lançamento — não confundir
    # "mês sem lançamento ainda" com "mês com realizado = 0".
    df["tem_realizado"] = df["mes"].isin(df_real["mes"])
    df["realizado"] = df["realizado"].fillna(0.0)
    df["realizado_acumulado"] = df["realizado"].cumsum()
    df["mes_nome"] = df["mes"].map(_NOMES_MES)

    df["tendencia_acumulada"] = pd.NA
    meses_com_dado = df.loc[df["tem_realizado"], "mes"]
    if not meses_com_dado.empty:
        ultimo_mes = int(meses_com_dado.max())
        acumulado_ate_agora = df.loc[df["mes"] == ultimo_mes, "realizado_acumulado"].iloc[0]
        orcado_acumulado_ate_agora = df.loc[df["mes"] == ultimo_mes, "orcado_acumulado"].iloc[0]
        # Fórmula do Forecast (ver docstring do módulo): saldo do que já
        # desviou do Orçado até agora, redistribuído nos meses restantes.
        saldo = acumulado_ate_agora - orcado_acumulado_ate_agora
        meses_restantes = list(range(ultimo_mes + 1, 13))
        ajuste_mensal = (saldo / len(meses_restantes)) if meses_restantes else 0.0

        df.loc[df["mes"] == ultimo_mes, "tendencia_acumulada"] = acumulado_ate_agora
        acumulado_forecast = acumulado_ate_agora
        for m in meses_restantes:
            orcado_mes = df.loc[df["mes"] == m, "orcado"].iloc[0]
            acumulado_forecast += (orcado_mes - ajuste_mensal)
            df.loc[df["mes"] == m, "tendencia_acumulada"] = acumulado_forecast

    return df


def figura_tendencia(df: pd.DataFrame, titulo: str) -> go.Figure:
    """Linha (padrão) x Barra alternável nos 2 acumulados (Orçado/
    Realizado) via botões — pedido do usuário em 2026-08-11. Migrado pro
    helper compartilhado `com_alternancia_barra_linha` em 2026-08-13
    (achado #6 da auditoria de UX: esta função e
    `visao_manutencao._grafico_mensal` reimplementavam o mesmo padrão de
    `updatemenus` cada uma na sua, e já tinham divergido sutilmente —
    ordem dos botões, texto do rótulo). A Tendência (projeção pontilhada)
    entra como `traces_extras`: fica sempre como linha nos 2 modos — é
    uma projeção, não um valor fechado do mês, e uma barra sugeriria um
    valor "batido" que ela não é."""
    df_real = df[df["tem_realizado"]]

    traces_extras = []
    annotations = []
    df_tend = df[df["tendencia_acumulada"].notna()]
    if not df_tend.empty:
        traces_extras.append(go.Scatter(
            name="Forecast",
            x=df_tend["mes_nome"], y=df_tend["tendencia_acumulada"],
            mode="lines+markers", line={"color": COR_FORECAST, "width": 2, "dash": "dot"},
            text=[fmt_reais_abrev(v) for v in df_tend["tendencia_acumulada"]],
            hovertemplate="Forecast: %{text}<extra></extra>",
            visible=True,
        ))
        # Forecast Dez fecha exatamente no Orçado Anual, por construção da
        # fórmula (saldo redistribuído) — não vale a pena colorir crimson/
        # seagreen aqui como antes (run-rate podia divergir do Orçado; este
        # não diverge nunca).
        projecao_final = df_tend["tendencia_acumulada"].iloc[-1]
        annotations.append({
            "x": df_tend["mes_nome"].iloc[-1], "y": projecao_final,
            "text": f"Forecast Dez: {fmt_reais_abrev(projecao_final)}",
            "showarrow": True, "arrowhead": 2, "ax": 30, "ay": -40,
            "font": {"color": COR_FORECAST, "size": 12}, "arrowcolor": COR_FORECAST,
        })

    fig = com_alternancia_barra_linha(
        categorias=df["mes_nome"].tolist(),
        series=[
            ("Orçado (Planejado) — acumulado", df["orcado_acumulado"], COR_ORCADO),
            ("Realizado — acumulado", df_real["realizado_acumulado"], COR_REALIZADO),
        ],
        titulo=titulo,
        yaxis_title="Acumulado no ano (R$)",
        traces_extras=traces_extras,
        padrao="linha",
        layout_extra={
            "margin": {"t": 70, "b": 40},
            "hovermode": "x unified",
            "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02},
            "annotations": annotations,
        },
    )
    # Eixo X das barras/linhas de Orçado usa todos os 12 meses; Realizado
    # só os meses com dado — `com_alternancia_barra_linha` monta os 2
    # primeiros traces (índice 0=Orçado, 1=Realizado) com o `categorias`
    # cheio; o trace de Realizado precisa do eixo X próprio (mais curto),
    # corrigido abaixo em vez de dentro do helper genérico (só esta
    # chamada tem esse caso: séries de tamanho diferente).
    for indice in (1, 3):  # bar[1]=Realizado, line[3]=Realizado
        fig.data[indice].x = df_real["mes_nome"]
    for indice in range(4):
        y = fig.data[indice].y
        fig.data[indice].text = [fmt_reais_abrev(v) for v in y]
        nome = fig.data[indice].name
        fig.data[indice].hovertemplate = f"{nome}: %{{text}}<extra></extra>"
    return fig
