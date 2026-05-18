# Strictness levels

Strictness is the primary axis of developer flexibility in Bulbasaur. It declares how much friction the author has agreed to. The framework asks for more as the author climbs the ladder — never ahead of it.

Strictness is **orthogonal to trust tier**. Trust tiers (`Experimental` → `Regulated`) are about *organizational governance*: who has approved this skill to run where. Strictness is about *how much the framework requires of the author*. A skill at `Experimental` tier can be `local` strictness; a skill at `Regulated` tier is always `regulated` strictness.

## The four levels

| Level | What the framework requires |
|---|---|
| `local` (default) | Public-spec valid `SKILL.md` only. No signing, no ownership, no Rego, no OTel, no marketplace. |
| `team` | Above + author identity attached to publish, ownership recommended (warning if missing), fast validators run, light marketplace (Git or filesystem directory). |
| `org` | Above + ownership required, full validator suite (registry-context trigger, prompt-injection, output contract), signing enforced (Sigstore), append-only audit log, OTel traces required, cost budget required, model compatibility matrix required. |
| `regulated` | Above + regulatory sign-off, prompt-injection corpus pinned to a versioned snapshot, model compat re-validated on every model upgrade, audit retention ≥ 7 years, all framework gates strict (no fail-open hooks). |

## The default-vs-required matrix

What every framework feature requires at each strictness level. Read top-to-bottom for one feature; read left-to-right for one strictness level.

| Feature | `local` | `team` | `org` | `regulated` |
|---|---|---|---|---|
| Public-spec validation (agentskills.io) | Required | Required | Required | Required |
| Fast Bulbasaur validators | Skipped unless `--strict` | Required | Required | Required |
| Full validator suite | Available | Recommended | Required | Required |
| Registry-Context Trigger Validator | Skipped (no registry) | Skipped (single-team scope) | Required | Required |
| Prompt-Injection Validator | Skipped | Optional | Required | Required (pinned corpus) |
| Semantic Fuzzer | Skipped | Optional | Required | Required |
| `ownership.yaml` | Optional | Recommended (warning) | Required | Required |
| Sigstore signing | Skipped | Optional | Required | Required |
| Lockfile | Generated | Generated | Required-in-repo | Required-in-repo |
| `compatibility-matrix.yaml` | Optional | Optional (declared if shared) | Required | Required (re-validated per upgrade) |
| Cost budget | Optional (advisory) | Optional (advisory) | Required (enforced) | Required (strict) |
| OTel traces | Optional | Required (basic) | Required (full attributes) | Required (full + retention SLA) |
| Audit log | Skipped | JSONL-local | Tamper-evident, central | Tamper-evident, 7-year retention |
| Install-time policy | Skipped | Optional | Required | Required |
| Approver workflow at promote | Skipped (self-promote) | Self-approve | Named approver | Named approver + regulatory sign-off |
| Tenant isolation | N/A | Optional | Required | Required |
| Hook fail-mode default | `fail-open` | `fail-open` | `fail-degraded` | `fail-closed` (required) |

The marketplace is the gate. A `team` marketplace refuses to host `local` skills. An `org` marketplace refuses to host below `org`. A `regulated` marketplace refuses to host below `regulated`. Inside the gate, every authoring step is the developer's choice.

## Climbing the ladder

A developer who built a `local` skill and wants to share it does the following:

```bash
# Day 1 — local (the quickstart you already ran)
bbsctl new my-skill
bbsctl compile
bbsctl run

# Week 2 — promote to team (Phase 2)
bbsctl strictness team        # interactive: prompts for ownership (skip if not ready)
                                # adds skill.yaml with strictness: team
                                # generates validation report
bbsctl publish my-skill --target claude-code-remote --marketplace my-team-skills

# Month 3 — promote to org (Phase 3)
bbsctl strictness org         # interactive: walks through org-tier requirements
                                # generates ownership.yaml, compatibility-matrix.yaml,
                                # cost_budget defaults, prompts to sign
bbsctl publish my-skill --target mcp-composer --marketplace my-company-skills
```

`bbsctl strictness <level>` is the single command that escalates. It does not skip steps; it adds them. The developer can stop at any level. The framework never forces escalation.

## How strictness is declared

At `local` strictness there is no explicit declaration — it's the default and nothing requires recording it.

At `team` and above, the strictness is set in a sibling `skill.yaml`:

```yaml
# skill.yaml — lands in Phase 2
schema_version: bulbasaur/v1
strictness: team    # local | team | org | regulated
# ... other fields per the strictness level
```

The compiler reads `skill.yaml` if it exists; otherwise the strictness is `local`. The `--strictness` CLI flag overrides both for one-shot commands (e.g. validating an `org` skill with `--strictness team` for a quick check).

## Why this exists

The DX charter (framework-build-plan.md §0) is explicit: defaults are permissive; progressive enhancement, not progressive obligation; the framework composes with developer tools rather than replacing them.

The previous design (framework-build-plan.old.md) was production-code-first — every MVP1 acceptance criterion required signing, ownership, Rego, OTel, and on-call wiring before a single skill ran. That order is right for the north star but wrong for adoption. The strictness axis lets the framework serve both:

- A solo developer trying things out ships at `local` strictness in five minutes.
- A regulated business unit ships at `regulated` strictness with every gate strict.

Both are legitimate uses of the same framework.

## The trade-off (explicit)

Making the framework default-permissive means a careless developer can ship a careless skill — but only to their own laptop (`local`) or a `local`-permissive marketplace. The marketplace is the gate, not the framework. A skill at `local` strictness cannot be installed into an `org`-tier marketplace.

That moves the enforcement point from "the framework refuses to compile" to "the marketplace refuses to host." We believe that's the right place for it — it preserves the five-minute promise without weakening governance where governance matters.

## See also

- [framework-build-plan.md §0 — DX charter](../framework-build-plan.md#0-developer-flexibility-charter)
- [framework-build-plan.md §1 — The strictness axis](../framework-build-plan.md#1-the-strictness-axis)
- [mental-model.md §8 — Skill Spec Guidelines](../mental-model.md)
- [agentskills.io specification](https://agentskills.io/specification)
