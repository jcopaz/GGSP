"""Fase 2 — Modelo dimensional: materializa fact_orcamento e fact_realizado
em DuckDB, na grão descrita em docs/00-especificacao-consolidada.md, seção 6
(Pacote, Conta, Centro de Custo, Mês).

Não cria dim_classificacao: Classificação contábil (CAPEX/OPEX) é atributo
de cada linha de fact_orcamento, direto da fonte — nunca inferido do
Pacote, porque o mesmo Pacote pode ter linhas CAPEX e OPEX ao mesmo tempo
(achado da Fase 1, confirmado nos dados reais: PM03 tem ambas).

dim_causa e fact_explicacao ficam para a Fase 3 (motor de causa) — não são
construídos aqui.

**Decisão de 2026-08-10 (a pedido do usuário)**: `fact_orcamento` passa a
ser uma combinação de 2 fontes, cada uma cobrindo só o que faz bem:

- **CAPEX**: continua vindo só da Base Zero (`load_base_zero`) — é a única
  fonte que temos pra CAPEX; a Consulta de Contas não cobre CAPEX (nenhuma
  conta com PEP aparece nela, só contas no formato "código-descrição" que
  já identificamos como OPEX).
- **OPEX**: passa a vir da Consulta de Contas (`load_consulta_contas`), não
  mais da Base Zero. Motivo: a Base Zero comprovadamente está incompleta
  pro OPEX — reconciliação em 2026-08-10 achou uma conta inteira do PM03
  ausente (`PM03009-`, R$ 18,37 MM) e outra parcial (`PM03011-`, faltando
  R$ 2,99 MM). A Consulta de Contas também traz OPEX pra pacotes que a
  Base Zero carregada não tem nenhuma linha (PD01-09, PM01, PM02, PP02,
  PASSIVO), e já vem com `gg_id` real por linha (a Base Zero não tem
  coluna de GG — ver `_atribuir_gg_orcamento` — então o CAPEX continua sem
  atribuição por GG individual até esse gap ser resolvido, mas o OPEX
  agora tem).

`fact_consulta_contas` continua existindo como tabela separada (Conta a
Conta, útil pra auditoria/drill-down) — ver `_reshape_consulta_contas_opex`
pra como ela vira `fact_orcamento`.

**Decisão de 2026-08-11 (a pedido do usuário)**: `fact_realizado` também
passa a ter `classificacao_contabil`, e o OPEX aí vem da Consulta de
Contas (`VersãoComparativo2`), não mais do SAP (Base Analítico) direto:

- **OPEX Orçado**: só Consulta de Contas (`VersãoComparativo1`) — sem
  fallback pra Base Zero (removido; já sabíamos que estava incompleta).
- **OPEX Realizado**: `VersãoComparativo2` (mesma planilha) — confirmado
  reconciliando quase exato (diferença de ~R$10 mil em R$23,9 MM) contra
  o total que o SAP já trazia. Na prática, o Realizado que o painel
  mostrava até aqui já era quase 100% OPEX.
- **CAPEX Realizado**: sem fonte carregada ainda — o usuário vai trazer
  de outro arquivo ("Base Crua"). Fica sem nenhuma linha em
  `fact_realizado` até lá — não é derivado por subtração (Total SAP −
  OPEX) nem inventado.
- O SAP (`load_realizado`) deixa de alimentar `fact_realizado` direto,
  mas continua intacto em `fact_realizado_documento` (Nível 6) — o
  cascateamento/detalhe documento-a-documento, Centro de Custo e
  Gerência do mesmo Realizado de OPEX, não uma fonte concorrente.

**CAPEX de Projetos e Obras (CJI4 Orçado + CJI3 Realizado)**, trazido em
2026-08-11 — fica em tabelas separadas `fact_cji4_capex_obras`/
`fact_cji3_capex_obras`, **não somado a `fact_orcamento`/
`fact_realizado`**:
- O escopo de Gerência desses dados (Mobilidade Urbana, Obras
  Ferroviárias, Expansão, Baixada Santista, Corredor São Paulo) foi
  **confirmado em 2026-08-12** como sendo GGG_0054/DINFRA (usuário, após
  cruzamento com o de/para oficial da planilha-mãe do PMO — ver
  docs/02-perguntas-em-aberto.md, item 21). A separação de
  `fact_orcamento`/`fact_realizado` continua de propósito, mas agora por
  outro motivo: são universos financeiros diferentes (diagrama trazido
  pelo usuário em 2026-08-11 — "Projetos"/Obras via metodologia FEL x
  "Manutenção Corrente"/OPEX+CAPEX Malha), não por dúvida de escopo. Vira
  seção própria "CAPEX Projetos (Obras)" no sidebar (`app.py`).
- `Classe de custo` (código numérico) já casa com 27 dos 29 valores do
  Catálogo de Contas existente (`load_catalogo_contas`) — reaproveitado
  aqui pra dar nome via `conta_interna_id`/`conta_interna_nome`, mesmo
  De/Para que já une Base Zero e SAP.
- `Catalago CAPEX Obras.xlsx` (`load_catalogo_capex_obras`) dá o nome do
  empreendimento/Gerência por projeto (`e_pep_projeto`, chave que bate
  100% com `Definição do projeto` do financeiro) — join opcional, sem
  ele os projetos ficam só com o código, sem nome.

Uso: python -m src.model.build_star_schema
"""
from __future__ import annotations

import os
import re

import duckdb
import pandas as pd

from src.config import carregar_config
from src.ingestion.loaders import (
    _reclassificar_grupo,
    carregar_catalogo_objeto_classificacao,
    load_base_zero,
    load_catalogo_capex_obras,
    load_catalogo_contas,
    load_cji3_capex_obras_realizado,
    load_cji4_capex_obras,
    load_consulta_contas,
    load_pce_consolidado,
    load_realizado,
    load_realizado_documentos,
    load_transferencia_combustivel_terceiros,
)


