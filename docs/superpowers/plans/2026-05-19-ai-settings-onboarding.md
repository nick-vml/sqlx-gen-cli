# AI Settings + Onboarding + Unit Tests — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidar toda configuração de IA em `config/ai_settings.json`, remover `api_key.txt`, adicionar wizard de onboarding na primeira execução, e cobrir os módulos críticos com testes unitários.

**Architecture:** Um novo módulo `src/utils/ai_settings.py` define `AISettings` (Pydantic) com `resolved_api_key()` que implementa a prioridade `ai_settings.json > OPENROUTER_API_KEY env`. Um módulo `src/cli/onboarding.py` detecta primeira execução e dispara wizard Rich interativo. `main.py` chama `_load_ai_settings()` no início de cada comando, que executa o wizard se necessário. `MetadataManager` recebe `AISettings` diretamente no lugar de `config.ai`.

**Tech Stack:** Python 3.9+, Pydantic v2, Rich, Typer, pytest, unittest.mock, httpx (já instalado via openai SDK)

---

## Mapa de arquivos

| Ação | Arquivo |
|------|---------|
| Criar | `src/utils/ai_settings.py` |
| Criar | `src/cli/__init__.py` |
| Criar | `src/cli/onboarding.py` |
| Criar | `tests/__init__.py` |
| Criar | `tests/conftest.py` |
| Criar | `tests/test_ai_settings.py` |
| Criar | `tests/test_onboarding.py` |
| Criar | `tests/test_openrouter_client.py` |
| Criar | `tests/test_config_loader.py` |
| Criar | `pytest.ini` |
| Modificar | `requirements.txt` |
| Modificar | `src/ai/openrouter_client.py` |
| Modificar | `src/utils/config_loader.py` |
| Modificar | `src/metadata/metadata_manager.py` |
| Modificar | `main.py` |
| Modificar | `config/generator.yaml` |
| Modificar | `.gitignore` |

---

## Task 0: Setup — pytest + conftest

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Adicionar pytest ao requirements.txt**

Adicionar ao final de `requirements.txt`:
```
pytest>=8.0.0
pytest-mock>=3.0.0
```

- [ ] **Step 2: Criar pytest.ini**

Criar `pytest.ini` na raiz do projeto:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 3: Criar tests/__init__.py**

Criar `tests/__init__.py` vazio.

- [ ] **Step 4: Criar tests/conftest.py**

Somente o fixture sem AISettings — o `sample_ai_settings` será adicionado em Task 1 após o módulo existir:
```python
import pytest
from pathlib import Path


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    return tmp_path
```

- [ ] **Step 5: Instalar dependências de teste**

```bash
pip install pytest pytest-mock
```

- [ ] **Step 6: Verificar que pytest está funcionando**

```bash
pytest --collect-only
```

Esperado: `no tests ran` ou `0 items` — sem erros de import.

- [ ] **Step 7: Commit**

```bash
git add pytest.ini tests/__init__.py tests/conftest.py requirements.txt
git commit -m "test: setup pytest infrastructure and conftest fixtures"
```

---

## Task 1: src/utils/ai_settings.py + tests

**Files:**
- Create: `src/utils/ai_settings.py`
- Create: `tests/test_ai_settings.py`

- [ ] **Step 1: Escrever os testes primeiro (TDD)**

Criar `tests/test_ai_settings.py`:
```python
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
```

- [ ] **Step 2: Confirmar que os testes falham**

```bash
pytest tests/test_ai_settings.py -v
```

Esperado: `ImportError: cannot import name 'AISettings' from 'src.utils.ai_settings'`

- [ ] **Step 3: Adicionar fixture sample_ai_settings ao conftest.py**

Atualizar `tests/conftest.py` adicionando ao final do arquivo:
```python
from src.utils.ai_settings import AISettings


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
```

- [ ] **Step 5: Implementar src/utils/ai_settings.py**

Criar `src/utils/ai_settings.py`:
```python
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
```

- [ ] **Step 6: Confirmar que os testes passam**

```bash
pytest tests/test_ai_settings.py -v
```

Esperado: `8 passed`

- [ ] **Step 7: Commit**

```bash
git add src/utils/ai_settings.py tests/test_ai_settings.py tests/conftest.py
git commit -m "feat: add AISettings model with load/save and resolved_api_key priority logic"
```

