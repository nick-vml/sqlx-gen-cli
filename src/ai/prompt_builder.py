"""
src/ai/prompt_builder.py
------------------------
Constrói prompts automaticamente para enviar ao LLM via OpenRouter.

Utiliza o glossário existente (glossario.json), a tabela de prefixos
e o catálogo de funções utils.js do Dataform como contexto base.
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.extractor.schema_extractor import TableSchema


def _transpose_sample(sample_data: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Transpõe [{col: val, ...}, ...] em {col: [val1, val2, ...], ...}."""
    result: dict[str, list[Any]] = {}
    for row in sample_data:
        for key, value in row.items():
            result.setdefault(key, []).append(value)
    return result


_CPF_RE = re.compile(r'^(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})$')
_CNPJ_RE = re.compile(r'^(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})$')
_EMAIL_RE = re.compile(r'\S+@\S+\.\S+')
_MONEY_RE = re.compile(r'R\$|(?<!\d)\d{1,3}(\.\d{3})*,\d{2}(?!\d)')
_DATE_RE = re.compile(r'\b(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})\b')
_BOOL_VALUES = frozenset({"sim", "não", "nao", "s", "n", "true", "false", "ativo", "inativo", "0", "1"})


def _detect_hints(col_name: str, sample_values: list[Any]) -> str:
    """Detecta padrões na amostra e retorna um hint para o prompt da IA."""
    non_null = [str(v) for v in sample_values if v is not None]
    if not non_null:
        return ""

    # CPF — prioridade 1
    if any(_CPF_RE.match(v.strip()) for v in non_null):
        return "[HINT: padrão CPF → PII=true, suggested_function: removeSpecialChars]"

    # CNPJ — prioridade 2
    if any(_CNPJ_RE.match(v.strip()) for v in non_null):
        return "[HINT: padrão CNPJ → PII=true, suggested_function: removeSpecialChars]"

    # Email
    if any(_EMAIL_RE.search(v) for v in non_null):
        return "[HINT: e-mail detectado → PII=true, suggested_function: cleanEmail]"

    # JSON estruturado
    for v in non_null:
        try:
            parsed = json.loads(v)
            if isinstance(parsed, (dict, list)):
                return "[HINT: STRING contém JSON estruturado → descrever campos internos se possível, suggested_function: none]"
        except (ValueError, TypeError):
            pass

    # Booleano texto — todos os não-nulos devem ser valores booleanos
    if all(v.strip().lower() in _BOOL_VALUES for v in non_null):
        return "[HINT: booleano → suggested_function: castBoolean]"

    # Monetário BRL
    if any(_MONEY_RE.search(v) for v in non_null):
        return "[HINT: valor monetário BRL → suggested_function: castMoneyBRL]"

    # Data em texto
    if any(_DATE_RE.search(v) for v in non_null):
        return "[HINT: data em texto → suggested_function: safeCastDate]"

    return ""


# ---------------------------------------------------------------
# Catálogo de funções utils.js do Dataform
# ---------------------------------------------------------------

