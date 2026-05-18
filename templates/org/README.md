# `org` strictness templates

> **Status:** Phase 3 deliverable. This directory is intentionally empty in Phase 1.

When Phase 3 ships, this directory will contain:

- `SKILL.md.template` — extends the `team` template.
- `skill.yaml.template` — the enterprise overlay with all org-tier required fields (model_compatibility, cost_budget, input/output contract paths, hooks declared).
- `ownership.yaml.template` — required at org strictness; full ownership object with SLOs and error-budget policy.
- `compatibility-matrix.yaml.template` — required at org strictness; declared validated model+runtime combinations.

`bbsctl new --strictness org` will scaffold from these templates once they land.

See [`docs/strictness-levels.md`](../../docs/strictness-levels.md) for what `org` strictness requires.
