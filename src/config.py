"""Leitura de config/settings.yaml — caminhos de arquivo e taxonomia de causas.

Nada aqui deve ficar hardcoded no código de ingestão/modelo: qualquer valor
que hoje já existe em config/settings.yaml (caminhos, ano fiscal, categorias
de causa) deve ser lido daqui.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_SETTINGS = RAIZ_PROJETO / "config" / "settings.yaml"


def carregar_config(caminho: Path = CAMINHO_SETTINGS) -> dict[str, Any]:
    with open(caminho, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    caminhos = cfg["caminhos"]
    for chave, valor in caminhos.items():
        caminhos[chave] = str(RAIZ_PROJETO / valor)

    # Override só para demo/teste: aponta o painel para um CSV de
    # explicações diferente do real (ex.: um fixture de exemplo) sem tocar
    # em data/staging/explicacoes.csv. Uso: PAINEL_EXPLICACOES_PATH=<path>.
    override_explicacoes = os.environ.get("PAINEL_EXPLICACOES_PATH")
    if override_explicacoes:
        caminhos["explicacoes"] = override_explicacoes

    return cfg
