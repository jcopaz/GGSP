"""Keep-awake do Fin360 com navegador de verdade (Playwright/Chromium).

Por que não curl (achado 2026-10-04): o Streamlit Community Cloud só conta
como "visita" uma sessão real — navegador executando o JS e abrindo o
WebSocket do app. O curl baixava só a casca HTML (~10 KB), que responde
HTTP 200 inclusive com o app DORMINDO (a tela "This app has gone to sleep"
também é desenhada via JS dentro dessa casca). Resultado: 230+ execuções
verdes no Actions e o app dormindo mesmo assim.

Aqui: abre a página, se aparecer o botão de acordar clica nele, e segura a
sessão aberta alguns segundos. Sai com código 1 se o app continuar
dormindo — o workflow fica vermelho em vez de mentir.
"""
from __future__ import annotations

import re
import sys

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

URL = "https://fin360.streamlit.app/"
BOTAO_ACORDAR = re.compile(r"get this app back up", re.I)


def main() -> int:
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(user_agent="Fin360-keep-awake/2.0")
        pagina.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        pagina.wait_for_timeout(10_000)

        botao = pagina.get_by_role("button", name=BOTAO_ACORDAR)
        if botao.count() and botao.first.is_visible():
            print("App estava DORMINDO — clicando em 'Yes, get this app back up!'")
            botao.first.click()
            try:
                botao.first.wait_for(state="hidden", timeout=180_000)
            except PWTimeout:
                print("::error::App não acordou em 3 min após o clique.")
                navegador.close()
                return 1
            # Pós-boot: deixa o app subir e abrir a sessão de verdade.
            pagina.wait_for_timeout(60_000)
        else:
            print("App acordado — mantendo a sessão aberta por 30 s.")
            pagina.wait_for_timeout(30_000)

        if botao.count() and botao.first.is_visible():
            print("::error::App continua dormindo após a visita.")
            navegador.close()
            return 1
        print("OK — sessão real aberta no app.")
        navegador.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
