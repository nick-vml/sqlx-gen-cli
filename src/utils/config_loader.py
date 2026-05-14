"""
src/utils/config_loader.py
--------------------------
Carrega e valida o arquivo YAML de configuração do framework.
"""
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------
# Modelos Pydantic para validação da configuração
# ---------------------------------------------------------------

class ProjectConfig(BaseModel):
    name: str = "dataform-generator"
    version: str = "1.0.0"


class PathsConfig(BaseModel):
    parquet_input: str = "./parquet"
    output_root: str = "./generated"
    bronze_output: str = "./generated/bronze"
    silver_output: str = "./generated/silver"
    docs_output: str = "./generated/docs"
    metadata_output: str = "./generated/metadata"


class BronzeConfig(BaseModel):
    schema_name: str = Field("bronze", alias="schema")
    type: str = "operations"
    has_output: bool = True
    bucket_env_var: str = "bucket_name"
    tags: list[str] = ["bronze"]
    labels: dict[str, str] = {}

    class Config:
        populate_by_name = True


class AuditColumn(BaseModel):
    name: str
    description: str


class SilverConfig(BaseModel):
    schema_name: str = Field("silver", alias="schema")
    type: str = "table"
    tags: list[str] = ["silver"]
    partition_by: str = ""
    cluster_by: list[str] = []
    labels: dict[str, str] = {}
    lookback_days: int = 1
    update_frequency: str = "diario"
    audit_columns: list[AuditColumn] = []

    class Config:
        populate_by_name = True


class NamingConfig(BaseModel):
    snake_case: bool = True
    normalize_columns: bool = True


class AIConfig(BaseModel):
    enabled: bool = True
    api_key_env: str = "OPENROUTER_API_KEY"
    model: str = "anthropic/claude-3.5-sonnet"
    fallback_models: list[str] = []
    max_retries: int = 3
    timeout_seconds: int = 60
    max_parallel: int = 3
    detect_pii: bool = True
    classify_sensitivity: bool = True


class GeneratorConfig(BaseModel):
    project: ProjectConfig = ProjectConfig()
    paths: PathsConfig = PathsConfig()
    bronze: BronzeConfig = BronzeConfig()
    silver: SilverConfig = SilverConfig()
    naming: NamingConfig = NamingConfig()
    ai: AIConfig = AIConfig()
    datasources_file: str = "./tabelas.json"
    glossary_file: str = "./glossario.json"


# ---------------------------------------------------------------
# Função de carregamento
# ---------------------------------------------------------------

def load_config(config_path: str = "config/generator.yaml") -> GeneratorConfig:
    """Carrega o YAML e retorna o modelo validado."""
    path = Path(config_path)
    if not path.exists():
        return GeneratorConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return GeneratorConfig(**raw)
