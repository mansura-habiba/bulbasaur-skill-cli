"""LLMJudge — score assertions through a configurable LLM backend.

The judge picks a backend through `skillctl.llm.build_backend`. Default is
Ollama (no API key). Operators can switch via `BBSCTL_LLM_BACKEND` or
`bbsctl eval --judge-backend <name>`.

Judge prompt: a single-turn JSON-mode prompt. The backend returns a JSON
object `{passed: bool, reason: str}` per assertion. Defensive parsing
recovers from malformed JSON with one retry; a second failure becomes a
failed verdict whose reason includes the parse error.
"""

from __future__ import annotations

import json
import re

from skillctl.llm import LLMBackend, LLMBackendError, build_backend

from .judge import Judge, JudgeVerdict

_DEFAULT_SYSTEM = (
    "You are an evaluation judge. Given the expected behaviour and the actual "
    "output of an AI agent skill, decide whether the actual output satisfies "
    "the assertion. Respond with a single JSON object on one line, no prose: "
    '{"passed": true|false, "reason": "<one sentence explanation>"}.'
)

_PROMPT_TEMPLATE = """\
Assertion: {assertion}

Expected behaviour (natural language):
{expected_output}

Actual output:
{actual_output}

Does the actual output satisfy the assertion? Reply with JSON only.\
"""


class LLMJudge(Judge):
    """LLM-as-judge using a configurable backend.

    Construction is lazy — the backend is resolved at instantiation but the
    first model call is delayed to `score()`. Errors from the backend surface
    as failing verdicts with a clear reason rather than crashing the run.
    """

    name = "llm"

    def __init__(
        self,
        *,
        backend: LLMBackend | None = None,
        backend_name: str | None = None,
        model: str | None = None,
        max_tokens: int = 256,
    ) -> None:
        self._backend = backend or build_backend(backend_name)
        self._model = model
        self._max_tokens = max_tokens

    def score(
        self, *, assertion: str, actual_output: str, expected_output: str
    ) -> JudgeVerdict:
        prompt = _PROMPT_TEMPLATE.format(
            assertion=assertion,
            expected_output=expected_output or "(no expected output supplied)",
            actual_output=actual_output or "(no actual output)",
        )

        try:
            response = self._backend.complete(
                prompt=prompt,
                model=self._model,
                system=_DEFAULT_SYSTEM,
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
        except LLMBackendError as exc:
            return JudgeVerdict(
                passed=False,
                reason=f"judge backend error: {exc}",
            )

        verdict = _parse_verdict(response.text)
        if verdict is not None:
            return verdict

        # Retry once with a stricter instruction.
        try:
            retry = self._backend.complete(
                prompt=prompt
                + "\n\nIMPORTANT: reply with only one JSON object and nothing else.",
                model=self._model,
                system=_DEFAULT_SYSTEM,
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
        except LLMBackendError as exc:
            return JudgeVerdict(
                passed=False,
                reason=f"judge backend error on retry: {exc}",
            )

        verdict = _parse_verdict(retry.text)
        if verdict is not None:
            return verdict

        return JudgeVerdict(
            passed=False,
            reason=(
                f"could not parse judge response as JSON; "
                f"got: {retry.text[:120]!r}"
            ),
        )


_JSON_OBJECT = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _parse_verdict(text: str) -> JudgeVerdict | None:
    """Pull the first JSON object out of `text`; convert to JudgeVerdict.

    Returns None if no JSON object is present or required keys are missing.
    """
    if not text:
        return None
    # Try the whole text first; if not JSON, search for an embedded object.
    candidates: list[str] = []
    text_stripped = text.strip()
    if text_stripped.startswith("{"):
        candidates.append(text_stripped)
    candidates.extend(_JSON_OBJECT.findall(text))

    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if "passed" not in data:
            continue
        passed = bool(data["passed"])
        reason = str(data.get("reason") or "")
        return JudgeVerdict(passed=passed, reason=reason)
    return None


__all__ = ["LLMJudge"]
