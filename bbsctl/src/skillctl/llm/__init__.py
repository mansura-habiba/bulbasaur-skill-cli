"""LLM backend adapter — the pluggable substrate for LLMJudge and live runtimes.

The framework needs to make model calls from two places:
  - LLMJudge scores eval assertions
  - The (planned) Claude Agent SDK runtime adapter activates skills

Both want the same interface: send a prompt, get a string back, with cost and
token telemetry. The backend choice — Ollama (local), Anthropic, OpenAI, a
raw local llama-cpp process — is a developer / operator decision, not a
framework decision. The strategy + factory pattern below normalizes them.

Adapters:
  OllamaBackend      — http://localhost:11434, model name passes through
  AnthropicBackend   — Messages API; requires ANTHROPIC_API_KEY
  OpenAIBackend      — Chat completions; requires OPENAI_API_KEY
  LocalLlamaBackend  — llama-cpp-python (placeholder; not wired)

Selection order (build_backend resolves):
  1. BBSCTL_LLM_BACKEND env var
  2. backend declared in eval.config.yaml or skill.yaml
  3. CLI flag override (--backend)
  4. Default: ollama (no API key required)
"""

from .base import LLMBackend, LLMResponse, LLMBackendError
from .factory import build_backend, list_backends, register_backend

__all__ = [
    "LLMBackend",
    "LLMBackendError",
    "LLMResponse",
    "build_backend",
    "list_backends",
    "register_backend",
]
