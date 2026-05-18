# Recipe: ship a skill to production-grade org strictness

> **Status:** Placeholder — full recipe lands in Phase 3.
> See [`strictness-levels.md`](../strictness-levels.md) for the strictness ladder this recipe walks.

This recipe will walk a developer through promoting a `team`-strictness skill to `org` strictness — the production-grade tier with signing, full validators, ownership, OTel, and cost budgets enforced.

## What this recipe will cover

When written, the recipe ships:

1. **Climb to `org` strictness.** `bbsctl strictness org` walks through:
   - Generating `ownership.yaml` (owner team, on-call, runbook, SLOs, error-budget policy).
   - Generating `compatibility-matrix.yaml` (model + runtime version ranges validated).
   - Declaring a cost budget (activation token budget, total token budget, per-activation ceiling).
   - Setting up Sigstore signing identity.
2. **Run the full validator suite.** Registry-context trigger validation, prompt-injection corpus, semantic fuzz, output contract.
3. **Publish to the org marketplace.** `bbsctl publish <skill> --target mcp-composer --marketplace <org-marketplace>` upserts into the MCP Composer runtime catalog with the org's tenant scoping (per the federation contract in [`mcp-composer-analysis.md`](../../mcp-composer-analysis.md) §10).
4. **Promotion workflow.** Named approver signs off; promotion event lands in the audit log.
5. **Runtime observability.** OTel traces appear in the org's dashboard with per-skill latency, cost, policy denials, output-validation pass rate.

## What works today

The `claude-code-local` target (Phase 1) is the demo path. Org-tier production deployment requires Phase 3 work.

## When this doc lands

Phase 3 Sprint 11 per the build plan — when `bbsctl strictness org`, MCP Composer federation, and the approval workflow all ship.
