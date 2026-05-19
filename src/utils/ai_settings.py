from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

AI_SETTINGS_PATH = Path("config/ai_settings.json")


class AISettings(BaseModel):
    enabled: bool = False
    api_key: str = Field(default="", repr=False)
    model: str = "openai/gpt-4o-mini"
    fallback_models: list[str] = []
    max_retries: int = 3
    timeout_seconds: int = 60
    max_parallel: int = 3
    detect_pii: bool = True
    classify_sensitivity: bool = True

    def resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        return os.getenv("OPENROUTER_API_KEY", "")


def load_ai_settings(path: Path | str = AI_SETTINGS_PATH) -> AISettings:
    p = Path(path)
    if not p.exists():
        return AISettings()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"ai_settings.json inválido: {e}") from e
    return AISettings(**raw)


def save_ai_settings(settings: AISettings, path: Path | str = AI_SETTINGS_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(settings.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
