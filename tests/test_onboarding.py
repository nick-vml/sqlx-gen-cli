import pytest
from pathlib import Path

from src.cli.onboarding import is_first_run, ensure_gitignore_entry


def test_is_first_run_true_when_no_settings(tmp_path):
    assert is_first_run(tmp_path / "ai_settings.json") is True


def test_is_first_run_false_when_settings_exist(tmp_path):
    settings_file = tmp_path / "ai_settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    assert is_first_run(settings_file) is False


def test_ensure_gitignore_adds_entry(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n__pycache__\n", encoding="utf-8")

    ensure_gitignore_entry("config/ai_settings.json", gitignore)

    content = gitignore.read_text(encoding="utf-8")
    assert "config/ai_settings.json" in content


def test_ensure_gitignore_no_duplicate(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("config/ai_settings.json\n", encoding="utf-8")

    ensure_gitignore_entry("config/ai_settings.json", gitignore)

    content = gitignore.read_text(encoding="utf-8")
    assert content.count("config/ai_settings.json") == 1


def test_ensure_gitignore_creates_file_if_missing(tmp_path):
    gitignore = tmp_path / ".gitignore"

    ensure_gitignore_entry("config/ai_settings.json", gitignore)

    assert gitignore.exists()
    assert "config/ai_settings.json" in gitignore.read_text(encoding="utf-8")
