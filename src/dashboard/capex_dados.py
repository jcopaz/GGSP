"""Camada de dados do CAPEX de Projetos e Obras (CJI4 Orçado + CJI3
Realizado) — trazida em 2026-08-11 (`fact_cji4_capex_obras`/
`fact_cji3_capex_obras`, ver build_star_schema.py) e agora com aba própria
no Side Bar, separada do OPEX (a pedido do usuário: "separar de vez as
camadas do OPEX para CAPEX").

Não reaproveita `src/engine/delta_calculator.calcular_delta` nem
`src/dashboard/tendencia.dados_tendencia`: os dois têm os nomes de tabela
(`fact_orcamento`/`fact_realizado`) fixos no SQL, não parametrizados — dá
menos risco escrever a mesma lógica aqui apontando pras tabelas de CJI4/CJI3
do que arriscar mexer em código já testado do lado OPEX.

Filtros da sidebar do organograma OPEX (Gerência/Coordenação/Centro de
Custo/PEP/Classificação/Pacote) NÃO se aplicam aqui — são de um vocabulário
diferente (`gerencia_nome`/`pacote_id`), sem correspondência com
`gerencia_obras`/`e_pep_projeto` do CAPEX Obras. Só 2 filtros da sidebar se
aplicam: Período (Ano/Trimestre/Mês — `ano`/`mes` existem nas duas fontes
com o mesmo significado) e, desde 2026-08-11 (a pedido do usuário: "preciso
ter um filtro no side bar com o projeto... os projetos também têm elemento
pep"), Projeto/Elemento PEP (`clausula_projeto_capex` em filtros.py, grupo
próprio "CAPEX Obras (Projeto/PEP)" na sidebar). `_filtro_base_capex()`
combina os 2, usado por toda consulta deste módulo.

**Escopo de Gerência confirmado em 2026-08-12** (usuário, após cruzamento
com o de/para oficial da planilha-mãe do PMO — ver docs/02-perguntas-em-
aberto.md, item 21): as 5 Gerências de Obras (Expansão, Obras
Ferroviárias, Baixada Santista, Mobilidade Urbana, Corredor São Paulo) são
todas GGG_0054/DINFRA. Sem filtro de `gg_escopo_dinfra` mesmo assim — não
porque o escopo seja incerto, mas porque não existe `gg_id` nessas tabelas
e não há nada fora do escopo pra cortar (100% confirmado dentro).
"""
from __future__ import annotations

import duckdb
import pandas as pd

from src.dashboard.filtros import (
    clausula_escopo_obras,
    clausula_periodo,
    clausula_projeto_capex,
    combinar_clausulas,
)

_TABELA_ORCADO = "fact_cji4_capex_obras"
_TABELA_REALIZADO = "fact_cji3_capex_obras"

_COLUNAS_UNIAO = [
    "e_pep_projeto", "elemento_pep", "classe_custo",
    "conta_interna_id", "conta_interna_nome", "nome_empreendimento", "gerencia_obras",
]


def _tabela_existe(con: duckdb.DuckDBPyConnection, nome: str) -> bool:
    (n,) = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [nome],
    ).fetchone()
    return n > 0


def tabelas_disponiveis(con: duckdb.DuckDBPyConnection) -> tuple[bool, bool]:
    """(tem_orcado, tem_realizado) — os 2 arquivos (CJI4/CJI3) são
    independentes entre si (ver build_star_schema.py), então cada página
    trata os 2 casos: só Orçado carregado, só Realizado, os dois, ou
    nenhum."""
    return _tabela_existe(con, _TABELA_ORCADO), _tabela_existe(con, _TABELA_REALIZADO)


def _fonte_uniao(tem_orc: bool, tem_real: bool) -> str | None:
    """SQL de união (Orçado + Realizado) só das colunas descritivas comuns
    (não financeiras) — usado pra enriquecer nome de Projeto/Conta/Gerência
    de Obras a partir de qualquer um dos 2 lados que tiver a informação."""
    colunas_sql = ", ".join(_COLUNAS_UNIAO)
    partes = []
    if tem_orc:
        partes.append(f"SELECT {colunas_sql} FROM {_TABELA_ORCADO}")
    if tem_real:
        partes.append(f"SELECT {colunas_sql} FROM {_TABELA_REALIZADO}")
    if not partes:
        return None
    return " UNION ALL ".join(partes)


