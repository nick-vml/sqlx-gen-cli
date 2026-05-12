"""
src/generators/silver_generator.py
------------------------------------
Gera arquivos .sqlx da camada Silver com:
- CAST explícito por tipo
- cleanString/padronização
- Colunas de auditoria (DT_SOURCE_MODIFIED, DT_UPDATED)
- Deduplicação via _FILE_NAME mais recente
- Glossário de colunas integrado
"""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, BaseLoader

from src.parquet.schema_extractor import TableSchema, ColumnSchema
from src.utils.config_loader import GeneratorConfig
from src.utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------
# Template Jinja2 para Silver SQLX
# ---------------------------------------------------------------

SILVER_TEMPLATE = """\
config {
  //--- 1. Tipo e Identificação ---
  type: "{{ config.type }}",
  schema: "{{ config.schema_name }}",
  name: "{{ db }}_{{ name }}",

  // --- 2. Controle de execução ---
  tags: [{% for t in tags %}"{{ t }}"{% if not loop.last %}, {% endif %}{% endfor %}],

  // --- 3. Documentação (Data Catalog) ---
  description: "{{ desc }}",
  columns: {
{{ columns_block }}
{% for audit in config.audit_columns %}    {{ audit.name }}: "{{ audit.description }}",
{% endfor %}  },
  bigquery: {
    partitionBy: "{{ config.partition_by }}",
    clusterBy: [{% for c in config.cluster_by %}"{{ c }}"{% if not loop.last %}, {% endif %}{% endfor %}],
    labels: { {% for k, v in config.labels.items() %}"{{ k }}": "{{ v }}"{% if not loop.last %}, {% endif %}{% endfor %} }
  }
}

pre_operations {
  ${helpers.checkUpdate(ref("{{ config.schema_name | replace('silver','bronze') }}", "{{ db }}_{{ name }}"), self(), '{{ config.update_frequency }}')}
}

WITH {{ db }}_{{ name }} AS (
    SELECT
        *,
        _FILE_NAME
    FROM ${ref("{{ config.schema_name | replace('silver','bronze') }}", "{{ db }}_{{ name }}")}
    WHERE
        date > DATE_SUB(CURRENT_DATE(), INTERVAL {{ config.lookback_days }} DAY)
        AND _FILE_NAME = (
            SELECT MAX(_FILE_NAME)
            FROM ${ref("{{ config.schema_name | replace('silver','bronze') }}", "{{ db }}_{{ name }}")}
            WHERE date > DATE_SUB(CURRENT_DATE(), INTERVAL {{ config.lookback_days }} DAY)
        )
)

SELECT
{{ select_block }},
  PARSE_DATETIME("%Y_%m_%d_%H_%M", REGEXP_EXTRACT(_FILE_NAME, r"\\d{4}_\\d{2}_\\d{2}_\\d{2}_\\d{2}")) AS DT_UPDATED
FROM {{ db }}_{{ name }}
"""


# ---------------------------------------------------------------
# Mapeamento de tipo → expressão de CAST no SELECT
# ---------------------------------------------------------------

_CAST_MAP: dict[str, str] = {
    "STRING": 'TRIM(CAST({col} AS STRING))',
    "INTEGER": 'SAFE_CAST({col} AS INT64)',
    "FLOAT": 'SAFE_CAST({col} AS FLOAT64)',
    "NUMERIC": 'SAFE_CAST({col} AS NUMERIC)',
    "BIGNUMERIC": 'SAFE_CAST({col} AS BIGNUMERIC)',
    "BOOLEAN": 'SAFE_CAST({col} AS BOOL)',
    "DATE": 'SAFE_CAST({col} AS DATE)',
    "TIMESTAMP": 'SAFE_CAST({col} AS TIMESTAMP)',
    "DATETIME": 'SAFE_CAST({col} AS DATETIME)',
    "TIME": 'SAFE_CAST({col} AS TIME)',
    "BYTES": 'CAST({col} AS BYTES)',
    "RECORD": '{col}',  # structs — sem cast
}


