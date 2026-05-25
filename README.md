# Bulbasaur

A skill framework for agentic development — aligned with the [agentskills.io specification](https://agentskills.io/specification). Skills are versioned, validated, published, and consumed like production dependencies.

> **North star.** Every skill must be designed, compiled, validated, deployed, monitored, and evaluated like production code — because once skills control agent behavior, they *are* production code.

> **The five-minute promise.** A fresh developer with `uv` installed can scaffold and run their first skill in under five minutes. No marketplace setup. No signing. No ownership document. No policy configuration. Friction climbs with the strictness level the developer opts into, never ahead of it.

## Install

```bash
# From PyPI (when published)
uv add bbsctl

# From source (development)
make install      # builds wheel → installs into .try-venv
```

## Quickstart

`uv` is the canonical Python toolchain — [install it first](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it.

```bash
# 1. Initialise your project (writes [tool.bulbasaur] to pyproject.toml)
bbsctl init --strictness team

# 2. Scaffold a new skill from the agentskills.io spec
bbsctl new my-skill

# 3. Edit the generated contract
#    → Fill in placeholders in SKILL.md (description, instructions, guardrails)
#    → Uncomment optional fields you need (license, compatibility, metadata)

# 4. Compile — validates frontmatter against the spec
bbsctl compile

# 5. Run — mock agent activates the skill
bbsctl run
```

See [`quickstart/`](quickstart/) for the full five-minute walkthrough and [`docs/quickstart.md`](docs/quickstart.md) for the longer guide.

## The skill contract

Every skill is scaffolded from a **spec-driven YAML schema** ([`agentskills-spec.yaml`](bbsctl/src/skillctl/agentskills/agentskills-spec.yaml)) that defines every field, constraint, and placeholder. When you run `bbsctl new`, you get a complete contract — not a blank file:

```yaml
---
name: my-skill
description: '[What My Skill does]. Use when [the trigger situation for my-skill].'

# Optional fields — uncomment and fill in as needed.
# Full spec: https://agentskills.io/specification
# license: Apache-2.0
# compatibility: Designed for Claude Code (or similar products)
# metadata:
#   author: your-org
#   version: 1.0
# allowed-tools: Bash(git:*) Read
---

## Instructions
1. [Step-by-step instructions for what the skill does]
2. [Continue with each discrete step]
3. [End with how to present the result]

## When to use this skill
- [Trigger condition 1: e.g. "User asks to extract data from a PDF"]
- [Trigger condition 2: e.g. "User mentions document conversion"]

## Guardrails
- **Must never:** [Action the skill must never take]
- **Must reject:** [Input the skill must refuse, e.g. "Reject PII in prompts"]
- **Must fallback:** [Behaviour when preconditions are not met]

## Examples
**Input:** [Describe an example user request]
**Output:** [Describe the expected response]

## Edge cases
- [Describe a common edge case and how to handle it]
```

The directory structure follows the [agentskills.io specification](https://agentskills.io/specification):

```
my-skill/
├── SKILL.md          # Required: metadata + instructions (the contract)
├── references/       # Optional: documentation (progressive loading)
├── scripts/          # Optional: executable code
├── assets/           # Optional: templates, data files, schemas
└── skill.yaml        # team+ only: enterprise overlay (strictness, ownership)
```

### Spec fields

| Field | Required | Constraint | Purpose |
|---|---|---|---|
| `name` | Yes | 1–64 chars, lowercase kebab-case, must match directory name | Unique identifier for activation |
| `description` | Yes | ≤ 1024 chars | Agent reads this to decide whether to activate |
| `license` | No | — | License name or reference to bundled file |
| `compatibility` | No | ≤ 500 chars | Environment requirements (product, packages, network) |
| `metadata` | No | Key-value map | Arbitrary metadata (author, version, etc.) |
| `allowed-tools` | No | Space-separated string | Pre-approved tools (experimental) |

### Body sections

| Section | Purpose |
|---|---|
| **Instructions** | Step-by-step instructions for what the skill does |
| **When to use this skill** | Activation cues — positive and negative triggers |
| **Guardrails** | Safety boundaries: what to never do, what to reject, fallback behaviour |
| **Examples** | Input/output examples for the agent |
| **Edge cases** | Known edge cases and how to handle them |
| **References** | Pointers to files loaded progressively at runtime |

## The two lifecycles

Every skill follows one of two paths — **generate** (author your own) or **fetch** (consume someone else's). Both paths converge on the same audit → evaluate → install pipeline.

```
Use Case 1: Generate                 Use Case 2: Fetch
─────────────────────                ─────────────────────
bbsctl new                           bbsctl fetch <url>
    │                                    │
    ▼                                    ▼
bbsctl compile                       ┌─────────────┐
    │                                │  staged in   │
    ▼                                │  .bulbasaur/ │
bbsctl audit                         │  staging/    │
    │                                └──────┬──────┘
    ▼                                       │
bbsctl eval                          bbsctl audit
    │                                    │
    ▼                                    ▼
bbsctl publish                       bbsctl eval
    │                                    │
    ▼                                    ▼
bbsctl add / install                 bbsctl add --staged / install
```

Each stage is a separate subcommand. Each stage is pluggable through a Strategy/Factory abstraction so you can swap implementations without touching the CLI.

| Stage | Command | What it does |
|---|---|---|
| Design | `bbsctl new` | Scaffold `SKILL.md` from the spec + `skill.yaml` at team+ |
| Compile | `bbsctl compile` | Parse frontmatter, validate against [agentskills.io](https://agentskills.io/specification), emit report |
| Fetch | `bbsctl fetch` | Download a skill from skills.sh or GitHub into `.bulbasaur/staging/` |
| Audit | `bbsctl audit` | Trust audit: spec-completeness, guardrails, scripts, broad permissions |
| Validate | `bbsctl validate --fast` | Structural checks: enterprise-spec, trigger heuristic, output-contract |
| Run | `bbsctl run` | Execute against an `AgentRuntime` adapter (mock today) |
| Evaluate | `bbsctl eval` *(Phase 3)* | Run the `evals/` corpus — triggers, behavior, injection, regression |
| Publish | `bbsctl publish` | Emit via a `PublishTarget` (marketplace, Claude Code, MCP Composer) |
| Install | `bbsctl add / install / lock` | Consume skills from a marketplace into `.bulbasaur/cache` via `skills.lock` |

Project-level config lives in `pyproject.toml` under `[tool.bulbasaur]`; `bbsctl init` writes it for you.

## Usage walkthrough

### Use Case 1: Generate → Audit → Evaluate → Install

Author a skill from scratch, validate it, publish to a marketplace, and consume it.

```bash
# Initialise the project
bbsctl init --strictness team

# Scaffold a new skill
bbsctl new pdf-processor

# Fill in the contract (edit SKILL.md: description, instructions, guardrails, examples)
cd pdf-processor && bbsctl compile

# Promote to team strictness
bbsctl strictness team --yes

# Audit and validate
bbsctl audit .
bbsctl validate --fast

# Evaluate (behavioral checks against the evals/ corpus)
bbsctl eval

# Publish to a marketplace
bbsctl marketplace init ../my-team-marketplace
bbsctl publish --marketplace ../my-team-marketplace

# Consume in another project
cd ../consumer-project
bbsctl add pdf-processor-plugin@../my-team-marketplace
bbsctl install
```

### Use Case 2: Fetch → Audit → Evaluate → Install

Fetch a skill from a public catalog, audit it for trust, and install only after review.

```bash
# Fetch from skills.sh or GitHub — auto-runs a trust audit
bbsctl fetch vercel-labs/agent-skills/web-design-guidelines

# Review the staged skill (quarantined in .bulbasaur/staging/)
cat .bulbasaur/staging/web-design-guidelines/SKILL.md

# Re-audit if needed
bbsctl audit .bulbasaur/staging/web-design-guidelines

# Evaluate against your own assertions
bbsctl eval .bulbasaur/staging/web-design-guidelines

# Install only when satisfied
bbsctl add --staged web-design-guidelines
bbsctl install
```

### JSON output for CI

```bash
bbsctl validate --output json > report.json
bbsctl compile  --output json > compile-report.json
```

### Makefile targets (development)

```bash
make build     # Build the wheel into bbsctl/dist/
make install   # Build + install wheel into .try-venv
make try       # Install + run the full end-to-end developer journey
make test      # Run the test suite
make lint      # Run ruff
make clean     # Remove build artifacts
```

## The strictness ladder

Strictness is the primary axis of developer flexibility. It declares how much friction the author has agreed to. The framework asks for more as the author climbs the ladder — never ahead of it.

| Level | What the framework requires | Typical use |
|---|---|---|
| `local` (default) | Spec-valid `SKILL.md` only | Solo dev, prototyping |
| `team` | + ownership stub, fast validators, team marketplace, `skill.yaml` | Small-team sharing |
| `org` | + full validators, **eval corpus + passing report**, signing, OTel, cost budgets | Production internal use |
| `regulated` | + regulatory sign-off, pinned eval corpora, retention SLAs, strict gates | High-risk workflows |

```bash
bbsctl strictness team    # adds skill.yaml, prompts for ownership stub
bbsctl strictness org     # full enterprise overlay, prompts to sign (Phase 3)
```

The framework does not force escalation. The **marketplace is the gate** that refuses to host skills below its declared strictness.

## Evaluating skills *(Phase 3)*

Validation is structural (does the manifest parse, are the fields sane). **Evaluation is behavioral** (given a corpus of test prompts, does the skill produce the right output and satisfy each declared assertion).

`bbsctl eval` reads an `evals/` directory next to the skill:

```
my-skill/
├── SKILL.md
├── skill.yaml
└── evals/
    ├── behavior.json       # prompt → expected_output + assertions
    ├── triggers.json       # activation-only cases (positive/negative)
    ├── injection.json      # required at org+ (pinned at regulated)
    └── snapshots/          # recorded outputs for regression compare
```

```bash
bbsctl eval                            # all suites
bbsctl eval --suite behavior           # one suite
bbsctl eval --output json > report.json  # CI
```

See [`docs/evaluation.md`](docs/evaluation.md) for the full spec, case schema, and CI recipes.

## Current status

| Stage | Status | Notes |
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

- [`docs/quickstart.md`](docs/quickstart.md) — five-minute walkthrough
- [`docs/strictness-levels.md`](docs/strictness-levels.md) — the strictness axis explained
- [`docs/spec-guidelines.md`](docs/spec-guidelines.md) — the spec, aligned with [agentskills.io](https://agentskills.io)
- [`docs/design-patterns.md`](docs/design-patterns.md) — skill design patterns (Strategy, Factory, Adapter, Decorator)
- [`docs/best-practices.md`](docs/best-practices.md) — authoring guidance
- [`docs/evaluation.md`](docs/evaluation.md) — the eval corpus convention and `bbsctl eval` *(Phase 3)*
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — error → fix table
- [`docs/friction-audit.md`](docs/friction-audit.md) — per-phase DX audit protocol

## Architecture

The framework is built on three reusable design patterns (per [`docs/design-patterns.md`](docs/design-patterns.md)):

- **Strategy + Factory** — `CompileStep`, `Validator`, `Evaluator`, `AgentRuntime`, `PublishTarget`. Each is an interface; concrete implementations register through a factory. Adding a new validator or runtime is one class plus one registration line.
- **Adapter** — for cross-framework runtimes (Claude Agent SDK, MCP, LangGraph, CrewAI, LangFlow). Each adapter normalizes a foreign runtime into the `AgentRuntime` interface so `bbsctl run` and `bbsctl eval` don't care which one is in use.
- **Decorator** — for cross-cutting concerns (telemetry, cost budgeting, audit logging) layered on top of runtimes and evaluators without modifying them.

## Project layout

```
bulbasaur/
├── bbsctl/                       the CLI package (Python ≥3.11, module: skillctl)
│   ├── src/skillctl/
│   │   ├── agentskills/          spec parser, rules, agentskills-spec.yaml
│   │   ├── commands/             CLI subcommands
│   │   ├── compile/              compile pipeline (Strategy pattern)
│   │   ├── eval/                 evaluator framework
│   │   ├── marketplace/          Git-backed marketplace + skills.lock
│   │   ├── runtime/              AgentRuntime adapters
│   │   ├── templates/            SKILL.md templates per strictness level
│   │   └── validate/             validator chain
│   ├── tests/
│   └── pyproject.toml
├── quickstart/                   the five-minute experience
├── docs/                         guides, recipes, audits
├── reference-plugins/            full-featured skill demos
├── tests/                        cross-cutting contract tests
├── Makefile                      build, install, try, test, lint, clean
└── .governance/                  capability + acceptance schemas
```

## Contributing

Two things make a PR easier to merge:

1. **A friction-audit note.** If your change touches the CLI surface or any error message, walk the affected flow as a fresh developer and note where you hesitated. The friction-audit protocol ([`docs/friction-audit.md`](docs/friction-audit.md)) is the template.
2. **No vapor options.** If you add an argparse `choices=` value, the implementation behind it must work end-to-end. The vapor-options lint test walks the support registry and will fail otherwise.

## License

Apache 2.0.