---

## Task 2: src/cli/onboarding.py + tests

**Files:**
- Create: `src/cli/__init__.py`
- Create: `src/cli/onboarding.py`
- Create: `tests/test_onboarding.py`

- [ ] **Step 1: Escrever os testes primeiro**

Criar `tests/test_onboarding.py`:
```python
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
```

- [ ] **Step 2: Confirmar que os testes falham**

```bash
pytest tests/test_onboarding.py -v
```

Esperado: `ImportError: cannot import name 'is_first_run' from 'src.cli.onboarding'`

- [ ] **Step 3: Criar src/cli/__init__.py**

Criar `src/cli/__init__.py` vazio.

- [ ] **Step 4: Implementar src/cli/onboarding.py**

Criar `src/cli/onboarding.py`:
```python
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
```

- [ ] **Step 5: Confirmar que os testes passam**

```bash
pytest tests/test_onboarding.py -v
```

Esperado: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add src/cli/__init__.py src/cli/onboarding.py tests/test_onboarding.py
git commit -m "feat: add onboarding wizard with first-run detection and gitignore helper"
```

---

## Task 3: Simplificar OpenRouterClient + tests

**Files:**
- Modify: `src/ai/openrouter_client.py`
- Create: `tests/test_openrouter_client.py`

- [ ] **Step 1: Escrever os testes primeiro**

Criar `tests/test_openrouter_client.py`:
```python
from unittest.mock import MagicMock, patch

import pytest

from src.ai.openrouter_client import AIResponse, OpenRouterClient


def test_chat_no_api_key_returns_empty():
    client = OpenRouterClient(api_key="", primary_model="openai/gpt-4o-mini")
    result = client.chat([{"role": "user", "content": "hello"}])

    assert result.model_used == "none"
    assert result.raw_content == ""
    assert result.parsed is None


def test_parse_json_from_markdown_block():
    raw = '```json\n{"key": "value"}\n```'
    result = OpenRouterClient._parse_json(raw)
    assert result == {"key": "value"}


def test_parse_json_plain():
    raw = '{"name": "test", "value": 42}'
    result = OpenRouterClient._parse_json(raw)
    assert result == {"name": "test", "value": 42}


def test_parse_json_embedded_in_text():
    raw = 'Aqui está o resultado: {"status": "ok"} fim.'
    result = OpenRouterClient._parse_json(raw)
    assert result == {"status": "ok"}


def test_chat_success():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"description": "test table"}'
    mock_response.usage.total_tokens = 42

    client = OpenRouterClient(api_key="sk-test", primary_model="openai/gpt-4o-mini")

    with patch.object(client._client.chat.completions, "create", return_value=mock_response):
        result = client.chat([{"role": "user", "content": "hello"}])

    assert result.model_used == "openai/gpt-4o-mini"
    assert result.parsed == {"description": "test table"}
    assert result.tokens_used == 42


def test_chat_fallback_on_model_failure():
    fallback_response = AIResponse(
        model_used="google/gemma-4-31b-it:free",
        raw_content='{"ok": true}',
        parsed={"ok": True},
    )

    client = OpenRouterClient(
        api_key="sk-test",
        primary_model="openai/gpt-4o-mini",
        fallback_models=["google/gemma-4-31b-it:free"],
    )

    def mock_try_model(model, messages, expect_json, temperature):
        if model == "openai/gpt-4o-mini":
            return None
        return fallback_response

    with patch.object(client, "_try_model", side_effect=mock_try_model):
        result = client.chat([{"role": "user", "content": "hello"}])

    assert result.model_used == "google/gemma-4-31b-it:free"
    assert result.parsed == {"ok": True}