def _agregado(
    con: duckdb.DuckDBPyConnection, tabela: str, existe: bool, coluna_valor: str,
    dims: list[str], where: str, params: list,
) -> pd.DataFrame:
    if not existe:
        return pd.DataFrame(columns=[*dims, coluna_valor])
    dims_sql = ", ".join(dims)
    return con.execute(
        f"SELECT {dims_sql}, SUM({coluna_valor}) AS {coluna_valor} "
        f"FROM {tabela} WHERE 1=1{where} GROUP BY {dims_sql}",
        params,
    ).df()


def _filtro_base_capex() -> tuple[str, list]:
    """Combina Período + Projeto/Elemento PEP da sidebar + o recorte de
    escopo do universo `capex_obras` (RBAC — docs/08, Fase RBAC-A.2, por
    `gerencia_obras`/`e_pep_projeto`). Usado por toda consulta deste
    módulo."""
    return combinar_clausulas(
        clausula_periodo(), clausula_projeto_capex(), clausula_escopo_obras()
    )


def calcular_delta_capex(
    con: duckdb.DuckDBPyConnection, dims: list[str], where: str = "", params: list | None = None,
) -> pd.DataFrame:
    """Mesma lógica de `delta_calculator.calcular_delta`, apontando pras
    tabelas de CAPEX Obras — `where`/`params` aplicados aos 2 lados (Orçado
    e Realizado têm exatamente as mesmas colunas descritivas aqui, ao
    contrário do par fact_orcamento/fact_realizado)."""
    params = params or []
    tem_orc, tem_real = tabelas_disponiveis(con)
    orcado = _agregado(con, _TABELA_ORCADO, tem_orc, "valor_orcado", dims, where, params)
    realizado = _agregado(con, _TABELA_REALIZADO, tem_real, "valor_realizado", dims, where, params)
    orcado = orcado.rename(columns={"valor_orcado": "orcado"})
    realizado = realizado.rename(columns={"valor_realizado": "realizado"})

    delta = orcado.merge(realizado, on=dims, how="outer") if dims else pd.concat([orcado, realizado], axis=1)
    delta["orcado"] = delta["orcado"].fillna(0.0)
    delta["realizado"] = delta["realizado"].fillna(0.0)
    delta["delta_total"] = delta["realizado"] - delta["orcado"]
    return delta


def resumo_geral_capex(con: duckdb.DuckDBPyConnection) -> dict:
    tem_orc, tem_real = tabelas_disponiveis(con)
    where_periodo, params_periodo = _filtro_base_capex()

    orcado = 0.0
    if tem_orc:
        (orcado,) = con.execute(
            f"SELECT COALESCE(SUM(valor_orcado), 0) FROM {_TABELA_ORCADO} WHERE 1=1{where_periodo}",
            params_periodo,
        ).fetchone()
    realizado = 0.0
    if tem_real:
        (realizado,) = con.execute(
            f"SELECT COALESCE(SUM(valor_realizado), 0) FROM {_TABELA_REALIZADO} WHERE 1=1{where_periodo}",
            params_periodo,
        ).fetchone()

    delta = realizado - orcado
    aderencia = (realizado / orcado) if orcado else None
    return {
        "orcado": orcado, "realizado": realizado, "delta": delta, "aderencia": aderencia,
        "tem_orcado": tem_orc, "tem_realizado": tem_real,
    }


