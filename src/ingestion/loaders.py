"""Fase 1 — ETL das duas fontes já validadas: Base Zero (Orçamento Aprovado)
e Base Analítico SAP (Realizado).

Cada loader devolve um DataFrame "tidy" (1 linha por item de orçamento/mês
ou por lançamento SAP), ainda na granularidade próxima da fonte. A
agregação para a grão do modelo dimensional (Pacote/Conta/Centro de
Custo/Mês) acontece em src/model/build_star_schema.py (Fase 2) — não aqui.
"""
from __future__ import annotations

import re

import pandas as pd

from src.config import RAIZ_PROJETO

MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

# Colunas descritivas da Base Zero que carregamos para fact_orcamento,
# mapeadas do nome de coluna original (linha de cabeçalho real do export,
# ver load_base_zero) para o nome em português usado no restante do projeto.
COLUNAS_BASE_ZERO = {
    "Área": "area",
    "Pacote": "pacote_id",
    "Conta": "conta_orcamento_id",
    "Tipo": "tipo_item",
    "Código do material/serviço": "codigo_material_servico",
    "Descrição do material/serviço": "descricao_material_servico",
    "Grupo/Disciplina": "grupo_disciplina",
    "Sub-Grupo/Escopo": "sub_grupo_escopo",
    "Split": "split",
    "Gerência": "gerencia_raw",
    "Centro de Trabalho": "centro_trabalho",
    "Classificação contábil": "classificacao_contabil",
    "Centro de Custo/PEP": "centro_custo_pep_raw",
}

# Regex de divisão do campo combinado "Centro de Custo/PEP" — ver
# _dividir_centro_custo_pep.
_PADRAO_PEP_COM_DESCRICAO = re.compile(r"^(?P<codigo>\S+)\s*\((?P<descricao>.+)\)\s*$")


