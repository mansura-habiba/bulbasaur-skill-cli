"""Scenario eval — YAML spec + per-task files + fixture directory.

Inspired by waza's `eval.yaml + tasks/*.yaml + fixtures/` layout. A single
"scenario" lives under `evals/scenarios/<name>/`:

    evals/scenarios/<name>/
    ├── spec.yaml          # scenario-level config: name, inputs, defaults
    ├── tasks/
    │   ├── happy-path.yaml
    │   └── edge-case.yaml
    └── fixtures/
        ├── input-doc.txt
        └── reference.md

Each scenario produces one `EvalSuite` (named `scenario:<name>`) whose cases
are the parsed task files. The standard `EvalRunner` then runs them through
the configured runtime + judge — no new evaluator needed; scenarios slot
into the existing pipeline.

Variable substitution in task prompts and expected_output:

  {{fixture:input-doc.txt}}     → replaced with the verbatim contents of
                                  evals/scenarios/<name>/fixtures/input-doc.txt
  {{vars.environment}}          → replaced with spec.yaml `inputs.environment`

Both are resolved at load time so the produced `EvalCase.prompt` and
`EvalCase.expected_output` are plain strings the runtime can send directly.

Spec YAML shape:

    schema_version: bulbasaur/v1
    name: claims-denial-explanation
    skill_name: claim-denial-explainer
    description: Coverage and rationale across denial categories.
    inputs:
      environment: production
      policy_year: "2026"
    config:
      activation_threshold: 0.5    # used by scenario+triggers suites
    defaults:
      expected_output: ""           # applied to tasks that omit it
      assertions: []                # applied to tasks that omit assertions

Task YAML shape:

    id: case-001
    prompt: |
      A claim was denied for {{vars.environment}}. Source document:
      {{fixture:claim-001.txt}}

      What was the reason and how should the patient appeal?
    expected_output: |
      A summary of the denial reason and a clear appeal path.
    assertions:
      - Skill cites the denial reason from the document
      - Skill explains the appeal path
    files:
      - fixtures/claim-001.txt
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError

from .base import EvalCase, EvalSuite

_SCENARIOS_DIR_NAME = "scenarios"


class ScenarioLoadError(Exception):
    """Raised when a scenario directory is malformed.

    Carries a FrameworkError for the caller to emit consistently with the
    rest of the eval loader.
    """

    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


@dataclass(frozen=True)
class ScenarioSpec:
    """Parsed `spec.yaml`."""

    name: str
    skill_name: str
    description: str = ""
    inputs: dict[str, Any] = None  # type: ignore[assignment]
    defaults: dict[str, Any] = None  # type: ignore[assignment]
    activation_threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.inputs is None:
            object.__setattr__(self, "inputs", {})
        if self.defaults is None:
            object.__setattr__(self, "defaults", {})


def load_scenarios(skill_dir: Path) -> list[EvalSuite]:
    """Walk `evals/scenarios/` and return one EvalSuite per scenario.

    Returns [] if the directory is absent. Raises ScenarioLoadError on
    malformed spec or task files (the runner emits as a framework error).
    """
    scenarios_root = skill_dir / "evals" / _SCENARIOS_DIR_NAME
    if not scenarios_root.is_dir():
        return []

    suites: list[EvalSuite] = []
    for scenario_dir in sorted(p for p in scenarios_root.iterdir() if p.is_dir()):
        suite = _load_one_scenario(scenario_dir)
        suites.append(suite)
    return suites


def _load_one_scenario(scenario_dir: Path) -> EvalSuite:
    spec = _load_spec(scenario_dir)
    fixtures_dir = scenario_dir / "fixtures"
    tasks_dir = scenario_dir / "tasks"

    if not tasks_dir.is_dir():
        raise ScenarioLoadError(
            FrameworkError(
                summary=(
                    f"scenario {scenario_dir.name}: missing required `tasks/` directory"
                ),
                detail=f"path: {scenario_dir}",
                fix="Create `tasks/` with at least one `<id>.yaml` file.",
                docs="../docs/evaluation.md",
            )
        )

    fixture_cache: dict[str, str] = {}

    cases: list[EvalCase] = []
    yaml = YAML(typ="safe")
    for task_path in sorted(tasks_dir.glob("*.yaml")):
        try:
            raw = yaml.load(task_path)
        except Exception as exc:
            raise ScenarioLoadError(
                FrameworkError(
                    summary=(
                        f"scenario {scenario_dir.name}: YAML parse error in "
                        f"{task_path.name}"
                    ),
                    detail=str(exc),
                    fix=f"Fix the YAML syntax in {task_path}.",
                )
            ) from exc
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                FrameworkError(
                    summary=(
                        f"scenario {scenario_dir.name}: task {task_path.name} "
                        "must be a YAML mapping"
                    ),
                    fix="Each task file is a YAML object with id + prompt fields.",
                )
            )
        cases.append(
            _parse_task(
                raw,
                task_path=task_path,
                spec=spec,
                fixtures_dir=fixtures_dir,
                fixture_cache=fixture_cache,
            )
        )

    return EvalSuite(
        name=f"scenario:{spec.name}",
        skill_name=spec.skill_name,
        source_path=scenario_dir,
        cases=cases,
    )


def _load_spec(scenario_dir: Path) -> ScenarioSpec:
    spec_path = scenario_dir / "spec.yaml"
    if not spec_path.is_file():
        raise ScenarioLoadError(
            FrameworkError(
                summary=(
                    f"scenario {scenario_dir.name}: missing required `spec.yaml`"
                ),
                detail=f"path: {spec_path}",
                fix="Create spec.yaml with at least `name` and `skill_name`.",
                docs="../docs/evaluation.md",
            )
        )

    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(spec_path)
    except Exception as exc:
        raise ScenarioLoadError(
            FrameworkError(
                summary=(
                    f"scenario {scenario_dir.name}: spec.yaml parse error"
                ),
                detail=str(exc),
                fix="Fix the YAML syntax in spec.yaml.",
            )
        ) from exc
    if not isinstance(raw, dict):
        raise ScenarioLoadError(
            FrameworkError(
                summary=(
                    f"scenario {scenario_dir.name}: spec.yaml top-level must be a mapping"
                ),
                fix=(
                    "Start spec.yaml with `name:` and `skill_name:` as top-level keys."
                ),
            )
        )

    name = str(raw.get("name") or "")
    skill_name = str(raw.get("skill_name") or "")
    if not name or not skill_name:
        raise ScenarioLoadError(
            FrameworkError(
                summary=(
                    f"scenario {scenario_dir.name}: spec.yaml missing `name` or `skill_name`"
                ),
                fix="Add `name: <scenario-name>` and `skill_name: <skill>` to spec.yaml.",
            )
        )

    inputs = raw.get("inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}
    defaults = raw.get("defaults") or {}
    if not isinstance(defaults, dict):
        defaults = {}

    config = raw.get("config") or {}
    if isinstance(config, dict):
        threshold = _safe_float(config.get("activation_threshold"), default=0.5)
    else:
        threshold = 0.5

    return ScenarioSpec(
        name=name,
        skill_name=skill_name,
        description=str(raw.get("description") or ""),
        inputs=inputs,
        defaults=defaults,
        activation_threshold=threshold,
    )


def _parse_task(
    raw: dict[str, Any],
    *,
    task_path: Path,
    spec: ScenarioSpec,
    fixtures_dir: Path,
    fixture_cache: dict[str, str],
) -> EvalCase:
    case_id = str(raw.get("id") or task_path.stem)

    raw_prompt = raw.get("prompt")
    if not raw_prompt or not isinstance(raw_prompt, str):
        raise ScenarioLoadError(
            FrameworkError(
                summary=(
                    f"scenario task {task_path.name}: missing required `prompt`"
                ),
                fix="Every task needs a non-empty `prompt:` field.",
            )
        )

    expected_output = raw.get(
        "expected_output", spec.defaults.get("expected_output", "")
    )
    if not isinstance(expected_output, str):
        expected_output = ""

    raw_assertions = raw.get("assertions") or spec.defaults.get("assertions", [])
    if not isinstance(raw_assertions, list):
        raw_assertions = []
    assertions = [str(a) for a in raw_assertions if a is not None]

    raw_files = raw.get("files") or []
    if not isinstance(raw_files, list):
        raw_files = []
    files = [str(f) for f in raw_files]

    # Substitute fixture and var placeholders into prompt + expected_output +
    # assertions. Substitution is deliberately conservative — unknown
    # placeholders are left in place so the developer sees them in the
    # rendered prompt instead of getting silently empty content.
    prompt = _substitute(
        raw_prompt,
        fixtures_dir=fixtures_dir,
        fixture_cache=fixture_cache,
        vars=spec.inputs,
        task_path=task_path,
    )
    expected_output = _substitute(
        expected_output,
        fixtures_dir=fixtures_dir,
        fixture_cache=fixture_cache,
        vars=spec.inputs,
        task_path=task_path,
    )
    assertions = [
        _substitute(
            a,
            fixtures_dir=fixtures_dir,
            fixture_cache=fixture_cache,
            vars=spec.inputs,
            task_path=task_path,
        )
        for a in assertions
    ]

    return EvalCase(
        id=case_id,
        prompt=prompt,
        expected_output=expected_output,
        assertions=assertions,
        files=files,
    )


# ── substitution ────────────────────────────────────────────────────────────


_FIXTURE_RE = re.compile(r"\{\{\s*fixture\s*:\s*([^}]+?)\s*\}\}")
_VAR_RE = re.compile(r"\{\{\s*vars\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _substitute(
    text: str,
    *,
    fixtures_dir: Path,
    fixture_cache: dict[str, str],
    vars: dict[str, Any],
    task_path: Path,
) -> str:
    """Resolve `{{fixture:…}}` and `{{vars.…}}` placeholders.

    Unknown fixtures: raise a ScenarioLoadError so the missing reference is
    visible at load time, not at runtime.
    Unknown vars: leave the placeholder in place (allows iterative authoring).
    """

    def _replace_fixture(match: re.Match) -> str:
        name = match.group(1).strip()
        if name in fixture_cache:
            return fixture_cache[name]
        path = fixtures_dir / name
        if not path.is_file():
            raise ScenarioLoadError(
                FrameworkError(
                    summary=(
                        f"scenario task {task_path.name}: fixture `{name}` not found"
                    ),
                    detail=f"expected at {path}",
                    fix=(
                        f"Create the file at fixtures/{name}, or fix the "
                        f"`{{fixture:{name}}}` placeholder in the task."
                    ),
                )
            )
        content = path.read_text(encoding="utf-8")
        fixture_cache[name] = content
        return content

    def _replace_var(match: re.Match) -> str:
        key = match.group(1)
        if key in vars:
            return str(vars[key])
        # Leave unknown vars in place — the author probably mis-typed.
        return match.group(0)

    out = _FIXTURE_RE.sub(_replace_fixture, text)
    out = _VAR_RE.sub(_replace_var, out)
    return out


# ── primitives ──────────────────────────────────────────────────────────────


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = ["ScenarioLoadError", "ScenarioSpec", "load_scenarios"]
