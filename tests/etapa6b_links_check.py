"""Etapa 6b da Visão Ideal (docs/07 §3.4) — links contextuais entre
"Análise Financeira" e "Evidências SAP".

Como a árvore do Nível 4/5 é HTML estático, o link é a nível de painel:
- painel "Contas e Centros de Custo" -> `st.page_link` "Evidências SAP —
  lançamentos deste recorte" (os filtros globais da sidebar não mudam ao
  navegar, então o recorte é preservado sem injetar nada);
- página "Evidências SAP" -> `st.page_link` "Voltar à Análise Financeira".
Ambos guardados: sem acesso à página-alvo, o link não aparece.

Uso: python -m tests.etapa6b_links_check
"""
from __future__ import annotations

import os

from streamlit.testing.v1 import AppTest


def _run(fn):
    os.environ["ORCAMENTO_SKIP_LOGIN"] = "1"
    at = AppTest.from_function(fn, default_timeout=150)
    at.run()
    os.environ.pop("ORCAMENTO_SKIP_LOGIN", None)
    return at


def _script_af_contas():
    import app
    app._frag_af_contas_cc()


def _script_af_contas_sem_alvo():
    import app
    app._PG_EVIDENCIAS_SAP = None
    app._frag_af_contas_cc()


def _script_evidencias():
    import app
    app.pagina_sap()


def main() -> None:
    at = _run(_script_af_contas)
    if at.exception:
        raise SystemExit(f"frag_af_contas_cc: {list(at.exception)}")
    labels = [p.label for p in at.get("page_link")]
    if "Evidências SAP — lançamentos deste recorte" not in labels:
        raise SystemExit(f"link pra Evidências SAP não apareceu no painel Contas/CC ({labels})")
    print("Análise Financeira > Contas e CC -> link 'Evidências SAP' presente: OK")

    at2 = _run(_script_af_contas_sem_alvo)
    if at2.exception:
        raise SystemExit(f"frag_af_contas_cc (sem alvo): {list(at2.exception)}")
    if any("Evidências SAP" in (p.label or "") for p in at2.get("page_link")):
        raise SystemExit("link apareceu mesmo sem página-alvo disponível")
    print("sem acesso à Evidências SAP -> link some: OK")

    at3 = _run(_script_evidencias)
    if at3.exception:
        raise SystemExit(f"pagina_sap: {list(at3.exception)}")
    labels3 = [p.label for p in at3.get("page_link")]
    if "Voltar à Análise Financeira" not in labels3:
        raise SystemExit(f"link de volta não apareceu na Evidências SAP ({labels3})")
    print("Evidências SAP -> link 'Voltar à Análise Financeira' presente: OK")

    print("\nOK — links contextuais Análise Financeira ⇄ Evidências SAP.")


if __name__ == "__main__":
    main()
