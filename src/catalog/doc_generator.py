"""
src/catalog/doc_generator.py
-----------------------------
Gera documentação técnica automaticamente:
- Markdown por tabela
- Data dictionary JSON
- Índice global de tabelas
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from src.extractor.schema_extractor import TableSchema
from src.utils.logger import get_logger

log = get_logger(__name__)


class DocGenerator:
    """Gera documentação em Markdown e JSON para tabelas."""

    def __init__(self, output_dir: str | Path = "./generated/docs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------
    # Markdown por tabela
    # ----------------------------------------------------------

    def generate_markdown(
        self,
        schema: TableSchema,
        ai_metadata: dict | None = None,
        layer: str = "silver",
    ) -> Path:
        """
        Gera um arquivo .md com a documentação da tabela.

        Args:
            schema: Schema extraído do Parquet.
            ai_metadata: Metadata enriquecida pela IA (opcional).
            layer: Camada da tabela (bronze | silver).
        """
        ai = ai_metadata or {}
        domain = ai.get("domain", "N/A")
        table_desc = ai.get("table_description", f"Tabela {schema.table_name}.")
        tags = ai.get("tags", [])
        sensitivity = ai.get("sensitivity", "low")

        # Mapa de colunas com AI
        col_map: dict[str, dict] = {}
        for c in ai.get("columns", []):
            col_map[c["name"].upper()] = c

        lines: list[str] = [
            f"# {schema.table_name.upper()}",
            "",
            f"> **Gerado automaticamente em:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            f"> **Camada:** `{layer}` | **Domínio:** `{domain}` | **Sensibilidade:** `{sensitivity}`",
            "",
            "## Descrição",
            "",
            table_desc,
            "",
        ]

        if tags:
            lines += ["## Tags", "", " ".join(f"`{t}`" for t in tags), ""]

        # Tabela de colunas
        lines += [
            "## Colunas",
            "",
            "| Coluna | Tipo | Nulável | PII | Descrição |",
            "|--------|------|---------|-----|-----------|",
        ]

        for col in schema.columns:
            ai_col = col_map.get(col.name.upper(), {})
            pii = "✅" if ai_col.get("pii") else "—"
            desc = ai_col.get("description", col.description or col.name.replace("_", " ").title())
            nullable = "✓" if col.nullable else "✗"
            lines.append(f"| `{col.name}` | {col.type} | {nullable} | {pii} | {desc} |")

        lines += [
            "",
            "---",
            "*Documentação gerada pelo dataform-generator framework*",
        ]

        content = "\n".join(lines)
        out_path = self.output_dir / f"{schema.table_name}.md"
        out_path.write_text(content, encoding="utf-8")
        log.info(f"  📄 Docs: {out_path.name}")
        return out_path

    # ----------------------------------------------------------
    # Data Dictionary JSON
    # ----------------------------------------------------------

    def generate_data_dictionary(
        self,
        schemas: list[TableSchema],
        ai_metadata_map: dict[str, dict] | None = None,
    ) -> Path:
        """Gera um data dictionary JSON com todas as tabelas."""
        ai_metadata_map = ai_metadata_map or {}
        dictionary: list[dict] = []

        for schema in schemas:
            ai = ai_metadata_map.get(schema.table_name, {})
            col_map = {c["name"].upper(): c for c in ai.get("columns", [])}

            entry = {
                "table": schema.table_name,
                "db": schema.db,
                "domain": ai.get("domain", ""),
                "description": ai.get("table_description", ""),
                "tags": ai.get("tags", []),
                "sensitivity": ai.get("sensitivity", "low"),
                "row_count": schema.row_count,
                "columns": [],
            }

            for col in schema.columns:
                ai_col = col_map.get(col.name.upper(), {})
                entry["columns"].append({
                    "name": col.name,
                    "type": col.type,
                    "nullable": col.nullable,
                    "description": ai_col.get("description", col.description),
                    "pii": ai_col.get("pii", False),
                    "sensitivity": ai_col.get("sensitivity", "low"),
                })

            dictionary.append(entry)

        out_path = self.output_dir / "data_dictionary.json"
        out_path.write_text(
            json.dumps(dictionary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info(f"  📚 Data dictionary: {out_path.name}")
        return out_path

    # ----------------------------------------------------------
    # Índice global (README)
    # ----------------------------------------------------------

    def generate_index(
        self,
        schemas: list[TableSchema],
        ai_metadata_map: dict[str, dict] | None = None,
    ) -> Path:
        """Gera um README.md com índice de todas as tabelas."""
        ai_metadata_map = ai_metadata_map or {}

        lines: list[str] = [
            "# Data Catalog — Índice de Tabelas",
            "",
            f"> Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            f"> Total de tabelas: **{len(schemas)}**",
            "",
            "| Tabela | Banco | Domínio | Sensibilidade | Colunas |",
            "|--------|-------|---------|---------------|---------|",
        ]

        for schema in schemas:
            ai = ai_metadata_map.get(schema.table_name, {})
            lines.append(
                f"| [{schema.table_name}](./{schema.table_name}.md)"
                f" | {schema.db or '—'}"
                f" | {ai.get('domain', '—')}"
                f" | {ai.get('sensitivity', 'low')}"
                f" | {len(schema.columns)} |"
            )

        out_path = self.output_dir / "README.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        log.info(f"  📑 Índice: {out_path.name}")
        return out_path
