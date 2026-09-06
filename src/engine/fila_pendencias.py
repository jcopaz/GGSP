"""Fase 7a.2 — motor da Fila de Pendências (Etapa 7 da Visão Ideal, `docs/09` §4).

A Fila é uma **query, não uma tabela**: recalculada a cada carga, cruzando o
Delta atual (warehouse DuckDB) com as justificativas **vigentes**
(`app.fact_explicacao_log` no Neon — ou um DataFrame injetado, pra teste).
Aqui só entra o cálculo — a UI (4 painéis) é a Fase 7b.

Regras (`docs/09` §4, decisões do usuário de 2026-09-06):

- **Sustaining Micro** (Conta × Gerência) — **sem threshold**. Até 2 pendências
  por (universo, gerência, conta):
    - `mensal`   — Delta do mês da competência > 0 e não coberto por
                   justificativa `micro`/`mensal` vigente daquela competência;
    - `acumulada`— Delta acumulado até o último mês fechado > 0 e não coberto
                   por justificativa `micro`/`acumulado` vigente do ano. Essa
                   "carrega": se já existe versão de meses anteriores e o
                   acumulado segue > 0, vira "revisar" (não "sem justificativa").
- **Sustaining Macro** (Pacote) — **só `acumulada`**, e só quando
  `delta_acum_pacote > 0` **e** `delta_acum_pacote >= threshold_justificativa
  .macro_pacote` (config).
- **Obras** (Projeto / `e_pep_projeto`) — **só `acumulada`**, e só quando
  `abs(delta_acum_projeto) >= threshold_justificativa.obras_projeto` (config).
  (Obras usa `abs` — variação grande dos 2 lados; `docs/09` §4.2. Micro/Macro
  usam `> 0` — pendência é estouro.)
- **Só mês fechado**: competência ≤ `ate_mes` (último mês com Realizado
  carregado no ano fiscal — derivado do dado, igual `tendencia.py`; a página
  7b pode passar o mês de referência real da carga).
- **Some / reabre sozinha**: nada de "resolver" manual. Se a soma das
  justificativas vigentes cobre o Delta, não há pendência; se a próxima carga
  muda o Delta, a pendência reaparece.
- **Recorte por usuário**: a cláusula de escopo (`docs/08`) entra por
  parâmetro. Em script/teste sem sessão ela vem vazia (`("", [])` = vê tudo) —
  quem barra quem-não-tem-acesso é o guard da página, não o motor.

`fact_realizado` hoje só tem linhas `OPEX` (ver `docs/09` §4.3-bis): pra
`capex_sustaining` o Realizado vem vazio e o motor não gera pendência desse
universo até a MRS carregar esse dado. É o comportamento correto, não um bug.
"""
from __future__ import annotations

import duckdb
import pandas as pd

# Sinal do Delta = realizado - orçado (docs/00 §2): positivo = estouro.
_EPS = 0.01  # 1 centavo — Delta abaixo disso é ruído de arredondamento, não pendência.

_CLASSIFICACAO_DO_UNIVERSO = {
    "opex_sustaining": "OPEX",
    "capex_sustaining": "CAPEX",
}

COLUNAS_JUSTIFICATIVA = [
    "universo", "nivel", "escopo_temporal", "gerencia_id",
    "conta_interna_id", "pacote_id", "e_pep_projeto",
    "ano", "mes", "valor_explicado",
]

COLUNAS_PENDENCIA = [
    "universo", "nivel", "escopo_temporal", "gerencia_id", "pacote_id",
    "conta_interna_id", "e_pep_projeto", "ano", "mes_competencia",
    "orcado", "realizado", "delta", "delta_coberto", "delta_pendente",
    "tem_versao_anterior", "motivo",
]


def justificativas_vazio() -> pd.DataFrame:
    """Frame vazio no schema esperado — "nenhuma justificativa vigente"."""
    return pd.DataFrame(columns=COLUNAS_JUSTIFICATIVA)


def pendencias_vazio() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUNAS_PENDENCIA)


