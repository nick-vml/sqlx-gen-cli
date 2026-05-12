"""
src/parquet/schema_extractor.py
--------------------------------
Extrai schema de arquivos .parquet de:
  - Caminhos locais  (ex: ./parquet/clientes.parquet)
  - GCS              (ex: gs://meu-bucket/path/to/clientes.parquet)
  - Diretório GCS    (ex: gs://meu-bucket/path/)

Autenticacao GCS: usa Application Default Credentials (ADC).
  Configure com: gcloud auth application-default login
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel

from src.utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------
# Mapeamento de tipos PyArrow -> BigQuery
# ---------------------------------------------------------------
_TYPE_MAP: dict[str, str] = {
    "int8": "INTEGER",
    "int16": "INTEGER",
    "int32": "INTEGER",
    "int64": "INTEGER",
    "uint8": "INTEGER",
    "uint16": "INTEGER",
    "uint32": "INTEGER",
    "uint64": "INTEGER",
    "float": "FLOAT",
    "float16": "FLOAT",
    "float32": "FLOAT",
    "float64": "FLOAT",
    "double": "FLOAT",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "string": "STRING",
    "utf8": "STRING",
    "large_utf8": "STRING",
    "binary": "BYTES",
    "large_binary": "BYTES",
    "date32": "DATE",
    "date64": "DATE",
    "timestamp[ns]": "TIMESTAMP",
    "timestamp[us]": "TIMESTAMP",
    "timestamp[ms]": "TIMESTAMP",
    "timestamp[s]": "TIMESTAMP",
    "time32": "TIME",
    "time64": "TIME",
    "duration": "INTEGER",
    "decimal128": "NUMERIC",
    "decimal256": "BIGNUMERIC",
}


def _map_type(arrow_type: pa.DataType) -> str:
    """Converte um tipo PyArrow para o equivalente BigQuery."""
    type_str = str(arrow_type).lower()
    if pa.types.is_struct(arrow_type):
        return "RECORD"
    if pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type):
        return "REPEATED"
    if pa.types.is_decimal(arrow_type):
        return "NUMERIC"
    for key, bq_type in _TYPE_MAP.items():
        if key in type_str:
            return bq_type
    return "STRING"


# ---------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------

class ColumnSchema(BaseModel):
    name: str
    type: str
    nullable: bool = True
    description: str = ""
    pii: bool = False
    sensitivity: str = "low"
    fields: list["ColumnSchema"] = []
    mode: str = "NULLABLE"


class TableSchema(BaseModel):
    table_name: str
    source_file: str
    db: str = ""
    row_count: int = 0
    columns: list[ColumnSchema] = []

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)


# ---------------------------------------------------------------
# Deteccao e resolucao de filesystem
# ---------------------------------------------------------------

def _is_gcs(path: str) -> bool:
    return str(path).startswith("gs://")


def _get_gcs_fs():
    """Retorna um gcsfs.GCSFileSystem autenticado via ADC."""
    try:
        import gcsfs
        return gcsfs.GCSFileSystem()
    except ImportError:
        raise ImportError(
            "gcsfs nao instalado. Execute: pip install gcsfs"
        )


def _gcs_list_parquets(gcs_path: str) -> list[str]:
    """Lista todos os arquivos .parquet sob um caminho GCS."""
    fs = _get_gcs_fs()
    raw_path = gcs_path.removeprefix("gs://")

    # Arquivo direto
    if raw_path.endswith(".parquet"):
        return [gcs_path] if fs.exists(raw_path) else []

    # Listagem recursiva
    try:
        all_files = fs.glob(f"{raw_path.rstrip('/')}/**/*.parquet")
        if not all_files:
            all_files = fs.glob(f"{raw_path.rstrip('/')}/*.parquet")
        return [f"gs://{f}" for f in all_files]
    except Exception as e:
        log.error(f"Erro ao listar GCS: {e}")
        return []


# ---------------------------------------------------------------
# Extrator principal
# ---------------------------------------------------------------

class SchemaExtractor:
    """
    Extrai schema de um arquivo .parquet.

    Suporta caminhos locais e gs:// (GCS).
    """

    def __init__(self, parquet_path: str | Path):
        self.path = str(parquet_path)
        self._is_gcs_path = _is_gcs(self.path)

    def extract(self) -> TableSchema:
        """Le o parquet e extrai o schema sem carregar dados."""
        if self._is_gcs_path:
            return self._extract_gcs()
        return self._extract_local()

    # ----------------------------------------------------------
    # Local
    # ----------------------------------------------------------

    def _extract_local(self) -> TableSchema:
        local_path = Path(self.path)
        if not local_path.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado: {self.path}")

        log.info(f"Lendo schema local: {local_path.name}")
        pf = pq.ParquetFile(local_path)
        arrow_schema: pa.Schema = pf.schema_arrow
        row_count = pf.metadata.num_rows

        return TableSchema(
            table_name=local_path.stem,
            source_file=self.path,
            row_count=row_count,
            columns=[self._parse_field(field) for field in arrow_schema],
        )

    # ----------------------------------------------------------
    # GCS
    # ----------------------------------------------------------

    def _extract_gcs(self) -> TableSchema:
        fs = _get_gcs_fs()
        raw = self.path.removeprefix("gs://")
        
        # Infere db e table_name pela estrutura: gs://bucket/db/name/...
        parts = raw.split("/")
        db = ""
        table_name = Path(raw).stem
        if len(parts) >= 4:
            db = parts[1]
            table_name = parts[2]

        log.info(f"Lendo schema GCS: {self.path} (db={db}, name={table_name})")

        # Lê apenas o schema sem baixar dados
        try:
            arrow_schema = pq.read_schema(self.path, filesystem=fs)
        except Exception:
            arrow_schema = pq.ParquetFile(fs.open(raw)).schema_arrow

        # Conta linhas via metadata
        try:
            pf_meta = pq.read_metadata(self.path, filesystem=fs)
            row_count = pf_meta.num_rows
        except Exception:
            row_count = 0
            log.warning(f"  Nao foi possivel contar linhas de {table_name}")

        return TableSchema(
            table_name=table_name,
            source_file=self.path,
            db=db,
            row_count=row_count,
            columns=[self._parse_field(field) for field in arrow_schema],
        )

    # ----------------------------------------------------------
    # Parser de campo
    # ----------------------------------------------------------

    def _parse_field(self, field: pa.Field) -> ColumnSchema:
        bq_type = _map_type(field.type)
        mode = "NULLABLE" if field.nullable else "REQUIRED"

        if pa.types.is_list(field.type) or pa.types.is_large_list(field.type):
            mode = "REPEATED"
            bq_type = _map_type(field.type.value_type)

        nested_fields: list[ColumnSchema] = []
        if pa.types.is_struct(field.type):
            for i in range(field.type.num_fields):
                nested_fields.append(self._parse_field(field.type.field(i)))

        return ColumnSchema(
            name=field.name,
            type=bq_type,
            nullable=field.nullable,
            mode=mode,
            fields=nested_fields,
        )


# ---------------------------------------------------------------
# Funcoes de alto nivel
# ---------------------------------------------------------------

def _extract_single(path: str) -> TableSchema | None:
    """Extrai schema de um arquivo unico (local ou GCS). Retorna None em caso de erro."""
    try:
        schema = SchemaExtractor(path).extract()
        log.info(f"  OK {schema.table_name}: {len(schema.columns)} colunas, {schema.row_count:,} linhas")
        return schema
    except Exception as e:
        log.error(f"  ERRO {path}: {e}")
        return None


def extract_from_list(paths: list[str | Path]) -> list[TableSchema]:
    """
    Extrai schemas de uma lista explícita de arquivos .parquet.

    Cada item pode ser:
    - Caminho local: ./parquet/clientes.parquet
    - Caminho GCS:   gs://bucket/dados/clientes.parquet

    Exemplo:
        schemas = extract_from_list([
            "gs://bucket/rfb/empresas.parquet",
            "gs://bucket/rfb/socios.parquet",
            "./local/clientes.parquet",
        ])
    """
    schemas: list[TableSchema] = []
    log.info(f"Processando lista de {len(paths)} arquivo(s)...")
    for path in paths:
        result = _extract_single(str(path))
        if result:
            schemas.append(result)
    return schemas


def extract_all_schemas(path: str | Path | list[str | Path]) -> list[TableSchema]:
    """
    Extrai schemas de .parquet a partir de:
    - Um diretório local:    './parquet/'
    - Um prefixo GCS:        'gs://bucket/prefix/'
    - Um arquivo único:      'gs://bucket/file.parquet' ou './local/file.parquet'
    - Uma lista de caminhos: ['gs://bucket/a.parquet', 'gs://bucket/b.parquet']

    Returns:
        Lista de TableSchema.
    """
    # ---- Lista de caminhos ----
    if isinstance(path, list):
        return extract_from_list(path)

    path_str = str(path)
    schemas: list[TableSchema] = []

    # ---- Arquivo único (GCS ou local) ----
    if path_str.endswith(".parquet"):
        result = _extract_single(path_str)
        return [result] if result else []

    # ---- GCS (diretório/prefixo) ----
    if _is_gcs(path_str):
        parquet_files = _gcs_list_parquets(path_str)
        if not parquet_files:
            log.warning(f"Nenhum .parquet encontrado em: {path_str}")
            return schemas
        log.info(f"Encontrados {len(parquet_files)} arquivo(s) no GCS.")
        return extract_from_list(parquet_files)

    # ---- Local (diretório) ----
    local_dir = Path(path_str)
    parquet_files_local = list(local_dir.rglob("*.parquet"))
    if not parquet_files_local:
        log.warning(f"Nenhum .parquet encontrado em: {local_dir}")
        return schemas
    return extract_from_list([str(p) for p in parquet_files_local])



def save_schema_json(schema: TableSchema, output_dir: str | Path) -> Path:
    """Salva o schema como JSON intermediario."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{schema.db}_" if schema.db else ""
    out_path = output_dir / f"{prefix}{schema.table_name}.schema.json"
    out_path.write_text(schema.to_json(), encoding="utf-8")
    return out_path
