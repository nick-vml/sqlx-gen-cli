"""
src/generators/silver_generator.py
------------------------------------
Gera arquivos .sqlx da camada Silver com:
- Funções utils.js do Dataform sugeridas pela IA
- CAST explícito por tipo (fallback quando não há IA)
- Colunas de auditoria (DT_SOURCE_MODIFIED, DT_UPDATED)
- Deduplicação via _FILE_NAME mais recente
- Glossário de colunas integrado
- Prefixos de coluna sugeridos pela IA (taxonomia inteligente)
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, BaseLoader
from rich.console import Console

from src.extractor.schema_extractor import TableSchema, ColumnSchema
from src.utils.config_loader import GeneratorConfig
from src.utils.logger import get_logger

log = get_logger(__name__)
console = Console()

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
# Mapeamento de tipo → expressão de CAST no SELECT (fallback)
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

# ---------------------------------------------------------------
# Mapeamento de funções utils.js → expressão SQLX
# ---------------------------------------------------------------

_UTILS_FUNCTION_MAP: dict[str, str] = {
    "cleanString":        '${{utils.cleanString("{col}")}}',
    "removeSpecialChars": '${{utils.removeSpecialChars("{col}")}}',
    "removeAccents":      '${{utils.removeAccents("{col}")}}',
    "normalizePercent":   '${{utils.normalizePercent("{col}")}}',
    "cleanEmail":         '${{utils.cleanEmail("{col}")}}',
    "castBoolean":        '${{utils.castBoolean("{col}")}}',
    "castMoneyBRL":       '${{utils.castMoneyBRL("{col}")}}',
    "extractInteger":     '${{utils.extractInteger("{col}")}}',
    "safeCastDate":       '${{utils.safeCastDate("{col}")}}',
    "normalizeExcelDate": '${{utils.normalizeExcelDate("{col}")}}',
    "normalizeHonorarios": '${{utils.normalizeHonorarios("{col}")}}',
    "safeCastDatetimeBR": '${{utils.safeCastDatetimeBR("{col}")}}',
    "get_value_letter":   '${{utils.get_value_letter("{col}")}}',
}

# Prefixos válidos na taxonomia
_VALID_PREFIXES = ("CD_", "ID_", "NO_", "DE_", "DT_", "VL_", "QT_", "TP_", "PC_", "IS_")


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
        Usa metadata de IA se disponível para descrições, prefixos e funções utils.js.
        """
        out_dir = Path(output_dir or self.config.paths.silver_output)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Enriquece com metadata de IA (descrições + prefixos + funções)
        col_descriptions: dict[str, str] = {}
        col_prefixes: dict[str, str] = {}
        col_functions: dict[str, str] = {}
        if ai_metadata and "columns" in ai_metadata:
            for c in ai_metadata["columns"]:
                name_upper = c["name"].upper()
                col_descriptions[name_upper] = c.get("description", "")
                if c.get("suggested_prefix"):
                    col_prefixes[name_upper] = c["suggested_prefix"].upper()
                if c.get("suggested_function") and c["suggested_function"] != "none":
                    col_functions[name_upper] = c["suggested_function"]

        cols_block, sel_block = self._build_blocks_from_table_schema(
            schema.columns, col_descriptions, col_prefixes, col_functions
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

    def _format_column_name(self, col_name: str, ai_prefix: str | None = None) -> str:
        """
        Aplica taxonomia (DT_, ID_, CD_, etc.) com base em:
        1. Prefixo sugerido pela IA (prioridade máxima)
        2. Regras estáticas de mapeamento
        3. Fallback DE_ se normalize_columns estiver habilitado
        """
        name = col_name.upper()

        # Se normalização de colunas está desabilitada, retorna o nome original em uppercase
        if not self.config.naming.normalize_columns:
            return name

        # Se já tem um prefixo válido, apenas retorna
        if name.startswith(_VALID_PREFIXES):
            return name

        # Regras de remoção de redundância: se o prefixo for "DT_", não queremos "DT_DATA_"
        redundancies = {
            "CD": ["CODIGO_", "ID_"],
            "NO": ["NOME_"],
            "DT": ["DATA_"],
            "VL": ["VALOR_"],
            "QT": ["QUANTIDADE_", "QTD_"],
            "TP": ["TIPO_"],
            "PC": ["PERCENTUAL_", "PORCENTAGEM_", "PCT_"],
            "IS": ["FLAG_", "INDICADOR_"],
            "DE": ["DESCRICAO_", "DESC_"]
        }

        # 1. Decide o prefixo base
        final_prefix = ai_prefix if ai_prefix and ai_prefix in redundancies else None
        
        # Fallback para regras estáticas se a IA não sugeriu ou sugeriu algo inválido
        if not final_prefix:
            for prefix, rules in redundancies.items():
                for rule in rules:
                    if name.startswith(rule):
                        final_prefix = prefix
                        break
                if final_prefix:
                    break
        
        # Se ainda não encontrou, fallback genérico
        if not final_prefix:
            final_prefix = "DE"

        # 2. Limpa o nome da coluna das redundâncias
        for rule in redundancies.get(final_prefix, []):
            if name.startswith(rule):
                name = name[len(rule):]
                break

        # Caso extremo onde a coluna era apenas a palavra redundante (ex: "DATA")
        if not name:
            name = col_name.upper()

        return f"{final_prefix}_{name}"

    def _get_cast_expression(
        self,
        col: ColumnSchema,
        ai_function: str | None = None,
    ) -> str:
        """
        Determina a expressão de CAST/transformação para uma coluna.
        
        Prioridade:
        1. Função utils.js sugerida pela IA
        2. CAST padrão baseado no tipo do Parquet
        """
        # 1. Se a IA sugeriu uma função utils.js, usa ela
        if ai_function and ai_function in _UTILS_FUNCTION_MAP:
            return _UTILS_FUNCTION_MAP[ai_function].format(col=col.name)

        # 2. Fallback: CAST padrão pelo tipo
        cast_expr = _CAST_MAP.get(col.type, 'TRIM(CAST({col} AS STRING))')
        return cast_expr.format(col=col.name)

    def _build_blocks_from_table_schema(
        self,
        columns: list[ColumnSchema],
        col_descriptions: dict[str, str] | None = None,
        col_prefixes: dict[str, str] | None = None,
        col_functions: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Constrói os blocos columns e SELECT a partir de ColumnSchema (Parquet)."""
        col_descriptions = col_descriptions or {}
        col_prefixes = col_prefixes or {}
        col_functions = col_functions or {}
        doc_lines: list[str] = []
        sel_lines: list[str] = []

        for col in columns:
            desc = (
                col_descriptions.get(col.name.upper())
                or self._get_description(col.name)
            )
            ai_prefix = col_prefixes.get(col.name.upper())
            ai_function = col_functions.get(col.name.upper())
            target_col = self._format_column_name(col.name, ai_prefix)

            doc_lines.append(f'    {target_col}: "{desc}",')

            cast_expr = self._get_cast_expression(col, ai_function)
            sel_lines.append(f"  {cast_expr} AS {target_col}")

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
        console.print(f"  [cyan]✓[/cyan] [dim]Silver:[/dim] {file_path.name}")
        return file_path