class SilverGenerator:
    """Gera arquivos SQLX da camada Silver."""

    def __init__(self, config: GeneratorConfig, glossary: dict[str, str] | None = None):
        self.config = config
        self.glossary = glossary or {}
        self._env = Environment(loader=BaseLoader())
        self._template = self._env.from_string(SILVER_TEMPLATE)

    # ----------------------------------------------------------
    # Geração a partir de TableSchema (Parquet)
    # ----------------------------------------------------------

    def generate_from_schema(
        self,
        schema: TableSchema,
        desc: str = "",
        ai_metadata: dict | None = None,
        output_dir: str | None = None,
    ) -> Path:
        """
        Gera .sqlx Silver a partir de um TableSchema extraído de Parquet.
        Usa metadata de IA se disponível para descrições de colunas.
        """
        out_dir = Path(output_dir or self.config.paths.silver_output)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Enriquece com metadata de IA
        col_descriptions: dict[str, str] = {}
        if ai_metadata and "columns" in ai_metadata:
            for c in ai_metadata["columns"]:
                col_descriptions[c["name"].upper()] = c.get("description", "")

        cols_block, sel_block = self._build_blocks_from_table_schema(
            schema.columns, col_descriptions
        )

        table_desc = desc
        if not table_desc and ai_metadata:
            table_desc = ai_metadata.get("table_description", "")
        if not table_desc:
            table_desc = f"Tabela refinada da camada Silver com dados de {schema.table_name}."

        return self._render_and_save(
            name=schema.table_name,
            db=schema.db or "raw",
            desc=table_desc,
            columns_block=cols_block,
            select_block=sel_block,
            out_dir=out_dir,
        )

    # ----------------------------------------------------------
    # Builders de blocos
    # ----------------------------------------------------------
    
    def _format_column_name(self, col_name: str) -> str:
        """Aplica taxonomia (DT_, ID_, CD_, etc.) com base nas regras fornecidas."""
        name = col_name.upper()
        
        # Se já tem um prefixo válido, apenas retorna
        valid_prefixes = ("CD_", "ID_", "NO_", "DE_", "DT_", "VL_", "QT_", "TP_", "PC_", "IS_")
        if name.startswith(valid_prefixes):
            return name
            
        # CD: Código / Identificador
        if name.startswith("CODIGO_"):
            return "CD_" + name[7:]
            
        # NO: Nome
        if name.startswith("NOME_"):
            return "NO_" + name[5:]
            
        # DT: Data
        if name.startswith("DATA_"):
            return "DT_" + name[5:]
            
        # VL: Valor Monetário
        if name.startswith("VALOR_"):
            return "VL_" + name[6:]
            
        # QT: Quantidade
        if name.startswith("QUANTIDADE_"):
            return "QT_" + name[11:]
        if name.startswith("QTD_"):
            return "QT_" + name[4:]
            
        # TP: Tipo / Categoria
        if name.startswith("TIPO_"):
            return "TP_" + name[5:]
            
        # PC: Porcentagem
        if name.startswith("PERCENTUAL_"):
            return "PC_" + name[11:]
        if name.startswith("PORCENTAGEM_"):
            return "PC_" + name[12:]
        if name.startswith("PCT_"):
            return "PC_" + name[4:]
            
        # IS: Condição (Booleano)
        if name.startswith("FLAG_"):
            return "IS_" + name[5:]
        if name.startswith("INDICADOR_"):
            return "IS_" + name[10:]
            
        # DE: Descrição / Restante (Fallback)
        # Campos textuais ou qualquer coisa não mapeada pelas regras anteriores
        return "DE_" + name

    def _build_blocks_from_table_schema(
        self,
        columns: list[ColumnSchema],
        col_descriptions: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Constrói os blocos columns e SELECT a partir de ColumnSchema (Parquet)."""
        col_descriptions = col_descriptions or {}
        doc_lines: list[str] = []
        sel_lines: list[str] = []

        for col in columns:
            desc = (
                col_descriptions.get(col.name.upper())
                or self._get_description(col.name)
            )
            target_col = self._format_column_name(col.name)
            
            doc_lines.append(f'    {target_col}: "{desc}",')

            cast_expr = _CAST_MAP.get(col.type, 'TRIM(CAST({col} AS STRING))')
            sel_lines.append(
                f"  {cast_expr.format(col=col.name)} AS {target_col}"
            )

        return "\n".join(doc_lines), ",\n".join(sel_lines)

    def _get_description(self, col_name: str) -> str:
        """Obtém descrição pelo glossário ou regras de prefixo."""
        key = col_name.upper()
        if key in self.glossary:
            return self.glossary[key]
        if key.startswith("DATA_"):
            subject = key.replace("DATA_", "").replace("_", " ").lower()
            return f"Data referente ao evento de {subject}."
        if key.startswith("CODIGO_"):
            subject = key.replace("CODIGO_", "").replace("_", " ").lower()
            return f"Código identificador de {subject}."

        # Prefixos padrão
        prefix_map = {
            "CD_": "Código de",
            "ID_": "Identificador de",
            "NO_": "Nome de",
            "DE_": "Descrição de",
            "DT_": "Data de",
            "VL_": "Valor monetário de",
            "QT_": "Quantidade de",
            "TP_": "Tipo de",
            "PC_": "Percentual de",
            "IS_": "Indicador booleano de",
        }
        for prefix, meaning in prefix_map.items():
            if key.startswith(prefix):
                subject = key[len(prefix):].replace("_", " ").lower()
                return f"{meaning} {subject}."

        return col_name.replace("_", " ").title()

    # ----------------------------------------------------------
    # Renderização e escrita
    # ----------------------------------------------------------

    def _render_and_save(
        self,
        name: str,
        db: str,
        desc: str,
        columns_block: str,
        select_block: str,
        out_dir: Path,
    ) -> Path:
        tags = [t for t in self.config.silver.tags if t != "silver"]
        tags.extend([name, f"{db}_silver"])

        content = self._template.render(
            config=self.config.silver,
            name=name,
            db=db,
            desc=desc,
            columns_block=columns_block,
            select_block=select_block,
            tags=tags,
        )

        file_path = out_dir / f"{db}_{name}.sqlx"
        file_path.write_text(content, encoding="utf-8")
        log.info(f"  ✅ Silver: {file_path.name}")
        return file_path
