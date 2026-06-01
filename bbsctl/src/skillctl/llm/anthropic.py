"""AnthropicBackend — Claude via the Messages API.

Requires `ANTHROPIC_API_KEY` in env. Uses stdlib `urllib` so the base install
stays dependency-light; users who want streaming or richer retries can drop in
the official anthropic SDK and register it through `register_backend`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .base import LLMBackend, LLMBackendError, LLMResponse


class AnthropicBackend(LLMBackend):
    name = "anthropic"

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._default_model = (
            default_model
            or os.environ.get("ANTHROPIC_MODEL")
            or self.DEFAULT_MODEL
        )
        if not self._api_key:
            # Defer the error: constructor must not raise for `list_backends`
            # to be safely callable in environments without keys.
            pass

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
                "AnthropicBackend: ANTHROPIC_API_KEY is not set. "
                "Export your API key or pick `--backend ollama` for a local model."
            )

        body: dict = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        request = urllib.request.Request(
            self.API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": self.API_VERSION,
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
                f"Anthropic API error {exc.code}: {body_text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMBackendError(f"Anthropic API unreachable: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        text = _join_content_blocks(payload.get("content", []))
        usage = payload.get("usage", {})

        return LLMResponse(
            text=text,
            model=payload.get("model", body["model"]),
            backend=self.name,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            latency_ms=latency_ms,
            metadata={"id": payload.get("id", "")},
        )


def _join_content_blocks(blocks: list[dict]) -> str:
    """Anthropic content blocks → flat string. Skips non-text blocks."""
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


__all__ = ["AnthropicBackend"]
