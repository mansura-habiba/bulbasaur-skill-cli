# `team` strictness templates

> **Status:** Phase 2 deliverable. This directory is intentionally empty in Phase 1.

When Phase 2 ships, this directory will contain:

- `SKILL.md.template` — extends the `local` template with the additional fields `team` strictness requires.
- `skill.yaml.template` — the enterprise overlay sibling, populated with the team-tier minimum fields (ownership stub, declared strictness).
- `ownership.yaml.template` — a recommended ownership stub (warning if missing at team strictness).

`bbsctl new --strictness team` will scaffold from these templates once they land.

See [`docs/strictness-levels.md`](../../docs/strictness-levels.md) for what `team` strictness requires.
