# `bbsctl` user guide

Install, configure, and run every command. Read top-to-bottom for the five-minute path, or jump to the command you need.

---

## Contents

- [1. Quickstart — five minutes from zero](#1-quickstart--five-minutes-from-zero)
- [2. Installation](#2-installation)
- [3. Configuration](#3-configuration)
- [4. Command reference](#4-command-reference)
- [5. End-to-end recipes](#5-end-to-end-recipes)
- [6. Troubleshooting](#6-troubleshooting)

---

## 1. Quickstart — five minutes from zero

Install `uv` if you don't have it, then:

```bash
uvx bbsctl new hello-skill
cd hello-skill
uvx bbsctl compile
uvx bbsctl run
uvx bbsctl publish
```

That scaffolds a skill, compiles it, activates it against the mock runtime, and publishes a marketplace directory next to it that stock Claude Code accepts via `/plugin marketplace add ./bulbasaur-marketplace`.

No marketplace setup, no signing, no API key.

---

## 2. Installation

### Prerequisites

- **Python ≥ 3.11, < 3.14** — required.
- **`uv`** — the canonical toolchain. [Install guide](https://docs.astral.sh/uv/getting-started/installation/).

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify
uv --version
uv python install 3.11
```

### Install methods

**Trial, no install** — fastest way to evaluate:

```bash
uvx bbsctl <command>
```

`uvx` downloads `bbsctl` into a transient cache and runs it. Nothing lands in your project. Good for evaluation and one-off runs.

**Project install** — recommended for any real use:

```bash
uv add bbsctl
bbsctl <command>
```

`bbsctl` becomes a project dependency in your `pyproject.toml`. Reproducible across machines once you commit `uv.lock`.

**Pip install** — for non-`uv` projects:

```bash
pip install bbsctl
```

Works but `uv` is canonical for the rest of this guide.

### Optional dependency groups

The base install is stdlib-only (plus `ruamel.yaml`). Heavier dependencies opt in:

```bash
uv add 'bbsctl[validator]'    # Phase 3 validator suite
uv add 'bbsctl[runtime]'      # OpenTelemetry, real runtime adapters
uv add 'bbsctl[registry]'     # Sigstore signing, OCI publish
uv add 'bbsctl[full]'         # everything
```

For development on `bbsctl` itself:

```bash
uv add 'bbsctl[dev]'          # pytest, ruff
```

### Verifying the install

```bash
bbsctl --version
bbsctl --help
```

Expected output: version string and a list of subcommands (init, new, strictness, compile, validate, run, eval, marketplace, publish, add, install, remove, list, lock).

---

## 3. Configuration

### The cascade — seven layers, highest priority wins

| Priority | Source | Scope | Set by |
|---|---|---|---|
| 1 | CLI flag | per-command | developer |
| 2 | Environment variable | shell session | developer or CI |
| 3 | `evals/eval.config.yaml`, `skill.yaml`, `permissions.yaml`, `ownership.yaml` | one skill | skill author |
| 4 | `pyproject.toml [tool.bulbasaur.*]` | one project | project lead |
| 5 | `~/.config/bbsctl/config.yaml` | one user | developer once |
| 6 | `/etc/bbsctl/config.yaml` or `$BBSCTL_ORG_CONFIG` | one org/machine | platform team |
| 7 | Built-in default | all users | framework code |

See [`docs/configuration.md`](configuration.md) for the full reference. The TL;DR is below.

### API keys

`bbsctl` reads keys from the environment, never from a YAML file:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."     # Claude Agent SDK runtime + LLMJudge
export OPENAI_API_KEY="sk-..."            # OpenAI backend
export OPENAI_API_BASE="http://localhost:1234/v1"  # local OpenAI-compatible server
export OLLAMA_HOST="http://localhost:11434"        # Ollama default endpoint
```

For Ollama (the only no-key option):

```bash
# Install Ollama, then pull a model:
ollama pull llama3:8b
```

### User-level config — `~/.config/bbsctl/config.yaml`

Set personal defaults once:

```yaml
schema_version: bulbasaur/v1

eval:
  runtime: claude-agent-sdk
  runtime_model: claude-sonnet-4-6
  judge: llm
  judge_backend: ollama
  judge_model: llama3:8b
  threshold: 1.0

llm_backends:
  ollama:
    host: http://localhost:11434
    default_model: llama3:8b
  anthropic:
    default_model: claude-sonnet-4-6
```

Every `bbsctl eval` from any project on your machine now uses Claude + Ollama-judged unless overridden.

### Org-level config — `/etc/bbsctl/config.yaml`

Same schema. Typically managed by a platform team:

```yaml
schema_version: bulbasaur/v1
eval:
  judge_backend: ollama
  judge_model: llama3:8b
llm_backends:
  ollama:
    host: http://internal-ollama.corp:11434
```

User-level settings override org-level for fields they explicitly set; org-level provides where the user is silent.

### Project-level config — `pyproject.toml`

```toml
[tool.bulbasaur]
default_strictness = "team"
marketplace = "./team-marketplace"

[tool.bulbasaur.eval]
runtime = "mock"
threshold = 0.95
```

Run `bbsctl init` to scaffold the section for you.

### Skill-level config — files next to `SKILL.md`

Each is sibling to `SKILL.md`:

| File | Purpose | Required at |
|---|---|---|
| `skill.yaml` | strictness, ownership stub, output_contract, model_compatibility | team+ |
| `permissions.yaml` | command/URL/MCP-tool allow-deny | org+ |
| `ownership.yaml` | team, contact, runbook, on-call, escalation | org+ |
| `evals/eval.config.yaml` | runtime + judge pinning for reproducible eval | optional |
| `evals/*.json` | behavior, injection, fuzz, triggers corpora | recommended at team+ |

### Environment variables — full reference

| Variable | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Required for Claude Agent SDK runtime and Anthropic LLMJudge |
| `OPENAI_API_KEY` | Required for OpenAI backend |
| `OPENAI_API_BASE` | Override the OpenAI base URL (LM Studio, vLLM, llama.cpp) |
| `OLLAMA_HOST` | Override the Ollama endpoint |
| `OLLAMA_MODEL` | Override the Ollama default model |
| `ANTHROPIC_MODEL` | Override the Claude default model |
| `BBSCTL_LLM_BACKEND` | Default LLM backend (`ollama` / `anthropic` / `openai`) |
| `BBSCTL_RUNTIME_MODEL` | Short alias for the eval runtime's model |
| `BBSCTL_JUDGE_BACKEND` | Short alias for the eval judge backend |
| `BBSCTL_JUDGE_MODEL` | Short alias for the eval judge model |
| `BBSCTL_EVAL_RUNTIME` | Eval runtime adapter |
| `BBSCTL_EVAL_RUNTIME_MODEL` | Eval runtime model |
| `BBSCTL_EVAL_RUNTIME_MAX_TOKENS` | Eval runtime per-activation max tokens |
| `BBSCTL_EVAL_RUNTIME_TEMPERATURE` | Eval runtime temperature |
| `BBSCTL_EVAL_JUDGE` | Eval judge name |
| `BBSCTL_EVAL_JUDGE_BACKEND` | Eval judge backend |
| `BBSCTL_EVAL_JUDGE_MODEL` | Eval judge model |
| `BBSCTL_EVAL_JUDGE_THRESHOLD` | Heuristic judge keyword overlap threshold |
| `BBSCTL_EVAL_JUDGE_MAX_TOKENS` | LLM judge per-assertion max tokens |
| `BBSCTL_EVAL_THRESHOLD` | Suite pass threshold |
| `BBSCTL_EVAL_FUZZ_N_VARIANTS` | SemanticFuzzer rephrasings per case |
| `BBSCTL_USER_CONFIG` | Override user-config path |
| `BBSCTL_ORG_CONFIG` | Override org-config path |
| `XDG_CACHE_HOME` | Override eval cache root |
| `XDG_CONFIG_HOME` | Override user-config root |
| `BBSCTL_DEBUG=1` | Print full Python tracebacks on framework error |

Long-form (`BBSCTL_EVAL_*`) takes precedence over short aliases.

---

## 4. Command reference

Each command shows: what it does, common flags, an example invocation, expected output.

### `bbsctl init` — set up Bulbasaur in a project

Writes `[tool.bulbasaur]` to `pyproject.toml`. Safe to re-run.

```bash
bbsctl init                          # add at local strictness
bbsctl init --strictness team        # team-tier default
bbsctl init --marketplace ./team-mp  # default marketplace path
bbsctl init --force                  # overwrite existing section
```

Expected:

```
Added [tool.bulbasaur] to /Users/you/project/pyproject.toml

Next:
  bbsctl new my-skill --strictness team
  bbsctl validate --fast
```

### `bbsctl new` — scaffold a skill

Creates a directory with `SKILL.md` (and `skill.yaml` at team+):

```bash
bbsctl new mq-restarter                          # local strictness (default)
bbsctl new mq-restarter --strictness team        # team strictness
bbsctl new mq-restarter --dir ~/skills           # parent directory
```

Expected:

```
Created /Users/you/mq-restarter/SKILL.md

Next:
  cd mq-restarter
  bbsctl compile
  bbsctl run
```

### `bbsctl strictness` — climb the ladder

Promotes an existing skill to a higher strictness rung:

```bash
bbsctl strictness team             # interactive prompts for ownership
bbsctl strictness team -y          # accept all defaults (CI)
```

Today supports `team`; `org` and `regulated` are roadmap items.

Expected:

```
Migrating `mq-restarter` to team strictness.

Created /Users/you/mq-restarter/skill.yaml

skill `mq-restarter` is now at team strictness.

Next steps:
  bbsctl validate --fast
  bbsctl publish --marketplace <path>
```

### `bbsctl compile` — run the compile pipeline

Parses `SKILL.md`, validates against [agentskills.io](https://agentskills.io/specification), writes `dist/compile-report.json`:

```bash
bbsctl compile                       # current directory
bbsctl compile path/to/skill         # other directory
bbsctl compile --output json         # machine-readable output
```

Expected:

```
bbsctl compile  ·  /path/to/skill  ·  strictness=local
  ✓ parse-frontmatter
  ✓ validate-agentskills-spec
  ✓ emit-report

compile OK  ·  0 error(s), 0 warning(s)  ·  1 ms
```

### `bbsctl validate` — fast or full validation

Runs the validator chain. `--fast` (default) takes under a second; `--full` adds Phase 3 validators.

```bash
bbsctl validate                     # --fast by default
bbsctl validate --fast              # explicit
bbsctl validate --full              # Phase 3 — adds registry-context, injection, fuzzer
bbsctl validate --output json       # CI integration
bbsctl validate --strictness org    # override declared strictness
```

Fast validators (always run): `enterprise-spec`, `basic-trigger`, `output-contract`, `permissions`, `ownership`.

Expected on a fresh scaffold (the placeholder description triggers a warning):

```
validate [fast] @ team: PASSED
  skill: /path/to/skill

  ✓ enterprise-spec (2ms)
  ✗ basic-trigger (1ms)
    WARN: description lacks action verbs (placeholder text)
  ✓ output-contract (1ms)
  ✓ permissions (1ms)
  ✓ ownership (1ms)

Result: PASSED  0 error(s), 1 warning(s)
```

### `bbsctl run` — activate against a runtime adapter

```bash
bbsctl run                                   # mock runtime, prompt "hello"
bbsctl run --runtime claude-agent-sdk        # real Claude (needs ANTHROPIC_API_KEY)
bbsctl run --prompt "restart mq-operator"    # custom prompt
```

Expected (mock):

```
[mock-agent] received prompt: 'hello'
[mock-agent] activated: mq-restarter
[mock-agent] reply: (first body line)
```

Expected (claude-agent-sdk):

```
[claude-agent-sdk] received prompt: 'restart mq-operator'
[claude-agent-sdk] activated: mq-restarter
[claude-agent-sdk] model: claude-sonnet-4-6
[claude-agent-sdk] tokens: in=512, out=187
[claude-agent-sdk] latency: 1843ms
```

### `bbsctl eval` — behavioral eval against a corpus

Reads `evals/*.json`. Each file is one suite (name = filename stem).

#### Suite filtering

```bash
bbsctl eval                          # every suite
bbsctl eval --suite behavior         # one suite
bbsctl eval --case 4                 # one case
bbsctl eval --mode smoke             # one case per suite (CI smoke)
bbsctl eval --mode fast              # every case (default)
bbsctl eval --mode full              # fast + regression compare (Phase 3)
```

#### Runtime selection

```bash
bbsctl eval --runtime mock                              # no API key
bbsctl eval --runtime claude-agent-sdk                  # real Claude
bbsctl eval --runtime claude-agent-sdk --runtime-model claude-sonnet-4-6
bbsctl eval --runtime-max-tokens 4096 --runtime-temperature 0.0
```

#### Judge selection

```bash
bbsctl eval --judge heuristic                           # default; no API key, deterministic
bbsctl eval --judge heuristic --judge-threshold 0.6     # tighter keyword overlap
bbsctl eval --judge llm --judge-backend ollama          # local LLM-as-judge
bbsctl eval --judge llm --judge-backend ollama --judge-model llama3:8b
bbsctl eval --judge llm --judge-backend anthropic --judge-model claude-haiku-4-5-20251001
bbsctl eval --judge llm --judge-backend openai --judge-model gpt-4o-mini
bbsctl eval --judge-max-tokens 512                      # per-assertion budget
```

#### Threshold control

```bash
bbsctl eval --threshold 1.0          # default; every assertion must pass
bbsctl eval --threshold 0.8          # pass if 80% of assertions pass
```

#### Reproducibility — cache + snapshots

```bash
bbsctl eval --cache                  # read + write the eval cache
bbsctl eval --refresh-cache          # force re-run; overwrite cache
bbsctl eval --snapshot behavior      # write evals/snapshots/behavior.<model>.json
```

#### Output

```bash
bbsctl eval                          # text
bbsctl eval --output json > report.json
bbsctl eval --output silent          # CI-only — exit code carries the signal
```

#### Expected text output

```
eval [fast] @ team: FAILED  (runtime=claude-agent-sdk:claude-sonnet-4-6, judge=llm:llama3:8b)
  skill: /path/to/mq-restarter
  score: 0.67  threshold: 1.00  (2/3 case(s) passing)
  cache_key: 2a8f3a88...  (skill=6e9e6c35, corpus=8de88672)

  suite `behavior`: FAIL  score=0.67  (2/3)
    ✓ case id=1  score=1.00  (1843ms)
      · Dry-run preview is presented before execution
      · kubectl rollout restart command is executed
      · Health checks are performed after execution
    ✓ case id=2  score=1.00  (1402ms)
      · ...
    ✗ case id=4  score=0.50  (1611ms)
      ✗ kube-system is detected as excluded
          (LLM judge: output mentions kube-system but does not say excluded)
      · No operator bypass is offered
```

#### Exit codes

- `0` — every suite passed (score ≥ threshold)
- `1` — at least one case failed
- `2` — framework error (missing `SKILL.md`, malformed corpus, etc.)

### `bbsctl publish` — push to a marketplace

```bash
bbsctl publish                                   # default target: claude-code-local
bbsctl publish my-skill                          # explicit skill dir
bbsctl publish --marketplace ./team-marketplace  # team-marketplace target
bbsctl publish --target claude-code-local --output ./dist
bbsctl publish --option marketplace_name=acme    # target-specific options
```

Expected for `claude-code-local`:

```
published via claude-code-local
  · marketplace: /path/to/bulbasaur-marketplace
  · plugin:      /path/to/bulbasaur-marketplace/plugins/mq-restarter-plugin

Next steps:
  /plugin marketplace add ./bulbasaur-marketplace
  /plugin install mq-restarter-plugin@bulbasaur-local
```

Expected for `--marketplace`:

```
published to marketplace `team-marketplace`
  plugin: /path/to/team-marketplace/plugins/mq-restarter-plugin

Next steps:
  /plugin marketplace add ./team-marketplace
  /plugin install mq-restarter-plugin@team-marketplace
```

The team-marketplace target writes `bundle.lock` (SHA-256 per file) and `bundle.sig` (placeholder for Sigstore at org+) alongside the plugin.

### `bbsctl marketplace` — manage marketplaces

```bash
bbsctl marketplace init ./team-marketplace                # scaffold
bbsctl marketplace init ./team-marketplace --owner alice  # owner metadata
bbsctl marketplace list ./team-marketplace                # list plugins
```

Expected for `init`:

```
Marketplace initialised: /path/to/team-marketplace
  name:  team-marketplace
  owner: alice

Next steps:
  bbsctl publish --marketplace ./team-marketplace
  # In Claude Code:
  /plugin marketplace add ./team-marketplace
```

### `bbsctl add` — add a skill dependency

```bash
bbsctl add my-skill@./team-marketplace
bbsctl add my-skill                          # if default marketplace is set in pyproject
```

Expected:

```
Added my-skill@0.1.0 [team]
  cache: /path/to/project/.bulbasaur/cache/my-skill
  lock:  /path/to/project/skills.lock
```

### `bbsctl install` — install everything in `skills.lock`

```bash
bbsctl install
```

Reads `skills.lock`, copies each plugin into `.bulbasaur/cache/`, deterministic.

### `bbsctl remove` — remove a skill from the lock

```bash
bbsctl remove my-skill
```

### `bbsctl list` — list installed skills

```bash
bbsctl list
```

Expected:

```
Installed skills (2):
  mq-restarter@0.1.0  [team]
    source: ./team-marketplace#mq-restarter@0.1.0
  oncall-triage@0.2.1  [team]
    source: ./team-marketplace#oncall-triage@0.2.1
```

### `bbsctl lock` — regenerate `skills.lock`

```bash
bbsctl lock
```

Writes the lockfile based on the current entries; does not install. Useful after manual edits.

---

## 5. End-to-end recipes

### Recipe A — solo developer, local strictness, five-minute path

```bash
uvx bbsctl new hello-skill
cd hello-skill
uvx bbsctl compile
uvx bbsctl run
uvx bbsctl publish

# In Claude Code:
# /plugin marketplace add ./bulbasaur-marketplace
# /plugin install hello-skill-plugin@bulbasaur-local
```

No API key, no marketplace setup, no signing. Done.

### Recipe B — team skill with real eval

Prerequisites:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # or use Ollama for free
```

Or, if you want offline:

```bash
ollama pull llama3:8b
```

Then:

```bash
uv add bbsctl
bbsctl init --strictness team --marketplace ./team-marketplace

bbsctl new mq-restarter --strictness team
cd mq-restarter
bbsctl validate --fast

# Author a corpus
mkdir evals
cat > evals/behavior.json <<'EOF'
{
  "skill_name": "mq-restarter",
  "evals": [
    {
      "id": 1,
      "prompt": "Restart deployment mq-operator in namespace mq-prod",
      "expected_output": "ValidationReport showing kubectl rollout restart was executed and health checks passed.",
      "files": [],
      "assertions": [
        "kubectl rollout restart command is executed",
        "Health checks are performed after execution"
      ]
    }
  ]
}
EOF

# Pin the eval inputs
cat > evals/eval.config.yaml <<'EOF'
schema_version: bulbasaur/v1
runtime: claude-agent-sdk
runtime_model: claude-sonnet-4-6
judge: llm
judge_backend: anthropic
judge_model: claude-haiku-4-5-20251001
threshold: 1.0
EOF

# Run
bbsctl eval --cache --output json > eval-report.json
bbsctl eval --snapshot behavior

# Publish
cd ..
bbsctl marketplace init ./team-marketplace
bbsctl publish --marketplace ./team-marketplace mq-restarter
```

### Recipe C — adopt across an org

Platform team sets defaults once:

```bash
sudo tee /etc/bbsctl/config.yaml <<'EOF'
schema_version: bulbasaur/v1
eval:
  judge_backend: ollama
  judge_model: llama3:8b
  threshold: 1.0
llm_backends:
  ollama:
    host: http://internal-ollama.corp:11434
EOF
```

Every developer in the org now runs `bbsctl eval` against internal Ollama with the approved judge model — no per-repo configuration. A developer who wants to try Anthropic for a one-off experiment:

```bash
BBSCTL_JUDGE_BACKEND=anthropic ANTHROPIC_API_KEY=... bbsctl eval
```

Or one-off CLI override:

```bash
bbsctl eval --judge-backend anthropic --judge-model claude-haiku-4-5-20251001
```

### Recipe D — CI integration with branch protection

Wire `bbsctl` into GitHub Actions. `.github/workflows/skill-checks.yml`:

```yaml
name: skill-checks
on: [pull_request, push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.11

      - name: Install
        run: uv add bbsctl

      - name: Compile
        run: bbsctl compile --output json > compile-report.json

      - name: Validate (fast)
        run: bbsctl validate --fast --output json > validate-report.json

      - name: Evaluate
        env:
          BBSCTL_JUDGE_BACKEND: ollama
          OLLAMA_HOST: ${{ secrets.OLLAMA_HOST }}
        run: bbsctl eval --cache --mode fast --output json > eval-report.json

      - uses: actions/upload-artifact@v4
        with:
          name: skill-reports
          path: |
            compile-report.json
            validate-report.json
            eval-report.json
```

Then in branch protection: require the `validate` job to succeed before merging.

---

## 6. Troubleshooting

### `bbsctl: command not found`

The install didn't put `bbsctl` on your PATH:

```bash
uv tool install bbsctl       # installs the binary on PATH
# or
uv run bbsctl <command>      # run inside the project
```

### `Python 3.11+ required`

```bash
uv python install 3.11
```

### `ANTHROPIC_API_KEY not set`

Export it before invoking the Claude-backed runtime or LLMJudge:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

For an offline run, switch to Ollama:

```bash
bbsctl eval --judge heuristic                     # no API call
bbsctl eval --judge llm --judge-backend ollama    # local Ollama
```

### `no evals/ directory found`

`bbsctl eval` requires at least one suite file under `evals/`. Create one:

```bash
mkdir evals
cat > evals/behavior.json <<'EOF'
{"skill_name": "my-skill", "evals": [{"id": 1, "prompt": "hi", "assertions": []}]}
EOF
```

### `permissions.yaml not found` (at org+ strictness)

`bbsctl validate` requires `permissions.yaml` at `org` and above. Either create one (see [`docs/permissions.md`](permissions.md)) or stay at `team`:

```bash
bbsctl validate --strictness team
```

### `digest mismatch` on `bbsctl install`

The bundle on disk doesn't match its `bundle.lock`. Either the marketplace was tampered with after publish, or the lock is stale. Re-publish:

```bash
bbsctl publish --marketplace <path> <skill>
```

### Eval reports `(cached)` when you didn't expect it

The cache key matched a previous run. To force a fresh run:

```bash
bbsctl eval --refresh-cache
```

If you changed something the cache should have caught (e.g. an env var), make sure the changed thing is part of the cache key — the key includes runtime, runtime_model, judge, judge_backend, judge_model, mode, filters, skill_hash, corpus_hash. Things outside that list (e.g. an internal Ollama URL change) do not invalidate the cache.

### Eval scores look wrong vs. what the agent actually did

Two common causes:

1. **HeuristicJudge is keyword-based.** The default threshold is `0.5`. If your assertion uses domain-specific synonyms, the heuristic will miss them. Switch to `--judge llm` for production scoring.
2. **The mock runtime returns a placeholder.** If you ran `bbsctl eval` without `--runtime claude-agent-sdk` or another real adapter, the runtime is the mock — it echoes a body line. Assertions about "kubectl is executed" will fail because the mock doesn't execute anything.

### Surprising config — find which layer set what

The eval report records every resolved field:

```bash
bbsctl eval --output json | jq '.runtime, .runtime_model, .judge, .judge_backend, .judge_model, .threshold'
```

If a value is unexpected, walk the cascade:

```bash
# What does the user-level file say?
cat ~/.config/bbsctl/config.yaml

# What does the org-level file say?
cat /etc/bbsctl/config.yaml 2>/dev/null

# What env vars are set?
env | grep -E '^(BBSCTL_|ANTHROPIC_|OPENAI_|OLLAMA_)'

# What does the skill-level file say?
cat ./evals/eval.config.yaml
```

The highest layer that defines the field wins. See [`docs/configuration.md`](configuration.md).

### Raw Python traceback instead of a `FrameworkError`

That's a framework bug, not a user error. To see the full traceback:

```bash
BBSCTL_DEBUG=1 bbsctl <command>
```

Then file an issue with the command, the SKILL.md, and the traceback.

### `vapor option` — argparse rejects a flag value that should work

The strictness ladder enforces a "no vapor options" rule: `--strictness org` won't appear in `--help` until the implementation supports it. If a roadmap feature you saw in a doc is rejected on the CLI, it isn't shipped yet. Check [`docs/bbsctl-roadmap.md`](bbsctl-roadmap.md) for the phase plan.

---

## See also

- [`docs/configuration.md`](configuration.md) — full cascade reference
- [`docs/evaluation.md`](evaluation.md) — eval module deep dive
- [`docs/permissions.md`](permissions.md) — permissions.yaml schema and runtime hooks
- [`docs/strictness-levels.md`](strictness-levels.md) — the strictness ladder
- [`docs/ide-integration.md`](ide-integration.md) — MCP + LSP + per-IDE design
- [`docs/bbsctl-roadmap.md`](bbsctl-roadmap.md) — what's wired vs. roadmap
- [`docs/skill-lifecycle-framework-whitepaper.md`](skill-lifecycle-framework-whitepaper.md) — the broader framework