def dados_gerencia_obras(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Orçado x Real x Delta por Gerência de Obras (Expansão, Obras
    Ferroviárias, Baixada Santista, Mobilidade Urbana, Corredor São Paulo)
    — equivalente ao Nível 1 (por GG) do lado OPEX, mas `gerencia_obras` já
    vem preenchida direto nas 2 tabelas (via Catálogo CAPEX Obras), sem
    precisar de bucket "Não atribuído" só pra CAPEX (esse bucket ainda
    existe pra linha sem catálogo casado — fica com rótulo vazio)."""
    where_periodo, params_periodo = _filtro_base_capex()
    df = calcular_delta_capex(con, dims=["gerencia_obras"], where=where_periodo, params=params_periodo)
    if df.empty:
        return df
    df["gerencia_obras"] = df["gerencia_obras"].fillna("")
    df["aderencia"] = df.apply(lambda r: (r["realizado"] / r["orcado"]) if r["orcado"] else None, axis=1)
    df["rotulo"] = df["gerencia_obras"].replace("", "Não catalogado")
    return df.reindex(df["orcado"].add(df["realizado"]).sort_values(ascending=False).index).reset_index(drop=True)


def dados_projetos(con: duckdb.DuckDBPyConnection, gerencia_obras: str | None = None) -> pd.DataFrame:
    """Orçado x Real x Delta por Projeto (`e_pep_projeto`) — equivalente ao
    Pacote do lado OPEX. `gerencia_obras=None` = todos os projetos; um
    valor específico recorta só os projetos daquela Gerência de Obras."""
    where_periodo, params_periodo = _filtro_base_capex()
    where, params = where_periodo, list(params_periodo)
    if gerencia_obras is not None:
        where += " AND gerencia_obras = ?"
        params.append(gerencia_obras)

    df = calcular_delta_capex(con, dims=["e_pep_projeto"], where=where, params=params)
    if df.empty:
        return df

    tem_orc, tem_real = tabelas_disponiveis(con)
    uniao = _fonte_uniao(tem_orc, tem_real)
    if uniao:
        nomes = con.execute(
            f"SELECT e_pep_projeto, MAX(NULLIF(nome_empreendimento, '')) AS nome_empreendimento, "
            f"MAX(NULLIF(gerencia_obras, '')) AS gerencia_obras FROM ({uniao}) GROUP BY e_pep_projeto"
        ).df()
        df = df.merge(nomes, on="e_pep_projeto", how="left")
    else:
        df["nome_empreendimento"] = ""
        df["gerencia_obras"] = ""
    df["nome_empreendimento"] = df["nome_empreendimento"].fillna("")
    df["gerencia_obras"] = df["gerencia_obras"].fillna("")
    return df.reindex(df["delta_total"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def rotulo_projeto(e_pep_projeto: str, nome_empreendimento: str | None = None) -> str:
    nome = (nome_empreendimento or "").strip()
    if nome:
        return f"{e_pep_projeto} - {nome}"
    return e_pep_projeto


def dados_contas(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Grão fino Gerência de Obras → Projeto → Conta (`conta_interna_id`),
    pro Nível 4 (árvore) e pro ranking de maiores desvios."""
    where_periodo, params_periodo = _filtro_base_capex()
    df = calcular_delta_capex(
        con, dims=["gerencia_obras", "e_pep_projeto", "conta_interna_id"],
        where=where_periodo, params=params_periodo,
    )
    if df.empty:
        return df
    df["gerencia_obras"] = df["gerencia_obras"].fillna("")

    tem_orc, tem_real = tabelas_disponiveis(con)
    uniao = _fonte_uniao(tem_orc, tem_real)
    if uniao:
        nomes_conta = con.execute(
            f"SELECT conta_interna_id, MAX(NULLIF(conta_interna_nome, '')) AS conta_interna_nome "
            f"FROM ({uniao}) GROUP BY conta_interna_id"
        ).df()
        nomes_projeto = con.execute(
            f"SELECT e_pep_projeto, MAX(NULLIF(nome_empreendimento, '')) AS nome_empreendimento "
            f"FROM ({uniao}) GROUP BY e_pep_projeto"
        ).df()
        df = df.merge(nomes_conta, on="conta_interna_id", how="left")
        df = df.merge(nomes_projeto, on="e_pep_projeto", how="left")
    else:
        df["conta_interna_nome"] = ""
        df["nome_empreendimento"] = ""
    df["conta_interna_nome"] = df["conta_interna_nome"].fillna("")
    df["nome_empreendimento"] = df["nome_empreendimento"].fillna("")
    return df


_NOMES_MES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
              7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def dados_tendencia_capex(
    con: duckdb.DuckDBPyConnection, ano_fiscal: int,
    gerencia_obras: str | None = None, e_pep_projeto: str | None = None,
) -> pd.DataFrame:
    """Mesmo formato de saída de `tendencia.dados_tendencia` (mes,
    orcado_acumulado, realizado_acumulado, tem_realizado,
    tendencia_acumulada) — pra reaproveitar `tendencia.figura_tendencia`
    sem duplicar o gráfico. `HAVING COUNT(*) FILTER (...) > 0` no Realizado:
    mesma correção de 2026-08-11 aplicada em `tendencia.dados_tendencia`,
    caso a fonte também venha com linha futura de valor 0.

    `gerencia_obras`/`e_pep_projeto`: recorte explícito do seletor do
    Painel Executivo (não da sidebar). Além disso, também aplica o filtro
    de Projeto/Elemento PEP da sidebar (`clausula_projeto_capex`) — não o
    de Período, que aqui é sempre o ano inteiro (`ano_fiscal`), igual
    `tendencia.dados_tendencia` também ignora o Período da sidebar."""
    tem_orc, tem_real = tabelas_disponiveis(con)
    filtros, params = ["ano = ?"], [ano_fiscal]
    if gerencia_obras:
        filtros.append("gerencia_obras = ?")
        params.append(gerencia_obras)
    if e_pep_projeto:
        filtros.append("e_pep_projeto = ?")
        params.append(e_pep_projeto)
    where_sidebar, params_sidebar = clausula_projeto_capex()
    where_escopo, params_escopo = clausula_escopo_obras()  # RBAC de escopo (docs/08)
    where = " AND ".join(filtros) + where_sidebar + where_escopo
    params = params + params_sidebar + params_escopo

    if tem_orc:
        df_orc = con.execute(
            f"SELECT mes, SUM(valor_orcado) AS orcado FROM {_TABELA_ORCADO} WHERE {where} GROUP BY mes",
            params,
        ).df()
    else:
        df_orc = pd.DataFrame(columns=["mes", "orcado"])
    if tem_real:
        df_real = con.execute(
            f"SELECT mes, SUM(valor_realizado) AS realizado FROM {_TABELA_REALIZADO} WHERE {where} GROUP BY mes "
            f"HAVING COUNT(*) FILTER (WHERE valor_realizado != 0) > 0",
            params,
        ).df()
    else:
        df_real = pd.DataFrame(columns=["mes", "realizado"])

    df = pd.DataFrame({"mes": range(1, 13)}).merge(df_orc, on="mes", how="left").merge(
        df_real, on="mes", how="left", suffixes=("", "_real")
    )
    df["orcado"] = df["orcado"].fillna(0.0)
    df["orcado_acumulado"] = df["orcado"].cumsum()
    df["tem_realizado"] = df["mes"].isin(df_real["mes"])
    df["realizado"] = df["realizado"].fillna(0.0)
    df["realizado_acumulado"] = df["realizado"].cumsum()
    df["mes_nome"] = df["mes"].map(_NOMES_MES)

    # Fórmula do Forecast (mesma de tendencia.py, recebida do usuário em
    # 2026-08-12 — ver docstring lá): saldo do que já desviou do Orçado
    # até o mês de referência, redistribuído nos meses restantes.
    df["tendencia_acumulada"] = pd.NA
    meses_com_dado = df.loc[df["tem_realizado"], "mes"]
    if not meses_com_dado.empty:
        ultimo_mes = int(meses_com_dado.max())
        acumulado_ate_agora = df.loc[df["mes"] == ultimo_mes, "realizado_acumulado"].iloc[0]
        orcado_acumulado_ate_agora = df.loc[df["mes"] == ultimo_mes, "orcado_acumulado"].iloc[0]
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


def dados_heatmap_gerencia_projeto(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """1 linha por (Gerência de Obras, Projeto) — mesmo grão do mapa de
    calor Gerência x Pacote do lado OPEX, ver mapa_calor_gerencia_pacote.py."""
    where_periodo, params_periodo = _filtro_base_capex()
    df = calcular_delta_capex(
        con, dims=["gerencia_obras", "e_pep_projeto"], where=where_periodo, params=params_periodo,
    )
    if df.empty:
        return df
    df["gerencia_obras"] = df["gerencia_obras"].fillna("")
    df["gerencia_rotulo"] = df["gerencia_obras"].replace("", "Não catalogado")
    return df
