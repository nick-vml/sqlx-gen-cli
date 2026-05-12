"""
src/metadata/metadata_manager.py
----------------------------------
Orquestra o enriquecimento de metadata via IA:
- Lê schemas extraídos
- Envia para OpenRouter
- Armazena resultados em JSON
- Detecta mudanças de schema (evolução)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.parquet.schema_extractor import TableSchema
from src.ai.openrouter_client import OpenRouterClient
from src.ai.prompt_builder import build_enrichment_prompt
from src.utils.config_loader import GeneratorConfig
from src.utils.logger import get_logger

log = get_logger(__name__)


class MetadataManager:
    """
    Gerencia o ciclo completo de enriquecimento de metadata.

    Fluxo:
        schema → prompt → LLM → parsing → save → detect_drift
    """

    def __init__(
        self,
        config: GeneratorConfig,
        ai_client: OpenRouterClient | None = None,
        glossary: dict[str, str] | None = None,
    ):
        self.config = config
        self.glossary = glossary or {}
        self._ai = ai_client or OpenRouterClient(
            api_key=None,  # lê de OPENROUTER_API_KEY
            primary_model=config.ai.model,
            fallback_models=config.ai.fallback_models,
            max_retries=config.ai.max_retries,
            timeout=config.ai.timeout_seconds,
        )

        self._metadata_dir = Path(config.paths.metadata_output)
        self._metadata_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------
    # Enriquecimento por tabela
    # ----------------------------------------------------------

    def enrich(self, schema: TableSchema) -> dict[str, Any]:
        """
        Envia schema ao LLM e retorna metadata enriquecida.
        Se a IA estiver desabilitada, retorna dict vazio.
        """
        if not self.config.ai.enabled:
            log.info("  ⏭️  AI desabilitada na configuração.")
            return {}

        existing = self._load_existing(schema)
        if existing:
            log.info(f"  ♻️  Metadata já existente para {schema.table_name} — reutilizando.")
            return existing

        log.info(f"  🤖 Enriquecendo metadata de: {schema.table_name}")
        messages = build_enrichment_prompt(schema, self.glossary)
        response = self._ai.chat(messages, expect_json=True)

        metadata = response.parsed or {}
        metadata["_meta"] = {
            "model": response.model_used,
            "tokens": response.tokens_used,
            "latency_ms": response.latency_ms,
        }

        self._save(schema, metadata)
        return metadata

    def enrich_batch(self, schemas: list[TableSchema]) -> dict[str, dict]:
        """Processa uma lista de schemas em batch."""
        results: dict[str, dict] = {}
        total = len(schemas)

        for i, schema in enumerate(schemas, 1):
            key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
            log.info(f"[{i}/{total}] {key}")
            try:
                results[key] = self.enrich(schema)
            except Exception as e:
                log.error(f"  ❌ Erro ao enriquecer {key}: {e}")
                results[key] = {}

        return results

    # ----------------------------------------------------------
    # Detecção de drift de schema
    # ----------------------------------------------------------

    def detect_schema_drift(
        self,
        old_schema: TableSchema,
        new_schema: TableSchema,
    ) -> dict[str, Any]:
        """
        Compara dois schemas e detecta drift:
        - Colunas adicionadas
        - Colunas removidas
        - Mudanças de tipo
        """
        old_cols = {c.name: c.type for c in old_schema.columns}
        new_cols = {c.name: c.type for c in new_schema.columns}

        added = [n for n in new_cols if n not in old_cols]
        removed = [n for n in old_cols if n not in new_cols]
        type_changed = [
            {"column": n, "old_type": old_cols[n], "new_type": new_cols[n]}
            for n in new_cols
            if n in old_cols and old_cols[n] != new_cols[n]
        ]

        has_drift = bool(added or removed or type_changed)
        report = {
            "table": new_schema.table_name,
            "has_drift": has_drift,
            "added": added,
            "removed": removed,
            "type_changed": type_changed,
        }

        if has_drift:
            log.warning(
                f"  ⚠️  Schema drift detectado em {new_schema.table_name}: "
                f"+{len(added)} cols, -{len(removed)} cols, {len(type_changed)} tipo(s) alterado(s)"
            )

        return report

    # ----------------------------------------------------------
    # Persistência
    # ----------------------------------------------------------

    def _get_filename(self, schema: TableSchema) -> str:
        prefix = f"{schema.db}_" if schema.db else ""
        return f"{prefix}{schema.table_name}.metadata.json"

    def _save(self, schema: TableSchema, metadata: dict) -> None:
        path = self._metadata_dir / self._get_filename(schema)
        path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_existing(self, schema: TableSchema) -> dict | None:
        path = self._metadata_dir / self._get_filename(schema)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None
