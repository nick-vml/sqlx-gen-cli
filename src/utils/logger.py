"""
src/utils/logger.py
-------------------
Logger estruturado usando Rich para output colorido no terminal.
"""
import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console()

# Inicializa o logging uma única vez no nível do módulo
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger configurado com Rich handler."""
    return logging.getLogger(name)
