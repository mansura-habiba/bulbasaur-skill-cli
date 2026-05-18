# `regulated` strictness templates

> **Status:** Phase 5 deliverable. This directory is intentionally empty in Phase 1.

When Phase 5 ships, this directory will contain:

- `SKILL.md.template` — extends the `org` template.
- `skill.yaml.template` — the enterprise overlay with all regulated-tier required fields. Strict hook fail-modes (no `fail-open`), regulatory sign-off references, pinned prompt-injection corpus version, audit retention SLA of 7+ years.
- `regulatory.yaml.template` — sign-off references, applicable regulations, compliance evidence pointers.

`bbsctl new --strictness regulated` will scaffold from these templates once they land.

See [`docs/strictness-levels.md`](../../docs/strictness-levels.md) for what `regulated` strictness requires.
