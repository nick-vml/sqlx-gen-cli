"""
main.py
--------
CLI do framework de geração SQLX.

Comandos disponíveis:
  generate      — Gera Bronze + Silver a partir de tabelas.json / Arquivos
  infer-schema  — Extrai schemas de arquivos (.parquet, .csv, .json)
  generate-docs — Gera documentação Markdown e data dictionary
  validate      — Valida os arquivos SQLX gerados

O flag --input aceita:
  - Um diretório local:         --input ./data/
  - Um prefixo GCS:             --input gs://bucket/dados/
  - Um arquivo único:           --input gs://bucket/dados/a.parquet
  - Múltiplos arquivos (repita)--input gs://bucket/a.csv --input gs://bucket/b.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
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
  parquet_input: "./files"
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
  max_parallel: 3
  detect_pii: true
  classify_sensitivity: true
"""

@app.command(name="init")
def init_project():
    """Inicializa a estrutura padrão para o Dataform Generator no diretório atual."""
    _banner()
    console.rule("[bold]Inicializando projeto[/bold]")
    
    dirs = ["config", "files", "generated/bronze", "generated/silver", "generated/metadata", "generated/docs"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]✓[/green] Diretório {d} criado/verificado")
        
    config_file = Path("config/generator.yaml")
    if not config_file.exists():
        config_file.write_text(DEFAULT_YAML, encoding="utf-8")
        console.print(f"  [green]✓[/green] Arquivo {config_file} criado com defaults")
        
    tabelas_file = Path("tabelas.json")
    if not tabelas_file.exists():
        tabelas_file.write_text('[\n  "./files/arquivo_exemplo.parquet"\n]\n', encoding="utf-8")
        console.print("  [green]✓[/green] Arquivo tabelas.json criado")
        
    glossary_file = Path("glossario.json")
    if not glossary_file.exists():
        glossary_file.write_text("{}\n", encoding="utf-8")
        console.print("  [green]✓[/green] Arquivo glossario.json criado")

    from rich.prompt import Prompt
    api_key_input = Prompt.ask("\n[bold cyan]🧠 Insira seu token do OpenRouter[/bold cyan] [dim](Opcional: pressione Enter para ignorar)[/dim]", default="")
    
    txt_content = f"{api_key_input}\n" if api_key_input else "cole-aqui-seu-token-do-openrouter\n"

    txt_key_file = Path("api_key.txt")
    if not txt_key_file.exists():
        txt_key_file.write_text(txt_content, encoding="utf-8")
        console.print("  [green]✓[/green] Arquivo api_key.txt criado")

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
    import pyfiglet
    from rich.align import Align
    
    title = pyfiglet.figlet_format("SQLX Gen", font="slant")
    
    subtitle = (
        "Framework de Geração Autónoma para Dataform & BigQuery\n"
        "[dim]Parquet -> Schema -> Bronze -> Silver -> IA -> Docs[/dim]"
    )

    panel = Panel(
        Align.center(f"[blue]{title}[/blue]\n{subtitle}"),
        border_style="blue",
        box=box.ROUNDED,
        padding=(1, 2)
    )
    console.print(panel)


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


def _display_drift_report(drift_reports: list[dict]):
    """Exibe um relatório visual de schema drift."""
    drifts = [r for r in drift_reports if r and r.get("has_drift")]
    if not drifts:
        return

    console.print()
    table = Table(title="Schema Drift Detectado", border_style="yellow", box=box.MINIMAL_HEAVY_HEAD)
    table.add_column("Tabela", style="default", no_wrap=True)
    table.add_column("+ Colunas", justify="right", style="green")
    table.add_column("- Colunas", justify="right", style="red")
    table.add_column("Tipo Alterado", justify="right", style="yellow")

    for drift in drifts:
        table.add_row(
            drift["table"],
            str(len(drift["added"])),
            str(len(drift["removed"])),
            str(len(drift["type_changed"])),
        )

    console.print(table)

    # Detalhes
    for drift in drifts:
        if drift["added"]:
            console.print(f"  [green]+[/green] [cyan]{drift['table']}[/cyan]: {', '.join(drift['added'])}")
        if drift["removed"]:
            console.print(f"  [red]-[/red] [cyan]{drift['table']}[/cyan]: {', '.join(drift['removed'])}")
        for tc in drift["type_changed"]:
            console.print(f"  [yellow]~[/yellow] [cyan]{drift['table']}.{tc['column']}[/cyan]: [dim]{tc['old_type']} -> {tc['new_type']}[/dim]")
    console.print()


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """Callback para iniciar o modo interativo se nenhum comando for passado."""
    if ctx.invoked_subcommand is None:
        _interactive_menu()


