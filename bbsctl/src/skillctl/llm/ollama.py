"""OllamaBackend — local model via Ollama HTTP API.

Default endpoint: http://localhost:11434. Model name passes through;
common choices: `llama3:8b`, `mistral:7b`, `qwen2.5:14b`.

No API key. Uses stdlib `urllib` to avoid pulling httpx into the base install.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .base import LLMBackend, LLMBackendError, LLMResponse


class OllamaBackend(LLMBackend):
    name = "ollama"

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "llama3:8b"

    def __init__(self, host: str | None = None, default_model: str | None = None) -> None:
        self._host = host or os.environ.get("OLLAMA_HOST") or self.DEFAULT_HOST
        self._default_model = default_model or os.environ.get(
            "OLLAMA_MODEL"
        ) or self.DEFAULT_MODEL

    def complete(
        self,
        *,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        body = {
            "model": model or self._default_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            body["system"] = system

        request = urllib.request.Request(
            f"{self._host}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LLMBackendError(
                f"Ollama unreachable at {self._host}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMBackendError(
                f"Ollama returned invalid JSON: {exc}"
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(
            text=payload.get("response", ""),
            model=payload.get("model", body["model"]),
            backend=self.name,
            prompt_tokens=payload.get("prompt_eval_count", 0),
            completion_tokens=payload.get("eval_count", 0),
            latency_ms=latency_ms,
            metadata={"host": self._host},
        )


__all__ = ["OllamaBackend"]
