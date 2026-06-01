# Configuration cascade

Every tunable in `bbsctl` resolves through the same seven-layer cascade. Highest priority wins.

| Priority | Source | Scope | Set by |
|---|---|---|---|
| 1 | CLI flag | Command invocation | Developer per-run |
| 2 | Environment variable | Shell session | Developer or CI |
| 3 | `evals/eval.config.yaml`, `skill.yaml`, `permissions.yaml` | One skill | Skill author |
| 4 | `pyproject.toml` `[tool.bulbasaur.*]` | One project | Project lead |
| 5 | `~/.config/bbsctl/config.yaml` | One user | Developer once |
| 6 | `/etc/bbsctl/config.yaml` (or `$BBSCTL_ORG_CONFIG`) | One org / machine | Platform team |
| 7 | Built-in default | All users | Framework code |

A user opens a project, runs `bbsctl eval`, and gets the resolved configuration of: their CLI flags, on top of their env vars, on top of the project's skill-level config, on top of their personal preferences, on top of the org-wide policy, on top of the framework defaults. No layer needs to be present; missing layers fall through.

## What is tunable

Every eval-related setting:

- `runtime`, `runtime_model`, `runtime_max_tokens`, `runtime_temperature`
- `judge`, `judge_backend`, `judge_model`, `judge_threshold`, `judge_max_tokens`
- `threshold` (suite pass score), `fuzz_n_variants`

LLM backend settings per backend (Ollama, Anthropic, OpenAI, plus any registered third-party):

- `host` or `api_base` (for backends that need it)
- `default_model`
- `api_key` (env vars only — never written to a YAML file by the framework)

Strictness defaults, marketplace defaults, cache directory, snapshot path format — all consult the same cascade.

## File schemas

### `~/.config/bbsctl/config.yaml` (user-level)

```yaml
schema_version: bulbasaur/v1
eval:
  runtime: claude-agent-sdk
  runtime_model: claude-sonnet-4-6
  runtime_max_tokens: 4096
  runtime_temperature: 0.0
  judge: llm
  judge_backend: ollama
  judge_model: llama3:8b
  judge_threshold: 0.5
  judge_max_tokens: 256
  threshold: 1.0
  fuzz_n_variants: 4
llm_backends:
  ollama:
    host: http://localhost:11434
    default_model: llama3:8b
  anthropic:
    default_model: claude-sonnet-4-6
  openai:
    api_base: https://api.openai.com/v1
    default_model: gpt-4o-mini
```

### `/etc/bbsctl/config.yaml` (org-level)

Same schema as user. Typically used by platform teams to enforce a baseline (a judge model the org has approved, a default Ollama host pointing at internal infrastructure, etc.). User-layer settings override the org-layer for non-empty fields.

### `evals/eval.config.yaml` (skill-level)

```yaml
schema_version: bulbasaur/v1
runtime: claude-agent-sdk
runtime_model: claude-sonnet-4-6
judge: llm
judge_backend: anthropic
judge_model: claude-haiku-4-5-20251001
threshold: 1.0
```

Skill-level pinning is what makes eval reports reproducible across machines.

### `pyproject.toml` `[tool.bulbasaur]`

```toml
[tool.bulbasaur]
default_strictness = "team"
marketplace = "./team-marketplace"

[tool.bulbasaur.eval]
runtime = "mock"
threshold = 0.95
```

Project-level config sits between user and skill. A monorepo can declare every skill defaults to `team` strictness; a skill that needs more can override in its own `skill.yaml`.

## Environment variables

Long form covers every field:

```
BBSCTL_EVAL_RUNTIME            BBSCTL_EVAL_JUDGE
BBSCTL_EVAL_RUNTIME_MODEL      BBSCTL_EVAL_JUDGE_BACKEND
BBSCTL_EVAL_RUNTIME_MAX_TOKENS BBSCTL_EVAL_JUDGE_MODEL
BBSCTL_EVAL_RUNTIME_TEMPERATURE BBSCTL_EVAL_JUDGE_THRESHOLD
BBSCTL_EVAL_THRESHOLD          BBSCTL_EVAL_JUDGE_MAX_TOKENS
BBSCTL_EVAL_FUZZ_N_VARIANTS
```

Short aliases for the most-used:

```
BBSCTL_RUNTIME_MODEL           BBSCTL_JUDGE_MODEL
BBSCTL_JUDGE_BACKEND           BBSCTL_LLM_BACKEND
```

Backend authentication uses the backend's native env vars: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_HOST`. The framework never reads these from YAML.

Pointing the cascade at custom files:

```
BBSCTL_USER_CONFIG=/path/to/my-config.yaml
BBSCTL_ORG_CONFIG=/etc/team/bbsctl.yaml
```

## CLI flag matrix

Every `bbsctl eval` flag corresponds to one cascade field:

```
--runtime                  --judge
--runtime-model            --judge-backend
--runtime-max-tokens       --judge-model
--runtime-temperature      --judge-threshold
--threshold                --judge-max-tokens
--fuzz-n-variants
--cache / --refresh-cache  (cache control, not a field)
--snapshot SUITE           (output, not a field)
```

A CLI flag set to a non-empty value wins over every lower layer. Setting nothing on the CLI means: use whatever the env / files resolved to.

## Resolution semantics

- **Empty string is "not set."** Unlike `None`, an explicit `""` in a YAML file is treated as the absence of an override.
- **Deny-wins for permissions.** The permissions cascade has a separate rule: deny rules from any layer union; allow rules cannot widen a stricter parent layer (validator enforces this).
- **Hash invalidation for eval cache.** The cache key includes every resolved config field. Changing the user-level `judge_model` invalidates every cached report; running `bbsctl eval` produces a fresh result.

## Debugging the cascade

```bash
bbsctl config show                          # planned; prints the resolved cascade
bbsctl eval --output json | jq '.runtime_model, .judge_model, .threshold'
```

Today, the JSON report already records every resolved field — `runtime_model`, `judge_backend`, `judge_model`, `threshold`, `skill_hash`, `corpus_hash`, `cache_key`. If a developer's run produced a surprising result, the report tells you exactly what cascade produced it.

## Why a cascade

The alternative — every developer setting every field per-command — fails three constituencies the framework serves:

- **A solo developer** wants to write `bbsctl eval` and have it work with the LLM they prefer. The user-level config gives them that.
- **A platform team** wants every team's evals to use the org-approved judge model and the internal Ollama host. The org-level config gives them that without per-repo configuration.
- **A regulated workflow** wants the eval inputs to be reproducible across machines and pinned across model upgrades. The skill-level `eval.config.yaml` plus the cache key gives them that.

The same cascade serves all three because each layer is owned by the role with authority over that scope.

## See also

- [`docs/evaluation.md`](evaluation.md) — eval module surface
- [`docs/permissions.md`](permissions.md) — permissions cascade (separate but parallel)
- [`docs/strictness-levels.md`](strictness-levels.md) — strictness rung defaults
- [`docs/ide-integration.md`](ide-integration.md) — how IDE integrations consume the cascade