UTILS_FUNCTIONS_CATALOG = """
## FUNÇÕES DISPONÍVEIS DO utils.js (Dataform)

Você DEVE sugerir a função mais adequada para cada coluna no campo "suggested_function".
Essas funções existem no Dataform e devem ser usadas no SELECT da camada Silver.

| Função                | Tipo de Dado            | Uso / Sintaxe no SQLX                                         |
|-----------------------|-------------------------|---------------------------------------------------------------|
| cleanString           | Texto / String geral    | ${utils.cleanString("coluna")}                                |
| removeSpecialChars    | Texto alfanumérico      | ${utils.removeSpecialChars("coluna")}                         |
| removeAccents         | Texto com acentos       | ${utils.removeAccents("coluna")}                              |
| normalizePercent      | Porcentagem / Decimal   | ${utils.normalizePercent("coluna")}                           |
| cleanEmail            | E-mail                  | ${utils.cleanEmail("coluna")}                                 |
| castBoolean           | Booleano (Sim/Não/etc)  | ${utils.castBoolean("coluna")}                                |
| castMoneyBRL          | Monetário R$ (BRL)      | ${utils.castMoneyBRL("coluna")}                               |
| extractInteger        | Número inteiro em texto | ${utils.extractInteger("coluna")}                             |
| safeCastDate          | Data (string → DATE)    | ${utils.safeCastDate("coluna")}                               |
| normalizeExcelDate    | Data de planilha Excel  | ${utils.normalizeExcelDate("coluna")}                         |
| normalizeHonorarios   | Financeiro ou Texto     | ${utils.normalizeHonorarios("coluna")}                        |
| safeCastDatetimeBR    | Datetime (fuso SP)      | ${utils.safeCastDatetimeBR("coluna")}                         |
| get_value_letter      | Letra → Valor primo     | ${utils.get_value_letter("coluna")}                           |

### REGRAS para "suggested_function":
- **Strings gerais** (nomes, descrições, observações) → "cleanString"
- **E-mails** → "cleanEmail"
- **CNPJ, CPF** (códigos alfanuméricos) → "removeSpecialChars" (remove pontos/traços)
- **Colunas booleanas** (Sim/Não, Ativo/Inativo, True/False) → "castBoolean"
- **Valores monetários** (R$, formato brasileiro 1.000,00) → "castMoneyBRL"
- **Datas em formato texto** → "safeCastDate"
- **Datetimes com fuso horário** → "safeCastDatetimeBR"
- **Percentuais** → "normalizePercent"
- **Campos com números inteiros misturados com texto** → "extractInteger"
- **Se nenhuma função se aplica** (ex: RECORD, BYTES, campos já tipados) → "none"
- **Analise a AMOSTRA para decidir** — se a amostra mostra "Sim"/"Não", use castBoolean mesmo que o tipo original seja STRING
"""


# ---------------------------------------------------------------
# Prompt base de sistema (incorpora regras do prompt.md)
# ---------------------------------------------------------------

SYSTEM_PROMPT = f"""Você é um especialista em Data Governance e Engenharia de Dados com profundo conhecimento em:
- BigQuery, Dataform, arquitetura Medallion
- Data Catalog e metadata management
- Identificação de PII e classificação de sensibilidade
- Taxonomia e domínios de negócio

Seu objetivo é analisar schemas de tabelas e retornar metadata enriquecida.

## DADOS DE AMOSTRA
Você receberá os valores de amostra de cada coluna listados diretamente abaixo do nome da coluna.
Use-os para:
- Identificar o tipo real dos dados (ex: STRING que contém JSON, DATA ou UUID)
- Inferir o significado semântico (ex: coluna 'STATUS' com valores 'ATIVO'/'INATIVO' → prefixo TP)
- Detectar sensibilidade e PII (CPFs, e-mails, telefones nos valores)

## HINTS DE PRÉ-ANÁLISE
Algumas colunas virão com [HINT: ...] baseados em análise automática de padrões.
Trate cada HINT como forte evidência — siga-o a menos que os valores da amostra
contradigam claramente. Nunca ignore um HINT sem justificativa nos dados.

## PADRÃO DE PREFIXOS — REGRAS DE TAXONOMIA

Você DEVE sugerir o prefixo mais adequado para CADA coluna. Use a tabela abaixo:

| Prefixo | Significado      | Quando usar                                           |
|---------|-----------------|-------------------------------------------------------|
| CD      | Código / ID      | Códigos internos, chaves de negócio, IDs numéricos    |
| ID      | Identificador    | UUIDs, identificadores únicos de sistema              |
| NO      | Nome            | Nomes de pessoas, empresas, sistemas                  |
| DE      | Descrição        | Textos descritivos, observações, campos livres        |
| DT      | Data            | Datas, timestamps, datetimes                          |
| VL      | Valor Monetário  | Valores em R$, custos, preços                         |
| QT      | Quantidade       | Contadores, quantidades numéricas                     |
| TP      | Tipo / Categoria | Enumerações, categorias, tipos                        |
| PC      | Porcentagem      | Percentuais, taxas                                    |
| IS      | Booleano         | Flags, indicadores, sim/não, ativo/inativo            |

**REGRAS IMPORTANTES para suggested_prefix:**
- Analise a AMOSTRA DE DADOS para decidir o prefixo correto
- CNPJ, CPF → use "CD" (é um código, não uma descrição)
- Campos como "PROCESSO_ATIVO", "FLAG_*" → use "IS" (é booleano)
- Campos como "IDREGISTRO" → use "ID" (é identificador)
- Campos como "STATUS", "FASE_*" → use "TP" (é tipo/categoria)
- Se a coluna já tem prefixo válido (CD_, ID_, etc.), mantenha-o
- Para colunas SEM prefixo padrão: use o nome completo como âncora semântica principal.
  Exemplos: "data_nascimento" → DT + safeCastDate; "numero_documento_fiscal" → CD + removeSpecialChars
- Palavras-chave em português que indicam prefixo:
  data/dt → DT | valor/vl → VL | nome/no → NO | quantidade/qt → QT
  percentual/pc → PC | tipo/tp → TP | indicador/is/flag → IS | codigo/cd → CD
- Palavras-chave em inglês:
  date → DT | value/amount → VL | name → NO | count → QT
  percent → PC | type/status → TP | flag/is_/has_ → IS | id/code → CD

## COLUNAS COM JSON ESTRUTURADO
Se uma coluna STRING contiver JSON na amostra (indicado por HINT ou visível nos valores):
- Descreva o propósito do campo e mencione que armazena um objeto estruturado
- Liste os campos internos mais relevantes identificados na amostra
- Use suggested_function: "none" (JSON não passa por limpeza simples)
- Avalie sensibilidade e PII com base no conteúdo interno do JSON, não só no nome da coluna

{UTILS_FUNCTIONS_CATALOG}

## FORMATO DE SAÍDA OBRIGATÓRIO
Retorne APENAS JSON válido, sem markdown, sem explicações extras:

{{
  "domain": "<domínio de negócio>",
  "table_description": "<descrição clara e técnica da tabela>",
  "tags": ["<tag1>", "<tag2>"],
  "sensitivity": "<low|medium|high>",
  "columns": [
    {{
      "name": "<nome_original_da_coluna>",
      "description": "<descrição>",
      "suggested_prefix": "<CD|ID|NO|DE|DT|VL|QT|TP|PC|IS>",
      "suggested_function": "<cleanString|removeSpecialChars|removeAccents|normalizePercent|cleanEmail|castBoolean|castMoneyBRL|extractInteger|safeCastDate|normalizeExcelDate|safeCastDatetimeBR|none>",
      "pii": <true|false>,
      "sensitivity": "<low|medium|high>"
    }}
  ]
}}"""


