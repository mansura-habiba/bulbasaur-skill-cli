# Evaluating skills

`bbsctl eval` runs behavioral tests against a skill, using an `evals/` corpus authored next to the skill.

> **Status.** Phase 1 of eval ships the loader, `BehaviorEvaluator`, `HeuristicJudge`, and the `bbsctl eval` subcommand. Trigger/injection/regression evaluators and the LLM judge land in Phase 3-4.

## The corpus

`bbsctl eval` reads `*.json` files directly under `evals/`. Each file is one suite; the suite name is the filename stem (`behavior.json` → suite `behavior`).

```
my-skill/
├── SKILL.md
├── skill.yaml              # team+
└── evals/
    ├── behavior.json       # required at org+
    ├── triggers.json       # optional (Phase 3 evaluator)
    ├── injection.json      # required at org+; pinned at regulated (Phase 3)
    └── snapshots/          # regression baselines (Phase 3 evaluator)
```

## Suite shape

```json
{
  "skill_name": "mq-executor",
  "evals": [
    {
      "id": 1,
      "prompt": "Execute approved remediation plan to restart mq-operator deployment in mq-prod namespace.",
      "expected_output": "ValidationReport showing kubectl rollout restart executed and health checks passed.",
      "files": [],
      "assertions": [
        "Dry-run preview is presented before execution",
        "kubectl rollout restart command is executed",
        "Health checks are performed after execution"
      ]
    }
  ]
}
```

`assertions` are natural-language claims a judge scores one by one. Case score is the fraction passing; suite score is the mean across cases.

## Running

```bash
bbsctl eval                                  # every suite under ./evals
bbsctl eval --suite behavior                 # one suite
bbsctl eval --case 4                         # one case (matches stringified id)
bbsctl eval --mode smoke                     # one case per suite
bbsctl eval --runtime mock                   # default; no API key
bbsctl eval --judge heuristic                # default; deterministic
bbsctl eval --output json > report.json      # CI
```

Exit codes: `0` every suite passed, `1` at least one case failed, `2` framework error (missing `SKILL.md`, missing `evals/`, malformed JSON).

## Judges

| Judge | Status | What it does |
|---|---|---|
| `heuristic` | Shipped | Keyword-overlap scoring with a stopword-filtered token set. Deterministic, no API key. Threshold defaults to 0.5. |
| `llm` | Phase 4 | LLM-as-judge using the Claude Agent SDK adapter. Replaces the heuristic when available. |

The heuristic judge is intentionally weak — it's there to exercise the plumbing in CI. The framework's mock runtime is also weak. Together they prove the path works end-to-end without pretending to do real inference.

## Strictness gating

- `local`, `team` — `evals/` is optional.
- `org` — `evals/behavior.json` required with ≥1 case; the marketplace gate refuses to host the skill without a passing report attached to the publish artifact.
- `regulated` — `evals/injection.json` corpus is hash-pinned in `skill.yaml`; a model-upgrade publish that regresses on the pinned corpus is blocked.

The gate is enforced by the marketplace at publish time, not by the framework at compile time. This preserves the five-minute promise and keeps strictness opt-in.

## Adding a new evaluator

Each suite filename maps to one `Evaluator` implementation via the factory. Register at import time:

```python
from skillctl.eval.factory import register_evaluator

register_evaluator(
    "triggers",
    lambda skill, runtime, judge: TriggerEvaluator(skill=skill, runtime=runtime, judge=judge),
)
```

Suites without a registered evaluator fall back to `BehaviorEvaluator`. See `skillctl/eval/factory.py` for the contract.

## See also

- [`README.md#evaluating-skills`](../README.md#evaluating-skills) — the user-facing overview
- [`docs/strictness-levels.md`](strictness-levels.md) — what each strictness level requires
- [agentskills.io/skill-creation/evaluating-skills](https://agentskills.io/skill-creation/evaluating-skills) — upstream methodology
