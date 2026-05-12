"""
src/ai/prompt_builder.py
------------------------
Constrói prompts automaticamente para enviar ao LLM via OpenRouter.

Utiliza o glossário existente (glossario.json) e a tabela de prefixos
definida no prompt.md como contexto base para geração de taxonomia.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.parquet.schema_extractor import TableSchema


# ---------------------------------------------------------------
# Prompt base de sistema (incorpora regras do prompt.md)
# ---------------------------------------------------------------

SYSTEM_PROMPT = """Você é um especialista em Data Governance e Engenharia de Dados com profundo conhecimento em:
- BigQuery, Dataform, arquitetura Medallion
- Data Catalog e metadata management
- Identificação de PII e classificação de sensibilidade
- Taxonomia e domínios de negócio

Seu objetivo é analisar schemas de tabelas e retornar metadata enriquecida.

## PADRÃO DE PREFIXOS (use para inferir semântica de colunas sem descrição explícita)

| Prefixo | Significado      | Tipo BQ             |
|---------|-----------------|---------------------|
| CD      | Código / ID      | STRING / INT        |
| ID      | Identificador    | UUID / STRING / INT |
| NO      | Nome            | STRING              |
| DE      | Descrição        | STRING              |
| DT      | Data            | DATETIME / DATE     |
| VL      | Valor Monetário  | NUMERIC / DECIMAL   |
| QT      | Quantidade       | INTEGER             |
| TP      | Tipo / Categoria | STRING              |
| PC      | Porcentagem      | NUMERIC / FLOAT     |
| IS      | Booleano         | BOOLEAN             |

## FORMATO DE SAÍDA OBRIGATÓRIO
Retorne APENAS JSON válido, sem markdown, sem explicações extras:

{
  "domain": "<domínio de negócio>",
  "table_description": "<descrição clara e técnica da tabela>",
  "tags": ["<tag1>", "<tag2>"],
  "sensitivity": "<low|medium|high>",
  "columns": [
    {
      "name": "<nome>",
      "description": "<descrição>",
      "pii": <true|false>,
      "sensitivity": "<low|medium|high>"
    }
  ]
}"""


def build_enrichment_prompt(
    schema: TableSchema,
    glossary: dict[str, str] | None = None,
) -> list[dict]:
    """
    Constrói a lista de mensagens para a API OpenRouter.

    Args:
        schema: Schema da tabela extraído do Parquet.
        glossary: Glossário de descrições de colunas conhecidas.

    Returns:
        Lista de dicts no formato OpenAI messages.
    """
    glossary = glossary or {}

    # Monta lista de colunas com descrições já conhecidas
    col_lines: list[str] = []
    for col in schema.columns:
        known_desc = glossary.get(col.name.upper(), "")
        hint = f" // Descrição conhecida: {known_desc}" if known_desc else ""
        col_lines.append(f"  - {col.name} ({col.type}, {'nullable' if col.nullable else 'required'}){hint}")

    cols_str = "\n".join(col_lines)

    user_content = f"""Analise a seguinte tabela e retorne a metadata enriquecida conforme o formato solicitado.

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


def build_docs_prompt(schema: TableSchema, ai_metadata: dict) -> list[dict]:
    """Constrói prompt para geração de documentação Markdown."""
    system = "Você é um technical writer especialista em documentação de dados. Escreva em português do Brasil."

    user = f"""Gere uma documentação técnica no formato Markdown para a tabela abaixo.

Tabela: {schema.table_name}
Domínio: {ai_metadata.get('domain', 'N/A')}
Descrição: {ai_metadata.get('table_description', 'N/A')}

Colunas com metadata:
{json.dumps(ai_metadata.get('columns', []), indent=2, ensure_ascii=False)}

A documentação deve incluir:
1. Título e descrição
2. Tabela de colunas (Nome | Tipo | PII | Descrição)
3. Tags e domínio
4. Observações de governança

Retorne apenas o Markdown, sem blocos de código ao redor."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