def _interactive_menu():
    from rich.prompt import Prompt, Confirm
    import sys

    # Limpa a tela
    console.clear()
    _banner()
    
    while True:
        menu_text = (
            "[cyan]1.[/cyan] [green]Gerar SQLX[/green] [dim](Cria arquivos Bronze e Silver)[/dim]\n"
            "[dim]2. Inferir Schemas (Inativo)[/dim]\n"
            "[dim]3. Validar SQLX (Inativo)[/dim]\n"
            "[cyan]4.[/cyan] Sair"
        )

        console.print(Panel(menu_text, title="Menu Principal", border_style="default", padding=(1, 2)))

        choice = Prompt.ask("\nSelecione uma opção", choices=["1", "2", "3", "4"], default="1")

        if choice == "4":
            console.print("\n[dim]Encerrando o gerador... Até logo! 👋[/dim]")
            sys.exit(0)
            
        elif choice == "1":
            console.print("\n[dim]─ Configuração da Geração ─[/dim]")
            p = Prompt.ask("📂 Caminho do arquivo/pasta [dim](Vazio = usar tabelas.json)[/dim]", default="")
            input_path = [p] if p else []
            layer = Prompt.ask("🛠️  Camadas", choices=["bronze", "silver", "both"], default="both")
            
            # IA só faz sentido para a camada Silver
            use_ai = False
            force = False
            if layer in ("silver", "both"):
                use_ai = Confirm.ask("🧠 Enriquecer metadados com IA (OpenRouter)?", default=True)
                if use_ai:
                    # Check if API key exists
                    from src.ai.openrouter_client import OpenRouterClient
                    temp_client = OpenRouterClient()
                    if not temp_client.api_key or "cole-aqui" in temp_client.api_key:
                        console.print("\n[yellow]Chave do OpenRouter não encontrada.[/yellow]")
                        console.print("[dim]A IA será desativada. Para ativar, coloque seu token no arquivo api_key.txt[/dim]\n")
                        use_ai = False
                    else:
                        force = Confirm.ask("🔄 Forçar nova análise [dim](ignorar cache existente)[/dim]?", default=False)
            
            console.print()
            generate(input=input_path, output=None, db=None, layer=layer, ai=use_ai, force=force)
            
        elif choice in ("2", "3"):
            console.print("\n[yellow]⚠️  Esta funcionalidade está temporariamente inativa![/yellow]")

        if not Confirm.ask("\nDeseja realizar outra operação?", default=True):
            console.print("\n[dim]Encerrando o gerador... Até logo! 👋[/dim]")
            break
        
        console.clear()
        _banner()



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
    force: bool = typer.Option(False, "--force/--cache", help="Forçar nova análise IA (--force) ou usar cache (--cache)"),
):
    """
    Gera arquivos SQLX Bronze e/ou Silver inferindo schemas de Parquet, CSV ou JSON.

    Exemplos:
      python main.py generate --layer both
      python main.py generate --input gs://bucket/rfb/ --force
      python main.py generate --input gs://bucket/a.csv --input gs://bucket/b.json --cache
    """
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

    from src.extractor.schema_extractor import extract_all_schemas
    with console.status("[dim]Preparando e resolvendo caminhos...[/dim]", spinner="dots"):
        resolved = _resolve_inputs(paths_to_process, config.paths.parquet_input)
        schemas = extract_all_schemas(resolved)

    if not schemas:
        console.print("[yellow]Nenhum schema encontrado.[/yellow]")
        raise typer.Exit(0)

    # --- Schema Drift Detection ---
    from src.metadata.metadata_manager import MetadataManager
    manager = MetadataManager(config, glossary=glossary, force=force)

    drift_reports = []
    for schema in schemas:
        drift = manager.detect_drift_from_saved(schema)
        if drift:
            drift_reports.append(drift)

    if drift_reports:
        _display_drift_report(drift_reports)

    # --- Enriquecimento com IA ---
    ai_results = {}
    if layer in ("silver", "both") and config.ai.enabled and ai:
        mode_label = "[red]FORCE[/red]" if force else "[green]CACHE[/green]"
        with console.status(f"[dim]Enriquecendo metadata com IA ({mode_label})...[/dim]", spinner="dots"):
            ai_results = manager.enrich_batch(schemas)

        # Auto-aprendizado do glossário
        new_entries = manager.update_glossary(ai_results, config.glossary_file)
        if new_entries:
            console.print(f"[dim]📖 Glossário auto-atualizado com {new_entries} novas entradas[/dim]")

    # --- Confirmação para arquivo único ---
    if len(schemas) == 1:
        schema = schemas[0]
        from rich.prompt import Prompt, Confirm
        
        # Previsão do nome final
        p_db = db or schema.db or "raw"
        p_table = schema.table_name
        
        console.print("\n[yellow]Confirmação de Nome[/yellow]")
        console.print(f"Origem: [dim]{schema.source_file}[/dim]")
        
        if not Confirm.ask(f"O nome do arquivo gerado será [green]{p_db}_{p_table}.sqlx[/green]. Está correto?", default=True):
            schema.db = Prompt.ask("Informe o nome do Banco (Dataset)", default=p_db)
            schema.table_name = Prompt.ask("Informe o nome da Tabela", default=p_table)
            console.print(f"Ajustado para: [green]{schema.db}_{schema.table_name}.sqlx[/green]\n")
        else:
            schema.db = p_db # Garante que o banco seja fixado

    console.rule(f"[dim]Gerando arquivos SQLX ({layer})[/dim]")
    for schema in schemas:
        # Se foi passado via flag --db, sobrecarrega o schema (exceto se já confirmamos acima)
        if db and len(schemas) > 1:
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
        aviso = (
            "Revise o código gerado em [cyan].sqlx[/cyan]!\n"
            "Verifique se as tipagens e formatações estão corretas e utilize as funções padronizadas "
            "do [green]utils.js[/green] do Dataform para eventuais tratamentos complexos e limpezas."
        )
        console.print()
        console.print(Panel(aviso, title="[yellow]Atenção: Camada Silver[/yellow]", border_style="yellow", padding=(1, 2)))

    console.print("\n[green]Geração concluída com sucesso.[/green]\n")


