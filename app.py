"""Painel Streamlit — GG Infraestrutura (SP) / MRS.

Navegação pela barra lateral (st.navigation): Visão Resumida Executiva,
Painel Executivo (Nível 1 → 2 → 3), Visão Manutenção (SP), Nível 4
(Contas), Nível 5 (Centro de Custo), Nível 6 (rastreabilidade SAP) e
Dados e Qualidade (era "Upload de Dados"). Nível 4-6 entraram no escopo a
pedido do usuário em 2026-08-06 (ver CLAUDE.md) — não fazem mais parte do
"fora do MVP" original.

**Reestruturado em 2026-08-11/12** (a pedido do usuário): a navegação
virou seções no Side Bar, renomeadas em 2026-08-12 pros nomes que o
próprio PMO usa — **"Plano de Manutenção"** (OPEX + CAPEX Manutenção
Malha juntos, sourced em Base Zero/Consulta de Contas/SAP — as 2 juntas
são o universo "Manutenção Corrente" do diagrama que o usuário trouxe em
2026-08-11) e **"Plano de Obras"** (CAPEX de Projetos e Obras, sourced só
em CJI4 Orçado + CJI3 Realizado, trazido em 2026-08-11, ver
capex_dados.py). `st.navigation` aceita um dict `{titulo_secao:
[st.Page, ...]}` pra criar esses cabeçalhos de seção — não precisa de N
chamadas `st.navigation` separadas.

**Etapa 2 da Visão Ideal (2026-09-02, ver docs/07):** as antigas seções
**"Dados"** (Upload de Dados, devolvida à navegação em 2026-08-17) e
**"Administração"** viraram um único grupo **"GESTÃO"**, com as páginas
**"Dados e Qualidade"** (era "Upload de Dados") e **"Administração"** (era
"Gestão e Auditoria"). É só rótulo/agrupamento — as chaves de permissão
(`upload`, `administracao`) e toda a lógica de página continuam iguais.

**"DINFRA" evitado em rótulos de UI desde 2026-08-12** (a pedido do
usuário: pode ser lido como a Diretoria inteira, que tem mais Gerências
Gerais além desta — ver docs/02-perguntas-em-aberto.md, item 5) — usar
"GG Infraestrutura (SP)" ou o nome oficial completo "GER. GERAL DE
INFRAESTRUTURA (SP)" em vez disso, em qualquer texto que apareça na tela.

"Plano de Obras" não tem página equivalente a Nível 5 (Centro de Custo):
o CJI4 (Orçado) não tem esse campo — só o CJI3 (Realizado) tem
`centro_custo_parceiro` —, então não dá pra fechar Orçado x Real nesse
nível sem inventar dado do lado que falta. Também não tem equivalente à
Visão Manutenção (SP): não existe o conceito de "família de pacote" nos
dados de CAPEX Obras.

Trocado de Plotly Dash para Streamlit em 2026-08-06 (ver CLAUDE.md, decisão
técnica) — a pedido do usuário, Dash foi considerado pouco amigável.

Modo simulação (barra lateral): gera causas/justificativas sintéticas
(src/engine/simulador.py) pra deixar waterfall/ranking/resumo executivo
totalmente operantes antes do processo real de preenchimento existir — ver
docs/02-perguntas-em-aberto.md, item 3. Nunca escreve no CSV real.

Uso: streamlit run src/dashboard/app.py
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# Garante que a raiz do repositório esteja no sys.path antes de qualquer
# "from src.xxx import yyy" abaixo. Necessário porque nem todo executor
# adiciona a raiz do projeto ao path sozinho ao rodar este arquivo como
# "main module" — funcionava local via `python -m streamlit run ...`
# (o -m adiciona o cwd), mas o Streamlit Community Cloud executa o main
# module de um jeito que não adiciona a raiz, só o diretório do próprio
# arquivo — sem isso, todo import "src.*" falha com
# "ModuleNotFoundError: No module named 'src'" (visto em produção
# 2026-08-27, ver docs/05-publicacao-online-e-seguranca.md).
#
# CORRIGIDO em 2026-09-01: `app.py` mudou de `src/dashboard/app.py` (3
# níveis abaixo da raiz, `git mv`) para a raiz do repositório. O cálculo de
# 3 `.parent` valia para o local antigo; hoje soma 2 níveis a mais que o
# necessário (aponta pra 2 pastas ACIMA da raiz real). Confirmado ao vivo:
# `AppTest.from_file("app.py")` quebrava com o mesmo `ModuleNotFoundError:
# No module named 'src'` que este bloco deveria estar prevenindo. Com
# `app.py` na raiz, 1 único `.parent` (do arquivo pro diretório que o
# contém) já é a raiz do projeto — mesma conta que `src/config.py::
# RAIZ_PROJETO` já faz a partir de 1 nível a menos.
_RAIZ_PROJETO = Path(__file__).resolve().parent
if str(_RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROJETO))

import duckdb
import pandas as pd
import streamlit as st

from src.auth.permissions import can_acessar_pagina, escopo_universo, is_admin, universos_permitidos
from src.dashboard.administracao import render_administracao
from src.auth.session import (
    clear_session,
    get_id,
    get_nome,
    get_papel,
    get_usuario,
    init_session,
    is_logged_in,
)
from src.auth.login import render_login, render_trocar_senha_obrigatoria
from src.config import carregar_config
from src.ingestion.arquivo_bruto import (
    info_arquivo_bruto,
    listar_tipos_salvos,
    restaurar_arquivo_bruto,
    salvar_arquivo_bruto,
    salvar_versao_arquivo,
)
from src.auth.audit import registrar_atividade, registrar_visualizacao_pagina
from src.dashboard.filtros import (
    guardar_e_faixa_universo,
    renderizar_badge_filtros_ativos,
    renderizar_filtros_sidebar,
)
from src.dashboard.layout import bloco_resumo_visual
from src.dashboard.nivel1_diretoria import gg_padrao, render_nivel1
from src.dashboard.mapa_calor_gerencia_pacote import render_mapa_calor_gerencia_pacote
from src.dashboard.nivel2_gg import render_gerencia_gg, render_nivel2, render_tendencia_gg
from src.dashboard.nivel3_pacotes import render_nivel3
from src.dashboard.nivel4_contas import render_nivel4_contas
from src.dashboard.nivel5_centro_custo import render_nivel5_centro_custo
from src.dashboard.nivel6_sap import render_nivel6_sap
from src.dashboard.resumo_executivo import render_resumo_executivo
from src.dashboard.visao_classificacao import UNIVERSO_POR_CLASSIFICACAO, render_visao_classificacao
from src.dashboard.visao_manutencao import render_visao_manutencao
from src.dashboard.projecao_opex import render_projecao_opex
from src.dashboard.capex_resumo import render_resumo_executivo_capex
from src.dashboard.capex_painel import render_painel_executivo_capex
from src.dashboard.capex_contas import render_nivel4_contas_capex
from src.dashboard.capex_rastreabilidade import render_nivel6_sap_capex
from src.dashboard.pce_especialista import render_pce_especialista
from src.engine.explanation_engine import COLUNAS_EXPLICACAO, validar_categorias
from src.engine.simulador import gerar_explicacoes_simuladas
from src.model.build_star_schema import build_star_schema
from src.branding import inject_shell_css, render_page_banner
from src.versao import APP_VERSION

st.set_page_config(page_title="Fin360 — GG Infraestrutura (SP)", layout="wide")

# Gate de sessão (Camada 2) — nenhuma página roda sem login. Precisa vir
# logo após set_page_config (única chamada Streamlit permitida antes) e
# antes de qualquer outro st.* — fail closed.
#
# ORCAMENTO_SKIP_LOGIN: bypass só para rodar localmente enquanto a rede da
# MRS bloquear a conexão direta até o Neon (porta 5432) — mesmo bloqueio já
# visto no SMTP da Brevo, ver docs/05-publicacao-online-e-seguranca.md.
# Padrão é sempre exigir login (fail closed); só pula se a variável de
# ambiente estiver setada explicitamente. No Streamlit Cloud essa variável
# não existe, então o login continua obrigatório lá — não desative isso
# em produção nem esqueça ligado sem perceber.
init_session()
if not is_logged_in() and os.environ.get("ORCAMENTO_SKIP_LOGIN") != "1":
    render_login()
    st.stop()
elif os.environ.get("ORCAMENTO_SKIP_LOGIN") == "1":
    st.warning("⚠️ Login desativado (ORCAMENTO_SKIP_LOGIN=1) — só para uso local. Nunca deixe isso ligado no deploy.")

# Troca de senha obrigatória (pedido do usuário 2026-08-28): usuário
# criado pela Administração entra com uma senha temporária única e fica
# preso aqui — nenhuma página do painel roda — até definir senha própria.
_usuario_sessao = get_usuario()
if (
    _usuario_sessao
    and _usuario_sessao.get("precisa_trocar_senha")
    and os.environ.get("ORCAMENTO_SKIP_LOGIN") != "1"
):
    render_trocar_senha_obrigatoria()
    st.stop()

# Casca visual (fundo/sidebar/tipografia) — só depois do gate, nunca
# aparece na tela de login (que tem seu próprio CSS em auth/login.py).
inject_shell_css()

CFG = carregar_config()

# Um tipo de arquivo = uma zona de upload própria, cada uma com seu próprio
# destino e sua própria validação — não existe uma zona genérica que aceite
# "qualquer arquivo" e tente adivinhar o tipo.
TIPOS_ARQUIVO = {
    # Rotina periódica — decisão do usuário em 2026-08-18: formato
    # padronizado, mesma estrutura de "Base Analítico - GG.xlsx" (SAP) e
    # dos exports CJI3/CJI4, upload esperado a cada rodada.
    "realizado": {
        "titulo": "Base Analítico SAP (Realizado)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"]["realizado"],
        "grupo": "Rotina periódica",
    },
    "cji4_capex_obras": {
        "titulo": "CJI4 (CAPEX Obras — Orçado)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"].get("cji4_capex_obras", ""),
        "grupo": "Rotina periódica",
    },
    "cji3_capex_obras": {
        "titulo": "CJI3 (CAPEX Obras — Realizado)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"].get("cji3_capex_obras", ""),
        "grupo": "Rotina periódica",
    },
    # Consulta de Contas: só o lado Realizado (VersãoComparativo2) tinha
    # sido considerado "fora de uso" em 2026-08-18 — confirmado depois,
    # no mesmo dia, que o VersãoComparativo1 (OPEX Orçado) continua vindo
    # dela, e é a ÚNICA fonte disso (Base Zero é comprovadamente
    # incompleta pro OPEX desde 2026-08-10) — por isso ela volta pra
    # rotina. `fact_realizado` continua usando VersãoComparativo2 pro
    # Realizado (usuário confirmou explicitamente que NÃO quer reverter
    # pro Base Analítico SAP direto nisso — ver docs/04-licoes-aprendidas.md).
    "consulta_contas": {
        "titulo": "Consulta de Contas (OPEX Orçado — Comparativo 1)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"].get("consulta_contas", ""),
        "grupo": "Rotina periódica",
    },
    # Consolidado.xlsx (trazida em 2026-08-19 à tarde — substitui "PCE Base
    # Luiz.xlsx" como fonte de rotina) — alimenta a Label do Especialista
    # (CAPEX Obras) e demais análises CAPEX. Só a aba "consolidado", já no
    # formato padrão confirmado pelo usuário. `fact_pce_realizado` (Nível
    # Realizado da Label do Especialista) não entra nesta zona — desde
    # 2026-08-27 é derivada em código a partir do CJI3 + Catálogo CAPEX
    # Obras (ver `build_star_schema._derivar_pce_realizado`), não depende
    # mais de nenhum arquivo separado — decisão do usuário de reduzir pro
    # mínimo de planilhas manuais.
    "pce_consolidado": {
        "titulo": "Consolidado (CAPEX Obras — Label do Especialista)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"].get("pce_consolidado", ""),
        "grupo": "Rotina periódica",
    },
    # Sob demanda — só sobe quando o Orçamento Aprovado for revisado ou a
    # relação de contas mudar, não é upload de toda rodada.
    "base_zero": {
        "titulo": "Base Zero (Orçamento Aprovado)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"]["base_zero"],
        "grupo": "Sob demanda",
    },
    "catalogo_contas": {
        "titulo": "Catálogo de Contas (De/Para Orçamento x Realizado)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"].get("catalogo_contas", ""),
        "grupo": "Sob demanda",
    },
    "catalogo_capex_obras": {
        "titulo": "Catálogo de Contas CAPEX (cadastro de projetos)",
        "extensoes": (".xlsx",),
        "caminho": CFG["caminhos"].get("catalogo_capex_obras", ""),
        "grupo": "Sob demanda",
    },
    "explicacoes": {
        "titulo": "Explicações de Causa (CSV de apoio)",
        "extensoes": (".csv",),
        "caminho": CFG["caminhos"]["explicacoes"],
        "grupo": "Sob demanda",
    },
    # "Transferência Combustível Terceiros" (Plano de Manutenção do PCM)
    # não entra na rotina (usuário: "não entrará como rotina de upload")
    # — é ajuste pontual; quando existir, continua sendo colocado direto
    # em data/raw/ (mesmo caminho configurado em settings.yaml), sem tela
    # própria. build_star_schema.py continua lendo se o arquivo existir.
}


def _conectar(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(CFG["caminhos"]["warehouse_db"], read_only=read_only)


def _garantir_base_pronta() -> None:
    """Roda 1x por sessão de script: se o warehouse não existir (disco
    efêmero do Streamlit Cloud apagado num reboot), tenta restaurar os
    arquivos brutos a partir do backup no Neon e reconstrói a base sozinho
    — sem precisar de reenvio manual quando não há arquivo novo de verdade.
    Falha silenciosa por completo: se o Neon estiver fora do ar ou não
    houver backup nenhum, simplesmente não faz nada — as telas continuam
    mostrando o aviso normal de "base não processada", e o usuário sempre
    pode subir manualmente."""
    if st.session_state.get("_base_restaurada_tentativa"):
        return
    st.session_state["_base_restaurada_tentativa"] = True

    if os.path.exists(CFG["caminhos"]["warehouse_db"]):
        return

    try:
        tipos_salvos = listar_tipos_salvos()
        restaurou_algo = False
        for tipo, info in TIPOS_ARQUIVO.items():
            if tipo in tipos_salvos and info["caminho"]:
                if restaurar_arquivo_bruto(tipo, info["caminho"]):
                    restaurou_algo = True
        if restaurou_algo:
            build_star_schema()
    except Exception:
        pass


def _base_pronta(con: duckdb.DuckDBPyConnection) -> bool:
    (n_tabelas,) = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fact_orcamento'"
    ).fetchone()
    return n_tabelas > 0


def _aviso_base_nao_processada() -> None:
    st.warning(
        "Base ainda não processada. Use a aba 'Gestão → Dados e Qualidade' "
        "pra subir os arquivos e clicar em 'Reprocessar base', ou rode "
        "`python -m src.model.build_star_schema` no terminal."
    )


def _validar_explicacoes_csv(dados: bytes) -> str | None:
    """Retorna mensagem de erro, ou None se o CSV está OK para salvar."""
    try:
        df = pd.read_csv(io.BytesIO(dados))
    except Exception as exc:
        return f"Não consegui ler o CSV: {exc}"

    faltando = set(COLUNAS_EXPLICACAO) - set(df.columns)
    if faltando:
        return f"Colunas faltando: {sorted(faltando)}. Esperado: {COLUNAS_EXPLICACAO}."

    if df.empty:
        return None

    try:
        validar_categorias(df, CFG["categorias_causa"])
    except ValueError as exc:
        return str(exc)

    return None


def _zona_upload(tipo: str, info: dict) -> None:
    st.subheader(info["titulo"])
    st.caption(f"Formato aceito: {', '.join(info['extensoes'])}")

    # Mostra a última versão salva no Neon (backup, sobrevive a reboot) —
    # ajuda a responder "preciso subir de novo ou já está guardado?" sem
    # precisar adivinhar. Falha silenciosa: se o Neon estiver indisponível
    # aqui, só não mostra a legenda, não trava a tela de upload.
    try:
        salvo = info_arquivo_bruto(tipo)
    except Exception:
        salvo = None
    if salvo:
        st.caption(
            f"💾 Última versão salva: '{salvo['nome_original']}' "
            f"({salvo['enviado_em']:%d/%m/%Y %H:%M})"
        )

    arquivo = st.file_uploader(
        "Arquivo", type=[e.lstrip(".") for e in info["extensoes"]],
        key=f"upload-{tipo}", label_visibility="collapsed",
    )
    if arquivo is None:
        return

    marcador_key = f"processado-{tipo}"
    marcador_atual = (arquivo.name, arquivo.size)
    if st.session_state.get(marcador_key) == marcador_atual:
        st.success(f"'{arquivo.name}' salvo em {info['caminho']}.")
        return

    dados = arquivo.getvalue()
    if tipo == "explicacoes":
        erro = _validar_explicacoes_csv(dados)
        if erro:
            st.error(erro)
            return

    os.makedirs(os.path.dirname(info["caminho"]), exist_ok=True)
    with open(info["caminho"], "wb") as f:
        f.write(dados)
    st.session_state[marcador_key] = marcador_atual

    # Backup no Neon — sobrevive a reboot do Streamlit Cloud. Best-effort:
    # se o Neon falhar aqui, o upload local já foi salvo e continua
    # funcionando normalmente pra esta sessão, só não fica restaurável
    # depois de um reboot.
    try:
        salvar_arquivo_bruto(tipo, arquivo.name, dados, get_id())
        # Histórico versionado (Administração > reverter upload) — cada
        # envio soma uma linha nova aqui, nunca sobrescreve (diferente do
        # salvar_arquivo_bruto acima, que só guarda a última). Mesmo
        # best-effort: se isso falhar, o upload em si já está salvo.
        salvar_versao_arquivo(tipo, arquivo.name, dados, get_id())
        registrar_atividade("upload", tipo, {"nome_arquivo": arquivo.name, "tamanho_bytes": len(dados)})
    except Exception as exc:
        st.warning(
            f"Arquivo salvo localmente, mas não consegui guardar backup no "
            f"banco (vai precisar reenviar se o app reiniciar): {exc}"
        )

    st.success(
        f"'{arquivo.name}' salvo em {info['caminho']}. "
        f"Clique em 'Reprocessar base' para atualizar o painel."
    )


def pagina_upload() -> None:
    render_page_banner("📤", "Dados e Qualidade", "Upload dos arquivos rotineiros, reprocessamento e conferência de carga.")
    with st.expander("Como funciona o upload"):
        st.caption(
            "**Rotina periódica**: formato padronizado (Base Analítico SAP "
            "no formato de \"Base Analítico - GG.xlsx\", CJI3, CJI4, "
            "Consulta de Contas — essa última é a única fonte de OPEX "
            "Orçado/Comparativo 1, o Realizado dela continua sendo a fonte "
            "de fact_realizado também) — sobe a cada nova rodada de dado. "
            "**Sob demanda**: só quando o Orçamento Aprovado for revisado "
            "ou a relação de contas mudar; sem eles, a tabela "
            "correspondente só continua com o que já estava em data/raw/, "
            "não trava o reprocessamento. A planilha de transferência do "
            "PCM (Combustível Terceiros) saiu da rotina de upload — se "
            "precisar ser atualizada, colocar direto em data/raw/ "
            "manualmente. Depois de subir, clique em 'Reprocessar base' "
            "pra reconstruir o modelo: as correções de Gerência (Malha "
            "SP/VP, Combustível Terceiros, CGG050/GG direto — ver "
            "`docs/04-licoes-aprendidas.md`) rodam automaticamente em cima "
            "do que estiver em data/raw/ nesse momento, não precisa "
            "reaplicar nada na mão."
        )

    grupos: dict[str, list[tuple[str, dict]]] = {}
    for tipo, info in TIPOS_ARQUIVO.items():
        grupos.setdefault(info["grupo"], []).append((tipo, info))

    for grupo, itens in grupos.items():
        st.subheader(grupo)
        colunas = st.columns(len(itens))
        for coluna, (tipo, info) in zip(colunas, itens):
            with coluna:
                _zona_upload(tipo, info)
        st.divider()

    if st.button("Reprocessar base", type="primary"):
        with st.spinner("Reprocessando..."):
            try:
                caminho_db = build_star_schema()
            except Exception as exc:
                st.error(f"Erro ao reprocessar: {exc}")
                return
            if not os.path.exists(caminho_db):
                # build_star_schema() devolve o caminho mesmo sem criar o
                # arquivo quando faltam os 2 arquivos obrigatórios em
                # data/raw/ (base_zero/realizado) — comum logo após um
                # deploy novo, onde data/raw/ nasce vazio. Sem essa checagem,
                # a conexão abaixo (read_only=True) quebra com
                # duckdb.IOException num arquivo que não existe (bug real,
                # visto em produção 2026-08-27, ver docs/04-licoes-aprendidas.md).
                st.warning(
                    "Ainda faltam arquivos obrigatórios em 'data/raw/' — "
                    "suba pelo menos a **Base Zero (Orçamento Aprovado)** e "
                    "o **Base Analítico SAP (Realizado)** acima antes de "
                    "reprocessar."
                )
                return
            con = _conectar()
            try:
                linhas = []
                for nome in (
                    "fact_orcamento", "fact_realizado",
                    "fact_cji4_capex_obras", "fact_cji3_capex_obras",
                    "fact_consulta_contas",
                ):
                    existe = con.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [nome]
                    ).fetchone()[0]
                    if not existe:
                        continue
                    (n,) = con.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()
                    linhas.append(f"{nome}: {n:,} linhas".replace(",", "."))
                (sem_gerencia_orc,) = con.execute(
                    "SELECT COUNT(*) FROM fact_orcamento WHERE gerencia_id IS NULL"
                ).fetchone()
                (sem_gerencia_real,) = con.execute(
                    "SELECT COUNT(*) FROM fact_realizado WHERE gerencia_id IS NULL"
                ).fetchone()
            finally:
                con.close()
        st.success("Base reprocessada com sucesso.")
        for linha in linhas:
            st.write(f"- {linha}")
        if sem_gerencia_orc or sem_gerencia_real:
            st.warning(
                f"Atenção: sobrou linha sem Gerência depois do reprocessamento "
                f"(Orçado: {sem_gerencia_orc}, Realizado: {sem_gerencia_real}). "
                f"Pode ser dado novo que as correções conhecidas não cobrem "
                f"ainda — vale investigar antes de considerar a base fechada."
            )
        else:
            st.info("Sem linha sem Gerência no Orçado nem no Realizado — atribuição 100% fechada.")


def pagina_resumo_executivo() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_resumo_executivo(
            con,
            st.session_state["caminho_explicacoes_ativo"],
            CFG["categorias_causa"],
            simulado=st.session_state["modo_simulado"],
            ano_fiscal=CFG["ano_fiscal_orcamento"],
        )
    finally:
        con.close()


def pagina_painel() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return

    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        # RBAC de escopo (docs/08, Fase RBAC-A.2, Opção B): quem não tem a
        # GG inteira em opex_sustaining não vê o waterfall de causa (Macro
        # por Pacote, cruza Gerências) — só o resumo/tendência/Gerência do
        # recorte dele.
        guardar_e_faixa_universo(con, "opex_sustaining")
        _tem_gg_inteira = escopo_universo("opex_sustaining")[1]

        if st.session_state["modo_simulado"] and _tem_gg_inteira:
            st.warning(
                "🎲 Modo simulação ativo — o waterfall e o ranking abaixo "
                "usam causas/justificativas sintéticas. Orçamento e "
                "Realizado continuam reais."
            )

        st.session_state.setdefault("gg_selecionado", gg_padrao(con))
        st.session_state.setdefault("categoria_selecionada", None)
        caminho_explicacoes = st.session_state["caminho_explicacoes_ativo"]

        def _sem_waterfall_recorte() -> None:
            st.info(
                "🔒 A decomposição de causa (waterfall por categoria) é Macro "
                "por Pacote e cruza Gerências — fica disponível só no acesso à "
                "GG inteira (Analista que apura a GG). Seu recorte mostra "
                "Orçado/Realizado/Delta, a Tendência e a Visão por Gerência."
            )

        # Nível 1 (resumo) e Nível 2 (waterfall) lado a lado, com uma linha
        # vertical separando os dois — pedido do usuário em 2026-08-10
        # ("colocaria o gráfico do lado desse resumo"), no lugar do
        # empilhado vertical (Nível 1 em cima, divider, Nível 2 embaixo).
        # Layout compartilhado desde 6.4.0 (ver src/dashboard/layout.py).
        bloco_resumo_visual(
            lambda: render_nivel1(con),
            (lambda: render_nivel2(
                con, st.session_state["gg_selecionado"], caminho_explicacoes,
                CFG["categorias_causa"], ano_fiscal=CFG["ano_fiscal_orcamento"],
            )) if _tem_gg_inteira else _sem_waterfall_recorte,
            key="painel",
        )

        st.divider()
        render_tendencia_gg(con, st.session_state["gg_selecionado"], ano_fiscal=CFG["ano_fiscal_orcamento"])

        render_gerencia_gg(con, st.session_state["gg_selecionado"])
        render_mapa_calor_gerencia_pacote(con, st.session_state["gg_selecionado"])

        if _tem_gg_inteira and st.session_state.get("categoria_selecionada"):
            st.divider()
            render_nivel3(
                con,
                st.session_state["gg_selecionado"],
                st.session_state["categoria_selecionada"],
                caminho_explicacoes,
                CFG["categorias_causa"],
            )
    finally:
        con.close()


def pagina_opex_capex_manutencao() -> None:
    """Unifica as antigas telas "Visão OPEX" e "CAPEX Manutenção — Malha"
    (2026-08-29, a pedido do usuário, depois de eu confirmar em código
    que as duas eram literalmente a mesma função —
    `render_visao_classificacao` — só trocando o parâmetro
    `classificacao`). Um `st.segmented_control` decide qual dos dois lados
    renderizar, no lugar de 2 itens de menu quase idênticos.

    Nota de RBAC: as chaves de permissão antigas ("visao_opex",
    "capex_manutencao") viraram uma só ("opex_capex_manutencao"). O
    controle fino por lado voltou pelo RBAC de escopo por universo
    (docs/08, Fase RBAC-A.2): OPEX = universo `opex_sustaining`, CAPEX =
    `capex_sustaining`. O toggle abaixo só mostra o(s) lado(s) que o
    usuário tem grant — quem só vê OPEX não consegue nem clicar em CAPEX.
    Ver CHANGELOG."""
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        permitidos = universos_permitidos()
        opcoes = [c for c in ("OPEX", "CAPEX") if UNIVERSO_POR_CLASSIFICACAO[c] in permitidos]
        if not opcoes:
            st.error(
                "🚫 Você não tem acesso ao OPEX nem ao CAPEX de Manutenção. "
                "Fale com o administrador para liberar."
            )
            return
        escolha = st.segmented_control(
            "Classificação Contábil", opcoes,
            default=opcoes[0], key="w_toggle_opex_capex_manutencao",
        )
        render_visao_classificacao(con, escolha or opcoes[0])
    finally:
        con.close()


def pagina_projecao_opex() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        render_projecao_opex(con, ano_fiscal=CFG["ano_fiscal_orcamento"])
    finally:
        con.close()


def pagina_manutencao() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_visao_manutencao(con, ano_fiscal=CFG["ano_fiscal_orcamento"])
    finally:
        con.close()


def pagina_contas() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_nivel4_contas(con, ano_fiscal=CFG["ano_fiscal_orcamento"])
    finally:
        con.close()


def pagina_centro_custo() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_nivel5_centro_custo(con, ano_fiscal=CFG["ano_fiscal_orcamento"])
    finally:
        con.close()


def pagina_sap() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        (n_tabelas,) = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fact_realizado_documento'"
        ).fetchone()
        if n_tabelas == 0:
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_nivel6_sap(con)
    finally:
        con.close()


def pagina_capex_resumo() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_resumo_executivo_capex(con)
    finally:
        con.close()


def pagina_capex_painel() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_painel_executivo_capex(con, ano_fiscal=CFG["ano_fiscal_orcamento"])
    finally:
        con.close()


def pagina_capex_contas() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_nivel4_contas_capex(con)
    finally:
        con.close()


def pagina_capex_rastreabilidade() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        renderizar_badge_filtros_ativos()
        render_nivel6_sap_capex(con)
    finally:
        con.close()


def pagina_pce_especialista() -> None:
    """Não chama `renderizar_badge_filtros_ativos()` de propósito — os
    filtros globais da sidebar (Pacote/Gerência/Período etc.) não têm
    equivalente em `fact_pce_consolidado` (universo à parte, sem
    `pacote_id`/`gerencia_id` compartilhado), mostrar o badge sugeriria
    que eles afetam esta página quando não afetam nada aqui."""
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        _aviso_base_nao_processada()
        return
    con = _conectar()
    try:
        if not _base_pronta(con):
            _aviso_base_nao_processada()
            return
        render_pce_especialista(con)
    finally:
        con.close()


def pagina_administracao() -> None:
    # Administração fala com o Neon (usuários/permissões/auditoria/
    # uploads) SEM depender do warehouse local — mas os dropdowns de
    # Gerência/Pacote/Centro de Custo/Coordenação (pedido do usuário
    # 2026-08-28: "campo selecionável", não texto livre) precisam de
    # dado real do warehouse. Passa a conexão só se a base já existir e
    # estiver pronta; render_administracao() aceita None e cai pra texto
    # livre nesses campos — nunca bloqueia o resto da página por causa
    # disso.
    caminho_db = CFG["caminhos"]["warehouse_db"]
    con = None
    if os.path.exists(caminho_db):
        con = _conectar()
        if not _base_pronta(con):
            con.close()
            con = None
    try:
        render_administracao(con)
    finally:
        if con is not None:
            con.close()


def _renderizar_usuario_logado() -> None:
    """Bloco de marca + conta. `st.logo()` (2026-08-28) é o mecanismo
    oficial do Streamlit pra fixar uma marca acima do menu de
    `st.navigation()` — a tentativa anterior via CSS (`with st.sidebar:
    render_logo_video()`) não funcionava porque o menu de navegação fica
    numa posição própria, independente da ordem de chamada no script.

    `st.logo()` só aceita imagem, não vídeo — mas aceita **GIF animado**,
    que mantém o loop (pedido do usuário: "logo tem que ter movimento
    igual ao do login"). `fin360_logo.gif` é gerado a partir do
    `fin360.mp4` — **regenerado em 2026-08-29** (75 frames, 280x280,
    paleta de 64 cores, ~2,6 MB; era 38 frames/~1,4 MB) depois do usuário
    reportar "loop diferente da tela de login": a amostragem antiga (a
    cada ~11,8 dos 450 frames do vídeo) pulava fases inteiras da animação
    (marca oculta → cor → cinza → dourado), parecendo outra animação. O
    crop 1:1 + zoom 1,7x (mesmo tratamento do `<video>` da tela de login,
    `render_logo_video()`) agora é aplicado 1x só, na geração do GIF —
    não mais também via CSS (`inject_shell_css`), que causava zoom
    duplicado (círculo preto sólido, sem a marca — ver histórico ali).
    `icon_image` (PNG estático) é o que aparece só no estado colapsado da
    sidebar, onde animação não faz diferença — já vinha bem enquadrado,
    não precisou regenerar.

    **Conflito registrado** (pedido posterior pediu usar `fin360.mp4`
    direto, sem converter pra GIF): mantive o GIF de propósito — é a
    única forma encontrada de ter a marca animada E corretamente
    posicionada acima do menu (`st.logo()` é o mecanismo que resolve o
    posicionamento, e ele não aceita vídeo). Usar o vídeo direto via
    `with st.sidebar:` volta a ter o problema de posição já resolvido.
    Se essa ressalva não for aceitável, precisa de decisão explícita —
    não revertida sozinha aqui.

    Precisa ficar fora de `with st.sidebar:` (não é sensível a container
    ambiente). Versão/assinatura ficam no rodapé
    (`_renderizar_rodape_sidebar`, chamado depois de `pg.run()`), não
    repetidas aqui.
    """
    caminho_logo = str(_RAIZ_PROJETO / "src" / "dashboard" / "static" / "fin360_logo.gif")
    caminho_icone = str(_RAIZ_PROJETO / "src" / "dashboard" / "static" / "fin360_logo.png")
    st.logo(caminho_logo, icon_image=caminho_icone, size="large")

    with st.sidebar:
        st.caption(f"👤 {get_nome()} · {get_papel()}")
        if st.button("Sair", use_container_width=True):
            clear_session()
            st.rerun()
        st.divider()


def _renderizar_rodape_sidebar() -> None:
    """Rodapé fixo no fim da sidebar (versão + assinatura) — chamado
    depois de `pg.run()` de propósito, pra ficar sempre abaixo de toda a
    navegação, não só do bloco de marca do topo."""
    with st.sidebar:
        st.markdown(
            f"""
            <div style="text-align:center;margin-top:1rem;padding-top:0.8rem;
                border-top:1px solid rgba(22,40,63,0.12);color:#5b6b85;font-size:0.72rem;">
                v{APP_VERSION}<br>Desenvolvido por Julio Paz
            </div>
            """,
            unsafe_allow_html=True,
        )


def _preparar_modo_simulacao() -> None:
    """Roda 1x por execução do script, antes de qualquer página: decide
    qual explicacoes.csv está "ativo" (real ou simulado) e, se simulado,
    (re)gera o CSV sintético só quando a semente mudou — não a cada rerun."""
    st.session_state.setdefault("modo_simulado", False)
    st.session_state.setdefault("simulacao_seed", 42)

    with st.sidebar:
        st.divider()
        st.session_state["modo_simulado"] = st.checkbox(
            "🎲 Simular causas/justificativas",
            value=st.session_state["modo_simulado"],
            help=(
                "Gera valores sintéticos de causa (distribuindo o Delta "
                "real de cada pacote pela taxonomia) pra deixar "
                "waterfall/ranking/resumo executivo populados pra "
                "demonstração. Nunca sobrescreve o CSV de apoio real."
            ),
        )
        if st.session_state["modo_simulado"] and st.button("🔄 Sortear de novo"):
            st.session_state["simulacao_seed"] += 1

    if not st.session_state["modo_simulado"]:
        st.session_state["caminho_explicacoes_ativo"] = CFG["caminhos"]["explicacoes"]
        return

    caminho_db = CFG["caminhos"]["warehouse_db"]
    caminho_simulado = CFG["caminhos"]["explicacoes_simuladas"]
    seed = st.session_state["simulacao_seed"]

    if os.path.exists(caminho_db) and st.session_state.get("simulacao_seed_gerada") != seed:
        con = _conectar()
        try:
            if _base_pronta(con):
                df_sim = gerar_explicacoes_simuladas(con, CFG["categorias_causa"], CFG["ano_fiscal_orcamento"], seed=seed)
                os.makedirs(os.path.dirname(caminho_simulado), exist_ok=True)
                df_sim.to_csv(caminho_simulado, index=False)
                st.session_state["simulacao_seed_gerada"] = seed
        finally:
            con.close()

    st.session_state["caminho_explicacoes_ativo"] = caminho_simulado


def _preparar_filtros_globais() -> None:
    caminho_db = CFG["caminhos"]["warehouse_db"]
    if not os.path.exists(caminho_db):
        return
    con = _conectar()
    try:
        if _base_pronta(con):
            renderizar_filtros_sidebar(con)
    finally:
        con.close()


# Título de app removido em 2026-08-28 (pedido do usuário: "reduza o
# texto, deixe só o essencial") — cada página já tem seu próprio
# st.header curto, e a marca Fin360 já está fixa na sidebar; repetir um
# título longo no topo de toda página era redundante.
_renderizar_usuario_logado()
_garantir_base_pronta()
_preparar_modo_simulacao()
_preparar_filtros_globais()

# RBAC por página (app.permissao_pagina) — adicionado em 2026-08-28.
# `_pagina_se_permitida` faz as 2 coisas ao mesmo tempo: (1) esconde a
# página do menu se `can_acessar_pagina` negar (devolve None,
# `_somente_paginas` filtra) — e (2) embrulha a função da página com uma
# revalidação da MESMA checagem antes de renderizar (defende contra
# acesso direto, não confia só em esconder do menu — pedido explícito do
# usuário: "não confiar apenas na ocultação da sidebar"). `chave` usa os
# mesmos identificadores de PAGINAS em administracao.py — mudar um sem o
# outro quebra o Editor de Permissões (fica mostrando/salvando uma chave
# que a navegação não reconhece).
def _com_guard_pagina(chave: str, funcao):
    def _pagina_guardada() -> None:
        if not can_acessar_pagina(chave):
            st.error("🚫 Você não tem permissão para acessar esta página.")
            st.stop()
        registrar_visualizacao_pagina(chave)
        funcao()

    _pagina_guardada.__name__ = getattr(funcao, "__name__", chave)
    return _pagina_guardada


def _pagina_se_permitida(chave: str, funcao, titulo: str, icon: str, default: bool = False):
    if not can_acessar_pagina(chave):
        return None
    return st.Page(_com_guard_pagina(chave, funcao), title=titulo, icon=icon, default=default)


def _somente_paginas(itens: list) -> list:
    return [item for item in itens if item is not None]


# Navegação em seções (dict, não lista — ver docstring do módulo).
# Renomeado em 2026-08-12 (a pedido do usuário) pra "Plano de Manutenção"
# / "Plano de Obras" — nomes que o próprio PMO usa (painel de referência
# trazido pelo usuário se chama exatamente "Plano de Manutenção"). As 2
# seções continuam batendo com o diagrama de 2026-08-11: "Manutenção
# Corrente" (OPEX + CAPEX Malha/Infra) e "Projetos" (CAPEX de Obras,
# metodologia FEL) — só juntei OPEX e CAPEX Manutenção numa seção só
# (antes eram 2 separadas), porque as duas juntas SÃO o "Plano de
# Manutenção" da referência, não 2 coisas diferentes.
#
# Etapa 2 da Visão Ideal (2026-09-02, ver docs/07): as antigas seções
# "Dados" e "Administração" viraram um único grupo "GESTÃO" — "Dados e
# Qualidade" (era "Upload de Dados") + "Administração" (era "Gestão e
# Auditoria"). Só rótulo/agrupamento; chaves de permissão (`upload`,
# `administracao`) e lógica de página inalteradas.

# Grupo GESTÃO montado antes do dict: "Dados e Qualidade" depende da
# permissão de página `upload` (via _pagina_se_permitida); "Administração"
# é sempre exclusiva de admin (checagem direta de papel, NÃO passa pelo
# can_acessar_pagina/permissao_pagina genérico — essa tela não pode ser
# liberada por engano via override de página). O grupo só entra no menu se
# sobrar ao menos 1 página visível pro usuário.
_paginas_gestao = _somente_paginas([
    _pagina_se_permitida("upload", pagina_upload, "Dados e Qualidade", "📤"),
])
if is_admin():
    _paginas_gestao.append(
        st.Page(
            _com_guard_pagina("administracao", pagina_administracao),
            title="Administração", icon="🛡️",
        )
    )

_secoes = {
    "Plano de Manutenção": _somente_paginas([
        _pagina_se_permitida("resumo_executivo", pagina_resumo_executivo, "Visão Resumo Executivo — GGSP", "🧭", default=True),
        _pagina_se_permitida("painel_executivo", pagina_painel, "Painel Executivo", "📊"),
        # Unificado em 2026-08-29 (a pedido do usuário) — "Visão OPEX" e
        # "CAPEX Manutenção — Malha" eram a mesma função
        # (render_visao_classificacao), só trocando o parâmetro; viram 1
        # item de menu com toggle interno (ver pagina_opex_capex_manutencao).
        # Base Zero (área "Malha Capex", R$43MM) — só a fatia Malha por
        # enquanto. Infra (Drenagem/Saneamento Vegetal/pequenas obras)
        # ainda não tem arquivo carregado.
        _pagina_se_permitida("opex_capex_manutencao", pagina_opex_capex_manutencao, "OPEX / CAPEX — Manutenção Malha", "🛠️"),
        _pagina_se_permitida("visao_manutencao", pagina_manutencao, "Visão Manutenção (SP)", "🛠️"),
        _pagina_se_permitida("projecao_opex", pagina_projecao_opex, "Projeção OPEX", "📈"),
        _pagina_se_permitida("contas", pagina_contas, "Nível 4 — Contas", "🧾"),
        _pagina_se_permitida("centro_custo", pagina_centro_custo, "Nível 5 — Centro de Custo", "🏗️"),
        _pagina_se_permitida("rastreabilidade_sap", pagina_sap, "Nível 6 — Rastreabilidade SAP", "🔎"),
    ]),
    "Plano de Obras": _somente_paginas([
        _pagina_se_permitida("capex_resumo", pagina_capex_resumo, "Resumo Executivo", "🧭"),
        _pagina_se_permitida("capex_painel", pagina_capex_painel, "Painel Executivo", "📊"),
        _pagina_se_permitida("capex_contas", pagina_capex_contas, "Nível 4 — Contas", "🧾"),
        _pagina_se_permitida("capex_rastreabilidade", pagina_capex_rastreabilidade, "Nível 6 — Rastreabilidade SAP", "🔎"),
        # Label do Especialista (PCE Base Luiz.xlsx, trazida em 2026-08-19)
        # — universo à parte de CJI4/CJI3, filtros próprios (Classificação
        # Atualizada/Gerência/Grupo/Versão), ver pce_especialista.py.
        _pagina_se_permitida("pce_especialista", pagina_pce_especialista, "CAPEX Obras — Especialista", "📐"),
    ]),
}
# "Upload de Dados" (hoje "Dados e Qualidade") tinha saído da navegação em
# 2026-08-11 e voltou em 2026-08-17 (reprocessar direto do painel quando
# CJI3/CJI4/Consulta de Contas forem atualizados, sem depender do terminal)
# — cobre arquivo dos dois universos. Desde a Etapa 2 da Visão Ideal
# (2026-09-02) fica no grupo GESTÃO, ao lado de "Administração".
if _paginas_gestao:
    _secoes["GESTÃO"] = _paginas_gestao

pg = st.navigation(_secoes)
pg.run()
_renderizar_rodape_sidebar()
