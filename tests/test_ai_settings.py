import json
import os
import pytest
from pathlib import Path

from src.utils.ai_settings import AISettings, load_ai_settings, save_ai_settings


def test_load_valid_settings(tmp_path):
    settings_file = tmp_path / "ai_settings.json"
    settings_file.write_text(json.dumps({
        "enabled": True,
        "api_key": "sk-or-v1-abc123",
        "model": "openai/gpt-4o",
        "fallback_models": ["google/gemma-4-31b-it:free"],
        "max_retries": 5,
        "timeout_seconds": 90,
        "max_parallel": 2,
        "detect_pii": False,
        "classify_sensitivity": False,
    }), encoding="utf-8")

    settings = load_ai_settings(settings_file)

    assert settings.enabled is True
    assert settings.api_key == "sk-or-v1-abc123"
    assert settings.model == "openai/gpt-4o"
    assert settings.fallback_models == ["google/gemma-4-31b-it:free"]
    assert settings.max_retries == 5
    assert settings.detect_pii is False


def test_load_missing_file_returns_defaults(tmp_path):
    settings = load_ai_settings(tmp_path / "nonexistent.json")

    assert settings.enabled is False
    assert settings.api_key == ""
    assert settings.model == "openai/gpt-4o-mini"


def test_load_invalid_json_raises(tmp_path):
    bad_file = tmp_path / "ai_settings.json"
    bad_file.write_text("{ invalid json", encoding="utf-8")

    with pytest.raises(ValueError, match="ai_settings.json inválido"):
        load_ai_settings(bad_file)


def test_save_and_reload(tmp_path, sample_ai_settings):
    path = tmp_path / "config" / "ai_settings.json"

    save_ai_settings(sample_ai_settings, path)
    reloaded = load_ai_settings(path)

    assert reloaded.enabled == sample_ai_settings.enabled
    assert reloaded.api_key == sample_ai_settings.api_key
    assert reloaded.model == sample_ai_settings.model
    assert reloaded.fallback_models == sample_ai_settings.fallback_models


def test_api_key_not_in_repr(sample_ai_settings):
    r = repr(sample_ai_settings)
    assert "sk-or-v1-test-fake-key-abc123" not in r


def test_resolved_api_key_from_settings(sample_ai_settings):
    assert sample_ai_settings.resolved_api_key() == "sk-or-v1-test-fake-key-abc123"


def test_resolved_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    settings = AISettings(enabled=True, api_key="")
    assert settings.resolved_api_key() == "sk-from-env"


def test_resolved_api_key_empty_when_nothing_set(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = AISettings(enabled=False, api_key="")
    assert settings.resolved_api_key() == ""