def carregar_justificativas_vigentes(universo: str | None = None) -> pd.DataFrame:
    """Lê `app.fact_explicacao_log WHERE vigente = true` do Neon
    (`src.auth.db`). **Falha-soft**: qualquer erro / Neon fora → frame vazio.
    O padrão seguro é "nada justificado" — a Fila mostra tudo como pendente,
    nunca esconde uma pendência real por causa de banco fora do ar.

    Ainda não há gravação nessa tabela pelo app (o store atual é o CSV solto,
    `data/staging/explicacoes.csv`) — esta função existe pra a Fase 7b já
    plugar sem retrabalho, e pro import do legado (Fase 7d)."""
    try:
        from src.auth.db import buscar_todos

        sql = (
            "SELECT universo, nivel, escopo_temporal, gerencia_id, "
            "conta_interna_id, pacote_id, e_pep_projeto, ano, mes, "
            "valor_explicado "
            "FROM app.fact_explicacao_log WHERE vigente = true"
        )
        params: tuple = ()
        if universo is not None:
            sql += " AND universo = %s"
            params = (universo,)
        linhas = buscar_todos(sql, params)
    except Exception:
        return justificativas_vazio()

    if not linhas:
        return justificativas_vazio()
    df = pd.DataFrame(linhas)
    for col in COLUNAS_JUSTIFICATIVA:
        if col not in df.columns:
            df[col] = pd.NA
    df["valor_explicado"] = pd.to_numeric(df["valor_explicado"], errors="coerce").fillna(0.0)
    return df[COLUNAS_JUSTIFICATIVA]


# --------------------------------------------------------------------------- #
# Delta por competência (mês) — Sustaining
# --------------------------------------------------------------------------- #
def _delta_sustaining_mensal(
    con: duckdb.DuckDBPyConnection, universo: str, escopo: tuple[str, list],
    ano_fiscal: int,
) -> pd.DataFrame:
    """Orçado × Realizado por (mês, gerência, pacote, conta) do universo
    Sustaining, filtrando `classificacao_contabil` nos 2 lados e aplicando o
    recorte de escopo (por `gerencia_id`, existe nos 2 fatos). Retorna
    `mes, gerencia_id, pacote_id, conta_interna_id, orcado, realizado`."""
    classificacao = _CLASSIFICACAO_DO_UNIVERSO[universo]
    esc, esc_p = escopo
    dims = ["mes", "gerencia_id", "pacote_id", "conta_interna_id"]
    dims_sql = ", ".join(dims)

    orcado = con.execute(
        f"SELECT {dims_sql}, SUM(valor_orcado) AS orcado FROM fact_orcamento "
        f"WHERE ano = ? AND classificacao_contabil = ?{esc} GROUP BY {dims_sql}",
        [ano_fiscal, classificacao, *esc_p],
    ).df()
    realizado = con.execute(
        f"SELECT {dims_sql}, SUM(valor_realizado) AS realizado FROM fact_realizado "
        f"WHERE ano = ? AND classificacao_contabil = ?{esc} GROUP BY {dims_sql}",
        [ano_fiscal, classificacao, *esc_p],
    ).df()

    df = orcado.merge(realizado, on=dims, how="outer")
    df["orcado"] = df["orcado"].fillna(0.0)
    df["realizado"] = df["realizado"].fillna(0.0)
    for col in ["gerencia_id", "pacote_id", "conta_interna_id"]:
        df[col] = df[col].fillna("")
    return df


