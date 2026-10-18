# Recipe: run the lifecycle pipeline

Walk compile → scan → eval → certify → approve → publish with **`bbsctl pipeline`**, or run each stage alone. There is no second CLI.

Background: [`../lifecycle.md`](../lifecycle.md). Command ↔ engine map (including SkillSpector for scan): [`how-to-commands.md`](how-to-commands.md). After the pipeline is green, package with [`how-to-publish.md`](how-to-publish.md).

## Prerequisites

- Skill directory with `SKILL.md`.
- `bbsctl` installed (`uv sync` / `uv run bbsctl` from this repo).

Optional engines (skip stages you do not need):

```bash
bbsctl doctor          # which engines are on PATH / pinned
# Engines group (SkillSpector, Mellea, …) when you need scan/certify:
uv sync --group engines
```

---

## Fast path (pre-commit)

Compile + fast validate only. No network, no LLM. Target under ~5 s.

```bash
cd my-skill
bbsctl pipeline --fast --to compile
# Same idea as: bbsctl compile && bbsctl validate --fast
```

Local dogfood from this repo: `make try-pipeline`.

---

## Full walk (fail fast)

```bash
cd my-skill
bbsctl pipeline --strictness team
```

| Flag | Effect |
|---|---|
| `--strictness local\|team\|org\|…` | Which stage plan to use |
| `--to <stage>` | Stop after that stage |
| `--from <stage>` | Resume from that stage |
| `--fast` | Cheap gates only |

Exit codes:

| Code | Meaning |
|---|---|
| `0` | All requested stages passed |
| `1` | A stage failed (findings / validators) |
| `2` | Engine or framework error (missing tool, bad config) |
| `3` | Waiting on human approve |

At org+ / regulated, a green run may stop with exit `3`:

```bash
bbsctl approve --by alice
bbsctl verify
bbsctl publish --marketplace ../my-team-marketplace
```

Evidence lands under `.bbsctl/evidence/<skill>-<hash>/`.

---

## Stage-by-stage (same engines, no orchestrator)

Use this when debugging a single gate:

```bash
bbsctl compile
bbsctl scan             # needs SkillSpector when configured
bbsctl eval
bbsctl certify          # needs mellea-skills when configured
bbsctl approve --by alice
bbsctl verify
bbsctl publish
```

Config for engine mapping lives in `[tool.bbsctl]` (see `bbsctl/pyproject.toml`).

---

## CI (GitHub Actions)

Same shape as next_move’s Bulbasaur workflow — checkout, install `bbsctl`, run pipeline, upload evidence.

```yaml
- uses: mansura-habiba/bulbasaur-skill-cli/.github/actions/bbsctl-pipeline@main
  with:
    path: path/to/skill
    strictness: team
    stages: compile
    install-from: clone
```

Or copy `.github/workflows/bbsctl-pipeline.yml` and point `path` at your skills tree.

---

## Engine missing or crashed (exit 2)

SkillSpector / Mellea are external CLIs. `bbsctl` does not retry inside those adapters — fix the engine, then resume.

```bash
bbsctl doctor                          # which engines are on PATH
# Install / repair the missing engine (see the Fix: line), then:
bbsctl pipeline --from scan            # or --from certify, etc.
```

Prior stages are reused from the stage cache when the skill hash is unchanged (`--no-cache` forces a full re-run). Failed stages are never written to the cache.

---

## Checklist

- [ ] `bbsctl doctor` shows the engines you expect (or you only use `--to compile`)
- [ ] `bbsctl pipeline --fast --to compile` is green locally
- [ ] Full `bbsctl pipeline` matches the strictness you intend to ship at
- [ ] If exit `3`: approve + verify before publish
- [ ] Evidence bundle exists under `.bbsctl/evidence/` when you care about audit

## See also

- [`how-to-publish.md`](how-to-publish.md) — package after the pipeline
- [`../lifecycle.md`](../lifecycle.md) — stage table and CI notes
- [README — Orchestrator](../../README.md#orchestrator-all-stages)
