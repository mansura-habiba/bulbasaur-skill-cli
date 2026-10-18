# Idempotency audit — bbsctl mutate commands

**Date:** 2026-10-18 (updated)  
**Principle:** make-operations-idempotent (reconcile from state; crash-safe writes)

## Tests applied

1. What happens if this runs twice in a row?
2. What happens if the previous run crashed at every possible point?
3. Does re-execution converge to the same end state?

## Fixed

| Surface | Weakness | Fix |
|---|---|---|
| JSON writes (catalog, ARD, marketplace.json, approval) | In-place `write_text` → crash = corrupt JSON | `skillctl.durable.atomic_write_*` |
| `bbsctl publish --marketplace` / local publish | `rmtree` then copy | Stage + `replace_directory` |
| `assemble_evidence` | `rmtree` live bundle | Stage + atomic replace; keep matching approval |
| Catalog sidecar / legacy index timestamps | Wall-clock every run | Content-stable / bump only on change |
| `bbsctl approve` | Same digest rewrote lock | No-op when by/note/digest match |
| Concurrent catalog / team marketplace upserts | RMW without lock | `durable.file_lock` around upsert + `save_manifest` merge |
| `marketplace export` mid-catalog crash | No resume cursor | `.bbsctl-export-checkpoint.json` + skip/resume + `--fresh` |
| External engines (SkillSpector / Mellea) | Opaque subprocess; unclear resume | Exit-2 Fix line with `bbsctl pipeline --from <stage>`; no cache on failure |

## Remaining / out of scope

| Surface | Notes |
|---|---|
| NFS advisory locks | Documented as same-host / local FS only |
| Auto-retry loops inside vendor CLIs | Explicit non-goal; resume via `--from` |
| Concurrent writers on different hosts | Needs distributed lock / single writer |

## Command posture

| Command | Behavior |
|---|---|
| `marketplace init` | Idempotent |
| `publish` / `--inplace` / `--marketplace` | Upsert by name; flock on shared JSON |
| `marketplace export` | Checkpoint + resume; `--fresh` clears |
| `discover` | Upsert by ARD identifier |
| `pipeline` | Fail-fast; cache only successes; `--from` resumes |
| `approve` | Cover digest; re-run same inputs = no-op |
| `verify` | Read-only |

## Code

- Helper: `bbsctl/src/skillctl/durable.py` (`atomic_write_*`, `file_lock`, `replace_directory`)
- Tests: `tests/test_durable_idempotency.py`, `tests/test_marketplace_export.py`, `tests/test_lifecycle_pipeline.py`