def _construir_dim_tempo(df_orc: pd.DataFrame, df_real: pd.DataFrame) -> pd.DataFrame:
    anos_meses = pd.concat([
        df_orc[["ano", "mes"]],
        df_real[["ano", "mes"]],
    ]).drop_duplicates().sort_values(["ano", "mes"])
    anos_meses["trimestre"] = ((anos_meses["mes"] - 1) // 3) + 1
    return anos_meses.reset_index(drop=True)


def _construir_dim_pacote(df_orc: pd.DataFrame, df_real: pd.DataFrame) -> pd.DataFrame:
    lado_orc = df_orc[["pacote_id", "familia_pacote"]].drop_duplicates()
    lado_orc["nome_pacote"] = pd.NA

    lado_real = df_real[["pacote_id", "familia_pacote", "pacote_nome"]].drop_duplicates()
    lado_real = lado_real.rename(columns={"pacote_nome": "nome_pacote"})

    dim = pd.concat([lado_orc, lado_real], ignore_index=True)
    # Quando o mesmo pacote aparece nas duas fontes, prioriza o nome vindo
    # do Realizado (Base Zero não traz nome de pacote, só descrição de item).
    dim = (
        dim.sort_values("nome_pacote", na_position="last")
        .drop_duplicates(subset=["pacote_id"], keep="first")
        .sort_values("pacote_id")
        .reset_index(drop=True)
    )
    return dim


def _construir_dim_gg(df_real: pd.DataFrame) -> pd.DataFrame:
    # GAP: só existe GG (gg_id/gg_nome) vindo da hierarquia do Realizado
    # (colunas HIERARQUIA-NÓS - GER GERAL). A Base Zero não tem coluna de
    # GG — só "Gerência" com valores SP/VP, sem confirmação se isso é o
    # mesmo nível hierárquico de GG (SP/RJ/FA/LC) da spec. fact_orcamento
    # não referencia dim_gg por isso. Ver docs/02-perguntas-em-aberto.md,
    # item 5 (escopo de dados / GGs ainda não confirmado).
    dim = df_real[["gg_id", "gg_nome"]].drop_duplicates().dropna(subset=["gg_id"])
    return dim.sort_values("gg_id").reset_index(drop=True)


# CGG050 não é "sem Gerência" — confirmado pelo usuário em 2026-08-17: é a
# conta própria (Orçado e Realizado) da Gerência Geral em si (Marcelo
# Modolo), separada das Gerências de campo (Malha SP, Malha VP, etc.).
# Cobre despesas administrativas/SG&A lançadas direto no nível da GG
# (viagens, material de escritório, uniformes...), discriminadas por
# pacote — não precisa (e não deve) ser redistribuída pras Gerências de
# campo, é o destino final mesmo. Vira uma linha própria na visão por
# Gerência em vez de cair em "Não atribuído" — regra geral, vale pra
# qualquer linha nova que chegue com esse Centro de Custo no futuro (ver
# `_aplicar_correcao_cgg050_direto_gg`), não só pro resíduo de 2026-08-17.
_GERENCIA_ID_GG_DIRETO = "CGG050"
_GERENCIA_NOME_GG_DIRETO = "GER. GERAL DE INFRAESTRUTURA (SP) - DIRETO GG (Marcelo Modolo)"


def _construir_dim_gerencia(df_real: pd.DataFrame) -> pd.DataFrame:
    # Mesmo GAP do dim_gg acima: só populamos com o que vem da hierarquia
    # do Realizado. O valor "Gerência" (SP/VP) da Base Zero fica como
    # atributo bruto em fact_orcamento.gerencia_raw, sem join para cá.
    dim = df_real[["gerencia_id", "gerencia_nome"]].drop_duplicates().dropna(subset=["gerencia_id"])
    dim = pd.concat([
        dim,
        pd.DataFrame([{"gerencia_id": _GERENCIA_ID_GG_DIRETO, "gerencia_nome": _GERENCIA_NOME_GG_DIRETO}]),
    ], ignore_index=True)
    return dim.drop_duplicates(subset=["gerencia_id"]).sort_values("gerencia_id").reset_index(drop=True)


def _derivar_coordenacao(df_real: pd.DataFrame) -> pd.Series:
    """Extrai Coordenação do nome do Centro de Custo (só Realizado).

    # GAP: não existe uma coluna "Coordenação" separada no export —
    # `Centro de custo` vem com nomes como "COORD.  MALHA - PARANAPIACABA".
    # Quando o nome começa com "COORD.", a Coordenação é o resto do texto
    # (normalizado); quando não começa (ex.: "GER. MALHA (SP)" — esse é
    # Centro de Custo de nível Gerência, não Coordenação), fica vazio, não
    # inventado. Base Zero (Orçamento) não tem nome de Centro de Custo, só
    # código — não dá pra derivar Coordenação desse lado.
    """
    nomes = df_real["centro_custo_nome"].fillna("")
    extraido = nomes.str.extract(r"^COORD\.?\s*(.+)$", flags=re.IGNORECASE)[0]
    return extraido.str.strip().str.replace(r"\s+", " ", regex=True)


# Confirmado pelo usuário em 2026-08-17: toda a fatia "SP" da Base Zero
# (Malha Capex) é da Gerência do Jefferson Luders, e toda a fatia "VP" é da
# Gerência do Vinicius Nascimento — mapeados pra Gerência formal já
# cadastrada em dim_gerencia (mesma tabela que o Realizado alimenta) porque
# nenhuma das duas tem nome de pessoa lá, só o código/nome oficial. Cobre
# 100% do gerencia_raw "SP"/"VP" que a Base Zero traz — não é um recorte
# por disciplina/PEP, é o nível SP-VP inteiro (usuário confirmou que a
# informação de região do PEP já é suficiente, não precisa granularidade
# menor). Ver docs/84_LICOES... equivalente / decisão registrada na
# conversa com o usuário — a pedido dele, ver catalogo_pep_financial_
# control_center.xlsx (data/raw) pro de/para original que motivou a
# pergunta, embora a regra final aplicada aqui seja mais ampla (região
# inteira, não só os PEPs MC/24004 e MC/24005 daquele catálogo).
_GERENCIA_ID_POR_REGIAO_BASE_ZERO = {
    "SP": "GGE_0025",  # GER MALHA (SP) — Jefferson Luders
    "VP": "GGE_0197",  # GER IMPLANT DE OBRAS E MALHA VP — Vinicius Nascimento
}


def _atribuir_gg_orcamento(df_orc: pd.DataFrame, dim_gg: pd.DataFrame) -> pd.DataFrame:
    """Anexa gg_id/gg_nome/gerencia_id a fact_orcamento para viabilizar
    Nível 1/2 por GG e a visão por Gerência.

    # GAP: Base Zero não tem coluna de GG (só "Gerência" SP/VP — ver GAP em
    # _construir_dim_gg). Como hoje só existe 1 GG real no Realizado
    # (Malha SP) e o próprio arquivo da Base Zero é escopado a "SP e VP", o
    # arquivo inteiro é atribuído a esse único GG — não é um join linha a
    # linha, é uma suposição de escopo do arquivo. Só é seguro enquanto
    # houver exatamente 1 GG carregado; com mais de um GG (RJ/FA/LC
    # chegando), isso vira ambíguo e fica None de propósito (ver
    # docs/02-perguntas-em-aberto.md, item 5 — não resolver por chute).

    `gerencia_id` usa `_GERENCIA_ID_POR_REGIAO_BASE_ZERO` (SP/VP ->
    Gerência confirmada pelo usuário, ver comentário acima). Qualquer
    `gerencia_raw` fora de SP/VP (não deveria acontecer na Base Zero, mas
    por segurança) fica `NA` — nunca inventada.
    """
    df_orc = df_orc.copy()
    if len(dim_gg) == 1:
        df_orc["gg_id"] = dim_gg.iloc[0]["gg_id"]
        df_orc["gg_nome"] = dim_gg.iloc[0]["gg_nome"]
    else:
        df_orc["gg_id"] = pd.NA
        df_orc["gg_nome"] = pd.NA
    df_orc["gerencia_id"] = df_orc["gerencia_raw"].map(_GERENCIA_ID_POR_REGIAO_BASE_ZERO)
    return df_orc


def _juntar_conta_interna(codigos: pd.Series, catalogo: pd.DataFrame | None) -> tuple[pd.Series, pd.Series]:
    """Casa `codigos` (conta_orcamento_id ou conta_razao_id, já em texto)
    contra `load_catalogo_contas`, devolvendo (conta_interna_id,
    conta_interna_nome) — a chave que une Orçamento e Realizado numa conta
    só no Nível 4 (decisão de 2026-08-10, a pedido do usuário: "não
    separar Contas do Orçamento e Contas do Realizado").

    Sem catálogo (arquivo não presente) ou código não catalogado, usa o
    próprio código como `conta_interna_id` e nome vazio — não inventa
    nome. Isso preserva o comportamento de antes (2 subárvores por
    código bruto) exatamente quando não há como unir de verdade.
    """
    codigos = codigos.astype(str).str.strip()
    if catalogo is None or catalogo.empty:
        return codigos, pd.Series([""] * len(codigos), index=codigos.index)

    mapa = catalogo.drop_duplicates(subset=["codigo"]).set_index("codigo")
    casado = codigos.to_frame("codigo").merge(
        mapa[["conta_interna_id", "conta_interna_nome"]],
        left_on="codigo", right_index=True, how="left",
    )
    conta_interna_id = casado["conta_interna_id"].fillna(casado["codigo"])
    conta_interna_nome = casado["conta_interna_nome"].fillna("")
    return conta_interna_id, conta_interna_nome


_COLUNAS_FACT_ORCAMENTO = [
    "ano", "mes", "pacote_id", "familia_pacote", "conta_orcamento_id",
    "conta_interna_id", "conta_interna_nome",
    "classificacao_contabil", "centro_custo_id", "pep_id", "pep_nome",
    "area", "gerencia_raw", "gerencia_id", "gg_id", "gg_nome",
    "tipo_item", "grupo_disciplina", "sub_grupo_escopo", "valor_orcado",
]


def _reshape_consulta_contas_opex(df_cc: pd.DataFrame) -> pd.DataFrame:
    """Reformata `load_consulta_contas` pro mesmo formato de
    `load_base_zero`, pra virar a fonte de OPEX de `fact_orcamento` (ver
    decisão de 2026-08-10 no topo do módulo).

    Campos que a Consulta de Contas não tem (area, pep, tipo/disciplina)
    ficam vazios — não inventar valor. `gerencia_raw` aqui é o nome de
    Gerência real da Consulta de Contas, não o SP/VP bruto que a Base Zero
    trazia — são conceitos diferentes, mas a coluna é só um atributo
    informativo, não uma chave de junção.

    `gerencia_id` (2026-08-11, a pedido do usuário: visão "por Gerência"
    dentro da GG no Painel Executivo) sai direto da própria Consulta de
    Contas — ela já extrai `gerencia_id`/`gerencia_nome` da coluna
    "GERENCIA" (ver `load_consulta_contas`), mesma hierarquia que o
    Realizado usa, sem precisar de join por nome. Só existe pro OPEX vindo
    daqui — CAPEX (Base Zero) não tem Gerência real, fica `NA` de
    propósito (ver `_atribuir_gg_orcamento` pro mesmo padrão já usado com
    GG).

    `conta_interna_id`/`conta_interna_nome` saem preenchidos direto da
    própria Consulta de Contas (`conta_id`/`conta_nome`) — ela já usa o
    mesmo código "interno" que o Catálogo de Contas (`PM03009`, não o
    número SAP), então não depende do catálogo pra ter nome aqui.
    """
    vazio = pd.Series([""] * len(df_cc), index=df_cc.index)
    return pd.DataFrame({
        "ano": df_cc["ano"],
        "mes": df_cc["mes"],
        "pacote_id": df_cc["pacote_id"],
        "familia_pacote": df_cc["familia_pacote"],
        "conta_orcamento_id": df_cc["conta_id"],
        "conta_interna_id": df_cc["conta_id"],
        "conta_interna_nome": df_cc["conta_nome"],
        "classificacao_contabil": "OPEX",
        "centro_custo_id": df_cc["centro_custo_id"],
        "pep_id": vazio,
        "pep_nome": vazio,
        "area": vazio,
        "gerencia_raw": df_cc["gerencia_nome"].fillna(""),
        "gerencia_id": df_cc["gerencia_id"],
        "gg_id": df_cc["gg_id"],
        "gg_nome": df_cc["gg_nome"],
        "tipo_item": vazio,
        "grupo_disciplina": vazio,
        "sub_grupo_escopo": vazio,
        "valor_orcado": df_cc["valor_orcado"],
    })


# Regra por Centro de Custo confirmada diretamente pelo usuário em
# 2026-08-17 (não inferida dos dados) — todos os 9 CCs da planilha do PCM
# resolvidos, nenhum resíduo sem confirmação. Cada entrada é uma ação:
# - ("assign", gerencia_id, gerencia_nome): fica em GGG_0054, ganha essa
#   Gerência (CGE041 já vinha cruzado com a Consulta de Contas; CGE053 é
#   confirmação direta do usuário: "faz parte do Vinicius" = mesma
#   Gerência já usada pro resto do CAPEX VP, GGE_0197).
# - ("exclude",): usuário confirmou que a Gerência **não é GGG_0054**
#   (Ferrovia do Aço/CGE052, Linha do Centro-MG/CGE039, Malha RJ/CGE040 —
#   parte da GGRJ; e as 4 coordenações CCR* de Vale do Paraíba, que apesar
#   do nome geográfico o usuário confirmou serem da GGFA, não da nossa
#   GG) — o valor sai do painel em vez de ganhar uma Gerência dentro do
#   escopo errado.
_REGRAS_COMBUSTIVEL_TERCEIROS: dict[str, tuple] = {
    "CGE041": ("assign", "GGE_0025", "GER MALHA (SP)"),
    "CGE053": ("assign", "GGE_0197", "GER IMPLANT DE OBRAS E MALHA VP"),
    "CGE052": ("exclude",),
    "CGE039": ("exclude",),
    "CGE040": ("exclude",),
    "CCR101": ("exclude",),
    "CCR062": ("exclude",),
    "CCR071": ("exclude",),
    "CCR093": ("exclude",),
}


def _aplicar_correcao_combustivel_terceiros(
    df_orc_opex: pd.DataFrame, df_transferencia: pd.DataFrame,
) -> pd.DataFrame:
    """Redistribui/exclui as fatias já confirmadas do Combustível Terceiros
    (ver `load_transferencia_combustivel_terceiros` e
    `_REGRAS_COMBUSTIVEL_TERCEIROS`) pra fora do bucket CGG050/"#GERENCIA
    INEXISTENTE" — mesmo mecanismo do `_GERENCIA_ID_POR_REGIAO_BASE_ZERO`
    (2026-08-17), mas pro lado OPEX/Consulta de Contas em vez do CAPEX/
    Base Zero.

    Localiza a(s) linha(s) sem Gerência cujo total bate com o total da
    planilha do PCM (mesmo `conta_orcamento_id`, `centro_custo_id`
    começando com "CGG050", `gerencia_id` nulo) — se não achar exatamente
    esse valor, não mexe em nada (mais seguro que assumir e descontar
    errado de uma linha parecida). Fatias com regra "exclude" reduzem o
    total do painel (a verba não é de GGG_0054); fatias sem regra nenhuma
    ficam como estavam, em "Não atribuído".
    """
    linhas_com_regra = df_transferencia[
        df_transferencia["centro_custo_id"].isin(_REGRAS_COMBUSTIVEL_TERCEIROS)
    ]
    if linhas_com_regra.empty:
        return df_orc_opex

    candidatas = df_orc_opex[
        df_orc_opex["gerencia_id"].isna()
        & df_orc_opex["centro_custo_id"].astype(str).str.startswith("CGG050")
    ]
    total_transferencia = float(df_transferencia["valor"].sum())
    linhas_alvo = candidatas[
        (candidatas["valor_orcado"] - total_transferencia).abs() < 1.0
    ]
    if linhas_alvo.empty:
        print(
            "AVISO: 'Transferência Combustível Terceiros' carregada, mas nenhuma "
            f"linha de CGG050 bate com o total dela (R$ {total_transferencia:,.2f}) — "
            "a planilha pode estar desatualizada em relação à Consulta de Contas "
            "atual. Essa fatia fica em 'Não atribuído'/cai no CGG050 genérico "
            "('GG direto') até alguém revisar. Não mexi em nada de propósito, pra "
            "não descontar valor errado de uma linha parecida."
        )
        return df_orc_opex

    df_orc_opex = df_orc_opex.copy()
    novas_linhas = []
    for idx in linhas_alvo.index:
        row = df_orc_opex.loc[idx]
        valor_restante = float(row["valor_orcado"])
        for _, linha_transf in linhas_com_regra.iterrows():
            cc = linha_transf["centro_custo_id"]
            acao = _REGRAS_COMBUSTIVEL_TERCEIROS[cc]
            valor_cc = float(linha_transf["valor"])
            conta_cc = str(linha_transf["conta_orcamento_id"]).strip()
            valor_restante -= valor_cc
            if acao[0] == "exclude":
                continue
            _, gerencia_id, gerencia_nome = acao
            nova_linha = row.copy()
            nova_linha["conta_orcamento_id"] = conta_cc
            nova_linha["centro_custo_id"] = cc
            nova_linha["gerencia_id"] = gerencia_id
            nova_linha["gerencia_raw"] = gerencia_nome
            nova_linha["valor_orcado"] = valor_cc
            novas_linhas.append(nova_linha)
        df_orc_opex.loc[idx, "valor_orcado"] = valor_restante

    if novas_linhas:
        df_orc_opex = pd.concat(
            [df_orc_opex, pd.DataFrame(novas_linhas)], ignore_index=True,
        )
    return df_orc_opex


def _aplicar_correcao_cgg050_direto_gg(df_orc_opex: pd.DataFrame) -> pd.DataFrame:
    """Atribui `_GERENCIA_ID_GG_DIRETO` a qualquer linha que ainda esteja
    sem Gerência e cujo Centro de Custo comece com "CGG050" — regra geral
    confirmada pelo usuário em 2026-08-17 (ver comentário em
    `_GERENCIA_ID_GG_DIRETO`), não um ajuste pontual.

    Roda **depois** de `_aplicar_correcao_combustivel_terceiros` de
    propósito: aquela função ainda precisa achar `gerencia_id IS NULL`
    pra separar a fatia que pertence a Gerências de campo (SP/VP) — só o
    que sobrar sem regra específica cai aqui, direto na GG.
    """
    df_orc_opex = df_orc_opex.copy()
    mascara = (
        df_orc_opex["gerencia_id"].isna()
        & df_orc_opex["centro_custo_id"].astype(str).str.startswith("CGG050")
    )
    df_orc_opex.loc[mascara, "gerencia_id"] = _GERENCIA_ID_GG_DIRETO
    df_orc_opex.loc[mascara, "gerencia_raw"] = _GERENCIA_NOME_GG_DIRETO
    return df_orc_opex


def _aplicar_correcao_cgg050_direto_gg_realizado(df_real_opex: pd.DataFrame) -> pd.DataFrame:
    """Mesma regra de `_aplicar_correcao_cgg050_direto_gg`, lado Realizado
    (colunas `gerencia_nome`/`valor_realizado`, não `gerencia_raw`/
    `valor_orcado`) — o mesmo fenômeno CGG050 apareceu também no
    Realizado (Consulta de Contas VersãoComparativo2), mesmas 8 contas de
    Despesas Gerais (Passagens, Hospedagem, etc.), confirmado em
    2026-08-17."""
    df_real_opex = df_real_opex.copy()
    mascara = (
        df_real_opex["gerencia_id"].isna()
        & df_real_opex["centro_custo_id"].astype(str).str.startswith("CGG050")
    )
    df_real_opex.loc[mascara, "gerencia_id"] = _GERENCIA_ID_GG_DIRETO
    df_real_opex.loc[mascara, "gerencia_nome"] = _GERENCIA_NOME_GG_DIRETO
    return df_real_opex


_COLUNAS_FACT_REALIZADO = [
    "ano", "mes", "pacote_id", "familia_pacote", "conta_razao_id",
    "conta_razao_nome", "conta_interna_id", "conta_interna_nome",
    "centro_custo_id", "centro_custo_nome", "coordenacao",
    "classificacao_contabil", "gg_id", "gg_nome", "gerencia_id", "gerencia_nome",
    "valor_realizado",
]


def _reshape_consulta_contas_realizado_opex(df_cc: pd.DataFrame) -> pd.DataFrame:
    """Reformata `load_consulta_contas` (`VersãoComparativo2` = Realizado)
    pro formato de `fact_realizado` — decisão do usuário em 2026-08-11:
    Consulta de Contas vira a fonte de verdade também do Realizado de
    OPEX, não só do Orçado (`_reshape_consulta_contas_opex`). Confirmado
    nos dados reais: o total de `VersãoComparativo2` (R$23,95 MM) bate
    quase exato com o que o SAP (Base Analítico) já trazia como Realizado
    total (R$23,94 MM, diferença de ~R$10 mil) — ou seja, o Realizado que
    o painel já mostrava era, na prática, quase só OPEX; CAPEX Realizado
    não tem fonte carregada ainda (usuário vai trazer de outro arquivo,
    "Base Crua" — não é derivado por subtração, fica ausente até chegar).

    O SAP (Base Analítico) deixa de alimentar `fact_realizado` direto,
    mas continua intacto em `fact_realizado_documento` (Nível 6) — o
    cascateamento/detalhe documento-a-documento, Centro de Custo e
    Gerência do mesmo Realizado de OPEX, não uma fonte concorrente.

    `conta_razao_id`/`conta_razao_nome` (código SAP numérico) não existem
    nesta fonte — ficam vazios. `conta_interna_id`/`conta_interna_nome`
    saem direto do próprio `conta_id`/`conta_nome`, mesmo tratamento do
    lado Orçado.
    """
    vazio = pd.Series([""] * len(df_cc), index=df_cc.index)
    return pd.DataFrame({
        "ano": df_cc["ano"],
        "mes": df_cc["mes"],
        "pacote_id": df_cc["pacote_id"],
        "familia_pacote": df_cc["familia_pacote"],
        "conta_razao_id": vazio,
        "conta_razao_nome": vazio,
        "conta_interna_id": df_cc["conta_id"],
        "conta_interna_nome": df_cc["conta_nome"],
        "centro_custo_id": df_cc["centro_custo_id"],
        "centro_custo_nome": df_cc["centro_custo_nome"],
        "coordenacao": _derivar_coordenacao(df_cc),
        "classificacao_contabil": "OPEX",
        "gg_id": df_cc["gg_id"],
        "gg_nome": df_cc["gg_nome"],
        "gerencia_id": df_cc["gerencia_id"],
        "gerencia_nome": df_cc["gerencia_nome"],
        "valor_realizado": df_cc["valor_realizado"],
    })


def _reshape_cji4_capex_obras(
    df_fin: pd.DataFrame,
    df_catalogo: pd.DataFrame | None,
    catalogo_contas: pd.DataFrame | None,
) -> pd.DataFrame:
    """Junta o financeiro CJI4 (`load_cji4_capex_obras`) com o catálogo de
    projetos (`load_catalogo_capex_obras`, opcional — dá nome/Gerência) e
    o Catálogo de Contas (`load_catalogo_contas`, opcional, reaproveitado
    — 27 dos 29 códigos de `classe_custo` já batem, confirmado em
    2026-08-11) — vira `fact_cji4_capex_obras`. Tabela separada, não
    somada a `fact_orcamento` (ver decisão no topo do módulo).
    """
    df = df_fin.copy()
    df["conta_interna_id"], df["conta_interna_nome"] = _juntar_conta_interna(
        df["classe_custo"], catalogo_contas
    )

    if df_catalogo is not None and not df_catalogo.empty:
        # 1 linha por projeto (primeira ocorrência) — o catálogo tem
        # várias linhas por projeto (1 por etapa/Título do cronograma),
        # mas o nome/Gerência do projeto não muda entre etapas.
        nomes_projeto = df_catalogo[
            ["e_pep_projeto", "nome_empreendimento", "gerencia_obras"]
        ].drop_duplicates(subset=["e_pep_projeto"], keep="first")
        df = df.merge(nomes_projeto, on="e_pep_projeto", how="left")
    else:
        df["nome_empreendimento"] = pd.NA
        df["gerencia_obras"] = pd.NA

    df["nome_empreendimento"] = df["nome_empreendimento"].fillna("")
    df["gerencia_obras"] = df["gerencia_obras"].fillna("")
    return df


def _reshape_cji3_capex_obras(
    df_real: pd.DataFrame,
    df_catalogo: pd.DataFrame | None,
    catalogo_contas: pd.DataFrame | None,
) -> pd.DataFrame:
    """Junta o Realizado CJI3 (`load_cji3_capex_obras_realizado`) com o
    catálogo de projetos e o Catálogo de Contas — mesmo tratamento de
    `_reshape_cji4_capex_obras`, pro par Orçado/Realizado ficar no mesmo
    formato e dar pra cruzar por `e_pep_projeto`/`elemento_pep`. Tabela
    separada `fact_cji3_capex_obras`, não somada a `fact_realizado` (ver
    decisão no topo do módulo — universo financeiro diferente, não dúvida
    de escopo, que já foi confirmado em 2026-08-12).
    """
    df = df_real.copy()
    df["conta_interna_id"], df["conta_interna_nome"] = _juntar_conta_interna(
        df["classe_custo"], catalogo_contas
    )

    if df_catalogo is not None and not df_catalogo.empty:
        nomes_projeto = df_catalogo[
            ["e_pep_projeto", "nome_empreendimento", "gerencia_obras"]
        ].drop_duplicates(subset=["e_pep_projeto"], keep="first")
        df = df.merge(nomes_projeto, on="e_pep_projeto", how="left")
    else:
        df["nome_empreendimento"] = pd.NA
        df["gerencia_obras"] = pd.NA

    df["nome_empreendimento"] = df["nome_empreendimento"].fillna("")
    df["gerencia_obras"] = df["gerencia_obras"].fillna("")
    return df


def _derivar_pce_realizado(
    df_cji3_capex_obras: pd.DataFrame,
    df_catalogo: pd.DataFrame | None,
) -> pd.DataFrame:
    """`fact_pce_realizado` (Realizado da "CAPEX Obras — Especialista")
    derivada inteiramente do CJI3 (já reshapeado com nome/Gerência do
    Catálogo, ver `_reshape_cji3_capex_obras`) + Catálogo CAPEX Obras —
    substitui a leitura direta de "PCE Base Luiz.xlsx" (removida em
    2026-08-27, ver docs/04-licoes-aprendidas.md item 20). Objetivo do
    usuário: mínimo de planilhas manuais, o máximo construído a partir
    das bases cruas do SAP que já sobem pela rotina normal.

    - `descricao` (Classificação fina: SERVIÇOS/MATERIAIS/ENGENHARIA...)
      vem de `carregar_catalogo_objeto_classificacao()` via `objeto` —
      achado 2026-08-27: 100% determinístico por Objeto no dado real, não
      é julgamento por lançamento.
    - `grupo` deriva de `descricao` via `_reclassificar_grupo`, mesma
      regra já usada em `load_pce_consolidado`/o antigo `load_pce_realizado`.
    - `classificacao_atualizada` (A+1..A+8/Não renovação) vem do Catálogo
      CAPEX Obras via `e_pep_projeto` — confirmado pelo usuário e 100%
      consistente por projeto no dado real (nenhum projeto com valor
      conflitante ou ausente).

    Objeto sem entrada no catálogo (não visto ainda) fica com `descricao`
    = "NÃO CLASSIFICADO" e `grupo` = `None` — não trava o reprocessamento,
    só fica sem cair em nenhum dos 8 blocos de Análise por Grupo até o
    catálogo ser atualizado.
    """
    catalogo_objeto = carregar_catalogo_objeto_classificacao()
    df = df_cji3_capex_obras.merge(
        catalogo_objeto[["objeto", "classificacao"]], on="objeto", how="left"
    )
    df = df.rename(columns={"classificacao": "descricao"})
    df["descricao"] = df["descricao"].fillna("NÃO CLASSIFICADO")
    df["grupo"] = pd.NA
    df = _reclassificar_grupo(df)

    if df_catalogo is not None and not df_catalogo.empty:
        classif_atual = df_catalogo[
            ["e_pep_projeto", "classificacao_atualizada"]
        ].drop_duplicates(subset=["e_pep_projeto"], keep="first")
        df = df.merge(classif_atual, on="e_pep_projeto", how="left")
    else:
        df["classificacao_atualizada"] = pd.NA

    return df[[
        "ano", "mes", "e_pep_projeto", "elemento_pep", "nome_empreendimento",
        "gerencia_obras", "grupo", "descricao", "classificacao_atualizada",
        "numero_documento", "data_documento", "data_lancamento", "valor_realizado",
    ]]


def _agregar_fact_orcamento(df_orc: pd.DataFrame) -> pd.DataFrame:
    chaves = [
        "ano", "mes", "pacote_id", "familia_pacote", "conta_orcamento_id",
        "conta_interna_id", "conta_interna_nome",
        "classificacao_contabil", "centro_custo_id", "pep_id", "pep_nome",
        "area", "gerencia_raw", "gerencia_id",
        "gg_id", "gg_nome", "tipo_item", "grupo_disciplina", "sub_grupo_escopo",
    ]
    return df_orc.groupby(chaves, dropna=False, as_index=False)["valor_orcado"].sum()


def _agregar_fact_realizado(df_real: pd.DataFrame) -> pd.DataFrame:
    chaves = [
        "ano", "mes", "pacote_id", "familia_pacote", "conta_razao_id",
        "conta_razao_nome", "conta_interna_id", "conta_interna_nome",
        "centro_custo_id", "centro_custo_nome", "coordenacao",
        "classificacao_contabil", "gg_id", "gg_nome", "gerencia_id", "gerencia_nome",
    ]
    return df_real.groupby(chaves, dropna=False, as_index=False)["valor_realizado"].sum()


def build_star_schema() -> str:
    cfg = carregar_config()
    caminho_bz = cfg["caminhos"]["base_zero"]
    caminho_real = cfg["caminhos"]["realizado"]
    caminho_db = cfg["caminhos"]["warehouse_db"]
    escopo_gg = cfg.get("gg_escopo_dinfra")

    os.makedirs(os.path.dirname(caminho_db), exist_ok=True)

    if not os.path.exists(caminho_bz) or not os.path.exists(caminho_real):
        print(
            "Arquivos de origem ainda não estão em data/raw/ "
            "(base_zero / realizado) — nada para carregar ainda."
        )
        return caminho_db

    df_orc = load_base_zero(caminho_bz, ano_fiscal=cfg["ano_fiscal_orcamento"])
    df_real = load_realizado(caminho_real)
    df_real["coordenacao"] = _derivar_coordenacao(df_real)
    df_fact_realizado_documento = load_realizado_documentos(caminho_real)
    df_fact_realizado_documento["coordenacao"] = _derivar_coordenacao(df_fact_realizado_documento)

    # Tabela separada, opcional — não participa de fact_orcamento/
    # fact_realizado nem dos testes de fechamento já validados (Fases 4/5).
    # Só materializa se o arquivo existir (fonte trazida em 2026-08-10,
    # ainda sem reconciliação 100% fechada — ver docs/02-perguntas-em-aberto.md).
    caminho_consulta_contas = cfg["caminhos"].get("consulta_contas")
    df_consulta_contas = None
    if caminho_consulta_contas and os.path.exists(caminho_consulta_contas):
        df_consulta_contas = load_consulta_contas(caminho_consulta_contas)

    # De/para mestre Conta -> "conta interna" (COD_CG_SAP) — une Orçamento
    # e Realizado numa conta só no Nível 4 (decisão de 2026-08-10, a
    # pedido do usuário). Opcional, mesmo padrão dos demais.
    caminho_catalogo_contas = cfg["caminhos"].get("catalogo_contas")
    catalogo_contas = None
    if caminho_catalogo_contas and os.path.exists(caminho_catalogo_contas):
        catalogo_contas = load_catalogo_contas(caminho_catalogo_contas)

    # CAPEX de Projetos e Obras (CJI4 Orçado + CJI3 Realizado) — tabelas
    # separadas, opcionais, não participam de fact_orcamento/
    # fact_realizado (ver decisão no topo do módulo: universo financeiro
    # diferente de Manutenção Corrente, não dúvida de escopo — escopo
    # DINFRA já confirmado em 2026-08-12). Os 3 arquivos são
    # independentes entre si: sem o catálogo, os projetos ficam só com o
    # código; sem o financeiro (CJI4/CJI3), a tabela correspondente nem é
    # criada.
    caminho_catalogo_capex_obras = cfg["caminhos"].get("catalogo_capex_obras")
    df_catalogo_capex_obras = None
    if caminho_catalogo_capex_obras and os.path.exists(caminho_catalogo_capex_obras):
        df_catalogo_capex_obras = load_catalogo_capex_obras(caminho_catalogo_capex_obras)

    caminho_cji4 = cfg["caminhos"].get("cji4_capex_obras")
    df_cji4_capex_obras = None
    if caminho_cji4 and os.path.exists(caminho_cji4):
        df_cji4_fin = load_cji4_capex_obras(caminho_cji4)
        df_cji4_capex_obras = _reshape_cji4_capex_obras(
            df_cji4_fin, df_catalogo_capex_obras, catalogo_contas
        )

    caminho_cji3 = cfg["caminhos"].get("cji3_capex_obras")
    df_cji3_capex_obras = None
    if caminho_cji3 and os.path.exists(caminho_cji3):
        df_cji3_fin = load_cji3_capex_obras_realizado(caminho_cji3)
        df_cji3_capex_obras = _reshape_cji3_capex_obras(
            df_cji3_fin, df_catalogo_capex_obras, catalogo_contas
        )

    # "Consolidado.xlsx" — base mestra de planejamento de CAPEX Obras,
    # tabela própria `fact_pce_consolidado`, mesmo padrão de isolamento do
    # CJI4/CJI3 (ver decisão no topo do módulo): não soma com
    # fact_orcamento/fact_realizado nem com fact_cji4/fact_cji3_capex_obras
    # — usuário confirmou em 2026-08-19 que a Label do Especialista usa
    # essa fonte à parte, com filtro de Versão próprio (não tem "a" versão
    # oficial única aqui).
    caminho_pce_consolidado = cfg["caminhos"].get("pce_consolidado")
    df_pce_consolidado = None
    if caminho_pce_consolidado and os.path.exists(caminho_pce_consolidado):
        df_pce_consolidado = load_pce_consolidado(caminho_pce_consolidado)

    # `fact_pce_realizado` — removida a dependência de "PCE Base Luiz.xlsx"
    # em 2026-08-27 (planilha curada manualmente, arriscada de manter:
    # qualquer mudança no jeito do Luiz montar o arquivo quebrava o
    # painel). Derivada agora inteiramente do CJI3 (já carregado acima) +
    # Catálogo CAPEX Obras — ver `_derivar_pce_realizado` e
    # docs/04-licoes-aprendidas.md, item 20. Só existe se o CJI3 também
    # existir (mesma fonte).
    df_pce_realizado = None
    if df_cji3_capex_obras is not None:
        df_pce_realizado = _derivar_pce_realizado(df_cji3_capex_obras, df_catalogo_capex_obras)

    # Escopo de GG (config `gg_escopo_dinfra`, confirmado com o usuário em
    # 2026-08-10 — ver comentário no settings.yaml): os exports de
    # Realizado/Consulta de Contas trazem GGs de outras Diretorias junto
    # (TI/Operações, "OFF DIR DE INFRAESTRUTURA") — esse painel é só
    # GER. GERAL DE INFRAESTRUTURA (SP). Filtra aqui, antes de qualquer
    # dimensão/agregação ser construída, pra não vazar total de fora do
    # escopo em nenhuma tela. Sem essa config (`gg_escopo_dinfra` vazio/
    # ausente), não filtra nada — não inventar escopo por suposição.
    if escopo_gg:
        df_real = df_real[df_real["gg_id"].isin(escopo_gg)].copy()
        df_fact_realizado_documento = df_fact_realizado_documento[
            df_fact_realizado_documento["gg_id"].isin(escopo_gg)
        ].copy()
        if df_consulta_contas is not None:
            df_consulta_contas = df_consulta_contas[df_consulta_contas["gg_id"].isin(escopo_gg)].copy()

    df_dim_tempo = _construir_dim_tempo(df_orc, df_real)
    df_dim_pacote = _construir_dim_pacote(df_orc, df_real)
    df_dim_gg = _construir_dim_gg(df_real)
    df_dim_gerencia = _construir_dim_gerencia(df_real)

    # CAPEX continua só da Base Zero. OPEX Orçado: só Consulta de Contas
    # (2026-08-11, a pedido do usuário — "fonte de verdade"). O fallback
    # pra Base Zero (que já confirmamos incompleta pro OPEX) foi removido
    # de propósito: sem o arquivo, OPEX Orçado fica vazio, não inventa um
    # número pior no lugar de um número ausente.
    df_orc_capex = df_orc[df_orc["classificacao_contabil"] == "CAPEX"].copy()
    df_orc_capex = _atribuir_gg_orcamento(df_orc_capex, df_dim_gg)
    # CAPEX da Base Zero não traz nome de conta nenhum (confirmado:
    # "PM03010" sozinho, sem texto) — só o catálogo resolve isso.
    df_orc_capex["conta_interna_id"], df_orc_capex["conta_interna_nome"] = _juntar_conta_interna(
        df_orc_capex["conta_orcamento_id"], catalogo_contas
    )

    if df_consulta_contas is not None:
        df_orc_opex = _reshape_consulta_contas_opex(df_consulta_contas)
    else:
        print(
            "AVISO: Consulta de Contas ausente — OPEX Orçado ficará vazio "
            "(Base Zero não é mais usada como fallback pro OPEX)."
        )
        df_orc_opex = pd.DataFrame(columns=_COLUNAS_FACT_ORCAMENTO)

    # De/para do PCM (2026-08-17) pra fechar parte do bucket CGG050/
    # "#GERENCIA INEXISTENTE" do Combustível Terceiros — só a fatia de SP,
    # ver `_aplicar_correcao_combustivel_terceiros`. Opcional/best-effort:
    # sem o arquivo, ou se o valor não bater exato, não faz nada.
    caminho_transferencia = cfg["caminhos"].get("transferencia_combustivel_terceiros")
    if caminho_transferencia and os.path.exists(caminho_transferencia):
        df_transferencia = load_transferencia_combustivel_terceiros(caminho_transferencia)
        df_orc_opex = _aplicar_correcao_combustivel_terceiros(df_orc_opex, df_transferencia)

    # Regra geral (2026-08-17): o que sobrar sem Gerência em CGG050 depois
    # da correção acima é despesa direta da GG (Marcelo Modolo), não gap —
    # ver `_aplicar_correcao_cgg050_direto_gg`.
    df_orc_opex = _aplicar_correcao_cgg050_direto_gg(df_orc_opex)

    df_orc_final = pd.concat(
        [df_orc_capex[_COLUNAS_FACT_ORCAMENTO], df_orc_opex[_COLUNAS_FACT_ORCAMENTO]],
        ignore_index=True,
    )

    df_fact_orcamento = _agregar_fact_orcamento(df_orc_final)

    # Realizado de OPEX: Consulta de Contas (VersãoComparativo2), fonte de
    # verdade decidida pelo usuário em 2026-08-11 — reconcilia quase exato
    # (diferença de ~R$10 mil em R$23,9 MM) contra o total que o SAP já
    # trazia, então o SAP (Base Analítico) deixa de alimentar
    # `fact_realizado` diretamente. Continua intacto em
    # `fact_realizado_documento` (Nível 6) — o cascateamento/detalhe
    # documento-a-documento, Centro de Custo e Gerência do mesmo Realizado
    # de OPEX, não uma fonte concorrente. CAPEX Realizado ainda não tem
    # fonte (o usuário vai trazer de outro arquivo, "Base Crua") — fica
    # sem nenhuma linha por enquanto, não inventado nem derivado por
    # subtração (Total SAP − OPEX).
    if df_consulta_contas is not None:
        df_real_opex = _reshape_consulta_contas_realizado_opex(df_consulta_contas)
        df_real_opex = _aplicar_correcao_cgg050_direto_gg_realizado(df_real_opex)
    else:
        print(
            "AVISO: Consulta de Contas ausente — Realizado de OPEX ficará "
            "vazio (SAP não alimenta mais fact_realizado diretamente)."
        )
        df_real_opex = pd.DataFrame(columns=_COLUNAS_FACT_REALIZADO)

    df_fact_realizado = _agregar_fact_realizado(df_real_opex[_COLUNAS_FACT_REALIZADO])

    # As variáveis Python acima usam prefixo df_ de propósito: sem isso, um
    # rerun encontra uma tabela já existente de mesmo nome no .duckdb e
    # "SELECT * FROM fact_orcamento" resolve para a tabela antiga do disco
    # (não para o DataFrame novo) — reescrevendo o schema velho em cima de
    # si mesmo silenciosamente, sem erro.
    con = duckdb.connect(caminho_db)
    try:
        con.execute("CREATE OR REPLACE TABLE dim_tempo AS SELECT * FROM df_dim_tempo")
        con.execute("CREATE OR REPLACE TABLE dim_pacote AS SELECT * FROM df_dim_pacote")
        con.execute("CREATE OR REPLACE TABLE dim_gg AS SELECT * FROM df_dim_gg")
        con.execute("CREATE OR REPLACE TABLE dim_gerencia AS SELECT * FROM df_dim_gerencia")
        if df_catalogo_capex_obras is not None:
            # Materializa o Catálogo CAPEX Obras como dimensão própria —
            # até 2026-08-29 só existia como DataFrame transiente, usado
            # pra enriquecer fact_cji4/fact_cji3_capex_obras/fact_pce_realizado
            # (e ali sempre deduplicado 1 linha por projeto, perdendo a
            # granularidade Título/Descrição do cronograma — ver
            # `_reshape_cji4_capex_obras`). Pedido do usuário 2026-08-29:
            # precisa da granularidade completa (Elemento PEP E Título/PEP
            # Filho) pra virar lista selecionável de Escopos de dados na
            # Administração (`administracao.py::_listar_elemento_pep`/
            # `_listar_pep_filho`) — nenhuma coluna nova/inventada, é o
            # mesmo DataFrame de `load_catalogo_capex_obras` sem perder
            # linha nenhuma.
            con.execute(
                "CREATE OR REPLACE TABLE dim_catalogo_capex_obras AS "
                "SELECT * FROM df_catalogo_capex_obras"
            )
        con.execute("CREATE OR REPLACE TABLE fact_orcamento AS SELECT * FROM df_fact_orcamento")
        con.execute("CREATE OR REPLACE TABLE fact_realizado AS SELECT * FROM df_fact_realizado")
        con.execute(
            "CREATE OR REPLACE TABLE fact_realizado_documento AS "
            "SELECT * FROM df_fact_realizado_documento"
        )
        if df_consulta_contas is not None:
            con.execute(
                "CREATE OR REPLACE TABLE fact_consulta_contas AS "
                "SELECT * FROM df_consulta_contas"
            )
        if df_cji4_capex_obras is not None:
            # Sem filtro de `escopo_gg` — não porque o escopo seja incerto
            # (confirmado em 2026-08-12: as 5 Gerências de Obras são todas
            # DINFRA/GGG_0054), mas porque não existe `gg_id` nesses dados
            # (só "Gerência" em texto) e não há nada fora do escopo pra
            # cortar. Materializa tudo.
            con.execute(
                "CREATE OR REPLACE TABLE fact_cji4_capex_obras AS "
                "SELECT * FROM df_cji4_capex_obras"
            )
        if df_cji3_capex_obras is not None:
            # Mesmo caso do CJI4 — sem `gg_id` nesta fonte, mas escopo já
            # confirmado como 100% DINFRA.
            con.execute(
                "CREATE OR REPLACE TABLE fact_cji3_capex_obras AS "
                "SELECT * FROM df_cji3_capex_obras"
            )
        if df_pce_consolidado is not None:
            con.execute(
                "CREATE OR REPLACE TABLE fact_pce_consolidado AS "
                "SELECT * FROM df_pce_consolidado"
            )
        if df_pce_realizado is not None:
            con.execute(
                "CREATE OR REPLACE TABLE fact_pce_realizado AS "
                "SELECT * FROM df_pce_realizado"
            )
    finally:
        con.close()

    return caminho_db


if __name__ == "__main__":
    caminho_db = build_star_schema()
    print(f"Star schema materializado em: {caminho_db}")