# ---------------------------------------------------------------
# Comando: infer-schema
# ---------------------------------------------------------------

@app.command(name="infer-schema")
def infer_schema(
    input: List[str] = typer.Option([], "--input", "-i", help="Caminho local, GCS ou lista de arquivos (.parquet, .csv, .json). Repita para múltiplos."),
    output: str = typer.Option("./generated/metadata", "--output", "-o", help="Diretório de saída dos schemas JSON"),
):
    """
    Extrai schemas de arquivos .parquet e salva como JSON.

    Exemplos:
      python main.py infer-schema --input gs://bucket/dados/
      python main.py infer-schema --input gs://bucket/rfb/empresas.parquet --input gs://bucket/rfb/socios.parquet
    """
    _ensure_config()
    from src.extractor.schema_extractor import extract_all_schemas, save_schema_json

    resolved = _resolve_inputs(input, "./files")
    
    with console.status("[dim]Inferindo schemas dos arquivos...[/dim]", spinner="dots"):
        schemas = extract_all_schemas(resolved)

    if not schemas:
        console.print("[yellow]Nenhum arquivo compatível encontrado.[/yellow]")
        raise typer.Exit(0)

    saved = []
    for schema in schemas:
        path = save_schema_json(schema, output)
        saved.append(path)

    # Exibe tabela resumo
    table = Table(title="Schemas Extraídos", box=box.SIMPLE_HEAD)
    table.add_column("Tabela", style="default", no_wrap=True)
    table.add_column("Colunas", justify="right", style="default")
    table.add_column("Linhas", justify="right", style="default")
    table.add_column("Amostra", justify="right", style="dim")
    table.add_column("Arquivo JSON", style="dim")

    for schema, path in zip(schemas, saved):
        table.add_row(
            schema.table_name,
            str(len(schema.columns)),
            f"{schema.row_count:,}",
            f"{len(schema.sample_data)} linhas",
            path.name,
        )

    console.print(table)
    console.print(f"\n[green]{len(saved)} schemas salvos em: {output}[/green]\n")


# ---------------------------------------------------------------
# Comando: validate
# ---------------------------------------------------------------