def test_retry_on_rate_limit():
    import httpx
    from openai import RateLimitError

    mock_success = MagicMock()
    mock_success.choices[0].message.content = '{"retried": true}'
    mock_success.usage.total_tokens = 5

    client = OpenRouterClient(api_key="sk-test", primary_model="openai/gpt-4o-mini", max_retries=2)

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError(
                "rate limit exceeded",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
                ),
                body=None,
            )
        return mock_success

    with patch.object(client._client.chat.completions, "create", side_effect=side_effect):
        with patch("src.ai.openrouter_client.time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.monotonic = MagicMock(return_value=0.0)
            result = client.chat([{"role": "user", "content": "hello"}])

    assert result.parsed == {"retried": True}
    assert result.retries == 1


def test_no_api_key_env_fallback_in_client():
    """OpenRouterClient does NOT read env vars itself — resolution is done by AISettings."""
    import os
    os.environ["OPENROUTER_API_KEY"] = "sk-should-not-be-used"
    client = OpenRouterClient(api_key="", primary_model="openai/gpt-4o-mini")
    result = client.chat([{"role": "user", "content": "test"}])
    del os.environ["OPENROUTER_API_KEY"]

    assert result.model_used == "none"
```

- [ ] **Step 2: Confirmar que os testes falham**

```bash
pytest tests/test_openrouter_client.py -v
```

Esperado: vários testes falham porque a assinatura do construtor ainda tem `api_key_env` e o fallback `api_key.txt`.

- [ ] **Step 3: Reescrever src/ai/openrouter_client.py**

Substituir o conteúdo completo de `src/ai/openrouter_client.py`:
```python
from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI, APIError, RateLimitError, APITimeoutError
from pydantic import BaseModel

from src.utils.logger import get_logger

log = get_logger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class AIResponse(BaseModel):
    model_used: str
    raw_content: str
    parsed: dict[str, Any] | None = None
    tokens_used: int = 0
    latency_ms: int = 0
    retries: int = 0


class OpenRouterClient:
    """
    Client OpenRouter com retry exponencial e fallback entre modelos.

    A API key deve ser resolvida externamente via AISettings.resolved_api_key()
    antes de instanciar este client. O client não lê variáveis de ambiente.
    """

    def __init__(
        self,
        api_key: str | None,
        primary_model: str = "anthropic/claude-3.5-sonnet",
        fallback_models: list[str] | None = None,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        self.api_key = api_key or ""
        self.primary_model = primary_model
        self.fallback_models = fallback_models or []
        self.max_retries = max_retries
        self.timeout = timeout

        self._client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=self.api_key or "NO_KEY",
        )

    def chat(
        self,
        messages: list[dict],
        expect_json: bool = True,
        temperature: float = 0.2,
    ) -> AIResponse:
        if not self.api_key:
            log.debug("API key ausente. Configure via config/ai_settings.json ou OPENROUTER_API_KEY.")
            return AIResponse(model_used="none", raw_content="", parsed=None)

        models = [self.primary_model] + self.fallback_models

        for model in models:
            result = self._try_model(model, messages, expect_json, temperature)
            if result is not None:
                return result
            log.warning(f"Modelo {model} falhou. Tentando próximo...")

        log.error("Todos os modelos falharam.")
        return AIResponse(model_used="none", raw_content="", parsed=None)

    def _try_model(
        self,
        model: str,
        messages: list[dict],
        expect_json: bool,
        temperature: float,
    ) -> AIResponse | None:
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info(f"[{model}] tentativa {attempt}/{self.max_retries}...")
                start = time.monotonic()

                completion = self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=self.timeout,
                )

                elapsed_ms = int((time.monotonic() - start) * 1000)
                raw = completion.choices[0].message.content or ""
                tokens = completion.usage.total_tokens if completion.usage else 0
                parsed = self._parse_json(raw) if expect_json else None

                log.info(f"  {model} — {tokens} tokens — {elapsed_ms}ms")
                return AIResponse(
                    model_used=model,
                    raw_content=raw,
                    parsed=parsed,
                    tokens_used=tokens,
                    latency_ms=elapsed_ms,
                    retries=attempt - 1,
                )

            except RateLimitError:
                wait = 2 ** attempt
                log.warning(f"  Rate limit. Aguardando {wait}s...")
                time.sleep(wait)

            except APITimeoutError:
                log.warning(f"  Timeout na tentativa {attempt}.")

            except APIError as e:
                log.error(f"  API error: {e}")
                return None

        return None

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(clean[start:end])
                except json.JSONDecodeError:
                    pass
        return None
