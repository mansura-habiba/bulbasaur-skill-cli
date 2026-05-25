"""Judges — score one assertion against one actual output.

A Judge is the smallest pluggable unit in the eval system. Each Judge takes a
natural-language assertion (e.g. "Dry-run preview is presented before
execution") and the runtime's actual output, and returns a verdict: pass/fail
plus a one-line reason.

Phase 1 ships HeuristicJudge — deterministic, no API key, no LLM. It uses
keyword overlap as a coarse proxy. This is intentionally weak; the framework's
mock runtime is also weak, so the two together exercise the plumbing without
pretending to do real inference.

Real LLM judging (LLMJudge) lands when the Claude Agent SDK adapter ships in
Phase 4. The interface below is what that adapter will implement.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class JudgeVerdict:
    """One assertion's score."""

    passed: bool
    reason: str


class Judge(ABC):
    """Strategy interface for judges."""

    name: str = "anonymous-judge"

    @abstractmethod
    def score(self, *, assertion: str, actual_output: str, expected_output: str) -> JudgeVerdict:
        """Return a verdict for one assertion against one actual output.

        Implementations must not raise on bad input — return a failing verdict
        with a clear reason instead.
        """


# A short, fixed stopword list so HeuristicJudge can be deterministic without
# pulling in NLTK or spaCy. Kept conservative — we'd rather over-match than
# under-match in the absence of real semantic judging.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "before", "but", "by",
        "can", "could", "did", "do", "does", "for", "from", "had", "has",
        "have", "if", "in", "into", "is", "it", "its", "of", "on", "or",
        "should", "so", "than", "that", "the", "then", "this", "to", "via",
        "was", "were", "when", "while", "will", "with", "without", "would",
        "you", "your",
    }
)


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")


def _tokens(text: str) -> set[str]:
    """Lowercase content tokens, stopwords removed."""
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if t.lower() not in _STOPWORDS and len(t) > 2
    }


class HeuristicJudge(Judge):
    """Deterministic keyword-overlap judge.

    For each assertion, extract content tokens and check how many appear in
    the actual output. Pass if the overlap ratio is at or above `threshold`
    (default 0.5). This is a placeholder for real LLM judging; it is good
    enough to wire end-to-end tests and CI smoke checks, and bad enough that
    nobody mistakes it for a real eval.

    The threshold is intentionally loose so the framework's mock runtime
    (which echoes a single body line) doesn't fail every assertion in a
    self-test. Real judging via LLMJudge replaces this in Phase 4.
    """

    name = "heuristic-judge"

    def __init__(self, threshold: float = 0.5) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {threshold}")
        self._threshold = threshold

    def score(
        self, *, assertion: str, actual_output: str, expected_output: str
    ) -> JudgeVerdict:
        assertion_tokens = _tokens(assertion)
        output_tokens = _tokens(actual_output)

        if not assertion_tokens:
            # Assertion is all stopwords / punctuation — refuse to judge.
            return JudgeVerdict(
                passed=False,
                reason="assertion contained no scorable tokens",
            )

        overlap = assertion_tokens & output_tokens
        ratio = len(overlap) / len(assertion_tokens)
        passed = ratio >= self._threshold

        return JudgeVerdict(
            passed=passed,
            reason=(
                f"heuristic overlap {len(overlap)}/{len(assertion_tokens)} "
                f"(ratio={ratio:.2f}, threshold={self._threshold:.2f})"
            ),
        )


__all__ = ["HeuristicJudge", "Judge", "JudgeVerdict"]
