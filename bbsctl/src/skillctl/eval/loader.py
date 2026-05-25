"""Load eval suites from an `evals/` directory.

Each `.json` file directly under `evals/` is one suite. The file shape is:

    {
      "skill_name": "...",
      "evals": [
        { "id": <int|str>, "prompt": "...", "expected_output": "...",
          "files": [], "assertions": [...] },
        ...
      ]
    }

The suite name is the filename without extension. `evals/behavior.json`
becomes suite `behavior`. Files in subdirectories (e.g. `evals/snapshots/`)
are ignored by the loader — those are managed by the RegressionEvaluator.

The loader is tolerant about case ids (accepts int or str) and missing
optional fields (files defaults to [], assertions defaults to []). It is
strict about the required fields (id, prompt) and surfaces a FrameworkError
with a fix line on malformed input.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skillctl.messaging import FrameworkError

from .base import EvalCase, EvalSuite


class EvalLoadError(Exception):
    """Raised when a suite file cannot be loaded.

    Carries a FrameworkError for the caller to emit; the exception itself
    is the framework-internal signal that loading failed.
    """

    def __init__(self, framework_error: FrameworkError) -> None:
        super().__init__(framework_error.summary)
        self.framework_error = framework_error


def load_suites(evals_dir: Path) -> list[EvalSuite]:
    """Load every `*.json` suite file directly under `evals_dir`.

    Returns an empty list if `evals_dir` does not exist — callers decide
    whether that is an error (e.g. org+ strictness requires a behavior suite).
    Subdirectories are not traversed.
    """
    if not evals_dir.is_dir():
        return []

    suites: list[EvalSuite] = []
    for path in sorted(evals_dir.glob("*.json")):
        suite = _load_one_suite(path)
        suites.append(suite)
    return suites


def _load_one_suite(path: Path) -> EvalSuite:
    """Load and validate one suite file."""
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise EvalLoadError(
            FrameworkError(
                summary=f"eval suite {path.name} is not valid JSON",
                detail=str(exc),
                fix=(
                    f"Validate the JSON syntax (e.g. `python -m json.tool {path}`) "
                    "and re-run `bbsctl eval`."
                ),
                docs="../docs/evaluation.md",
            )
        ) from exc

    if not isinstance(data, dict):
        raise EvalLoadError(
            FrameworkError(
                summary=f"eval suite {path.name} must be a JSON object",
                detail=f"got: {type(data).__name__}",
                fix=(
                    "Wrap the suite in an object: "
                    '{"skill_name": "...", "evals": [...]}.'
                ),
            )
        )

    skill_name = data.get("skill_name")
    if not skill_name or not isinstance(skill_name, str):
        raise EvalLoadError(
            FrameworkError(
                summary=f"eval suite {path.name} is missing required field `skill_name`",
                fix=(
                    "Add a top-level `skill_name` string matching the skill being evaluated."
                ),
            )
        )

    raw_evals = data.get("evals")
    if not isinstance(raw_evals, list):
        raise EvalLoadError(
            FrameworkError(
                summary=f"eval suite {path.name} is missing required field `evals` (array)",
                fix='Add a top-level `evals` array of case objects.',
            )
        )

    cases = [_parse_case(c, suite_path=path, index=i) for i, c in enumerate(raw_evals)]

    return EvalSuite(
        name=path.stem,
        skill_name=skill_name,
        source_path=path,
        cases=cases,
    )


def _parse_case(raw: Any, *, suite_path: Path, index: int) -> EvalCase:
    """Parse one case object, enforcing required fields."""
    if not isinstance(raw, dict):
        raise EvalLoadError(
            FrameworkError(
                summary=(
                    f"eval suite {suite_path.name} case #{index} must be an object"
                ),
                detail=f"got: {type(raw).__name__}",
                fix='Each item in `evals` must be an object with `id` and `prompt`.',
            )
        )

    case_id_raw = raw.get("id")
    if case_id_raw is None:
        raise EvalLoadError(
            FrameworkError(
                summary=(
                    f"eval suite {suite_path.name} case #{index} is missing `id`"
                ),
                fix="Every case needs a stable `id` (string or integer).",
            )
        )
    case_id = str(case_id_raw)

    prompt = raw.get("prompt")
    if not prompt or not isinstance(prompt, str):
        raise EvalLoadError(
            FrameworkError(
                summary=(
                    f"eval suite {suite_path.name} case id={case_id} is missing `prompt`"
                ),
                fix="Every case needs a non-empty `prompt` string.",
            )
        )

    expected_output = raw.get("expected_output", "")
    if not isinstance(expected_output, str):
        raise EvalLoadError(
            FrameworkError(
                summary=(
                    f"eval suite {suite_path.name} case id={case_id} has "
                    "non-string `expected_output`"
                ),
                fix="`expected_output` must be a natural-language string.",
            )
        )

    raw_assertions = raw.get("assertions", [])
    if not isinstance(raw_assertions, list):
        raise EvalLoadError(
            FrameworkError(
                summary=(
                    f"eval suite {suite_path.name} case id={case_id} has "
                    "non-array `assertions`"
                ),
                fix="`assertions` must be an array of natural-language strings.",
            )
        )
    assertions = [str(a) for a in raw_assertions if a is not None]

    raw_files = raw.get("files", [])
    if not isinstance(raw_files, list):
        raw_files = []
    files = [str(f) for f in raw_files]

    return EvalCase(
        id=case_id,
        prompt=prompt,
        expected_output=expected_output,
        assertions=assertions,
        files=files,
    )


__all__ = ["EvalLoadError", "load_suites"]