@app.command(name="validate")
def validate(
    directory: str = typer.Option("./generated/silver", "--dir", "-d", help="Diretório com arquivos .sqlx para validar"),
):
    """
    Valida os arquivos SQLX gerados, verificando:
    - Sintaxe do bloco config
    - Aliases duplicados no SELECT
    - CASTs ausentes
    - Consistência entre columns e SELECT

    Exemplos:
      python main.py validate --dir ./generated/silver
    """
    console.rule("[dim]Validando arquivos SQLX[/dim]")

    sqlx_dir = Path(directory)
    if not sqlx_dir.exists():
        console.print(f"[red]Diretório não encontrado:[/red] {directory}")
        raise typer.Exit(1)

    sqlx_files = list(sqlx_dir.glob("*.sqlx"))
    if not sqlx_files:
        console.print(f"[yellow]Nenhum arquivo .sqlx encontrado em {directory}[/yellow]")
        raise typer.Exit(0)

    total_issues = 0

    for file_path in sqlx_files:
        content = file_path.read_text(encoding="utf-8")
        issues: list[str] = []

        # 1. Verifica se tem bloco config
        if "config {" not in content:
            issues.append("Bloco `config {}` não encontrado")

        # 2. Extrai aliases do SELECT (AS NOME_COLUNA)
        aliases = re.findall(r'\bAS\s+(\w+)', content, re.IGNORECASE)
        seen: dict[str, int] = {}
        for alias in aliases:
            upper = alias.upper()
            seen[upper] = seen.get(upper, 0) + 1
        duplicates = [name for name, count in seen.items() if count > 1]
        if duplicates:
            issues.append(f"Aliases duplicados: {', '.join(duplicates)}")

        # 3. Verifica colunas no bloco columns vs aliases no SELECT
        columns_match = re.search(r'columns:\s*\{([^}]+)\}', content, re.DOTALL)
        if columns_match:
            doc_cols = set(re.findall(r'(\w+):', columns_match.group(1)))
            sel_cols = {a.upper() for a in aliases}
            
            # Colunas documentadas mas ausentes no SELECT
            missing_in_select = doc_cols - sel_cols
            if missing_in_select:
                issues.append(f"Documentadas mas ausentes no SELECT: {', '.join(missing_in_select)}")

        # 4. Verifica se há colunas sem CAST
        select_block = content.split("SELECT")[-1] if "SELECT" in content else ""
        raw_cols = re.findall(r'^\s+(\w+)\s+AS\s+', select_block, re.MULTILINE)
        if raw_cols:
            issues.append(f"Colunas sem CAST/SAFE_CAST: {', '.join(raw_cols)}")

        # Output
        if issues:
            total_issues += len(issues)
            console.print(f"\n[yellow]{file_path.name}[/yellow]")
            for issue in issues:
                console.print(f"  [red]->[/red] {issue}")
        else:
            console.print(f"  [green]✓[/green] [dim]{file_path.name}[/dim]")

    console.print()
    if total_issues == 0:
        console.print(Panel(f"[green]Todos os {len(sqlx_files)} arquivos foram validados sem problemas.[/green]", border_style="green"))
    else:
        console.print(Panel(f"[red]{total_issues} problema(s) encontrado(s) em {len(sqlx_files)} arquivo(s)[/red]", border_style="red"))


# ---------------------------------------------------------------
# Comando: generate-docs
# ---------------------------------------------------------------

@app.command(name="generate-docs")
def generate_docs(
    input: List[str] = typer.Option([], "--input", "-i", help="Caminho local, GCS ou lista de arquivos. Repita para múltiplos."),
    output: str = typer.Option("./generated/docs", "--output", "-o", help="Diretório de docs"),
    ai: bool = typer.Option(True, "--ai/--no-ai", help="Habilitar IA"),
    force: bool = typer.Option(False, "--force/--cache", help="Forçar nova análise IA"),
):
    """
    Gera documentação Markdown e data dictionary usando as inferências da IA.

    Exemplos:
      python main.py generate-docs --input gs://bucket/dados/
      python main.py generate-docs --force
    """
    
    config_path = _ensure_config()
    config = load_config(config_path)

    from src.extractor.schema_extractor import extract_all_schemas
    from src.catalog.doc_generator import DocGenerator

    resolved = _resolve_inputs(input, "./files")
    
    with console.status("[dim]Extraindo schemas dos arquivos...[/dim]", spinner="dots"):
        schemas = extract_all_schemas(resolved)

    if not schemas:
        console.print("[yellow]Nenhum schema encontrado.[/yellow]")
        raise typer.Exit(0)

    ai_map: dict[str, dict] = {}
    if config.ai.enabled and ai:
        from src.metadata.metadata_manager import MetadataManager
        glossary: dict = _load_json(config.glossary_file) if Path(config.glossary_file).exists() else {}
        manager = MetadataManager(config, glossary=glossary, force=force)

        with console.status("[dim]Enriquecendo metadata com IA para documentação...[/dim]", spinner="dots"):
            ai_map = manager.enrich_batch(schemas)

    with console.status("[dim]Montando arquivos Markdown...[/dim]", spinner="dots"):
        doc_gen = DocGenerator(output)
        for schema in schemas:
            key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
            doc_gen.generate_markdown(schema, ai_metadata=ai_map.get(key))

        doc_gen.generate_data_dictionary(schemas, ai_metadata_map=ai_map)
        doc_gen.generate_index(schemas, ai_metadata_map=ai_map)

    console.print(f"\n[green]Documentação gerada em: {output}[/green]")


# ---------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------

if __name__ == "__main__":
    app()
