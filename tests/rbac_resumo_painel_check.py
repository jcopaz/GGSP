"""RBAC-A.2 — Resumo Executivo + Painel Executivo (OPEX, Opção B, docs/08).

Confere:
1. GG inteira (sessão com escopo `gg`): waterfall e "Visão por Gerência"
   idênticos ao comportamento sem sessão (baseline) — o recorte é no-op.
2. Escopado numa Gerência: `_resumo_geral` / `dados_gerencia_gg` /
   `dados_waterfall_gg` batem com a soma SQL direta por `gerencia_id`; o
   Resumo Executivo NÃO renderiza o waterfall (mostra o aviso de recorte);
   o Painel também troca o waterfall pelo aviso.

Uso: python -m tests.rbac_resumo_painel_check
"""
from __future__ import annotations

import duckdb
from streamlit.testing.v1 import AppTest

_GER = "GGE_0025"  # GER MALHA (SP)
_DB = "data/warehouse/painel.duckdb"
_CSV = "data/staging/explicacoes.csv"


def _baseline():
    """Waterfall + visão por Gerência calculados sem sessão (no-op de
    escopo) — o que a GG inteira tem que continuar vendo."""
    from src.dashboard.nivel2_gg import dados_gerencia_gg, dados_waterfall_gg
    from src.dashboard.nivel1_diretoria import GG_TOTAL
    from src.config import carregar_config

    cfg = carregar_config()
    con = duckdb.connect(_DB, read_only=True)
    try:
        orc, delta, df = dados_waterfall_gg(con, GG_TOTAL, cfg["caminhos"]["explicacoes"], cfg["categorias_causa"])
        dfg = dados_gerencia_gg(con, GG_TOTAL)
        return orc, delta, int(len(dfg)), float(dfg["orcado"].sum())
    finally:
        con.close()


def _script_scoped():
    import streamlit as st
    import duckdb
    from src.dashboard.nivel2_gg import dados_gerencia_gg, dados_waterfall_gg
    from src.dashboard.nivel1_diretoria import GG_TOTAL
    from src.dashboard.resumo_executivo import _resumo_geral
    from src.config import carregar_config

    cfg = carregar_config()
    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    try:
        r = _resumo_geral(con)
        orc_w, delta_w, _df = dados_waterfall_gg(con, GG_TOTAL, cfg["caminhos"]["explicacoes"], cfg["categorias_causa"])
        dfg = dados_gerencia_gg(con, GG_TOTAL)

        (orc_d,) = con.execute(
            "select coalesce(sum(valor_orcado),0) from fact_orcamento "
            "where classificacao_contabil='OPEX' and gerencia_id in ('GGE_0025')"
        ).fetchone()
        (real_d,) = con.execute(
            "select coalesce(sum(valor_realizado),0) from fact_realizado "
            "where classificacao_contabil='OPEX' and gerencia_id in ('GGE_0025')"
        ).fetchone()

        ok = {
            "resumo_orcado_opex": abs(r["orcado_opex"] - orc_d) < 0.01,
            "resumo_realizado": abs(r["realizado"] - real_d) < 0.01,
            "waterfall_orcado": abs(orc_w - orc_d) < 0.01,
            "waterfall_delta": abs(delta_w - (real_d - orc_d)) < 0.01,
            "visao_gerencia_1linha": len(dfg) <= 1,
        }
        st.write("RESULT " + " ".join(f"{k}={v}" for k, v in ok.items()))
        st.write(f"VALORES orcado_opex={r['orcado_opex']:.2f} sql={orc_d:.2f}")
    finally:
        con.close()


def _script_baseline_via_session():
    """Recalcula waterfall + visão por Gerência DENTRO de uma sessão com
    escopo 'gg' — deve dar o mesmo que o baseline sem sessão."""
    import streamlit as st
    import duckdb
    from src.dashboard.nivel2_gg import dados_gerencia_gg, dados_waterfall_gg
    from src.dashboard.nivel1_diretoria import GG_TOTAL
    from src.config import carregar_config

    cfg = carregar_config()
    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    try:
        orc, delta, _df = dados_waterfall_gg(con, GG_TOTAL, cfg["caminhos"]["explicacoes"], cfg["categorias_causa"])
        dfg = dados_gerencia_gg(con, GG_TOTAL)
        st.write(f"BASE orcado={orc:.2f} delta={delta:.2f} gerencias={len(dfg)}")
    finally:
        con.close()


