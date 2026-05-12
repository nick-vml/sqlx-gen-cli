"""
main.py
--------
CLI do framework de geração SQLX.

Comandos disponíveis:
  generate      — Gera Bronze + Silver a partir de tabelas.json / Parquet
  infer-schema  — Extrai schemas de arquivos .parquet
  enrich-ai     — Enriquece metadata via OpenRouter
  generate-docs — Gera documentação Markdown e data dictionary

O flag --input aceita:
  - Um diretório local:         --input ./parquet/
  - Um prefixo GCS:             --input gs://bucket/dados/
  - Um arquivo único:           --input gs://bucket/dados/a.parquet
  - Múltiplos arquivos (repita)--input gs://bucket/a.parquet --input gs://bucket/b.parquet
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.utils.config_loader import load_config
from src.utils.logger import get_logger

app = typer.Typer(
    name="dataform-generator",
    help="Framework de geração automática de SQLX para Dataform/BigQuery",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()
log = get_logger("main")

# Carrega as variáveis do arquivo .env (como OPENROUTER_API_KEY)
load_dotenv()

# ---------------------------------------------------------------
# Config e Init
# ---------------------------------------------------------------

def _ensure_config() -> str:
    for path in ["config/generator.yaml", "generator.yaml"]:
        if Path(path).exists():
            return path
    
    console.print("[red]Arquivo de configuração (generator.yaml) não encontrado![/red]")
    console.print("Execute [bold cyan]sqlx_gen init[/bold cyan] (ou python main.py init) para inicializar um novo projeto.")
    raise typer.Exit(1)


DEFAULT_YAML = """\
# ============================================================
# Configuração Global do Framework de Geração SQLX
# ============================================================
project:
  name: "dataform-generator"
  version: "1.0.0"

paths:
  parquet_input: "./parquet"
  output_root: "./generated"
  bronze_output: "./generated/bronze"
  silver_output: "./generated/silver"
  docs_output: "./generated/docs"
  metadata_output: "./generated/metadata"

bronze:
  schema: "bronze"
  type: "operations"
  has_output: true
  bucket_env_var: "bucket_name"
  tags: ["bronze"]
  labels:
    owner: "gd"
    confidencialidade: "baixa"

silver:
  schema: "silver"
  type: "table"
  tags: ["silver"]
  partition_by: ""
  cluster_by: []
  labels:
    owner: "gd"
    confidencialidade: "baixa"
  lookback_days: 1
  update_frequency: "diario"
  audit_columns:
    - name: "DT_UPDATED"
      description: "Data da última atualização do registro na tabela"

naming:
  snake_case: true
  normalize_columns: true

datasources_file: "./tabelas.json"
glossary_file: "./glossario.json"

ai:
  enabled: true
  api_key_env: "OPENROUTER_API_KEY"
  model: "openai/gpt-oss-120b:free"
  fallback_models:
    - "openai/gpt-oss-20b:free"
    - "google/gemma-4-31b-it:free"
  max_retries: 3
  timeout_seconds: 60
  detect_pii: true
  classify_sensitivity: true
