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


def _list_files(path: str, extensions: list[str]) -> list[str]:
    """Lista arquivos com as extensões permitidas no GCS ou Local."""
    if _is_gcs(path):
        fs = _get_gcs_fs()
        raw_path = path.removeprefix("gs://")
        
        # Arquivo direto
        if any(raw_path.lower().endswith(ext) for ext in extensions):
            return [path] if fs.exists(raw_path) else []

        # Listagem recursiva
        all_files = []
        for ext in extensions:
            try:
                found = fs.glob(f"{raw_path.rstrip('/')}/**/*{ext}")
                if not found:
                    found = fs.glob(f"{raw_path.rstrip('/')}/*{ext}")
                all_files.extend([f"gs://{f}" for f in found])
            except Exception:
                continue
        return all_files
    else:
        local_dir = Path(path)
        if local_dir.is_file():
            return [path] if any(path.lower().endswith(ext) for ext in extensions) else []
        
        files = []
        for ext in extensions:
            files.extend([str(p) for p in local_dir.rglob(f"*{ext}")])
        return files



# ---------------------------------------------------------------
# Extrator principal
# ---------------------------------------------------------------

class SchemaExtractor:
    """
    Extrai schema de arquivos .parquet, .csv ou .json.
    Suporta caminhos locais e gs:// (GCS).
    """

    def __init__(self, file_path: str | Path):
        self.path = str(file_path)
        self.extension = Path(self.path).suffix.lower()
        self._is_gcs_path = _is_gcs(self.path)

    def extract(self) -> TableSchema:
        """Extrai o schema do arquivo baseado na sua extensão."""
        if self.extension == ".parquet":
            return self._extract_parquet()
        elif self.extension == ".csv":
            return self._extract_csv()
        elif self.extension in (".json", ".jsonl", ".ndjson"):
            return self._extract_json()
        else:
            raise ValueError(f"Extensão não suportada: {self.extension}")

    def _get_input_stream(self):
        if self._is_gcs_path:
            fs = _get_gcs_fs()
            return fs.open(self.path.removeprefix("gs://"))
        return open(self.path, "rb")

    def _infer_names(self) -> tuple[str, str]:
        """Infere db (dataset) e table_name a partir do path GCS ou Local."""
        if self._is_gcs_path:
            raw = self.path.removeprefix("gs://")
            parts = [p for p in raw.split("/") if p]
            
            # Padrão gs://projeto/dataset/tabela/arquivo.ext
            # parts[0] = projeto (bucket)
            # parts[1] = dataset (db)
            # parts[2] = tabela
            db = parts[1] if len(parts) >= 2 else ""
            table_name = parts[2] if len(parts) >= 3 else Path(self.path).stem
            return db, table_name
        else:
            return "", Path(self.path).stem

    def _extract_parquet(self) -> TableSchema:
        db, table_name = self._infer_names()
        
        if self._is_gcs_path:
            fs = _get_gcs_fs()
            try:
                arrow_schema = pq.read_schema(self.path, filesystem=fs)
                pf_meta = pq.read_metadata(self.path, filesystem=fs)
                row_count = pf_meta.num_rows
            except Exception:
                # Fallback se não conseguir ler apenas metadata
                with self._get_input_stream() as f:
                    pf = pq.ParquetFile(f)
                    arrow_schema = pf.schema_arrow
                    row_count = pf.metadata.num_rows

            return TableSchema(
                table_name=table_name,
                source_file=self.path,
                db=db,
                row_count=row_count,
                columns=[self._parse_field(field) for field in arrow_schema],
            )
        else:
            local_path = Path(self.path)
            pf = pq.ParquetFile(local_path)
            return TableSchema(
                table_name=table_name,
                source_file=self.path,
                db=db,
                row_count=pf.metadata.num_rows,
                columns=[self._parse_field(field) for field in pf.schema_arrow],
            )

    def _extract_csv(self) -> TableSchema:
        import pyarrow.csv as pv
        db, table_name = self._infer_names()
        log.info(f"Inferindo schema de CSV: {self.path} (table={table_name})")
        with self._get_input_stream() as f:
            table = pv.read_csv(f)
            return TableSchema(
                table_name=table_name,
                source_file=self.path,
                db=db,
                row_count=table.num_rows,
                columns=[self._parse_field(field) for field in table.schema],
            )

    def _extract_json(self) -> TableSchema:
        import pyarrow.json as pj
        db, table_name = self._infer_names()
        log.info(f"Inferindo schema de JSON: {self.path} (table={table_name})")
        with self._get_input_stream() as f:
            table = pj.read_json(f)
            return TableSchema(
                table_name=table_name,
                source_file=self.path,
                db=db,
                row_count=table.num_rows,
                columns=[self._parse_field(field) for field in table.schema],
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
    """Extrai schemas de uma lista explícita de arquivos."""
    schemas: list[TableSchema] = []
    log.info(f"Processando lista de {len(paths)} arquivo(s)...")
    for path in paths:
        result = _extract_single(str(path))
        if result:
            schemas.append(result)
    return schemas


def extract_all_schemas(path: str | Path | list[str | Path]) -> list[TableSchema]:
    """
    Extrai schemas de arquivos (.parquet, .csv, .json) a partir de:
    - Um diretório local ou GCS
    - Um arquivo único
    - Uma lista de caminhos
    """
    extensions = [".parquet", ".csv", ".json", ".jsonl", ".ndjson"]
    
    if isinstance(path, list):
        return extract_from_list(path)

    path_str = str(path)
    
    # Se for um arquivo único direto
    if any(path_str.lower().endswith(ext) for ext in extensions):
        result = _extract_single(path_str)
        return [result] if result else []

    # Se for um diretório (GCS ou Local)
    found_files = _list_files(path_str, extensions)
    if not found_files:
        log.warning(f"Nenhum arquivo suportado {extensions} encontrado em: {path_str}")
        return []
    
    log.info(f"Encontrados {len(found_files)} arquivo(s).")
    return extract_from_list(found_files)




def save_schema_json(schema: TableSchema, output_dir: str | Path) -> Path:
    """Salva o schema como JSON intermediario."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{schema.db}_" if schema.db else ""
    out_path = output_dir / f"{prefix}{schema.table_name}.schema.json"
    out_path.write_text(schema.to_json(), encoding="utf-8")
    return out_path
