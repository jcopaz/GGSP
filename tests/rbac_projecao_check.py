"""RBAC-A.2 — enforcement de escopo na Projeção OPEX (docs/08).

Confere que o filtro de escopo por Gerência aplicado em `dados_tendencia`
(via o fragmento que `render_projecao_opex` monta) bate exatamente com a
soma SQL direta do recorte, e que sem escopo o total é maior.

Precisa do warehouse real (`data/warehouse/painel.duckdb`).
Uso: python -m tests.rbac_projecao_check
"""
from __future__ import annotations

import duckdb

from src.config import carregar_config
from src.dashboard.tendencia import dados_tendencia

_ALVO = ["GGE_0025"]  # GER MALHA (SP)
_FRAG_TUDO = (" AND classificacao_contabil = 'OPEX'", [])
_FRAG_ESCOPO = (
    " AND classificacao_contabil = 'OPEX' AND gerencia_id IN (?)",
    list(_ALVO),
)


def _sql_direto(con, familia: str, gerencias: list[str] | None) -> float:
    cond = "ano = ? AND familia_pacote = ? AND classificacao_contabil = 'OPEX'"
    params: list = [2026, familia]
    if gerencias:
        cond += f" AND gerencia_id IN ({', '.join(['?'] * len(gerencias))})"
        params += gerencias
    (v,) = con.execute(
        f"SELECT COALESCE(SUM(valor_orcado), 0) FROM fact_orcamento WHERE {cond}", params
    ).fetchone()
    return float(v)


def main() -> None:
    cfg = carregar_config()
    ano = cfg["ano_fiscal_orcamento"]
    con = duckdb.connect(cfg["caminhos"]["warehouse_db"], read_only=True)
    try:
        falhas = 0
        for familia in ("PD", "PP", "PM"):
            df_escopo = dados_tendencia(
                con, ano, familia=familia,
                filtro_orcado=_FRAG_ESCOPO, filtro_realizado=_FRAG_ESCOPO,
            )
            df_tudo = dados_tendencia(
                con, ano, familia=familia,
                filtro_orcado=_FRAG_TUDO, filtro_realizado=_FRAG_TUDO,
            )
            orc_escopo = float(df_escopo["orcado"].sum())
            orc_tudo = float(df_tudo["orcado"].sum())
            direto_escopo = _sql_direto(con, familia, _ALVO)
            direto_tudo = _sql_direto(con, familia, None)

            ok_escopo = abs(orc_escopo - direto_escopo) < 0.01
            ok_tudo = abs(orc_tudo - direto_tudo) < 0.01
            ok_menor = orc_escopo <= orc_tudo + 0.01

            print(
                f"{familia}: escopo={orc_escopo:,.2f} (SQL {direto_escopo:,.2f}) "
                f"| tudo={orc_tudo:,.2f} (SQL {direto_tudo:,.2f}) "
                f"| {'OK' if (ok_escopo and ok_tudo and ok_menor) else 'FALHOU'}"
            )
            falhas += 0 if (ok_escopo and ok_tudo and ok_menor) else 1

        # GGE_0025 é a maior fatia de OPEX PM — o recorte tem que ser
        # estritamente menor que o total nessa família (prova que o filtro
        # não é no-op).
        df_pm_escopo = dados_tendencia(
            con, ano, familia="PM",
            filtro_orcado=_FRAG_ESCOPO, filtro_realizado=_FRAG_ESCOPO,
        )
        df_pm_tudo = dados_tendencia(
            con, ano, familia="PM",
            filtro_orcado=_FRAG_TUDO, filtro_realizado=_FRAG_TUDO,
        )
        if float(df_pm_escopo["orcado"].sum()) >= float(df_pm_tudo["orcado"].sum()):
            print("FALHOU: recorte PM não ficou menor que o total — filtro não aplicou.")
            falhas += 1
        else:
            print("OK — recorte PM estritamente menor que o total (filtro aplicou).")

        if falhas:
            raise SystemExit(f"{falhas} verificação(ões) falhou(ram).")
        print("\nOK — enforcement de escopo da Projeção bate com a soma SQL direta.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
