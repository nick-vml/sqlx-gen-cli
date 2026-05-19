from __future__ import annotations

from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from src.utils.ai_settings import AI_SETTINGS_PATH, AISettings, save_ai_settings

console = Console()

POPULAR_MODELS: list[tuple[str, str]] = [
    ("openai/gpt-4o-mini", "rápido, econômico"),
    ("openai/gpt-4o", "mais capaz"),
    ("anthropic/claude-3.5-sonnet", "recomendado"),
    ("google/gemma-4-31b-it:free", "gratuito"),
    ("openai/gpt-oss-120b:free", "gratuito"),
]


def is_first_run(path: Path = AI_SETTINGS_PATH) -> bool:
    return not Path(path).exists()


def ensure_gitignore_entry(entry: str, gitignore_path: Path = Path(".gitignore")) -> None:
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if entry in content:
            return
        updated = content.rstrip("\n") + f"\n{entry}\n"
    else:
        updated = f"{entry}\n"
    gitignore_path.write_text(updated, encoding="utf-8")


def run_onboarding_wizard(settings_path: Path = AI_SETTINGS_PATH) -> AISettings:
    console.print(Panel(
        "[bold cyan]SQLX Gen — Configuração Inicial[/bold cyan]\n"
        "[dim]Vamos configurar a IA em menos de 1 minuto.[/dim]\n\n"
        "[dim]Você pode editar [bold]config/ai_settings.json[/bold] a qualquer momento.[/dim]",
        border_style="cyan",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))

    api_key = Prompt.ask(
        "\n[bold]🔑 API Key do OpenRouter[/bold] [dim](Enter para pular — desativa IA)[/dim]",
        default="",
        password=True,
    )

    enabled = bool(api_key)

    model_lines = "\n".join(
        f"  [bold cyan]{i + 1}.[/bold cyan] [green]{m}[/green] [dim]({desc})[/dim]"
        for i, (m, desc) in enumerate(POPULAR_MODELS)
    )
    model_lines += f"\n  [bold cyan]{len(POPULAR_MODELS) + 1}.[/bold cyan] [yellow]Digitar manualmente[/yellow]"
    console.print(f"\n[bold]🤖 Modelo padrão:[/bold]\n{model_lines}\n")

    choices = [str(i + 1) for i in range(len(POPULAR_MODELS) + 1)]
    choice = Prompt.ask("Selecione", choices=choices, default="3")
    idx = int(choice) - 1

    if idx < len(POPULAR_MODELS):
        model = POPULAR_MODELS[idx][0]
    else:
        model = Prompt.ask("Digite o ID do modelo (ex: openai/gpt-4o-mini)")

    settings = AISettings(enabled=enabled, api_key=api_key, model=model)
    save_ai_settings(settings, settings_path)
    ensure_gitignore_entry("config/ai_settings.json")

    console.print(f"\n  [green]✓[/green] Configuração salva em [cyan]{settings_path}[/cyan]")
    if not enabled:
        console.print("  [yellow]⚠[/yellow]  IA desativada. Edite [cyan]config/ai_settings.json[/cyan] para ativar.\n")
    else:
        console.print("  [green]✓[/green] [cyan]config/ai_settings.json[/cyan] adicionado ao .gitignore\n")

    return settings