```

- [ ] **Step 4: Confirmar que os testes passam**

```bash
pytest tests/test_openrouter_client.py -v
```

Esperado: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ai/openrouter_client.py tests/test_openrouter_client.py
git commit -m "refactor: simplify OpenRouterClient — remove api_key.txt fallback, api_key resolved externally"
```

---

## Task 4: Atualizar config_loader.py + tests

**Files:**
- Modify: `src/utils/config_loader.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Escrever os testes primeiro**

Criar `tests/test_config_loader.py`:
```python
import textwrap
import pytest
from pathlib import Path

from src.utils.config_loader import GeneratorConfig, load_config


def test_load_valid_yaml(tmp_path):
    yaml_file = tmp_path / "generator.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        project:
          name: "my-project"
          version: "2.0.0"
        paths:
          bronze_output: "./out/bronze"
          silver_output: "./out/silver"
        bronze:
          schema: "bronze"
          type: "operations"
          has_output: true
          bucket_env_var: "MY_BUCKET"
          tags: ["bronze"]
        silver:
          schema: "silver"
          type: "table"
          tags: ["silver"]
        naming:
          snake_case: true
          normalize_columns: true
        datasources_file: "./data.json"
        glossary_file: "./gloss.json"
    """), encoding="utf-8")

    config = load_config(str(yaml_file))

    assert config.project.name == "my-project"
    assert config.project.version == "2.0.0"
    assert config.paths.bronze_output == "./out/bronze"
    assert config.bronze.schema_name == "bronze"
    assert config.silver.type == "table"
    assert config.naming.snake_case is True
    assert config.datasources_file == "./data.json"


def test_load_missing_yaml_returns_defaults(tmp_path):
    config = load_config(str(tmp_path / "nonexistent.yaml"))

    assert isinstance(config, GeneratorConfig)
    assert config.project.name == "dataform-generator"
    assert config.paths.bronze_output == "./generated/bronze"


def test_generator_config_has_no_ai_field():
    config = GeneratorConfig()
    assert not hasattr(config, "ai"), (
        "GeneratorConfig não deve ter campo 'ai' — config de IA pertence ao AISettings"
    )
```

- [ ] **Step 2: Confirmar que test_generator_config_has_no_ai_field falha**

```bash
pytest tests/test_config_loader.py::test_generator_config_has_no_ai_field -v
```

Esperado: `FAILED` — `GeneratorConfig` ainda tem o campo `ai`.

- [ ] **Step 3: Remover AIConfig de config_loader.py**

Substituir o conteúdo completo de `src/utils/config_loader.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    name: str = "dataform-generator"
    version: str = "1.0.0"


class PathsConfig(BaseModel):
    parquet_input: str = "./parquet"
    output_root: str = "./generated"
    bronze_output: str = "./generated/bronze"
    silver_output: str = "./generated/silver"
    docs_output: str = "./generated/docs"
    metadata_output: str = "./generated/metadata"


class BronzeConfig(BaseModel):
    schema_name: str = Field("bronze", alias="schema")
    type: str = "operations"
    has_output: bool = True
    bucket_env_var: str = "bucket_name"
    tags: list[str] = ["bronze"]
    labels: dict[str, str] = {}

    model_config = {"populate_by_name": True}


class AuditColumn(BaseModel):
    name: str
    description: str


class SilverConfig(BaseModel):
    schema_name: str = Field("silver", alias="schema")
    type: str = "table"
    tags: list[str] = ["silver"]
    partition_by: str = ""
    cluster_by: list[str] = []
    labels: dict[str, str] = {}
    lookback_days: int = 1
    update_frequency: str = "diario"
    audit_columns: list[AuditColumn] = []

    model_config = {"populate_by_name": True}


class NamingConfig(BaseModel):
    snake_case: bool = True
    normalize_columns: bool = True


class GeneratorConfig(BaseModel):
    project: ProjectConfig = ProjectConfig()
    paths: PathsConfig = PathsConfig()
    bronze: BronzeConfig = BronzeConfig()
    silver: SilverConfig = SilverConfig()
    naming: NamingConfig = NamingConfig()
    datasources_file: str = "./tabelas.json"
    glossary_file: str = "./glossario.json"


def load_config(config_path: str = "config/generator.yaml") -> GeneratorConfig:
    path = Path(config_path)
    if not path.exists():
        return GeneratorConfig()
    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    raw.pop("ai", None)  # ignora seção ai: legada se ainda existir no YAML
    return GeneratorConfig(**raw)
```

- [ ] **Step 4: Confirmar que todos os testes passam**

```bash
pytest tests/test_config_loader.py -v
```

Esperado: `3 passed`

- [ ] **Step 5: Rodar todos os testes para garantir que nada quebrou**

```bash
pytest -v
```

Esperado: todos os testes passam.

- [ ] **Step 6: Commit**

```bash
git add src/utils/config_loader.py tests/test_config_loader.py
git commit -m "refactor: remove AIConfig from GeneratorConfig — AI config now lives in AISettings"
```

---

## Task 5: Atualizar MetadataManager

**Files:**
- Modify: `src/metadata/metadata_manager.py`

> Sem novos testes nesta tarefa — os módulos que MetadataManager usa já estão cobertos. Verificação via suite completa.

- [ ] **Step 1: Atualizar o construtor e referências a config.ai**

Substituir o conteúdo completo de `src/metadata/metadata_manager.py`:
```python
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from rich.console import Console

from src.extractor.schema_extractor import TableSchema
from src.ai.openrouter_client import OpenRouterClient
from src.ai.prompt_builder import build_enrichment_prompt
from src.utils.ai_settings import AISettings
from src.utils.config_loader import GeneratorConfig
from src.utils.logger import get_logger

log = get_logger(__name__)
console = Console()


class MetadataManager:
    def __init__(
        self,
        config: GeneratorConfig,
        ai_settings: AISettings,
        ai_client: OpenRouterClient | None = None,
        glossary: dict[str, str] | None = None,
        force: bool = False,
    ):
        self.config = config
        self._ai_settings = ai_settings
        self.glossary = glossary or {}
        self.force = force
        self._ai = ai_client or OpenRouterClient(
            api_key=ai_settings.resolved_api_key(),
            primary_model=ai_settings.model,
            fallback_models=ai_settings.fallback_models,
            max_retries=ai_settings.max_retries,
            timeout=ai_settings.timeout_seconds,
        )
        self._metadata_dir = Path(config.paths.metadata_output)
        self._metadata_dir.mkdir(parents=True, exist_ok=True)

    def enrich(self, schema: TableSchema) -> dict[str, Any]:
        if not self._ai_settings.enabled:
            log.info("  AI desabilitada na configuração.")
            return {}

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
        results: dict[str, dict] = {}
        total = len(schemas)
        max_workers = min(self._ai_settings.max_parallel, total)

        if max_workers <= 1 or total == 1:
            for i, schema in enumerate(schemas, 1):
                key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
                console.print(f"  [cyan][{i}/{total}][/cyan] {key}")
                try:
                    results[key] = self.enrich(schema)
                except Exception as e:
                    log.error(f"  Erro ao enriquecer {key}: {e}")
                    results[key] = {}
            return results

        console.print(f"  [dim]⚡ Processamento paralelo com {max_workers} workers[/dim]")

        def _process(idx: int, schema: TableSchema) -> tuple[str, dict]:
            key = f"{schema.db}_{schema.table_name}" if schema.db else schema.table_name
            console.print(f"  [cyan][{idx}/{total}][/cyan] {key}")
            try:
                return key, self.enrich(schema)
            except Exception as e:
                log.error(f"  Erro ao enriquecer {key}: {e}")
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

    def detect_schema_drift(self, old_schema: TableSchema, new_schema: TableSchema) -> dict[str, Any]:
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
                f"  Schema drift em {new_schema.table_name}: "
                f"+{len(added)} cols, -{len(removed)} cols, {len(type_changed)} tipo(s)"
            )

        return report

    def detect_drift_from_saved(self, schema: TableSchema) -> dict[str, Any] | None:
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
            log.warning(f"  Não foi possível carregar schema anterior: {e}")
            return None

    def update_glossary(self, ai_results: dict[str, dict], glossary_path: str | Path) -> int:
        glossary_path = Path(glossary_path)
        existing = json.loads(glossary_path.read_text(encoding="utf-8")) if glossary_path.exists() else {}

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

        return added_count

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
```

- [ ] **Step 2: Rodar todos os testes**

```bash
pytest -v
```

Esperado: todos passam.

- [ ] **Step 3: Commit**

```bash
git add src/metadata/metadata_manager.py
git commit -m "refactor: MetadataManager receives AISettings directly instead of config.ai"
```

---

## Task 6: Atualizar main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Adicionar helper _load_ai_settings e atualizar imports**

No topo de `main.py`, logo após os imports existentes, substituir:
```python
from src.utils.config_loader import load_config
from src.utils.logger import get_logger
```
por:
```python
from src.utils.config_loader import load_config
from src.utils.logger import get_logger
from src.utils.ai_settings import load_ai_settings as _load_ai_settings_file
```

- [ ] **Step 2: Adicionar função _load_ai_settings após _ensure_config**

Adicionar após a função `_ensure_config()` (por volta da linha 58):
```python
def _load_ai_settings():
    from src.cli.onboarding import is_first_run, run_onboarding_wizard
    import yaml

    if Path("api_key.txt").exists():
        console.print(
            "[yellow]⚠️  Arquivo api_key.txt encontrado — este arquivo não é mais utilizado.[/yellow]\n"
            "[dim]Sua API key deve estar em [bold]config/ai_settings.json[/bold].[/dim]\n"
        )

    for yaml_path in ["config/generator.yaml", "generator.yaml"]:
        p = Path(yaml_path)
        if p.exists():
            try:
                raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                if "ai" in raw:
                    console.print(
                        f"[yellow]⚠️  Seção 'ai:' encontrada em {yaml_path} — não é mais lida.[/yellow]\n"
                        "[dim]Você pode remover esse bloco do YAML com segurança.[/dim]\n"
                    )
            except Exception:
                pass

    if is_first_run():
        return run_onboarding_wizard()
    return _load_ai_settings_file()
```

- [ ] **Step 3: Atualizar init_project — remover api_key.txt, usar wizard**

Substituir o bloco de criação do `api_key.txt` em `init_project()` (linhas 148–156 aprox.):

**Antes:**
```python
from rich.prompt import Prompt
api_key_input = Prompt.ask("\n[bold cyan]🧠 Insira seu token do OpenRouter[/bold cyan] [dim](Opcional: pressione Enter para ignorar)[/dim]", default="")

txt_content = f"{api_key_input}\n" if api_key_input else "cole-aqui-seu-token-do-openrouter\n"

txt_key_file = Path("api_key.txt")
if not txt_key_file.exists():
    txt_key_file.write_text(txt_content, encoding="utf-8")
    console.print("  [green]✓[/green] Arquivo api_key.txt criado")

console.print("\n[bold green]Projeto inicializado com sucesso![/bold green]")
```

**Depois:**
```python
console.print("\n[bold green]Projeto inicializado com sucesso![/bold green]")
console.print("\n[dim]Configurando integração com IA...[/dim]")
from src.cli.onboarding import run_onboarding_wizard
run_onboarding_wizard()
```

- [ ] **Step 4: Atualizar DEFAULT_YAML — remover seção ai:**

No `DEFAULT_YAML` (constante em main.py), remover o bloco:
```yaml
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
```

- [ ] **Step 5: Atualizar _interactive_menu — remover verificação com OpenRouterClient**

Substituir o bloco de verificação da API key na seleção da opção 1 do menu:

**Antes:**
```python
use_ai = False
force = False
if layer in ("silver", "both"):
    use_ai = Confirm.ask("🧠 Enriquecer metadados com IA (OpenRouter)?", default=True)
    if use_ai:
        # Check if API key exists
        from src.ai.openrouter_client import OpenRouterClient
        temp_client = OpenRouterClient()
        if not temp_client.api_key or "cole-aqui" in temp_client.api_key:
            console.print("\n[bold yellow]⚠️  AVISO: Chave do OpenRouter não encontrada![/bold yellow]")
            console.print("[dim]A IA será desativada. Para ativar, coloque seu token no arquivo [bold]api_key.txt[/bold][/dim]\n")
            use_ai = False
        else:
            force = Confirm.ask("🔄 Forçar nova análise [dim](ignorar cache existente)[/dim]?", default=False)
```

**Depois:**
```python
use_ai = False
force = False
ai_settings = _load_ai_settings()
if layer in ("silver", "both"):
    use_ai = Confirm.ask("🧠 Enriquecer metadados com IA (OpenRouter)?", default=True)
    if use_ai:
        if not ai_settings.resolved_api_key():
            console.print("\n[bold yellow]⚠️  AVISO: API key não encontrada![/bold yellow]")
            console.print("[dim]A IA será desativada. Para ativar, edite [bold]config/ai_settings.json[/bold][/dim]\n")
            use_ai = False
        else:
            force = Confirm.ask("🔄 Forçar nova análise [dim](ignorar cache existente)[/dim]?", default=False)
```

- [ ] **Step 6: Atualizar comando generate — passar ai_settings ao MetadataManager**

No comando `generate()`, substituir a criação do `MetadataManager`:

**Antes:**
```python
from src.metadata.metadata_manager import MetadataManager
manager = MetadataManager(config, glossary=glossary, force=force)
```

**Depois:**
```python
from src.metadata.metadata_manager import MetadataManager
ai_settings = _load_ai_settings()
manager = MetadataManager(config, ai_settings=ai_settings, glossary=glossary, force=force)
```

E substituir a condição que verifica `config.ai.enabled`:

**Antes:**
```python
if layer in ("silver", "both") and config.ai.enabled and ai:
```

**Depois:**
```python
if layer in ("silver", "both") and ai_settings.enabled and ai:
```

- [ ] **Step 7: Atualizar comando generate_docs — passar ai_settings**

No comando `generate_docs()`, substituir:

**Antes:**
```python
if config.ai.enabled and ai:
    from src.metadata.metadata_manager import MetadataManager
    glossary: dict = _load_json(config.glossary_file) if Path(config.glossary_file).exists() else {}
    manager = MetadataManager(config, glossary=glossary, force=force)
```

**Depois:**
```python
ai_settings = _load_ai_settings()
if ai_settings.enabled and ai:
    from src.metadata.metadata_manager import MetadataManager
    glossary: dict = _load_json(config.glossary_file) if Path(config.glossary_file).exists() else {}
    manager = MetadataManager(config, ai_settings=ai_settings, glossary=glossary, force=force)
```

- [ ] **Step 8: Rodar todos os testes**

```bash
pytest -v
```

Esperado: todos os testes passam.

- [ ] **Step 9: Commit**

```bash
git add main.py
git commit -m "feat: integrate _load_ai_settings into CLI — first-run wizard, remove api_key.txt, pass AISettings to MetadataManager"
```

---

## Task 7: Cleanup final

**Files:**
- Modify: `config/generator.yaml`
- Modify: `.gitignore`

- [ ] **Step 1: Remover seção ai: do generator.yaml**

Editar `config/generator.yaml` removendo o bloco inteiro:
```yaml
# --- Integração com IA (OpenRouter) ---
ai:
  enabled: true
  api_key_env: "OPENROUTER_API_KEY"
  model: "openai/gpt-oss-120b:free"
  fallback_models:
    - "openai/gpt-oss-20b:free"
    - "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    - "google/gemma-4-31b-it:free"
  max_retries: 3
  timeout_seconds: 60
  max_parallel: 3
  # Classificação de sensibilidade automática
  detect_pii: true
  classify_sensitivity: true
```

- [ ] **Step 2: Atualizar .gitignore**

No arquivo `.gitignore`, substituir a linha `api_key.txt` por `config/ai_settings.json`:

**Antes:**
```
api_key.txt
```

**Depois:**
```
config/ai_settings.json
```

- [ ] **Step 3: Rodar todos os testes pela última vez**

```bash
pytest -v
```

Esperado: todos os testes passam.

- [ ] **Step 4: Commit final**

```bash
git add config/generator.yaml .gitignore
git commit -m "chore: remove ai: section from generator.yaml and update .gitignore for ai_settings.json"
```

---

## Verificação final

Após todos os commits, verificar manualmente:

```bash
# Deve disparar o wizard de onboarding se ai_settings.json não existir
python main.py generate --help

# Deve mostrar o menu interativo com wizard se for primeira execução
python main.py

# Todos os testes devem passar
pytest -v --tb=short
```

Contagem esperada de testes: **24 passed** (8 ai_settings + 5 onboarding + 8 openrouter_client + 3 config_loader).
