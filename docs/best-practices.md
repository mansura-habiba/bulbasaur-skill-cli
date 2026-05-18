# Skill best practices

> **Status:** Placeholder — full guidance is a Phase 2 deliverable.
> See [`mental-model.md` §7](../mental-model.md) for the working best-practices list.

This document will be the durable internal cookbook — authoring imperatives, common anti-patterns, recurring failure modes, "gotchas" that should appear in every relevant skill. It is updated whenever a postmortem produces a generalizable lesson.

## What this document will cover when written

The Phase 2 deliverable expands `mental-model.md` §7 into:

- **Authoring imperatives.** Write descriptions like routing code, not marketing text. Use third-person imperative for instructions. Cap SKILL.md body at 500 lines. Embed a Gotchas section.
- **Anti-patterns to reject.** Overlapping descriptions, multi-capability skills, ungoverned references, missing risk tier on high-risk skills, wildcards in `allowed-tools`, hardcoded paths instead of `${CLAUDE_PLUGIN_ROOT}`, missing ownership, missing trigger tests.
- **Failure modes (curated).** Each named failure with detection mechanism, containment action, and recovery path. Used as the basis of the regression test corpus.

## When this doc lands

Phase 2 Sprint 2 per the build plan. Maintained as a living document — every postmortem updates the relevant section.
