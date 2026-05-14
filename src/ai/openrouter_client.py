"""
src/ai/openrouter_client.py
----------------------------
Client OpenRouter para chamadas LLM com retry automático,
fallback entre modelos e logging de observabilidade.
"""
from __future__ import annotations

import json
import os
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
    Client OpenRouter com:
    - Retry automático com backoff exponencial
    - Fallback entre múltiplos modelos
    - Parsing automático de JSON na resposta
    - Logging estruturado de cada chamada
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        primary_model: str = "anthropic/claude-3.5-sonnet",
        fallback_models: list[str] | None = None,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        self.api_key = api_key or os.getenv(api_key_env, "")
        if not self.api_key:
            log.warning(f"⚠️  {api_key_env} não definida — chamadas AI desativadas.")

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
        """
        Envia mensagens para o LLM. Tenta modelos em sequência se houver erro.

        Args:
            messages: Lista de mensagens no formato OpenAI.
            expect_json: Se True, tenta parsear a resposta como JSON.
            temperature: Temperatura do LLM (0 = determinístico).

        Returns:
            AIResponse com conteúdo e metadata da chamada.
        """
        if not self.api_key:
            log.error("API key ausente. Configure OPENROUTER_API_KEY.")
            return AIResponse(model_used="none", raw_content="", parsed=None)

        models = [self.primary_model] + self.fallback_models

        for model in models:
            result = self._try_model(model, messages, expect_json, temperature)
            if result is not None:
                return result
            log.warning(f"⚠️  Modelo {model} falhou. Tentando próximo...")

        log.error("❌ Todos os modelos falharam.")
        return AIResponse(model_used="none", raw_content="", parsed=None)

    def _try_model(
        self,
        model: str,
        messages: list[dict],
        expect_json: bool,
        temperature: float,
    ) -> AIResponse | None:
        """Tenta chamar um modelo específico com retry exponencial."""
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info(f"🤖 [{model}] tentativa {attempt}/{self.max_retries}...")
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

                parsed = None
                if expect_json:
                    parsed = self._parse_json(raw)

                log.info(
                    f"  ✅ {model} — {tokens} tokens — {elapsed_ms}ms"
                    + (" — JSON OK" if parsed else " — JSON inválido")
                )

                return AIResponse(
                    model_used=model,
                    raw_content=raw,
                    parsed=parsed,
                    tokens_used=tokens,
                    latency_ms=elapsed_ms,
                    retries=attempt - 1,
                )

            except RateLimitError:
                wait = 2**attempt
                log.warning(f"  Rate limit. Aguardando {wait}s...")
                time.sleep(wait)

            except APITimeoutError:
                log.warning(f"  Timeout na tentativa {attempt}.")

            except APIError as e:
                log.error(f"  API error: {e}")
                return None  # Não faz retry em erros de API

        return None

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Tenta extrair JSON do texto da resposta LLM."""
        # Remove blocos de código ```json ... ```
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Tenta encontrar o primeiro objeto JSON no texto
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(clean[start:end])
                except json.JSONDecodeError:
                    pass
        return None
