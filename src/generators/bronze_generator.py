"""
src/generators/bronze_generator.py
------------------------------------
Gera arquivos .sqlx da camada Bronze a partir de:
- Listas de tabelas (tabelas.json)
- Schemas extraídos de Parquets
- Configuração central (generator.yaml)
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, BaseLoader
from rich.console import Console

from src.extractor.schema_extractor import TableSchema
from src.utils.config_loader import GeneratorConfig
from src.utils.logger import get_logger

log = get_logger(__name__)
console = Console()

# ---------------------------------------------------------------
# Template Jinja2 para Bronze SQLX
# ---------------------------------------------------------------

BRONZE_TEMPLATE = """\
config {
  type: "{{ config.type }}",
  schema: "{{ config.schema_name }}",
  name: "{{ db }}_{{ name }}",
  tags: [{% for t in tags %}"{{ t }}"{% if not loop.last %}, {% endif %}{% endfor %}],
  hasOutput: {{ "true" if config.has_output else "false" }},
  description: "{{ desc }}"
}

CREATE EXTERNAL TABLE IF NOT EXISTS ${self()}
WITH PARTITION COLUMNS (
  date DATE
)
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://${env.{{ config.bucket_env_var }}}/{{ db }}/{{ name }}/*.parquet'],
  hive_partition_uri_prefix = 'gs://${env.{{ config.bucket_env_var }}}/{{ db }}/{{ name }}/',
  require_hive_partition_filter = true
);
"""


class BronzeGenerator:
    """Gera arquivos SQLX da camada Bronze."""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        self._env = Environment(loader=BaseLoader())
        self._template = self._env.from_string(BRONZE_TEMPLATE)

    # ----------------------------------------------------------
    # Descrições automáticas por origem
    # ----------------------------------------------------------

    _DESC_TEMPLATES: dict[str, str] = {
        "iilex": "Tabela externa conectada ao GCS contendo dados brutos em formato Parquet de {desc} extraído da API do {db_upper} particionados por dia.",
        "ibge": "Tabela externa conectada ao GCS contendo dados brutos em formato Parquet de {desc} extraído da API do {db_upper} particionados por dia.",
        "pgfn": "Tabela externa conectada ao GCS contendo dados brutos em formato Parquet de {desc} extraído de CSVs zipados da Procuradoria-Geral da Fazenda Nacional particionados por dia.",
        "rfb": "Tabela externa conectada ao GCS contendo dados brutos em formato Parquet de {desc} extraído de CSVs zipados da Receita Federal do Brasil particionados por dia.",
    }

    def _build_desc(self, db: str, desc: str) -> str:
        template = self._DESC_TEMPLATES.get(
            db,
            "Tabela externa conectada ao GCS contendo dados brutos de {desc} particionados por dia no formato Parquet.",
        )
        return template.format(desc=desc.replace("_", " "), db_upper=db.upper().replace("_", " "))

    # ----------------------------------------------------------
    # Geração a partir de TableSchema (Parquet)
    # ----------------------------------------------------------

    def generate_from_schema(
        self,
        schema: TableSchema,
        desc: str = "",
        output_dir: str | None = None,
    ) -> Path:
        """Gera .sqlx Bronze a partir de um TableSchema extraído de Parquet."""
        out_dir = Path(output_dir or self.config.paths.bronze_output)
        out_dir.mkdir(parents=True, exist_ok=True)

        db = schema.db or "raw"
        table_desc = desc or self._build_desc(db, schema.table_name)

        return self._render_and_save(schema.table_name, db, table_desc, out_dir)

    # ----------------------------------------------------------
    # Renderização e escrita
    # ----------------------------------------------------------

    def _render_and_save(
        self,
        name: str,
        db: str,
        desc: str,
        out_dir: Path,
    ) -> Path:
        tags = [t for t in self.config.bronze.tags if t != "bronze"]
        tags.extend([name, f"{db}_bronze"])

        content = self._template.render(
            config=self.config.bronze,
            name=name,
            db=db,
            desc=desc,
            tags=tags,
        )

        file_path = out_dir / f"{db}_{name}.sqlx"
        file_path.write_text(content, encoding="utf-8")
        console.print(f"  [green]✓[/green] [dim]Bronze:[/dim] {file_path.name}")
        return file_path
