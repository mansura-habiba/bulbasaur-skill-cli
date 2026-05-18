# Bulbasaur quickstart

The five-minute promise — from zero to running skill — measured wall-clock and tested in CI on every PR.

## Prerequisites

- `uv` (the canonical Python toolchain — [install instructions](https://docs.astral.sh/uv/getting-started/installation/))
- Python `>=3.11, <3.14` (uv installs this for you if needed)

`pip` works as a fallback for environments where uv is not yet available, but uv is what the framework standardizes on. See [ADR 0002](../docs/adr/0002-uv-toolchain.md).

## The flow

```bash
# 1. Trial without installing — uvx runs bbsctl in an ephemeral env
uvx bbsctl new hello-skill
cd hello-skill
uvx bbsctl compile
uvx bbsctl run
```

Or, to install into a project:

```bash
uv add bbsctl
bbsctl new hello-skill
cd hello-skill
bbsctl compile
bbsctl run
```

Expected output from `bbsctl run`:

```
[mock-agent] activated: hello-skill
[mock-agent] reply: Hello! I'm the hello-skill — your first Bulbasaur skill.
```

## What just happened

- `bbsctl new` scaffolded a `SKILL.md` from the `local`-strictness template. Two required fields (`name`, `description`) plus a one-line body. That is all the public [agentskills.io](https://agentskills.io) spec requires.
- `bbsctl compile` validated the frontmatter against the public spec (name rules, description length, etc.) and emitted a small `dist/compile-report.json`. At `local` strictness no enterprise validation runs.
- `bbsctl run` invoked a mock agent that loaded the skill and applied the body's instruction to the sample input.

No marketplace was set up. No signature was generated. No ownership document was required. No policy configuration was touched.

## Where to go next

| If you want to... | Read |
|---|---|
| Understand the strictness ladder | [`../docs/strictness-levels.md`](../docs/strictness-levels.md) |
| Share a skill with your team | [`../docs/recipes/share-with-team.md`](../docs/recipes/share-with-team.md) |
| Ship a skill to production | [`../docs/recipes/ship-to-org.md`](../docs/recipes/ship-to-org.md) |
| See more skill patterns | [`../docs/design-patterns.md`](../docs/design-patterns.md) |
| Diagnose an error | [`../docs/troubleshooting.md`](../docs/troubleshooting.md) |

## The CI smoke test

The script [`ci.sh`](ci.sh) runs the exact flow above in CI on every pull request. If it takes more than five minutes wall clock, the PR fails. This is how we keep the promise honest.
