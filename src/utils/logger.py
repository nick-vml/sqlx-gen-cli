"""
src/utils/logger.py
-------------------
Logger estruturado usando Rich para output colorido no terminal.
"""
import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console()


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger configurado com Rich handler."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    return logging.getLogger(name)