def build_enrichment_prompt(
    schema: TableSchema,
    glossary: dict[str, str] | None = None,
) -> list[dict]:
    """
    Constrói a lista de mensagens para a API OpenRouter.

    Args:
        schema: Schema da tabela extraído do Parquet/CSV/JSON.
        glossary: Glossário de descrições de colunas conhecidas.

    Returns:
        Lista de dicts no formato OpenAI messages.
    """
    glossary = glossary or {}
    transposed = _transpose_sample(schema.sample_data)

    col_lines: list[str] = []
    for col in schema.columns:
        known_desc = glossary.get(col.name.upper(), "")
        desc_hint = f"  // Descrição conhecida: {known_desc}" if known_desc else ""

        samples = transposed.get(col.name, [])
        sample_repr = json.dumps(samples, ensure_ascii=False, default=str) if samples else "N/A"
        pattern_hint = _detect_hints(col.name, samples)

        line = (
            f"  - {col.name} ({col.type}, {'nullable' if col.nullable else 'required'}){desc_hint}\n"
            f"    Amostras: {sample_repr}"
        )
        if pattern_hint:
            line += f"\n    {pattern_hint}"

        col_lines.append(line)

    cols_str = "\n".join(col_lines)

    user_content = f"""Analise a seguinte tabela e retorne a metadata enriquecida conforme o formato solicitado.
Para cada coluna, os valores de amostra estão listados diretamente abaixo do nome da coluna.
Use-os para validar tipos, identificar padrões e inferir o significado de campos obscuros.
Siga os HINTs de pré-análise como forte evidência.

IMPORTANTE: Para cada coluna, sugira:
1. O prefixo de taxonomia mais adequado no campo "suggested_prefix"
2. A função utils.js mais adequada no campo "suggested_function"

Tabela: {schema.table_name}
Banco/Origem: {schema.db or 'desconhecido'}
Total de linhas: {schema.row_count:,}

Colunas:
{cols_str}

Retorne APENAS o JSON de metadata, sem nenhum texto adicional."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
