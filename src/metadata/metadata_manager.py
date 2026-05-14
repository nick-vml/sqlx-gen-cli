"""
src/metadata/metadata_manager.py
----------------------------------
Orquestra o enriquecimento de metadata via IA:
- Lê schemas extraídos
- Envia para OpenRouter (com processamento paralelo)
- Armazena resultados em JSON
- Detecta mudanças de schema (evolução)
- Auto-aprendizado do glossário
- Suporte a cache (--force / --cache)
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from rich.console import Console

from src.extractor.schema_extractor import TableSchema
from src.ai.openrouter_client import OpenRouterClient
from src.ai.prompt_builder import build_enrichment_prompt
from src.utils.config_loader import GeneratorConfig
from src.utils.logger import get_logger

log = get_logger(__name__)
console = Console()


class MetadataManager:
    """
    Gerencia o ciclo completo de enriquecimento de metadata.

    Fluxo:
        schema → prompt → LLM → parsing → save → glossary → detect_drift
    """

    def __init__(
        self,
        config: GeneratorConfig,
        ai_client: OpenRouterClient | None = None,
        glossary: dict[str, str] | None = None,
        force: bool = False,
    ):
        self.config = config
        self.glossary = glossary or {}
        self.force = force
        self._ai = ai_client or OpenRouterClient(
            api_key=None,
            api_key_env=config.ai.api_key_env,
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
        Usa cache se force=False e metadata existente.
        """
        if not self.config.ai.enabled:
            log.info("  ⏭️  AI desabilitada na configuração.")
            return {}

        # Cache: reutiliza metadata existente se não forçar
        if not self.force:
            existing = self._load_existing(schema)
            if existing:
                console.print(f"  [dim]♻️  Cache: reutilizando metadata de {schema.table_name}[/dim]")
                return existing

        console.print(f"  [dim]🤖 Enriquecendo metadata de: {schema.table_name}[/dim]")
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
        """
        Processa uma lista de schemas em batch.
        Usa ThreadPoolExecutor para paralelismo controlado.
        """
        results: dict[str, dict] = {}
        total = len(schemas)
        max_workers = min(self.config.ai.max_parallel, total)

        if max_workers <= 1 or total == 1:
            # Sequencial para 1 item ou max_parallel=1
            for i, schema in enumerate(schemas, 1):
                key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
                console.print(f"  [cyan][{i}/{total}][/cyan] {key}")
                try:
                    results[key] = self.enrich(schema)
                except Exception as e:
                    log.error(f"  ❌ Erro ao enriquecer {key}: {e}")
                    results[key] = {}
            return results

        # Processamento paralelo
        console.print(f"  [dim]⚡ Processamento paralelo com {max_workers} workers[/dim]")

        def _process(idx: int, schema: TableSchema) -> tuple[str, dict]:
            key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
            console.print(f"  [cyan][{idx}/{total}][/cyan] {key}")
            try:
                return key, self.enrich(schema)
            except Exception as e:
                log.error(f"  ❌ Erro ao enriquecer {key}: {e}")
                return key, {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process, i, schema): schema
                for i, schema in enumerate(schemas, 1)
            }
            for future in as_completed(futures):
                key, metadata = future.result()
                results[key] = metadata

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

    def detect_drift_from_saved(self, schema: TableSchema) -> dict[str, Any] | None:
        """
        Compara o schema atual com o salvo anteriormente (se existir).
        Retorna o relatório de drift ou None se não houver schema anterior.
        """
        saved_path = Path(self.config.paths.metadata_output)
        prefix = f"{schema.db}_" if schema.db else ""
        schema_file = saved_path / f"{prefix}{schema.table_name}.schema.json"

        if not schema_file.exists():
            return None

        try:
            raw = json.loads(schema_file.read_text(encoding="utf-8"))
            old_schema = TableSchema(**raw)
            return self.detect_schema_drift(old_schema, schema)
        except Exception as e:
            log.warning(f"  ⚠️  Não foi possível carregar schema anterior: {e}")
            return None

    # ----------------------------------------------------------
    # Glossário auto-aprendizado
    # ----------------------------------------------------------

    def update_glossary(
        self,
        ai_results: dict[str, dict],
        glossary_path: str | Path,
    ) -> int:
        """
        Mescla as descrições de colunas da IA de volta no glossário.
        Só adiciona colunas que ainda NÃO existem no glossário.

        Returns:
            Quantidade de novas entradas adicionadas.
        """
        glossary_path = Path(glossary_path)

        # Carrega glossário existente
        if glossary_path.exists():
            existing = json.loads(glossary_path.read_text(encoding="utf-8"))
        else:
            existing = {}

        added_count = 0
        for _table_key, metadata in ai_results.items():
            if not metadata or "columns" not in metadata:
                continue
            for col in metadata["columns"]:
                col_key = col["name"].upper()
                if col_key not in existing and col.get("description"):
                    existing[col_key] = col["description"]
                    added_count += 1

        if added_count > 0:
            glossary_path.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            console.print(f"  [dim]📖 Glossário atualizado: +{added_count} novas entradas[/dim]")

        return added_count

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
