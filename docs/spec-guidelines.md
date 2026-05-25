# Skill spec guidelines

> **Status:** Placeholder — full document is a Phase 2 deliverable.

This document will be the internal extension of the public [agentskills.io specification](https://agentskills.io/specification) — naming every required field, every reserved field, every naming and versioning rule, every constraint on descriptions and triggers, every output contract requirement.

Until it lands, the source-of-truth for Phase 1 is:

- **Public spec contract.** The fields and rules at [agentskills.io/specification](https://agentskills.io/specification). Bulbasaur enforces these in `skillctl/src/skillctl/agentskills/rules.py`.
- **Enterprise overlay.** Lives in a sibling `skill.yaml` at `team`+ strictness. The schema lands in Phase 2.
- **Strictness levels.** See [`strictness-levels.md`](strictness-levels.md) for what's required at each level.

## What this document will cover when written

The full guidelines will document:

- Identity and naming rules (kebab-case, length caps, namespacing).
- Routing-contract vs. execution-bundle split (Phase 2).
- Required-field schemas at each strictness level.
- Description discipline (no model instructions, no hidden characters, no superlatives).
- Reference manifest format (source provenance, freshness SLA).
- Script manifest format (language, entrypoint, idempotence, determinism).
- Output contract requirements per risk tier.
- Trigger-test minimum counts per strictness.
- Compatibility-matrix requirements.
- Ownership object requirements.
- The two-stage validation chain (skills-ref public-spec → Bulbasaur enterprise).

## When this doc lands

Phase 2 Sprint 1 per the build plan. Tracked at the build-plan section that lists docs deliverables.
