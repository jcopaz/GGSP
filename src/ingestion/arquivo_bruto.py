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


# ---------------------------------------------------------------------------
# Histórico VERSIONADO (app.arquivo_bruto_versao) — adicionado em 2026-08-28
# pra tela de Administração (reversão manual de upload). Complementa as
# funções acima, não substitui: `arquivo_bruto` continua sendo a "última
# versão" usada pelo auto-restore de reboot; `arquivo_bruto_versao` guarda
# TODAS as versões, cada upload soma uma linha nova (nunca sobrescreve).
# ---------------------------------------------------------------------------

def salvar_versao_arquivo(
    tipo: str, nome_original: str, conteudo: bytes, usuario_id: str | None
) -> None:
    """Chamar sempre junto de `salvar_arquivo_bruto` (mesmo upload, as duas
    tabelas) — nunca sozinha, senão o histórico e a "última versão" saem
    de sincronia."""
    executar(
        """
        insert into app.arquivo_bruto_versao (tipo, nome_original, conteudo, tamanho_bytes, enviado_por, enviado_em)
        values (%s, %s, %s, %s, %s, now())
        """,
        (tipo, nome_original, conteudo, len(conteudo), usuario_id),
    )


def listar_versoes_arquivo(tipo: str | None = None, limite: int = 200) -> list[dict]:
    """Metadados de versões salvas (sem o conteúdo) — mais recente primeiro.
    `tipo=None` lista de todos os tipos (tela de Administração)."""
    if tipo:
        return buscar_todos(
            "select id, tipo, nome_original, tamanho_bytes, enviado_por, enviado_em, ativo "
            "from app.arquivo_bruto_versao where tipo = %s order by enviado_em desc limit %s",
            (tipo, limite),
        )
    return buscar_todos(
        "select v.id, v.tipo, v.nome_original, v.tamanho_bytes, v.enviado_em, v.ativo, "
        "u.nome_completo from app.arquivo_bruto_versao v "
        "left join app.usuario u on u.id = v.enviado_por "
        "order by v.enviado_em desc limit %s",
        (limite,),
    )


def restaurar_versao_arquivo(versao_id: str, caminho_destino: str) -> bool:
    """Reversão manual (tela de Administração): busca o conteúdo da versão
    pelo `id`, **sobrescreve** `caminho_destino` incondicionalmente (ao
    contrário de `restaurar_arquivo_bruto`, que só preenche se estiver
    faltando) — é uma reversão deliberada, não um auto-restore. Também
    atualiza `app.arquivo_bruto` (última versão) com o mesmo conteúdo, pra
    não ficar dessincronizada do que voltou pro disco (senão o próximo
    reboot restauraria a versão errada). Devolve False se o `id` não
    existir; quem chama decide a mensagem de erro."""
    linha = buscar_um(
        "select tipo, nome_original, conteudo, enviado_por from app.arquivo_bruto_versao where id = %s",
        (versao_id,),
    )
    if not linha:
        return False
    os.makedirs(os.path.dirname(caminho_destino), exist_ok=True)
    conteudo = bytes(linha["conteudo"])
    with open(caminho_destino, "wb") as f:
        f.write(conteudo)
    salvar_arquivo_bruto(linha["tipo"], linha["nome_original"], conteudo, linha["enviado_por"])
    return True
