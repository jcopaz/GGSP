"""Backup/restauração dos arquivos brutos de upload (data/raw/) no Neon.

Existe porque o disco do Streamlit Community Cloud não é garantido entre
reboots (ver docs/05-publicacao-online-e-seguranca.md) — sem isso, todo
reboot exigiria reenviar manualmente cada arquivo, mesmo sem nada novo pra
subir. Aqui só guarda o ÚLTIMO arquivo de cada tipo (sobrescreve a cada
novo upload) — não é histórico/versionamento, é só uma cópia de segurança
pra recompor data/raw/ sozinho.

Reaproveita a conexão genérica de src.auth.db (não é módulo de auth, só
mora lá porque foi onde a conexão Postgres apareceu primeiro no projeto).
"""
from __future__ import annotations

import os

from src.auth.db import buscar_todos, buscar_um, executar


def salvar_arquivo_bruto(
    tipo: str, nome_original: str, conteudo: bytes, usuario_id: str | None
) -> None:
    executar(
        """
        insert into app.arquivo_bruto (tipo, nome_original, conteudo, tamanho_bytes, enviado_por, enviado_em)
        values (%s, %s, %s, %s, %s, now())
        on conflict (tipo) do update set
            nome_original = excluded.nome_original,
            conteudo = excluded.conteudo,
            tamanho_bytes = excluded.tamanho_bytes,
            enviado_por = excluded.enviado_por,
            enviado_em = excluded.enviado_em
        """,
        (tipo, nome_original, conteudo, len(conteudo), usuario_id),
    )


def restaurar_arquivo_bruto(tipo: str, caminho_destino: str) -> bool:
    """Se `caminho_destino` já existir, não faz nada (devolve True). Senão,
    tenta restaurar do Postgres. Devolve True se o arquivo existe ao final
    (já existia ou foi restaurado agora), False se não há backup salvo."""
    if os.path.exists(caminho_destino):
        return True
    linha = buscar_um("select conteudo from app.arquivo_bruto where tipo = %s", (tipo,))
    if not linha:
        return False
    os.makedirs(os.path.dirname(caminho_destino), exist_ok=True)
    with open(caminho_destino, "wb") as f:
        f.write(bytes(linha["conteudo"]))
    return True


def info_arquivo_bruto(tipo: str) -> dict | None:
    """Metadados do backup salvo (sem o conteúdo) — pra mostrar 'última
    versão salva' na tela de upload."""
    return buscar_um(
        "select nome_original, tamanho_bytes, enviado_em from app.arquivo_bruto where tipo = %s",
        (tipo,),
    )


def listar_tipos_salvos() -> set[str]:
    """Todos os `tipo` com backup salvo — usado por _garantir_base_pronta()
    pra restaurar em lote sem 1 SELECT por tipo."""
    return {linha["tipo"] for linha in buscar_todos("select tipo from app.arquivo_bruto")}