"""

@app.command(name="init")
def init_project():
    """Inicializa a estrutura padrão para o Dataform Generator no diretório atual."""
    _banner()
    console.rule("[bold]Inicializando projeto[/bold]")
    
    dirs = ["config", "parquet", "generated/bronze", "generated/silver", "generated/metadata", "generated/docs"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]✓[/green] Diretório {d} criado/verificado")
        
    config_file = Path("config/generator.yaml")
    if not config_file.exists():
        config_file.write_text(DEFAULT_YAML, encoding="utf-8")
        console.print(f"  [green]✓[/green] Arquivo {config_file} criado com defaults")
        
    tabelas_file = Path("tabelas.json")
    if not tabelas_file.exists():
        tabelas_file.write_text('[\n  "./parquet/arquivo_exemplo.parquet"\n]\n', encoding="utf-8")
        console.print(f"  [green]✓[/green] Arquivo tabelas.json criado")
        
    env_file = Path(".env")
    if not env_file.exists():
        env_file.write_text('OPENROUTER_API_KEY=sk-or-v1-...\n', encoding="utf-8")
        console.print(f"  [green]✓[/green] Arquivo .env criado")

    console.print("\n[bold green]Projeto inicializado com sucesso![/bold green]")



# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _load_json(path: str) -> dict | list:
    p = Path(path)
    if not p.exists():
        console.print(f"[red]Arquivo não encontrado: {path}[/red]")
        raise typer.Exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _banner():
    console.print(Panel.fit(
        "[bold cyan]Dataform SQLX Generator[/bold cyan]\n"
        "[dim]Parquet -> Schema -> Bronze -> Silver -> AI -> Docs[/dim]",
        border_style="cyan",
    ))


def _resolve_inputs(inputs: list[str], default: str) -> list[str] | str:
    """
    Resolve o argumento --input:
    - Se nenhum foi passado: usa o default (diretório)
    - Se um único foi passado: retorna a string diretamente (pode ser dir ou arquivo)
    - Se múltiplos foram passados: retorna lista de arquivos
    """
    if not inputs:
        return default
    if len(inputs) == 1:
        return inputs[0]
    return inputs


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """Callback para iniciar o modo interativo se nenhum comando for passado."""
    if ctx.invoked_subcommand is None:
        _interactive_menu()


def _interactive_menu():
    from rich.prompt import Prompt, Confirm

    _banner()
    while True:
        console.print("\n[bold]🚀 VML Dataform - SQLX Generator[/bold]")
        console.print("1. [cyan]Gerar[/cyan] arquivos SQLX (Bronze/Silver)")
        console.print("2. [cyan]Inferir[/cyan] Schemas de Parquet")
        console.print("3. [cyan]Gerar Documentação[/cyan] Markdown (AI)")
        console.print("4. [red]Sair[/red]")

        choice = Prompt.ask("\nOpção", choices=["1", "2", "3", "4"], default="1")

        if choice == "4":
            break
        elif choice == "1":
            p = Prompt.ask("Caminho do Parquet (deixe vazio para ler do tabelas.json)", default="")
            input_path = [p] if p else []
            layer = Prompt.ask("Camada a gerar", choices=["bronze", "silver", "both"], default="both")
            db = Prompt.ask("Filtrar por banco (deixe vazio para todos)", default="")
            use_ai = Confirm.ask("Deseja enriquecer os metadados com Inteligência Artificial (OpenRouter)?", default=True)
            generate(input=input_path, output=None, db=db if db else None, layer=layer, ai=use_ai)
        elif choice == "2":
            p = Prompt.ask("Caminho do Parquet (local ou GCS)", default="./parquet")
            out = Prompt.ask("Diretório de saída", default="./generated/metadata")
            infer_schema(input=[p], output=out)
        elif choice == "3":
            p = Prompt.ask("Caminho do Parquet (deixe vazio para ler do tabelas.json)", default="")
            input_path = [p] if p else []
            out = Prompt.ask("Diretório de saída", default="./generated/docs")
            use_ai = Confirm.ask("Deseja documentar com inteligência artificial?", default=True)
            generate_docs(input=input_path, output=out, ai=use_ai)

        if not Confirm.ask("\n[bold]Deseja realizar outra operação?[/bold]", default=True):
            break



# ---------------------------------------------------------------
# Comando: generate
# ---------------------------------------------------------------

@app.command()
def generate(
    input: List[str] = typer.Option([], "--input", "-i", help="Caminho GCS/local. Se vazio, lê do tabelas.json."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Diretório de saída"),
    db: Optional[str] = typer.Option(None, "--db", help="Filtrar por banco (ex: rfb, pgfn)"),
    layer: str = typer.Option("both", "--layer", "-l", help="bronze | silver | both"),
    ai: bool = typer.Option(True, "--ai/--no-ai", help="Habilitar IA"),
):
    """
    Gera arquivos SQLX Bronze e/ou Silver inferindo schemas do Parquet.

    Exemplos:
      python main.py generate --layer both
      python main.py generate --input gs://bucket/rfb/
      python main.py generate --input gs://bucket/a.parquet --input gs://bucket/b.parquet
    """
    _banner()
    config_path = _ensure_config()
    config = load_config(config_path)

    if output:
        config.paths.bronze_output = str(Path(output) / "bronze")
        config.paths.silver_output = str(Path(output) / "silver")

    from src.generators.bronze_generator import BronzeGenerator
    from src.generators.silver_generator import SilverGenerator

    bronze_gen = BronzeGenerator(config)
    glossary: dict = _load_json(config.glossary_file) if Path(config.glossary_file).exists() else {}
    silver_gen = SilverGenerator(config, glossary)

    # Lógica unificada para Parquet
    paths_to_process = input
    if not paths_to_process:
        if Path(config.datasources_file).exists():
            paths_to_process = _load_json(config.datasources_file)
            console.print(f"[dim]Lendo {len(paths_to_process)} caminhos do {config.datasources_file}[/dim]")
        else:
            paths_to_process = [config.paths.parquet_input]

    from src.parquet.schema_extractor import extract_all_schemas
    resolved = _resolve_inputs(paths_to_process, config.paths.parquet_input)
    
    with console.status("[bold cyan]Extraindo schemas do Parquet...[/bold cyan]", spinner="dots"):
        schemas = extract_all_schemas(resolved)

    if not schemas:
        console.print("[yellow]Nenhum schema encontrado.[/yellow]")
        raise typer.Exit(0)

    ai_results = {}
    if layer in ("silver", "both") and config.ai.enabled and ai:
        from src.metadata.metadata_manager import MetadataManager
        manager = MetadataManager(config, glossary=glossary)
        
        with console.status("[bold magenta]Enriquecendo metadata com AI (Isso pode levar alguns minutos)...[/bold magenta]", spinner="bouncingBar"):
            ai_results = manager.enrich_batch(schemas)

    console.rule(f"[bold]Gerando arquivos SQLX ({layer})[/bold]")
    for schema in schemas:
        if db:
            schema.db = db
        if layer in ("bronze", "both"):
            bronze_gen.generate_from_schema(schema, output_dir=config.paths.bronze_output)
        if layer in ("silver", "both"):
            key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
            silver_gen.generate_from_schema(
                schema, 
                ai_metadata=ai_results.get(key), 
                output_dir=config.paths.silver_output
            )
    if layer in ("silver", "both"):
        from rich.panel import Panel
        aviso = (
            "Revise [bold]muito[/bold] o código gerado em [cyan].sqlx[/cyan]!\n"
            "Verifique se as tipagens e formatações estão corretas e utilize as funções padronizadas "
            "do [bold green]utils.js[/bold green] do Dataform para eventuais tratamentos complexos e limpezas."
        )
        console.print(Panel(aviso, title="⚠️  AVISO: Camada Silver", border_style="yellow"))

    console.print("\n[bold green]Geração concluída![/bold green]")


# ---------------------------------------------------------------
# Comando: infer-schema
# ---------------------------------------------------------------

@app.command(name="infer-schema")
def infer_schema(
    input: List[str] = typer.Option([], "--input", "-i", help="Caminho local, GCS ou lista de .parquet. Repita para múltiplos."),
    output: str = typer.Option("./generated/metadata", "--output", "-o", help="Diretório de saída dos schemas JSON"),
):
    """
    Extrai schemas de arquivos .parquet e salva como JSON.

    Exemplos:
      python main.py infer-schema --input gs://bucket/dados/
      python main.py infer-schema --input gs://bucket/rfb/empresas.parquet --input gs://bucket/rfb/socios.parquet
    """
    _banner()
    _ensure_config()
    from src.parquet.schema_extractor import extract_all_schemas, save_schema_json

    resolved = _resolve_inputs(input, "./parquet")
    
    with console.status("[bold cyan]Inferindo schemas do Parquet...[/bold cyan]", spinner="dots"):
        schemas = extract_all_schemas(resolved)

    if not schemas:
        console.print("[yellow]Nenhum arquivo .parquet encontrado.[/yellow]")
        raise typer.Exit(0)

    saved = []
    for schema in schemas:
        path = save_schema_json(schema, output)
        saved.append(path)

    # Exibe tabela resumo
    table = Table(title="Schemas Extraídos")
    table.add_column("Tabela", style="cyan")
    table.add_column("Colunas", justify="right")
    table.add_column("Linhas", justify="right")
    table.add_column("Arquivo JSON")

    for schema, path in zip(schemas, saved):
        table.add_row(
            schema.table_name,
            str(len(schema.columns)),
            f"{schema.row_count:,}",
            path.name,
        )

    console.print(table)
    console.print(f"\n[bold green]{len(saved)} schemas salvos em: {output}[/bold green]")




# ---------------------------------------------------------------
# Comando: generate-docs
# ---------------------------------------------------------------

@app.command(name="generate-docs")
def generate_docs(
    input: List[str] = typer.Option([], "--input", "-i", help="Caminho local, GCS ou lista de .parquet. Repita para múltiplos."),
    output: str = typer.Option("./generated/docs", "--output", "-o", help="Diretório de docs"),
    ai: bool = typer.Option(True, "--ai/--no-ai", help="Habilitar IA"),
):
    """
    Gera documentação Markdown e data dictionary usando as inferências da IA.

    Exemplos:
      python main.py generate-docs --input gs://bucket/dados/
    """
    _banner()
    
    config_path = _ensure_config()
    config = load_config(config_path)

    from src.parquet.schema_extractor import extract_all_schemas
    from src.catalog.doc_generator import DocGenerator
    import json as _json

    resolved = _resolve_inputs(input, "./parquet")
    
    with console.status("[bold cyan]Extraindo schemas do Parquet...[/bold cyan]", spinner="dots"):
        schemas = extract_all_schemas(resolved)

    if not schemas:
        console.print("[yellow]Nenhum schema encontrado.[/yellow]")
        raise typer.Exit(0)

    ai_map: dict[str, dict] = {}
    if config.ai.enabled and ai:
        from src.metadata.metadata_manager import MetadataManager
        glossary: dict = _load_json(config.glossary_file) if Path(config.glossary_file).exists() else {}
        manager = MetadataManager(config, glossary=glossary)
        
        with console.status("[bold magenta]Enriquecendo metadata com AI para documentação...[/bold magenta]", spinner="bouncingBar"):
            ai_map = manager.enrich_batch(schemas)

    with console.status("[bold yellow]Montando arquivos Markdown...[/bold yellow]", spinner="dots"):
        doc_gen = DocGenerator(output)
        for schema in schemas:
            key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
            doc_gen.generate_markdown(schema, ai_metadata=ai_map.get(key))

        doc_gen.generate_data_dictionary(schemas, ai_metadata_map=ai_map)
        doc_gen.generate_index(schemas, ai_metadata_map=ai_map)

    console.print(f"\n[bold green]Documentação gerada em: {output}[/bold green]")


# ---------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------

if __name__ == "__main__":
    app()
