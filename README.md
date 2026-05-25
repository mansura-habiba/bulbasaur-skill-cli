# Bulbasaur

A developer utility for building, validating, and managing AI agent skills — aligned with the [agentskills.io specification](https://agentskills.io/specification). One CLI (`bbsctl`) that covers the full skill lifecycle: scaffold, compile, audit, evaluate, publish, and install.

Skills are validated contracts with frontmatter metadata, structured body sections (instructions, guardrails, triggers, examples), and an eval corpus that scores assertions against actual output. Skills are versioned through `skills.lock` — content-addressed by sha256 digest — so every team member gets the exact same versions.

Two workflows:

1. **Author your own** — scaffold from the agentskills.io spec, compile, audit, evaluate, publish to a team marketplace, install as a locked dependency.
2. **Consume external skills** — fetch from [skills.sh](https://skills.sh) or GitHub, quarantine in staging, trust-audit (guardrails, scripts, permissions), install after review.

## Install

```bash
# From PyPI (when published)
uv add bbsctl

# From source (development)
make install
```

## Quickstart

[Install `uv`](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it.

```bash
# 1. Initialise your project
uv run bbsctl init --strictness team

# 2. Scaffold a skill from the agentskills.io spec
uv run bbsctl new log-analyzer

# 3. Fill in the contract
#    → Edit log-analyzer/SKILL.md: description, instructions, guardrails, examples

# 4. Compile — validates frontmatter against the spec
cd log-analyzer && uv run bbsctl compile

# 5. Run — mock agent activates the skill
uv run bbsctl run
```

That's the five-minute promise. From here you can climb the strictness ladder, add evals, publish to a marketplace, or fetch external skills.

## The two lifecycles

```
Use Case 1: Generate                 Use Case 2: Fetch
─────────────────────                ─────────────────────
bbsctl new                           bbsctl fetch <url>
    │                                    │
    ▼                                    ▼
bbsctl compile                       ┌─────────────┐
    │                                │  quarantined │
    ▼                                │  in staging  │
bbsctl audit                         └──────┬──────┘
    │                                       │
    ▼                                bbsctl audit
bbsctl eval                              │
    │                                    ▼
    ▼                                bbsctl eval
bbsctl publish                           │
    │                                    ▼
    ▼                                bbsctl add --staged
bbsctl add / install                 bbsctl install
```

### Use Case 1: Generate → Audit → Evaluate → Install

Author a skill, validate it, evaluate it against assertions, and share it.

```bash
# Scaffold and compile
uv run bbsctl new log-analyzer
cd log-analyzer && uv run bbsctl compile

# Promote to team strictness (adds skill.yaml with ownership)
uv run bbsctl strictness team --yes

# Audit and validate
uv run bbsctl audit .
uv run bbsctl validate --fast

# Write an eval corpus (evals/behavior.json) and evaluate
uv run bbsctl eval

# Publish to a team marketplace
uv run bbsctl marketplace init ../my-team-marketplace
uv run bbsctl publish --marketplace ../my-team-marketplace

# Consume in another project
cd ../consumer-project
uv run bbsctl add log-analyzer-plugin@../my-team-marketplace
uv run bbsctl install
```

### Use Case 2: Fetch → Audit → Evaluate → Install

Fetch an external skill, audit it for trust, and install only after review.

```bash
# Fetch from skills.sh or GitHub — auto-runs a trust audit
uv run bbsctl fetch vercel-labs/agent-skills/web-design-guidelines

# Review the staged skill (quarantined in .bulbasaur/staging/)
cat .bulbasaur/staging/web-design-guidelines/SKILL.md

# Re-audit if needed
uv run bbsctl audit .bulbasaur/staging/web-design-guidelines

# Install only when satisfied
uv run bbsctl add --staged web-design-guidelines
uv run bbsctl install
```

## The skill contract

Every skill is scaffolded from a **spec-driven YAML schema** ([`agentskills-spec.yaml`](bbsctl/src/skillctl/agentskills/agentskills-spec.yaml)). When you run `bbsctl new`, you get a complete contract — not a blank file:

```yaml
---
name: log-analyzer
description: Analyze application log files to identify errors, warnings, and anomalies.
  Use when the user asks to investigate logs or diagnose application issues.
# license: Apache-2.0
# compatibility: Designed for Claude Code (or similar products)
# metadata:
#   author: your-org
#   version: 1.0
# allowed-tools: Bash(grep:*) Read
---

## Instructions
1. Read the provided log file or log snippet from the user's input.
2. Parse each log entry and classify by severity: ERROR, WARN, INFO, DEBUG.
3. Group related errors by stack trace or error code to identify distinct issues.
4. Present a structured report: critical errors first, then warnings, then anomalies.

## When to use this skill
- User asks to "look at", "analyze", or "investigate" a log file
- User pastes log output and asks "what went wrong?"
- Do NOT activate for metric dashboards — those are not logs

## Guardrails
- **Must never:** Modify or delete the original log files
- **Must reject:** Log snippets containing credentials or API keys — flag and redact
- **Must fallback:** If the log format is unrecognized, ask the user to clarify

## Examples
**Input:** "Analyze this log file and tell me why the service keeps crashing"
**Output:** 3 distinct crash patterns: OOM kills (5x), connection pool exhaustion (2x),
unhandled NullPointerException in PaymentService.process() (1x). Investigate OOM first.

## Edge cases
- Interleaved logs from multiple services: group by service name before analyzing
- Massive log files (>100MB): suggest filtering by time range first
```

### Skill directory structure

```
log-analyzer/
├── SKILL.md          # Required: metadata + instructions (the contract)
├── evals/            # Eval corpus (behavior.json, triggers.json, injection.json)
├── references/       # Optional: documentation (progressive loading)
├── scripts/          # Optional: executable code
├── assets/           # Optional: templates, data files, schemas
└── skill.yaml        # team+ only: enterprise overlay (strictness, ownership)
```

## Evaluating skills

Validation is structural (does the manifest parse?). **Evaluation is behavioral** — given a corpus of test prompts, does the skill produce the right output and satisfy each declared assertion?

```json
{
  "skill_name": "log-analyzer",
  "evals": [
    {
      "id": 1,
      "prompt": "Analyze this log and tell me what's wrong:\n2025-05-20 14:01:12 ERROR PaymentService - Connection refused to db-primary:5432\n2025-05-20 14:01:15 ERROR PaymentService - Failed to process payment: DBConnectionException",
      "expected_output": "Database connection failures as root cause, retry exhaustion leading to payment failure.",
      "assertions": [
        "The reply identifies db-primary:5432 connection failures as the root issue",
        "The reply recommends checking database availability first"
      ]
    }
  ]
}
```

```bash
uv run bbsctl eval                              # all suites
uv run bbsctl eval --suite behavior             # one suite
uv run bbsctl eval --output json > report.json  # CI
```

The mock runtime + heuristic judge is deterministic — no LLM, no API key. Real LLM judging via the Claude Agent SDK adapter uses the same interface.

See [`docs/evaluation.md`](docs/evaluation.md) for the full spec, case schema, and CI recipes.

## The trust audit

Every external skill passes through a trust audit before installation. The audit checks:

| Check | What it catches |
|---|---|
| **spec-completeness** | Missing required fields, name mismatches |
| **body-sections** | Missing Instructions, Guardrails, or When-to-use sections |
| **guardrails-quality** | Skills with no safety boundaries defined |
| **scripts** | Executable code bundled with the skill |
| **broad-permissions** | Overly permissive `allowed-tools` declarations |
| **enterprise-overlay** | Missing `skill.yaml` at team+ strictness |

```bash
uv run bbsctl audit .bulbasaur/staging/web-design-guidelines
uv run bbsctl audit --output json  # for CI gates
```

Verdict is one of: **TRUSTED**, **TRUSTED (with warnings)**, or **DO NOT TRUST (without review)**.

## The strictness ladder

Strictness controls how much friction the framework applies. It climbs with you — never ahead of you.

| Level | What the framework requires | Typical use |
|---|---|---|
| `local` (default) | Spec-valid `SKILL.md` only | Solo dev, prototyping |
| `team` | + `skill.yaml`, ownership stub, fast validators, team marketplace | Small-team sharing |
| `org` | + full validators, **eval corpus + passing report**, signing, OTel, cost budgets | Production internal use |
| `regulated` | + regulatory sign-off, pinned eval corpora, retention SLAs, strict gates | High-risk workflows |

```bash
uv run bbsctl strictness team     # adds skill.yaml, prompts for ownership stub
uv run bbsctl strictness org      # full enterprise overlay (Phase 3)
```

The framework does not force escalation. The **marketplace is the gate** that refuses to host skills below its declared strictness.

## CLI reference

| Command | What it does |
|---|---|
| `bbsctl init` | Write `[tool.bulbasaur]` config to `pyproject.toml` |
| `bbsctl new <name>` | Scaffold `SKILL.md` from the spec |
| `bbsctl compile` | Parse frontmatter, validate against agentskills.io, emit report |
| `bbsctl run` | Execute against an `AgentRuntime` adapter |
| `bbsctl strictness <level>` | Promote a skill to a higher strictness level |
| `bbsctl validate --fast` | Structural checks: enterprise-spec, trigger heuristic, output-contract |
| `bbsctl eval` | Run the `evals/` corpus and score assertions |
| `bbsctl audit <path>` | Trust audit: spec-completeness, guardrails, scripts, permissions |
| `bbsctl fetch <url>` | Download from skills.sh or GitHub into `.bulbasaur/staging/` |
| `bbsctl marketplace init` | Create a Git-backed team marketplace |
| `bbsctl publish --marketplace` | Publish a skill to a marketplace |
| `bbsctl add <skill>@<source>` | Install a skill from a marketplace into `skills.lock` |
| `bbsctl add --staged <name>` | Install a skill from the staging area |
| `bbsctl install` | Install all skills from `skills.lock` |
| `bbsctl list` | List installed skills |

Every command supports `--output json` for CI integration.

## Error contract

Every error in the framework has the same shape — summary, detail, fix, docs:

```
ERROR: invalid skill name: must be lowercase (no uppercase letters)
  Detail: agentskills.io rule violation (code=pattern)
  Fix:    Rename to a lowercase kebab-case identifier (e.g. `my-skill`).
  Docs:   https://agentskills.io/specification#name-field
```

The `Fix` line is always copy-pasteable. The audit-enforced rule is that 90%+ of errors carry a Fix.

## Current status

| Command | Status | Notes |
|---|---|---|
| `bbsctl new` | **Shipped** | Spec-driven scaffold with all fields + sections |
| `bbsctl compile` | **Shipped** | Frontmatter validation against agentskills.io |
| `bbsctl validate --fast` | **Shipped** | enterprise-spec, basic-trigger, output-contract |
| `bbsctl validate --full` | Stub | Phase 3: + registry-context trigger, injection, fuzzer |
| `bbsctl run` | Mock only | Real adapters land in Phase 4+ |
| `bbsctl eval` | **Shipped** | Behavior corpus + heuristic judge (mock runtime) |
| `bbsctl fetch` | **Shipped** | Download from skills.sh / GitHub into staging |
| `bbsctl audit` | **Shipped** | Trust audit: spec, guardrails, scripts, permissions |
| `bbsctl init` | **Shipped** | Writes `[tool.bulbasaur]` to `pyproject.toml` |
| `bbsctl strictness team` | **Shipped** | Interactive ownership prompt, `--yes` for CI |
| `bbsctl marketplace init / list` | **Shipped** | Git-backed, Claude Code compatible |
| `bbsctl publish --marketplace` | **Shipped** | Team marketplace target |
| `bbsctl add / install / remove / list` | **Shipped** | `skills.lock` with sha256 digest |
| `bbsctl strictness org / regulated` | Not yet | Phase 3 / Phase 5 |
| Sigstore signing | Not yet | Phase 3 |

## Documentation

- [`docs/demo.md`](docs/demo.md) — 8-minute live demo walkthrough
- [`docs/strictness-levels.md`](docs/strictness-levels.md) — the strictness axis explained
- [`docs/evaluation.md`](docs/evaluation.md) — the eval corpus convention and `bbsctl eval`
- [`docs/spec-guidelines.md`](docs/spec-guidelines.md) — the spec, aligned with [agentskills.io](https://agentskills.io)
- [`docs/design-patterns.md`](docs/design-patterns.md) — Strategy, Factory, Adapter, Decorator patterns
- [`docs/best-practices.md`](docs/best-practices.md) — authoring guidance
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — error → fix table

## Architecture

The framework is built on three reusable patterns (per [`docs/design-patterns.md`](docs/design-patterns.md)):

- **Strategy + Factory** — `CompileStep`, `Validator`, `Evaluator`, `AgentRuntime`, `PublishTarget`. Each is an interface; concrete implementations register through a factory. Adding a new validator or runtime is one class plus one registration line.
- **Adapter** — for cross-framework runtimes (Claude Agent SDK, MCP, LangGraph, CrewAI). Each adapter normalizes a foreign runtime into the `AgentRuntime` interface so `bbsctl run` and `bbsctl eval` don't care which one is in use.
- **Decorator** — for cross-cutting concerns (telemetry, cost budgeting, audit logging) layered on top of runtimes and evaluators without modifying them.

## Project layout

```
bulbasaur-skill-cli/
├── bbsctl/                       the CLI package (Python ≥3.11, module: skillctl)
│   ├── src/skillctl/
│   │   ├── agentskills/          spec parser, rules, agentskills-spec.yaml
│   │   ├── audit/                trust audit checks and runner
│   │   ├── commands/             CLI subcommands
│   │   ├── compile/              compile pipeline (Strategy pattern)
│   │   ├── eval/                 evaluator framework
│   │   ├── marketplace/          Git-backed marketplace + skills.lock
│   │   ├── publish/              publish targets
│   │   ├── run/                  AgentRuntime adapters
│   │   ├── templates/            SKILL.md templates per strictness level
│   │   └── validate/             validator chain
│   ├── tests/
│   └── pyproject.toml
├── reference-plugins/            demo skills (hello-skill, log-analyzer)
├── quickstart/                   the five-minute experience
├── docs/                         guides, recipes, audits
├── tests/                        cross-cutting contract tests
├── Makefile                      build, install, try, test, lint, clean
└── .governance/                  capability + acceptance schemas
```

## Makefile targets

```bash
make build     # Build the wheel into bbsctl/dist/
make install   # Build + install wheel into .try-venv
make try       # Install + run the full end-to-end developer journey
make test      # Run the test suite
make lint      # Run ruff
make clean     # Remove build artifacts
```

## Contributing

Two things make a PR easier to merge:

1. **A friction-audit note.** If your change touches the CLI surface or any error message, walk the affected flow as a fresh developer and note where you hesitated. The friction-audit protocol ([`docs/friction-audit.md`](docs/friction-audit.md)) is the template.
2. **No vapor options.** If you add an argparse `choices=` value, the implementation behind it must work end-to-end. The vapor-options lint test walks the support registry and will fail otherwise.

## License

Apache 2.0.