def _ultimo_mes_realizado(
    con: duckdb.DuckDBPyConnection, tabela: str, coluna_valor: str, ano_fiscal: int,
) -> int:
    """Último mês do ano fiscal com pelo menos 1 linha de valor != 0 — mesma
    convenção de "mês com dado" de `tendencia.py`/`capex_dados.py`. 0 se não
    há Realizado nenhum (universo sem dado → sem mês fechado → sem pendência)."""
    row = con.execute(
        f"SELECT MAX(mes) FROM {tabela} "
        f"WHERE ano = ? AND {coluna_valor} IS NOT NULL AND {coluna_valor} != 0",
        [ano_fiscal],
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# --------------------------------------------------------------------------- #
# Cobertura por justificativa vigente
# --------------------------------------------------------------------------- #
def _soma_coberta(
    df_just: pd.DataFrame, filtro: dict, chaves: list[str],
) -> pd.DataFrame:
    """Soma `valor_explicado` das justificativas vigentes que casam com
    `filtro` (igualdade exata) agrupando por `chaves`. Retorna
    `chaves + ['delta_coberto', 'tem_versao_anterior']`."""
    if df_just.empty:
        return pd.DataFrame(columns=[*chaves, "delta_coberto", "tem_versao_anterior"])
    m = pd.Series(True, index=df_just.index)
    for col, val in filtro.items():
        m &= (df_just[col] == val)
    sub = df_just[m]
    if sub.empty:
        return pd.DataFrame(columns=[*chaves, "delta_coberto", "tem_versao_anterior"])
    agg = (
        sub.groupby(chaves, dropna=False)
        .agg(delta_coberto=("valor_explicado", "sum"),
             tem_versao_anterior=("valor_explicado", "size"))
        .reset_index()
    )
    agg["tem_versao_anterior"] = agg["tem_versao_anterior"] > 0
    return agg


# --------------------------------------------------------------------------- #
# Motor
# --------------------------------------------------------------------------- #
def calcular_fila_pendencias(
    con: duckdb.DuckDBPyConnection,
    universo: str,
    df_justificativas: pd.DataFrame | None,
    ano_fiscal: int,
    threshold_macro: float,
    threshold_obras: float,
    escopo_sustaining: tuple[str, list] = ("", []),
    escopo_obras: tuple[str, list] = ("", []),
    ate_mes: int | None = None,
) -> pd.DataFrame:
    """Fila de pendências de **um** universo. `df_justificativas`: frame de
    justificativas vigentes (schema `COLUNAS_JUSTIFICATIVA`); `None` = nenhuma.

    `escopo_sustaining` / `escopo_obras`: pares (fragmento_sql, params) de
    `filtros.clausula_escopo("...")` / `clausula_escopo_obras()`. Aplicados
    só ao universo correspondente.

    `ate_mes`: último mês fechado. `None` → derivado do dado (último mês com
    Realizado != 0 no ano). A página 7b passa o mês de referência da carga.

    Retorna 1 linha por pendência (`COLUNAS_PENDENCIA`), `motivo` ∈
    `realizado_sem_orcado` / `estouro_mes` / `estouro_acumulado`.
    """
    df_just = df_justificativas if df_justificativas is not None else justificativas_vazio()
    if not df_just.empty:
        df_just = df_just[df_just["universo"] == universo]

    if universo == "capex_obras":
        return _fila_obras(con, df_just, ano_fiscal, threshold_obras, escopo_obras, ate_mes)
    if universo in _CLASSIFICACAO_DO_UNIVERSO:
        return _fila_sustaining(
            con, universo, df_just, ano_fiscal, threshold_macro, escopo_sustaining, ate_mes
        )
    raise ValueError(f"universo desconhecido: {universo!r}")


def _fila_sustaining(
    con: duckdb.DuckDBPyConnection, universo: str, df_just: pd.DataFrame,
    ano_fiscal: int, threshold_macro: float, escopo: tuple[str, list],
    ate_mes: int | None,
) -> pd.DataFrame:
    limite = ate_mes if ate_mes is not None else _ultimo_mes_realizado(
        con, "fact_realizado", "valor_realizado", ano_fiscal
    )
    if limite <= 0:
        return pendencias_vazio()

    mensal = _delta_sustaining_mensal(con, universo, escopo, ano_fiscal)
    mensal = mensal[mensal["mes"] <= limite].copy()
    if mensal.empty:
        return pendencias_vazio()
    mensal["delta"] = mensal["realizado"] - mensal["orcado"]

    linhas: list[dict] = []

    # --- Micro mensal: uma competência de cada vez -------------------------- #
    cob_mes = _soma_coberta(
        df_just,
        {"nivel": "micro", "escopo_temporal": "mensal", "ano": ano_fiscal},
        ["gerencia_id", "conta_interna_id", "mes"],
    )
    est_mes = mensal.merge(cob_mes, on=["gerencia_id", "conta_interna_id", "mes"], how="left")
    est_mes["delta_coberto"] = est_mes["delta_coberto"].fillna(0.0)
    est_mes["tem_versao_anterior"] = est_mes["tem_versao_anterior"].fillna(False)
    est_mes["delta_pendente"] = est_mes["delta"] - est_mes["delta_coberto"]
    for _, r in est_mes[est_mes["delta_pendente"] > _EPS].iterrows():
        # "realizado sem orçamento" = gastou onde não havia verba (orçado ≈ 0
        # e realizado positivo). Realizado negativo com orçado 0 é estorno/
        # crédito, não gasto sem verba — cai no motivo genérico de estouro.
        realizado_sem_orcado = abs(r["orcado"]) < _EPS and r["realizado"] > _EPS
        linhas.append({
            "universo": universo, "nivel": "micro", "escopo_temporal": "mensal",
            "gerencia_id": r["gerencia_id"], "pacote_id": r["pacote_id"],
            "conta_interna_id": r["conta_interna_id"], "e_pep_projeto": "",
            "ano": ano_fiscal, "mes_competencia": int(r["mes"]),
            "orcado": r["orcado"], "realizado": r["realizado"], "delta": r["delta"],
            "delta_coberto": r["delta_coberto"], "delta_pendente": r["delta_pendente"],
            "tem_versao_anterior": bool(r["tem_versao_anterior"]),
            "motivo": "realizado_sem_orcado" if realizado_sem_orcado else "estouro_mes",
        })

    # --- Micro acumulada: avaliada só no último mês fechado ---------------- #
    acum = (
        mensal.groupby(["gerencia_id", "pacote_id", "conta_interna_id"], dropna=False)
        .agg(orcado=("orcado", "sum"), realizado=("realizado", "sum"))
        .reset_index()
    )
    acum["delta"] = acum["realizado"] - acum["orcado"]
    cob_acum = _soma_coberta(
        df_just,
        {"nivel": "micro", "escopo_temporal": "acumulado", "ano": ano_fiscal},
        ["gerencia_id", "conta_interna_id"],
    )
    acum = acum.merge(cob_acum, on=["gerencia_id", "conta_interna_id"], how="left")
    acum["delta_coberto"] = acum["delta_coberto"].fillna(0.0)
    acum["tem_versao_anterior"] = acum["tem_versao_anterior"].fillna(False)
    acum["delta_pendente"] = acum["delta"] - acum["delta_coberto"]
    for _, r in acum[(acum["delta"] > _EPS) & (acum["delta_pendente"] > _EPS)].iterrows():
        linhas.append({
            "universo": universo, "nivel": "micro", "escopo_temporal": "acumulado",
            "gerencia_id": r["gerencia_id"], "pacote_id": r["pacote_id"],
            "conta_interna_id": r["conta_interna_id"], "e_pep_projeto": "",
            "ano": ano_fiscal, "mes_competencia": limite,
            "orcado": r["orcado"], "realizado": r["realizado"], "delta": r["delta"],
            "delta_coberto": r["delta_coberto"], "delta_pendente": r["delta_pendente"],
            "tem_versao_anterior": bool(r["tem_versao_anterior"]),
            "motivo": "estouro_acumulado",
        })

    # --- Macro (Pacote) acumulada, com threshold -------------------------- #
    macro = (
        mensal.groupby("pacote_id", dropna=False)
        .agg(orcado=("orcado", "sum"), realizado=("realizado", "sum"))
        .reset_index()
    )
    macro["delta"] = macro["realizado"] - macro["orcado"]
    cob_macro = _soma_coberta(
        df_just,
        {"nivel": "macro", "escopo_temporal": "acumulado", "ano": ano_fiscal},
        ["pacote_id"],
    )
    macro = macro.merge(cob_macro, on=["pacote_id"], how="left")
    macro["delta_coberto"] = macro["delta_coberto"].fillna(0.0)
    macro["tem_versao_anterior"] = macro["tem_versao_anterior"].fillna(False)
    macro["delta_pendente"] = macro["delta"] - macro["delta_coberto"]
    acima = (
        (macro["delta"] > _EPS)
        & (macro["delta"] >= threshold_macro)
        & (macro["delta_pendente"] > _EPS)
    )
    for _, r in macro[acima].iterrows():
        linhas.append({
            "universo": universo, "nivel": "macro", "escopo_temporal": "acumulado",
            "gerencia_id": "", "pacote_id": r["pacote_id"],
            "conta_interna_id": "", "e_pep_projeto": "",
            "ano": ano_fiscal, "mes_competencia": limite,
            "orcado": r["orcado"], "realizado": r["realizado"], "delta": r["delta"],
            "delta_coberto": r["delta_coberto"], "delta_pendente": r["delta_pendente"],
            "tem_versao_anterior": bool(r["tem_versao_anterior"]),
            "motivo": "estouro_acumulado",
        })

    if not linhas:
        return pendencias_vazio()
    return pd.DataFrame(linhas)[COLUNAS_PENDENCIA]


def _fila_obras(
    con: duckdb.DuckDBPyConnection, df_just: pd.DataFrame, ano_fiscal: int,
    threshold_obras: float, escopo: tuple[str, list], ate_mes: int | None,
) -> pd.DataFrame:
    from src.dashboard.capex_dados import tabelas_disponiveis

    tem_orc, tem_real = tabelas_disponiveis(con)
    if not tem_real:
        return pendencias_vazio()

    limite = ate_mes if ate_mes is not None else _ultimo_mes_realizado(
        con, "fact_cji3_capex_obras", "valor_realizado", ano_fiscal
    )
    if limite <= 0:
        return pendencias_vazio()

    esc, esc_p = escopo
    orcado = con.execute(
        "SELECT e_pep_projeto, SUM(valor_orcado) AS orcado FROM fact_cji4_capex_obras "
        f"WHERE ano = ? AND mes <= ?{esc} GROUP BY e_pep_projeto",
        [ano_fiscal, limite, *esc_p],
    ).df() if tem_orc else pd.DataFrame(columns=["e_pep_projeto", "orcado"])
    realizado = con.execute(
        "SELECT e_pep_projeto, SUM(valor_realizado) AS realizado FROM fact_cji3_capex_obras "
        f"WHERE ano = ? AND mes <= ?{esc} GROUP BY e_pep_projeto",
        [ano_fiscal, limite, *esc_p],
    ).df()

    df = orcado.merge(realizado, on="e_pep_projeto", how="outer")
    df["orcado"] = df["orcado"].fillna(0.0)
    df["realizado"] = df["realizado"].fillna(0.0)
    df["e_pep_projeto"] = df["e_pep_projeto"].fillna("")
    df["delta"] = df["realizado"] - df["orcado"]

    cob = _soma_coberta(
        df_just,
        {"escopo_temporal": "acumulado", "ano": ano_fiscal},
        ["e_pep_projeto"],
    )
    df = df.merge(cob, on=["e_pep_projeto"], how="left")
    df["delta_coberto"] = df["delta_coberto"].fillna(0.0)
    df["tem_versao_anterior"] = df["tem_versao_anterior"].fillna(False)
    df["delta_pendente"] = df["delta"] - df["delta_coberto"]

    # Obras: threshold sobre |Delta| (docs/09 §4.2) — pendência dos 2 lados.
    alvo = (df["delta"].abs() >= threshold_obras) & (df["delta_pendente"].abs() > _EPS)
    linhas: list[dict] = []
    for _, r in df[alvo].iterrows():
        # "realizado sem orçamento" = gastou onde não havia verba (orçado ≈ 0
        # e realizado positivo). Realizado negativo com orçado 0 é estorno/
        # crédito, não gasto sem verba — cai no motivo genérico de estouro.
        realizado_sem_orcado = abs(r["orcado"]) < _EPS and r["realizado"] > _EPS
        linhas.append({
            "universo": "capex_obras", "nivel": "macro", "escopo_temporal": "acumulado",
            "gerencia_id": "", "pacote_id": "", "conta_interna_id": "",
            "e_pep_projeto": r["e_pep_projeto"],
            "ano": ano_fiscal, "mes_competencia": limite,
            "orcado": r["orcado"], "realizado": r["realizado"], "delta": r["delta"],
            "delta_coberto": r["delta_coberto"], "delta_pendente": r["delta_pendente"],
            "tem_versao_anterior": bool(r["tem_versao_anterior"]),
            "motivo": "realizado_sem_orcado" if realizado_sem_orcado else "estouro_acumulado",
        })

    if not linhas:
        return pendencias_vazio()
    return pd.DataFrame(linhas)[COLUNAS_PENDENCIA]
