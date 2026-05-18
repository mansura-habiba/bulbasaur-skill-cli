# Quickstart

Five minutes from zero to a skill running locally, and another minute to load it into Claude Code. No marketplace setup. No signing. No API key.

## Prerequisites

- `uv` ([install](https://docs.astral.sh/uv/getting-started/installation/)) — the framework's canonical Python toolchain (ADR 0002).
- Python `>=3.11, <3.14` (uv installs it for you if needed).
- Claude Code (only for the "load into Claude Code" step at the end).

## Step 1 — Scaffold

```bash
uvx bbsctl new hello-skill
```

Or, if you'd like to install `bbsctl` into a project rather than run it on the fly:

```bash
uv add bbsctl
bbsctl new hello-skill
```

This creates `hello-skill/SKILL.md` with two required frontmatter fields (`name`, `description`) and a default body. That is the entire skill at `local` strictness — there is no `skill.yaml`, no `ownership.yaml`, no policy bundle. The agentskills.io spec requires only the two fields.

## Step 2 — Compile

```bash
cd hello-skill
bbsctl compile
```

Expected output:

```
bbsctl compile  ·  /path/to/hello-skill  ·  strictness=local
  ✓ parse-frontmatter
  ✓ validate-agentskills-spec
  ✓ emit-report

compile OK  ·  0 error(s), 0 warning(s)  ·  1 ms
```

What the compile does at `local` strictness:

1. Parses `SKILL.md`, validates the frontmatter against [agentskills.io](https://agentskills.io/specification) rules — name pattern, description length, etc.
2. Re-affirms spec validity (a separate step so future Phase 2 work can cross-check against the upstream `skills-ref` reference validator).
3. Writes `dist/compile-report.json` with the full compile artifact.

No enterprise validation runs at `local`. That lands when you climb the strictness ladder. See [strictness-levels.md](strictness-levels.md).

## Step 3 — Run

```bash
bbsctl run
```

Default output:

```
[mock-agent] received prompt: 'hello'
[mock-agent] activated: hello-skill
[mock-agent] reply: (the first instruction line from your skill body)
```

The `--runtime mock` agent is deterministic — no LLM, no API call. It exists so the framework's plumbing is testable end-to-end without external dependencies. To send a different prompt:

```bash
bbsctl run --prompt "hi there"
```

Real runtime adapters (Claude Agent SDK, MCP, LangGraph) land in Phase 4.

## Step 4 — Publish to a local Claude Code marketplace

```bash
cd ..
bbsctl publish hello-skill
```

This builds a marketplace directory next to your skill:

```
bulbasaur-marketplace/
├── .claude-plugin/
│   └── marketplace.json
└── plugins/
    └── hello-skill-plugin/
        ├── .claude-plugin/
        │   └── plugin.json
        └── skills/
            └── hello-skill/
                └── SKILL.md
```

This is exactly the shape stock Claude Code expects. `bbsctl publish` validates the output against the public spec — `claude plugin validate ./bulbasaur-marketplace` will return `✔ Validation passed`.

## Step 5 — Load into Claude Code

The `publish` command prints the exact next steps. From your Claude Code session:

```
/plugin marketplace add ./bulbasaur-marketplace
/plugin install hello-skill-plugin@bulbasaur-local
/hello-skill-plugin:hello-skill
```

That is it. The skill now runs inside Claude Code with no patches, no API key, no signing, no marketplace server.

## What you didn't have to do

- Sign anything.
- Configure a remote marketplace.
- Fill out `ownership.yaml` or `compatibility-matrix.yaml`.
- Set up OpenTelemetry, Rego policies, or PagerDuty.
- Install anything besides `bbsctl` (and the optional Claude Code for Step 5).

All of that exists. None of it is required at `local` strictness. The marketplace is the gate that asks for each — see [strictness-levels.md](strictness-levels.md) for the climb.

## What's next

| If you want to... | Read |
|---|---|
| Understand the strictness ladder | [strictness-levels.md](strictness-levels.md) |
| Share a skill with your team | [recipes/share-with-team.md](recipes/share-with-team.md) *(Phase 2)* |
| Ship a skill to production | [recipes/ship-to-org.md](recipes/ship-to-org.md) *(Phase 3)* |
| Diagnose an error | [troubleshooting.md](troubleshooting.md) |
| Learn the skill design patterns | [design-patterns.md](design-patterns.md) *(Phase 2)* |

## The five-minute promise

The flow above is measured wall-clock by the `quickstart-smoke.yml` GitHub Actions workflow on every pull request. If the end-to-end time exceeds 300 seconds, the PR fails. The script is at [`quickstart/ci.sh`](../quickstart/ci.sh). As of the latest Phase 1 release, the typical wall-clock time end-to-end is well under one second — we have considerable margin.
