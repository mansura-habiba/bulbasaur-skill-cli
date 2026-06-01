"""OpenAIBackend — chat completions via the OpenAI HTTP API.

Requires `OPENAI_API_KEY` in env. Also supports OpenAI-compatible local servers
(LM Studio, vLLM, llama.cpp's `--api`) via `OPENAI_API_BASE`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .base import LLMBackend, LLMBackendError, LLMResponse


class OpenAIBackend(LLMBackend):
    name = "openai"

    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_API_BASE = "https://api.openai.com/v1"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._api_base = (
            api_base
            or os.environ.get("OPENAI_API_BASE")
            or self.DEFAULT_API_BASE
        ).rstrip("/")
        self._default_model = (
            default_model
            or os.environ.get("OPENAI_MODEL")
            or self.DEFAULT_MODEL
        )

    def complete(
        self,
        *,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self._api_key:
            raise LLMBackendError(
                "OpenAIBackend: OPENAI_API_KEY is not set. "
                "Export your API key, point OPENAI_API_BASE at a local server, "
                "or pick `--backend ollama` for a no-key option."
            )

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model or self._default_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        request = urllib.request.Request(
            f"{self._api_base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:500]
            raise LLMBackendError(
                f"OpenAI API error {exc.code}: {body_text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMBackendError(f"OpenAI API unreachable: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        choices = payload.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = payload.get("usage", {})

        return LLMResponse(
            text=text,
            model=payload.get("model", body["model"]),
            backend=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
            metadata={"api_base": self._api_base},
        )


__all__ = ["OpenAIBackend"]
