# Bulbasaur quickstart

The five-minute promise — from zero to running skill — measured wall-clock and tested in CI on every PR.

## Prerequisites

- Python `>=3.11, <3.14`
- `uv` recommended (or `pip` / `poetry`)

## The flow

```bash
# 1. Install (≤30 seconds)
uv add skillctl                # or: pip install skillctl

# 2. Scaffold (≤5 seconds)
skillctl new hello-skill

# 3. Compile and run (≤30 seconds combined)
cd hello-skill
skillctl compile
skillctl run
```

Expected output from `skillctl run`:

```
[mock-agent] activated: hello-skill
[mock-agent] reply: Hello! I'm the hello-skill — your first Bulbasaur skill.
```

## What just happened

- `skillctl new` scaffolded a `SKILL.md` from the `local`-strictness template. Two required fields (`name`, `description`) plus a one-line body. That is all that the public [agentskills.io](https://agentskills.io) spec requires.
- `skillctl compile` validated the frontmatter against the public spec (name rules, description length, etc.) and emitted a small `dist/compile-report.json`. At `local` strictness no enterprise validation runs.
- `skillctl run` invoked a mock agent that loaded the skill and applied the body's instruction to the sample input.

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
