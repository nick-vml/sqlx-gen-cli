import pytest
from pathlib import Path

from src.utils.ai_settings import AISettings


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    return tmp_path


@pytest.fixture
def sample_ai_settings() -> AISettings:
    return AISettings(
        enabled=True,
        api_key="sk-or-v1-test-fake-key-abc123",
        model="openai/gpt-4o-mini",
        fallback_models=["google/gemma-4-31b-it:free"],
        max_retries=3,
        timeout_seconds=60,
        max_parallel=3,
        detect_pii=True,
        classify_sensitivity=True,
    )