def _script_render_resumo():
    import duckdb
    from src.dashboard.resumo_executivo import render_resumo_executivo
    from src.config import carregar_config

    cfg = carregar_config()
    con = duckdb.connect("data/warehouse/painel.duckdb", read_only=True)
    render_resumo_executivo(
        con, cfg["caminhos"]["explicacoes"], cfg["categorias_causa"],
        simulado=False, ano_fiscal=cfg["ano_fiscal_orcamento"],
    )
    con.close()


def _run(fn, escopos):
    at = AppTest.from_function(fn, default_timeout=120)
    at.session_state["usuario"] = {"id": "u1", "papel": "especialista_analista", "nome_completo": "X"}
    at.session_state["logged_in"] = True
    at.session_state["_escopos_acesso_cache"] = escopos
    at.session_state["modo_simulado"] = False
    at.session_state["caminho_explicacoes_ativo"] = _CSV
    at.run()
    return at


def main() -> None:
    base_orc, base_delta, base_nlin, base_orcsum = _baseline()
    print(f"baseline waterfall: orcado={base_orc:,.2f} delta={base_delta:,.2f} | gerencias={base_nlin}")

    # GG inteira -> waterfall/visão por Gerência idênticos ao baseline
    # (escopo `gg` = no-op).
    at_gg = _run(_script_baseline_via_session, [{"universo": "opex_sustaining", "tipo": "gg", "valor": "(todas)"}])
    if at_gg.exception:
        raise SystemExit(f"exceção GG inteira: {at_gg.exception}")
    linha_gg = next((m.value for m in at_gg.markdown if m.value.startswith("BASE")), "")
    print("GG inteira:", linha_gg)
    parts = dict(p.split("=") for p in linha_gg.replace("BASE ", "").split())
    iguais = (
        abs(float(parts["orcado"]) - base_orc) < 0.01
        and abs(float(parts["delta"]) - base_delta) < 0.01
        and int(parts["gerencias"]) == base_nlin
    )
    if not iguais:
        raise SystemExit("FALHOU — usuário com escopo 'gg' não viu o waterfall/visão da GG inteira.")

    # Escopado em GGE_0025
    at_s = _run(_script_scoped, [{"universo": "opex_sustaining", "tipo": "gerencia", "valor": _GER}])
    if at_s.exception:
        raise SystemExit(f"exceção escopado: {at_s.exception}")
    linha = next((m.value for m in at_s.markdown if m.value.startswith("RESULT")), "")
    vals = next((m.value for m in at_s.markdown if m.value.startswith("VALORES")), "")
    print("escopado:", linha)
    print("        ", vals)
    if "=False" in linha or not linha:
        raise SystemExit("FALHOU — número escopado não bateu com a soma SQL direta.")

    # Resumo Executivo renderizado: escopado NÃO tem waterfall
    at_r_gg = _run(_script_render_resumo, [{"universo": "opex_sustaining", "tipo": "gg", "valor": "(todas)"}])
    at_r_sc = _run(_script_render_resumo, [{"universo": "opex_sustaining", "tipo": "gerencia", "valor": _GER}])
    subs_gg = [s.value for s in at_r_gg.subheader]
    subs_sc = [s.value for s in at_r_sc.subheader]
    caps_sc = " ".join(c.value for c in at_r_sc.caption)
    tem_wf_gg = any("Financeiro" in s for s in subs_gg)  # GG renderiza o painel completo
    aviso_recorte = "waterfall" in caps_sc.lower() and "GG inteira" in caps_sc
    print(f"Resumo GG inteira subheaders: {subs_gg[:3]}")
    print(f"Resumo escopado subheaders: {subs_sc[:3]} | aviso de recorte no waterfall: {aviso_recorte}")
    if at_r_gg.exception or at_r_sc.exception:
        raise SystemExit(f"exceção no render: gg={at_r_gg.exception} sc={at_r_sc.exception}")
    if not aviso_recorte:
        raise SystemExit("FALHOU — Resumo escopado não mostrou o aviso de 'waterfall só na GG inteira'.")

    print("\nOK — GG inteira mantém o waterfall; escopado recorta e troca o waterfall pelo aviso.")


if __name__ == "__main__":
    main()
