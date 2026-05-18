# Skill design patterns

> **Status:** Placeholder — full catalog is a Phase 2 deliverable.
> See [`mental-model.md` §6](../mental-model.md) for the working pattern list.

This document will be the canonical catalog of supported skill design patterns. Each pattern names when to use it, the structural constraints, expected failure modes, SDK support, and links to a cookbook example.

## What this document will cover when written

The catalog already lives in `mental-model.md` §6 — the twelve composition patterns (Instruction-Only, Skill+Reference, Skill+Script, Skill+MCP-Tool, Validator, Human-Gate, Planner-Executor, Skill DAG, Shadow, Circuit Breaker, A/B Routing Contract, Composition Gateway) plus the five Mellea-derived generation patterns (Generative Artifact, Deterministic Tool Dispatch, Analytical Pipeline, Constrained Reasoning, Adversarial Classification).

The Phase 2 deliverable rewrites that catalog into a dedicated document with:

- Per-pattern: when-to-use, structural constraints, expected failure modes, SDK template name, cookbook entry link.
- A discovery section explaining how to pick the right pattern for a task.
- A composition section explaining how patterns combine (e.g. Planner-Executor + Human-Gate + Circuit Breaker).
- The `bbsctl new --pattern <name>` flag that scaffolds from a pattern (Phase 2).

## When this doc lands

Phase 2 Sprint 2 per the build plan. The cookbook examples land alongside under `docs/cookbook/`.