def _dividir_centro_custo_pep(serie: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Separa o campo combinado "Centro de Custo/PEP" da Base Zero em dois
    eixos reais e paralelos — não um dentro do outro: Centro de Custo
    (formato "CCRxxx"/"CGExxx", sem "/") e Elemento PEP (contém "/", ex.:
    "ME/22001", "MC/24004C-04-02-05 (CREMALHEIRA-SP-IPA-Cremalheira)").

    Confirmado contra o dado real em 2026-08-10:
    - Toda linha "CCRxxx"/"CGExxx" bate 1:1 com `Cód. Centro de custo` do
      Realizado (SAP) — é Centro de Custo de verdade.
    - Nenhum código com "/" aparece no Realizado — porque lá o campo
      próprio de PEP vem 100% vazio no export (não porque o PEP não
      exista), ver docs/02-perguntas-em-aberto.md.
    - Essa divisão bate 100% com `Classificação contábil`: toda linha CAPEX
      tem "/" (é PEP), toda linha OPEX não tem (é Centro de Custo) — mesma
      regra descrita na Ata 07/08 (CAPEX usa Projeto/PEP, OPEX usa Centro
      de Custo/Ordem). Uma linha que quebrar essa correspondência no
      futuro é sinal de inconsistência a investigar, não bug do parser.
    """
    bruto = serie.fillna("").astype(str).str.strip()
    eh_pep = bruto.str.contains("/", regex=False)

    extraido = bruto.str.extract(_PADRAO_PEP_COM_DESCRICAO)
    pep_id = extraido["codigo"].fillna(bruto)
    pep_nome = extraido["descricao"].fillna("")

    centro_custo_id = bruto.where(~eh_pep, "")
    pep_id = pep_id.where(eh_pep, "")
    pep_nome = pep_nome.where(eh_pep, "")

    return centro_custo_id, pep_id, pep_nome

# Colunas de texto com grafia inconsistente na fonte (ex.: "Serviço" vs
# "SERVIÇO", "Equipe Fixa" vs "EQUIPE FIXA") — normaliza só maiúsculas e
# espaço, não reclassifica nada (ex.: "CI - EQUIPE FIXA" continua distinto
# de "EQUIPE FIXA", isso pode ser uma categoria diferente de verdade).
COLUNAS_NORMALIZAR_TEXTO = ["tipo_item", "grupo_disciplina", "sub_grupo_escopo"]


def _encontrar_linha_cabecalho(raw: pd.DataFrame, marcador: str = "Área") -> int:
    """Acha a linha real de cabeçalho da Base Zero.

    O export tem 2 linhas de "sujeira" antes do cabeçalho de fato (título +
    linha de grupo mesclado dos blocos mensais) — procurar pelo marcador em
    vez de fixar um índice numérico deixa o loader resiliente a uma linha a
    mais/a menos de título no topo do arquivo.
    """
    for i in range(min(10, len(raw))):
        if str(raw.iat[i, 0]).strip() == marcador:
            return i
    raise ValueError(
        f"Não encontrei a linha de cabeçalho da Base Zero (procurei por "
        f"'{marcador}' nas primeiras 10 linhas). O layout do export mudou?"
    )


def _col_por_nome(header: pd.Series, nome: str) -> int:
    """Índice da 1ª coluna cujo cabeçalho é exatamente `nome`.

    Usa a 1ª ocorrência de propósito: a Base Zero tem uma célula mesclada
    ("Pacote") que se repete em 2 colunas na leitura crua — só a primeira
    tem o dado real, a segunda é um artefato de célula mesclada do Excel.
    """
    for i, v in enumerate(header):
        if str(v).strip() == nome:
            return i
    raise KeyError(f"Coluna '{nome}' não encontrada no cabeçalho da Base Zero.")


def load_base_zero(path: str, ano_fiscal: int) -> pd.DataFrame:
    """Carrega a Base Zero (Orçamento Aprovado) em formato longo.

    1 linha por item de material/serviço orçado x mês. As 12 colunas
    mensais wide (bloco "Valor Financeiro Reajustado": "Vl <mês>" +
    "Total P26") viram linhas — não existe coluna de ano na fonte, então o
    ano fiscal vem de config/settings.yaml (`ano_fiscal_orcamento`).

    # GAP: ano fixo assumido a partir do rótulo "Total P26"/"Vl <mês>" do
    # export (Valor Financeiro Reajustado) — Base Zero não tem coluna de
    # ano explícita. Ver docs/02-perguntas-em-aberto.md, item 5.
    """
    raw = pd.read_excel(path, sheet_name=0, header=None)
    linha_cab = _encontrar_linha_cabecalho(raw)
    header = raw.iloc[linha_cab]
    dados = raw.iloc[linha_cab + 1:].reset_index(drop=True)

    # Colunas descritivas: seleciona por nome (1ª ocorrência).
    atributos = pd.DataFrame({
        novo: dados[_col_por_nome(header, original)]
        for original, novo in COLUNAS_BASE_ZERO.items()
    })
    atributos["familia_pacote"] = (
        atributos["pacote_id"].astype(str).str.extract(r"^([A-Za-z]+)")[0]
    )
    atributos["centro_custo_id"], atributos["pep_id"], atributos["pep_nome"] = (
        _dividir_centro_custo_pep(atributos["centro_custo_pep_raw"])
    )
    atributos = atributos.drop(columns=["centro_custo_pep_raw"])
    for coluna in COLUNAS_NORMALIZAR_TEXTO:
        atributos[coluna] = atributos[coluna].fillna("").astype(str).str.strip().str.upper()

    # Colunas mensais: bloco "Valor Financeiro Reajustado", rótulos "Vl <mês>".
    # (O espaçamento entre "Vl" e o mês é inconsistente no export original —
    # "Vl  Jan" com 2 espaços, "Vl Fev" com 1 — por isso o regex usa \s+.)
    padrao_vl = re.compile(r"^Vl\s+(\w+)$", re.IGNORECASE)
    colunas_mes = []
    for idx, rotulo in enumerate(header):
        m = padrao_vl.match(str(rotulo).strip())
        if m:
            abrev = m.group(1).strip().lower()
            if abrev in MESES_PT:
                colunas_mes.append((idx, MESES_PT[abrev]))

    if len(colunas_mes) != 12:
        raise ValueError(
            f"Esperava 12 colunas mensais 'Vl <mês>' na Base Zero, achei "
            f"{len(colunas_mes)}. O layout do export mudou?"
        )

    partes = []
    for idx_col, mes in colunas_mes:
        parte = atributos.copy()
        parte["mes"] = mes
        parte["valor_orcado"] = pd.to_numeric(dados[idx_col], errors="coerce").fillna(0.0)
        partes.append(parte)

    resultado = pd.concat(partes, ignore_index=True)
    resultado["ano"] = ano_fiscal
    return resultado


def load_realizado(path: str) -> pd.DataFrame:
    """Carrega a Base Analítico SAP (Realizado) em formato longo.

    1 linha por lançamento/nota fiscal. Ano/mês vêm de "Exercício Período
    Fiscal" (formato AAAAMM). O export termina com uma linha de total e
    linhas de rodapé (filtros aplicados) sem "Exercício Período Fiscal"
    preenchido — essas linhas são descartadas.
    """
    df = pd.read_excel(path, sheet_name=0)

    df = df[df["Exercício Período Fiscal"].notna()].copy()
    periodo = df["Exercício Período Fiscal"].astype(int)
    df["ano"] = periodo // 100
    df["mes"] = periodo % 100

    df["gg_id"], df["gg_nome"] = _parte_hierarquia_generico(df["HIERARQUIA-NÓS - GER GERAL"])
    df["gerencia_id"], df["gerencia_nome"] = _parte_hierarquia_generico(df["HIERARQUIA-NÓS - GERENCIA"])

    df["familia_pacote"] = df["COD_PCT_SAP"].astype(str).str.extract(r"^([A-Za-z]+)")[0]

    resultado = pd.DataFrame({
        "ano": df["ano"],
        "mes": df["mes"],
        "pacote_id": df["COD_PCT_SAP"],
        "pacote_nome": df["NM_PCT_SAP"],
        "familia_pacote": df["familia_pacote"],
        "conta_razao_id": df["Conta do Razão"],
        "conta_razao_nome": df["Texto descritivo das contas do Razão"],
        "centro_custo_id": df["Cód. Centro de custo"],
        "centro_custo_nome": df["Centro de custo"],
        "gg_id": df["gg_id"],
        "gg_nome": df["gg_nome"],
        "gerencia_id": df["gerencia_id"],
        "gerencia_nome": df["gerencia_nome"],
        "dre_final": df["DRE_FINAL"],
        "numero_documento": df["Nº documento"],
        "valor_realizado": pd.to_numeric(df["Montante em moeda da empresa"], errors="coerce").fillna(0.0),
    })
    return resultado


_PADRAO_HIERARQUIA = re.compile(r"^(\S+)\s*\((.*)\)\s*$")


def _parte_hierarquia_generico(serie: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Formato de origem: "GGG_0054 (GER. GERAL DE INFRAESTRUTURA (SP))" ->
    ("GGG_0054", "GER. GERAL DE INFRAESTRUTURA (SP)"). Compartilhado entre
    load_realizado, load_realizado_documentos e load_consulta_contas."""
    extraido = serie.astype(str).str.extract(_PADRAO_HIERARQUIA)
    return extraido[0], extraido[1]


def _dividir_codigo_nome(serie: pd.Series) -> tuple[pd.Series, pd.Series]:
    """"PP02-PESSOAL - DESCENTRALIZADO" -> ("PP02", "PESSOAL - DESCENTRALIZADO").
    Separa só no 1º "-" (nomes de conta/pacote têm "-" dentro do próprio
    texto, ex. "PESSOAL - DESCENTRALIZADO")."""
    partes = serie.fillna("").astype(str).str.split("-", n=1, expand=True)
    codigo = partes[0].str.strip()
    nome = partes[1].str.strip() if 1 in partes.columns else pd.Series([""] * len(serie))
    return codigo, nome.fillna("")


def load_consulta_contas(path: str) -> pd.DataFrame:
    """Carrega "Consulta de Contas.xlsx" — fonte trazida em 2026-08-10,
    Orçado (`VersãoComparativo1`) x Realizado (`VersãoComparativo2`) já com
    Pacote e Conta cruzados na mesma linha (sem o problema de vocabulário
    diferente que a Base Zero x Realizado SAP têm — ver nivel4_contas.py).

    Confirmado com dado real em 2026-08-10 (reconciliação PM03/GGG_0054):
    `VersãoComparativo1` é o Orçado **OPEX** da Base Zero (o Orçado CAPEX
    não aparece aqui — todas as contas vêm no formato "código-descrição",
    mesmo padrão que identificamos como OPEX em `_dividir_centro_custo_pep`
    e em `load_base_zero`). `VersãoComparativo2` é o mesmo Realizado que já
    carregamos (bateu na casa dos R$ mil, não milhão, na reconciliação).

    # GAP: reconciliação achou 2 contas do PM03 que não fecham com a Base
    # Zero carregada — "PM03009-SERVIÇOS DE INFRA ESTRUTURA DE VIA" (R$
    # 18,37 MM) não existe no Base Zero atual, e "PM03011-" tem uma
    # diferença de R$ 2,99 MM. Ver docs/02-perguntas-em-aberto.md — ainda
    # não confirmado com a Alice se é Base Zero desatualizado ou outra
    # causa. Não assumir que esta fonte corrige a Base Zero sem essa
    # confirmação.

    `VersãoComparativo3` vem 100% vazia no arquivo atual — não usada.
    """
    df = pd.read_excel(path, sheet_name="Export")

    periodo = df["COMPETENCIA"].astype(str).str.split("/", expand=True)
    ano = pd.to_numeric(periodo[0], errors="coerce")
    mes = pd.to_numeric(periodo[1], errors="coerce")

    gg_id, gg_nome = _parte_hierarquia_generico(df["GER GERAL"])
    gerencia_id, gerencia_nome = _parte_hierarquia_generico(df["GERENCIA"])
    diretoria_id, diretoria_nome = _parte_hierarquia_generico(df["DIRETORIA"])
    centro_custo_id, centro_custo_nome = _dividir_codigo_nome(df["CC(Descrição)"])
    pacote_id, pacote_nome = _dividir_codigo_nome(df["Pacote"])
    conta_id, conta_nome = _dividir_codigo_nome(df["Conta"])

    resultado = pd.DataFrame({
        "ano": ano,
        "mes": mes,
        "gg_id": gg_id,
        "gg_nome": gg_nome,
        "gerencia_id": gerencia_id,
        "gerencia_nome": gerencia_nome,
        "diretoria_id": diretoria_id,
        "diretoria_nome": diretoria_nome,
        "centro_custo_id": centro_custo_id,
        "centro_custo_nome": centro_custo_nome,
        "pacote_id": pacote_id,
        "familia_pacote": pacote_id.str.extract(r"^([A-Za-z]+)")[0],
        "pacote_nome": pacote_nome,
        "conta_id": conta_id,
        "conta_nome": conta_nome,
        "dominio": df["Descrição"],
        "linha_dre": df["d_DRE"],
        "responsavel": df["CC_PONTA_FIRME"],
        "valor_orcado": pd.to_numeric(df["VersãoComparativo1"], errors="coerce").fillna(0.0),
        "valor_realizado": pd.to_numeric(df["VersãoComparativo2"], errors="coerce").fillna(0.0),
    })
    resultado = resultado[resultado["ano"].notna() & resultado["mes"].notna()].copy()
    resultado["ano"] = resultado["ano"].astype(int)
    resultado["mes"] = resultado["mes"].astype(int)
    return resultado


def load_catalogo_contas(path: str) -> pd.DataFrame:
    """Carrega "Catalago de Contas.xlsx" — o de/para mestre entre código de
    conta e "conta interna" (`COD_CG_SAP`/`NM_CG_SAP`), trazido em
    2026-08-10. É o que une Orçamento (Base Zero) e Realizado (SAP) numa
    conta só: o mesmo `COD_CG_SAP` aparece em 2 tipos de linha —

    - linha "interna" (`Nº conta do Razão` = "IPM03009", com o "I" na
      frente): o código já é o mesmo que a Base Zero usa (`PM03009`),
      só com "I" na frente. Sem essa linha, o lado do Orçamento fica sem
      nome nenhum (confirmado: "PM03009" sozinho, sem texto, é o que a
      Base Zero traz).
    - linha "SAP real" (`Nº conta do Razão` = "4130110101", numérico):
      mapeia o código que o Realizado usa (`conta_razao_id`) pro mesmo
      `COD_CG_SAP`.

    Confirmado com dado real em 2026-08-10: 1.323 códigos distintos,
    nenhuma duplicidade. Devolve 1 linha por código (com e sem o prefixo
    "I", quando aplicável) — quem usa isso decide como casar contra
    `conta_orcamento_id`/`conta_razao_id`.
    """
    df = pd.read_excel(path, sheet_name="Export")
    df = df[df["Nº conta do Razão"].notna()].copy()

    codigo_bruto = df["Nº conta do Razão"].astype(str).str.strip()
    codigo_sem_i = codigo_bruto.where(
        ~codigo_bruto.str.match(r"^I[A-Za-z]{2}\d"), codigo_bruto.str[1:]
    )

    base = pd.DataFrame({
        "pacote_id": df["COD_PCT_SAP"],
        "conta_interna_id": df["COD_CG_SAP"],
        "conta_interna_nome": df["NM_CG_SAP"],
        "linha_dre": df["LinhaDRE"],
    })

    parte_bruta = base.copy()
    parte_bruta["codigo"] = codigo_bruto

    parte_sem_i = base.copy()
    parte_sem_i["codigo"] = codigo_sem_i

    resultado = pd.concat([parte_bruta, parte_sem_i], ignore_index=True)
    resultado = resultado.drop_duplicates(subset=["codigo"])
    return resultado


def load_realizado_documentos(path: str) -> pd.DataFrame:
    """Carrega o Base Analítico SAP na granularidade de lançamento, com os
    campos de rastreabilidade documental do Nível 6 (docs/00, seção 7):
    documento, NF, fornecedor, data, texto do lançamento.

    Não alimenta fact_realizado (que agrega em Pacote/Conta/Mês) — só a
    tela de rastreabilidade (Nível 6), que precisa do grão de lançamento.

    # GAP: "Usuário" do lançamento SAP (campo pedido na spec) não existe no
    # export atual. O campo mais próximo é PONTA_FIRME (e-mail do
    # responsável/ponta firme da GG) — rotulado como tal, não como
    # "usuário", pra não sugerir que é quem lançou no SAP.
    """
    df = pd.read_excel(path, sheet_name=0)
    df = df[df["Exercício Período Fiscal"].notna()].copy()
    periodo = df["Exercício Período Fiscal"].astype(int)
    df["ano"] = periodo // 100
    df["mes"] = periodo % 100

    gg_id, _ = _parte_hierarquia_generico(df["HIERARQUIA-NÓS - GER GERAL"])

    return pd.DataFrame({
        "ano": df["ano"],
        "mes": df["mes"],
        "pacote_id": df["COD_PCT_SAP"],
        "conta_razao_id": df["Conta do Razão"],
        "conta_razao_nome": df["Texto descritivo das contas do Razão"],
        "centro_custo_id": df["Cód. Centro de custo"],
        "centro_custo_nome": df["Centro de custo"],
        "numero_documento": df["Nº documento"],
        "numero_nota_fiscal": df["Nº da nota fiscal"],
        "fornecedor": df["Nome 1 da organização"],
        "data_documento": pd.to_datetime(df["Data do documento"], errors="coerce"),
        "texto_item": df["Texto do item"],
        "responsavel": df["PONTA_FIRME"],
        "gg_id": gg_id,
        "valor_realizado": pd.to_numeric(df["Montante em moeda da empresa"], errors="coerce").fillna(0.0),
    })


_COLUNAS_MES_CJI4 = [f"Valor/moeda ACC{str(m).zfill(3)}" for m in range(1, 13)]


def load_cji4_capex_obras(path: str) -> pd.DataFrame:
    """Carrega "CJI4.xlsx" — export financeiro de CAPEX de Projetos e
    Obras (trazido em 2026-08-11), lado Orçado/Planejado (o Realizado vem
    depois, via CJI3, ainda não recebido — confirmado com o usuário).

    Formato wide: 1 linha por (Definição do projeto, Elemento PEP, Classe
    de custo, documento), com 12 colunas de valor mensal
    ("Valor/moeda ACC001".."ACC012" = períodos contábeis 1-12, mesmo
    padrão SAP de `Exercício Período Fiscal` já usado em `load_realizado`)
    — vira longo aqui (1 linha por mês), igual `load_base_zero` já faz
    pro Orçamento tradicional.

    # GAP: as colunas ACCxxx são períodos contábeis, não confirmado 1:1
    # com mês calendário (assumido aqui igual ao padrão SAP já visto no
    # resto do projeto — período 1 = janeiro etc.) — confirmar se algum
    # número não bater na reconciliação.

    O export tem linhas de subtotal por "Objeto" sem `Definição do
    projeto`/`Elemento PEP`/`Exercício` preenchidos (confirmado: 532
    linhas assim) — descartadas aqui, não são lançamento real.

    Linhas com valor espelhado positivo/negativo pro mesmo projeto+conta
    (ex.: uma linha +R$387mil em todos os meses e outra -R$387mil idêntica)
    são reversão/revisão de orçamento do próprio SAP — não tratadas aqui,
    a soma natural já zera o par quando agregado, sem precisar filtrar.
    """
    df = pd.read_excel(path, sheet_name="Data")
    df = df[df["Definição do projeto"].notna()].copy()

    colunas_base = {
        "Definição do projeto": "e_pep_projeto",
        "Elemento PEP": "elemento_pep",
        "Classe de custo": "classe_custo",
        "Exercício": "ano",
        "Criado por": "criado_por",
        "Data do documento": "data_documento",
    }

    partes = []
    for mes, coluna_valor in enumerate(_COLUNAS_MES_CJI4, start=1):
        parte = df[list(colunas_base)].rename(columns=colunas_base).copy()
        parte["mes"] = mes
        parte["valor_orcado"] = pd.to_numeric(df[coluna_valor], errors="coerce").fillna(0.0)
        partes.append(parte)

    resultado = pd.concat(partes, ignore_index=True)
    resultado["ano"] = pd.to_numeric(resultado["ano"], errors="coerce").astype("Int64")
    resultado["classe_custo"] = (
        pd.to_numeric(resultado["classe_custo"], errors="coerce").astype("Int64").astype(str)
    )
    resultado["data_documento"] = pd.to_datetime(resultado["data_documento"], errors="coerce")
    return resultado


def load_catalogo_capex_obras(path: str) -> pd.DataFrame:
    """Carrega "Catalago CAPEX Obras.xlsx" — cadastro de projetos/obras
    (trazido em 2026-08-11): nome do empreendimento, Gerência,
    classificação, coordenadas. Chave `e_pep_projeto` (mesmo código de
    `Definição do projeto` no financeiro `load_cji4_capex_obras` — bate
    100% nos dados reais, confirmado em 2026-08-11).

    1 projeto (`E_PEP`) pode ter várias linhas aqui (1 por "Título"/etapa
    do cronograma) — não agrega, devolve a granularidade original; quem
    usa decide se quer 1 linha por projeto (ex.: primeira ocorrência) ou
    manter o detalhe por etapa.

    `classificacao_atualizada` (coluna "Classificação atualizada" —
    valores A+1..A+8/"Não renovação", ciclo de renovação de portfólio)
    passou a ser carregada em 2026-08-27: é 100% consistente por projeto
    (0 de 95 `E_PEP` com mais de 1 valor, verificado no dado real) e
    nunca vazia — vira a fonte de `fact_pce_realizado.classificacao_atualizada`
    (`build_star_schema._derivar_pce_realizado`), eliminando a dependência
    de "PCE Base Luiz.xlsx" pra esse campo (confirmado pelo usuário que
    vem do Catálogo, e os valores batem 1:1 nos dados reais).
    """
    df = pd.read_excel(path, sheet_name="Auxiliar")
    return pd.DataFrame({
        "e_pep_projeto": df["E_PEP"],
        "id_projeto": df["ID Projeto"],
        "nome_empreendimento": df["E_NomedoEmpreendimento"],
        "gerencia_obras": df["Gerência"],
        "titulo_etapa": df["Título"],
        "descricao_etapa": df["Descrição"],
        "classificacao": df["Classificação"],
        "grupo": df["Grupo"],
        "origem": df["Origem"],
        "nome_simplificado": df["Nome Simplificado"],
        "classificacao_atualizada": df["Classificação atualizada"],
    })


# Reclassificação Descrição -> Grupo (PCE Base Luiz.xlsx, trazida em
# 2026-08-19). A coluna "Grupo" bruta da fonte é inconsistente entre
# versões — confirmado em FC06+06, onde SERVIÇOS/MATERIAIS/ENGENHARIA/
# EQUIPAMENTOS/INDIRETOS MRS/SMA/FUNDIÁRIO_RI_REGULATÓRIO aparecem como
# Grupo próprio em vez de rolar pra "OBRA/PRÉ-OBRA" como em toda outra
# versão (verificado direto na planilha bruta, não é bug de leitura).
# O usuário passou o de-para Versão x Grupo x Descrição correto (texto +
# imagem, 2026-08-19: "o que eu te passei agora é a classificação
# correta") e pediu que a regra seja aplicada internamente sempre que a
# base for reimputada, não só uma correção pontual — por isso o `grupo`
# de saída é sempre DERIVADO da `descricao` aqui, ignorando o valor bruto
# de "Grupo" da fonte (que só sobrevive como fallback pra Descrição não
# catalogada abaixo, caso apareça uma nova no futuro).
#
# Repara que isso é diferente do agrupamento "Obra e Pré-Obra"/"Rateios"
# de `pce_especialista._GRUPO_OBRA_PRE_OBRA`/`_GRUPO_RATEIOS` — aquele é
# um recorte de análise que propositalmente inclui DESAFIO e RATEIOS
# dentro de "Obra e Pré-Obra" também; aqui é a classificação de Grupo
# "oficial" (1 Descrição -> exatamente 1 Grupo), onde DESAFIO e RATEIOS
# têm bucket próprio.
_GRUPO_CANONICO_POR_DESCRICAO = {
    "SERVIÇOS": "OBRA/PRÉ-OBRA",
    "MATERIAIS": "OBRA/PRÉ-OBRA",
    "ENGENHARIA": "OBRA/PRÉ-OBRA",
    "EQUIPAMENTOS": "OBRA/PRÉ-OBRA",
    "INDIRETOS MRS": "OBRA/PRÉ-OBRA",
    "SMA": "OBRA/PRÉ-OBRA",
    "FUNDIÁRIO_RI_REGULATÓRIO": "OBRA/PRÉ-OBRA",
    "SAVING": "OBRA/PRÉ-OBRA",
    "CUSTOS DO PROPRIETÁRIO": "CUSTOS DO PROPRIETÁRIO",
    "OWNER'S ENGINEERING": "OWNER'S ENGINEERING",
    "VIAGEM": "VIAGEM",
    "ESCALATION": "ESCALATION",
    "CONTINGÊNCIA": "CONTINGÊNCIA",
    "CAPITALIZAÇÃO": "CAPITALIZAÇÃO",
    "RATEIOS": "RATEIOS",
    "DESAFIO": "DESAFIO",
    "JURÍDICO": "RATEIOS",
}


def _reclassificar_grupo(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza `descricao` (strip/upper, resolve duplicidade de caixa
    tipo "Contingência" x "CONTINGÊNCIA") e recalcula `grupo` a partir de
    `_GRUPO_CANONICO_POR_DESCRICAO`. Descrição não catalogada mantém o
    `grupo` original da fonte como fallback, em vez de virar nulo."""
    tem_descricao = df["descricao"].notna()
    df.loc[tem_descricao, "descricao"] = (
        df.loc[tem_descricao, "descricao"].astype(str).str.strip().str.upper()
    )
    grupo_reclassificado = df["descricao"].map(_GRUPO_CANONICO_POR_DESCRICAO)
    df["grupo"] = grupo_reclassificado.fillna(df["grupo"])
    return df


def load_pce_consolidado(path: str) -> pd.DataFrame:
    """Carrega a aba "consolidado" de "PCE Base Luiz.xlsx" (trazida em
    2026-08-19) — base mestra de planejamento de CAPEX Obras: 2022-2038,
    13 versões (`Orçamento 2026`/`Orçamento 2026 Original` = formal,
    `PN24`/`PN25`/`PN26_2ºInput`/`FEL3` = rodadas de plano, `FC01+11`
    .."FC06+06" = forecast rolante) — mais rica que `load_cji4_capex_obras`
    (só 1 versão) e já vem com Grupo/Classificação/Renegociação juntos, sem
    precisar cruzar com `load_catalogo_capex_obras` à parte.

    Linhas com valor espelhado positivo/negativo pro mesmo (projeto,
    Elemento PEP, Exercício, Versão) são histórico de revisão do próprio
    PCE (cada edição gera um par reversão+novo valor) — mesmo padrão já
    visto em `load_cji4_capex_obras`, a soma natural zera o par quando
    agregado, não precisa filtrar.

    Grão **mensal** (2026-08-19, a pedido do usuário — Orçado/Forecast
    Mensal x Acumulado na Label do Especialista): explode as 12 colunas
    "Valor/moeda ACC001".."ACC012" (mesmo padrão de período contábil já
    usado em `load_cji4_capex_obras` — período 1 = janeiro etc.), 1 linha
    por mês em vez de só o "Valor total" agregado. `valor_total` anual
    vira `SUM(valor)` agrupando por mês em quem consumir isso — não é
    mais coluna própria aqui, pra não duplicar a mesma informação em 2
    granularidades diferentes na mesma tabela.

    Célula `"-"` (texto) representando zero em algumas linhas — convertida
    pra 0.0 aqui (`errors="coerce"` vira NaN, tratado como zero, não
    descartado).
    """
    df = pd.read_excel(path, sheet_name="consolidado", header=1)
    df.columns = [str(c).strip() if isinstance(c, str) else c for c in df.columns]
    df = df[df["Definição do projeto"].notna()].copy()

    colunas_base = {
        "Definição do projeto": "e_pep_projeto",
        "Elemento PEP": "elemento_pep",
        "Empreendimento": "nome_empreendimento",
        "Gerência": "gerencia_obras",
        "Exercício": "ano",
        "Descrição": "descricao",
        "Versão": "versao",
        "Grupo": "grupo",
        "Classificação inicial": "classificacao_inicial",
        "Classificação atualizada": "classificacao_atualizada",
        "É Renegociação?": "renegociacao",
    }

    partes = []
    for mes, coluna_valor in enumerate(_COLUNAS_MES_CJI4, start=1):
        parte = df[list(colunas_base)].rename(columns=colunas_base).copy()
        parte["mes"] = mes
        parte["valor"] = pd.to_numeric(df[coluna_valor], errors="coerce").fillna(0.0)
        partes.append(parte)

    resultado = pd.concat(partes, ignore_index=True)
    resultado["ano"] = pd.to_numeric(resultado["ano"], errors="coerce").astype("Int64")
    resultado = _reclassificar_grupo(resultado)
    return resultado


def carregar_catalogo_objeto_classificacao() -> pd.DataFrame:
    """Tabela De/Para `Objeto` (código SAP) -> `Classificação` fina
    (SERVIÇOS/MATERIAIS/ENGENHARIA...), congelada em
    `config/catalogo_objeto_classificacao.csv`.

    Substitui a dependência de "PCE Base Luiz.xlsx" (removida em
    2026-08-27) — achado: `Objeto` determina a Classificação de forma
    100% consistente (0 de 1.188 objetos únicos com mais de 1 valor,
    verificado no dado real de 2026-08-27), não é julgamento por
    lançamento. É por isso que dá pra tratar como catálogo estável em vez
    de precisar reenviar um arquivo curado a cada rodada — ver
    `build_star_schema._derivar_pce_realizado` e
    `docs/04-licoes-aprendidas.md`, item 20.

    Não é arquivo de upload (não muda por rodada de dado) — arquivo do
    próprio repositório, path fixo relativo à raiz do projeto. Se um
    `Objeto` novo aparecer numa rodada futura sem estar aqui, fica sem
    Classificação (fica "NÃO CLASSIFICADO", ver `_derivar_pce_realizado`)
    até alguém atualizar este CSV — não trava o reprocessamento.
    """
    caminho = RAIZ_PROJETO / "config" / "catalogo_objeto_classificacao.csv"
    df = pd.read_csv(caminho, dtype={"objeto": str})
    return df


def load_transferencia_combustivel_terceiros(path: str) -> pd.DataFrame:
    """Carrega a aba "Resumo" de "Transferência Combustível Terceiras - FA,
    MG e RJ vf 30.04 1.xlsx" — trazida pelo usuário em 2026-08-17.

    O PCM usa essa planilha pra redistribuir, por Centro de Custo real, um
    valor de Combustível Terceiros que no SAP (Consulta de Contas) chega
    inteiro numa linha só com `GERENCIA = "#GERENCIA INEXISTENTE"` (CC
    `CGG050`, o CC da própria GG — mesmo fenômeno "estrutural" já
    documentado pro CGG050 em 2026-08-12). Confirmado nos dados reais:
    o total desta aba (R$ 1.838.883,43) bate quase exato (diff R$ 0,43,
    arredondamento) com o valor da linha `#GERENCIA INEXISTENTE` de
    `PM03011` em Jan/2026.

    Devolve 1 linha por Centro de Custo de destino, com o valor a
    subtrair do bucket CGG050 e redistribuir. Só a linha de SP (`CGE041`)
    tem `gerencia_id` resolvido de forma segura hoje (bate com o
    `centro_custo_id` que a própria Consulta de Contas já usa pra SP em
    outras linhas — ver `_aplicar_correcao_combustivel_terceiros` em
    build_star_schema.py). As demais linhas (VP genérico `CGE053`,
    coordenações `CCR*`, F.Aço/MG/RJ) não têm `gerencia_id` confirmado
    ainda — fica pra quando a pesquisa no Copilot (ver
    docs/05-briefing-copilot-gerencia-vp-e-escopo-gg.md) voltar.
    """
    df = pd.read_excel(path, sheet_name="Resumo", header=1)
    df = df.dropna(subset=["CC"]).copy()
    return pd.DataFrame({
        "escopo": df["Escopo"],
        "conta_orcamento_id": df["Conta"],
        "centro_custo_id": df["CC"],
        "centro_custo_nome": df["DESCRIÇÃO CENTRO DE CUSTO"],
        "valor": df["Valor"],
    })


def load_cji3_capex_obras_realizado(path: str) -> pd.DataFrame:
    """Carrega o export SAP CJI3 (trazido em 2026-08-11) — Realizado de
    CAPEX de Projetos e Obras, no grão de lançamento (1 linha por
    documento/item), pra cruzar com o Orçado do CJI4
    (`load_cji4_capex_obras`) por `e_pep_projeto`/`elemento_pep`.

    `estornado = 'X'` marca lançamento revertido/cancelado no próprio SAP
    — excluído aqui (convenção padrão de relatório CJI3: contar um
    lançamento estornado infla o Realizado com um valor que não é mais
    válido). Confirmado nos dados reais em 2026-08-11: 218 documentos com
    a flag, R$39,3 MM — só 1 tem uma linha de reversão explícita
    apontando de volta pra ele via "Nº doc.de referência" (esse campo é
    usado majoritariamente pra outra coisa no export, não é um índice
    confiável de par de estorno) — por isso a exclusão é só pela própria
    flag, não por tentar casar pares.

    Usa `Data de lançamento` (intervalo limpo, 2026-01 a 2026-07 nos
    dados atuais) pra ano/mês, não `Data do documento` (que traz datas de
    2025, aparentemente data de criação do documento/projeto, não da
    competência do lançamento).

    A última linha do export é um total geral (confirmado: `Definição do
    projeto` vazia, valor R$477,8 MM sozinho, sem nenhum outro campo
    preenchido) — descartada junto com qualquer outra linha assim.
    """
    df = pd.read_excel(path, sheet_name=0)
    df = df[df["estornado"].isna() & df["Definição do projeto"].notna()].copy()

    data_lancamento = pd.to_datetime(df["Data de lançamento"], errors="coerce")
    return pd.DataFrame({
        "ano": data_lancamento.dt.year,
        "mes": data_lancamento.dt.month,
        "e_pep_projeto": df["Definição do projeto"],
        "elemento_pep": df["Elemento PEP"],
        # `objeto`/`denominacao_objeto` — adicionados em 2026-08-27, fonte
        # de `fact_pce_realizado.descricao` via
        # config/catalogo_objeto_classificacao.csv (ver
        # build_star_schema._derivar_pce_realizado): achado 2026-08-27 de
        # que `Objeto` determina a Classificação fina (SERVIÇOS/MATERIAIS/
        # ENGENHARIA...) de forma 100% consistente — não é julgamento por
        # lançamento, é uma tabela De/Para pequena e estável. Já vinha no
        # export CJI3 sem ser extraído.
        "objeto": df["Objeto"],
        "denominacao_objeto": df["Denominação objeto"],
        "classe_custo": pd.to_numeric(df["Classe de custo"], errors="coerce").astype("Int64").astype(str),
        "centro_custo_parceiro": df["Cent.custo  parceiro"],
        "numero_documento": df["Nº documento"],
        "data_documento": pd.to_datetime(df["Data do documento"], errors="coerce"),
        "data_lancamento": data_lancamento,
        "texto_pedido": df["Texto do pedido"],
        "valor_realizado": pd.to_numeric(df["Valor/moeda ACC"], errors="coerce").fillna(0.0),
    })
