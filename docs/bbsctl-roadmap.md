# bbsctl — planned features roadmap

Prioritized plan for planned-but-unshipped features in `bbsctl`. Sources: phase markers in `skillctl/`, [`docs/strictness-levels.md`](strictness-levels.md), and BBS-200 lifecycle work ([`docs/lifecycle.md`](lifecycle.md)).

**Last updated:** 2026-10-18

Status legend: **✓** shipped · **◐** partial / stub · **✗** not started.

**Contributing.** Newcomers: read [`CONTRIBUTING.md`](../CONTRIBUTING.md), then pick a [good first issue](https://github.com/mansura-habiba/bulbasaur-skill-cli/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) or propose one from a small **◐** / **✗** row below. Large P1–P3 items need a full [Task Card](https://github.com/mansura-habiba/bulbasaur-skill-cli/issues/new/choose) before implementation.

---

## 0. Shipped since the previous revision (do not re-plan)

These are done. Keep them out of the open P0–P3 queues.

### Lifecycle orchestrator (BBS-200) — inside `bbsctl` only

| Feature | Status | Notes |
|---|---|---|
| `bbsctl pipeline` (fail-fast stage walk) | ✓ | `--fast`, `--to`, `--from`, `--strictness` |
| Standalone stages: `scan`, `certify`, `approve`, `verify`, `doctor` | ✓ | Engines via PEP 735 `engines` group + adapters |
| Evidence bundle under `.bbsctl/evidence/` | ✓ | Placeholder Sigstore sig (real signing still pending) |
| GH Action `bbsctl-pipeline` + sample workflow | ✓ | next_move-shaped install |
| Recipes: [how-to-run-pipeline](recipes/how-to-run-pipeline.md), [how-to-publish](recipes/how-to-publish.md) | ✓ | Linked from quickstart |
| Naming | ✓ | Product is **`bbsctl` only** — no second `skillops` binary; package `skillctl.lifecycle`, config `[tool.bbsctl]` |

### Distribution verbs

| Feature | Status | Notes |
|---|---|---|
| `bbsctl publish` (claude-code-local default) | ✓ | |
| `bbsctl publish --marketplace` (team Git / plugins/ copy) | ✓ | |
| `bbsctl publish … --inplace` (catalog curation, no file copy) | ✓ | `.claude-plugin/marketplace.json` + sidecar |
| `bbsctl discover` (ARD emit-only) | ✓ | Optional `--ard` on publish |
| `bbsctl marketplace init / list / export` | ✓ | **Admin only** — not a third user verb for publish/ard |
| `marketplace add-tenant / policy / federate` | ✗ | Still backlog (P3) |

### P0 / eval substrate that already landed

| Feature | Status | Notes |
|---|---|---|
| Claude Agent SDK runtime adapter | ✓ | `run/claude_agent_sdk.py`; also `ollama` |
| `LLMJudge` (`--judge llm`) | ✓ | `eval/llm_judge.py` |
| Model pinning + `evals/eval.config.yaml` + eval cache | ✓ | `eval/reproducibility.py` |
| Snapshot **write** (`--snapshot`) | ✓ | Baseline files under `evals/snapshots/` |
| `permissions.yaml` schema + validate + policy checks | ✓ | `docs/permissions.md`; compile/runtime hook enforcement still limited |

### Still open from the original P0 set

| Feature | Status | Notes |
|---|---|---|
| `RegressionEvaluator` + real `--mode full` compare | ◐ | Mode exists in CLI help; runner does **not** yet compare against snapshots |
| `TriggerEvaluator` | ✗ | Not registered |
| Permissions **runtime** hook enforcement | ◐ | Policy/validate yes; Phase 4 hook bus still missing |

---

## 1. Inventory — remaining planned features

### Phase 2 leftovers — team compile depth

| Feature | Status | Source |
|---|---|---|
| Spec-lint compile step | ✗ | `compile/pipeline.py`, `compile/steps.py` |
| Dependency-audit compile step | ✗ | same |
| Reference-freshness compile step | ✗ | same |

### Phase 3 — org strictness

| Feature | Status | Source |
|---|---|---|
| Full validator suite — registry-context trigger | ✗ | `validate/__init__.py` |
| Full validator suite — prompt-injection corpus (validate path) | ◐ | Eval has `InjectionEvaluator`; validate `--full` still ≈ fast |
| Full validator suite — semantic fuzzer | ◐ | Eval has `fuzz` suite; validate path not wired |
| `skill.yaml` full schema validation | ◐ | Dict-only / partial today |
| `ownership.yaml` schema + validator | ✗ | Strictness ladder org row |
| `compatibility-matrix.yaml` schema + validator | ✗ | Strictness ladder org row |
| Sigstore signing in publish / evidence | ◐ | Placeholder `bundle.sig` only |
| Install-time signature verification | ✗ | `commands/install.py` |
| `bbsctl strictness org` | ✗ | CLI choices: `team` only |
| `claude-code-remote` publish target | ✗ | `publish/__init__.py` |
| `mcp-composer` publish target | ✗ | same |
| `oci` publish target | ✗ | same |
| `TriggerEvaluator` | ✗ | `eval/factory.py` |
| `RegressionEvaluator` + FULL = FAST + snapshot compare | ◐ | Snapshot write yes; compare no |
| Eval mode `FULL` meaningfully distinct from FAST | ◐ | Help text promises regression; runner ignores mode beyond smoke/fast |

### Phase 4 — runtime + observability

| Feature | Status | Source |
|---|---|---|
| Claude Agent SDK runtime adapter | ✓ | Shipped (see §0) |
| `LLMJudge` | ✓ | Shipped (see §0) |
| Claude Code runtime adapter | ✗ | `run/__init__.py` |
| Hook bus | ✗ | Strictness ladder hook-fail-mode |
| Cost budget enforcer | ✗ | Strictness ladder |
| OTel traces | ✗ | Strictness ladder |

### Phase 5 — regulated

| Feature | Status | Source |
|---|---|---|
| `bbsctl strictness regulated` | ✗ | `strictness_cmd.py` |
| Pinned eval-corpus hash in `skill.yaml` | ✗ | Ladder |
| Regulatory sign-off on publish artifact | ✗ | Ladder |
| 7-year audit retention metadata | ✗ | Ladder |
| Strict gates — `fail-closed` hook default | ✗ | Ladder |

### Phase 6 — additional runtimes

| Feature | Status | Source |
|---|---|---|
| MCP server runtime adapter | ✗ | `run/__init__.py` |
| LangGraph runtime adapter | ✗ | same |

### Cross-cutting

| Feature | Status | Source |
|---|---|---|
| `bbsctl author` + `skill-creator` reference skill | ✗ | Design / adoption |
| Judge calibration corpus + harness | ✗ | Whitepaper §3 |
| Audit JSONL emission (local at team, tamper-evident at org) | ✗ | Strictness ladder |
| Marketplace federation (`add-tenant` / `policy` / `federate`) | ✗ | Was bundled with `list`; `list` shipped admin-only |

**Open count (approx.):** ~25 features still ✗ or ◐. Lifecycle + dist verbs + most of original P0 eval runtime are **off** the open queue.

---

## 2. Prioritization criteria

Unchanged. Four axes, 1–3 each; total drives the tier.

1. **Adoption blocker (1–3).** Real user trip in the next 30 days?
2. **Demoability (1–3).** Visible upgrade in a 7-minute demo?
3. **Dependency footprint (1–3).** Unblocks other planned features?
4. **Effort (inverted, 1–3).** 3 = ≤1 sprint; 1 = ≥3 sprints.

Tier cuts: **P0** sum ≥ 10 · **P1** 8–9 · **P2** 6–7 · **P3** ≤ 5.

---

## 3. Prioritized open work

### P0 — ship next (finish the original eval story)

| # | Feature | Block | Demo | Dep | Eff | Sum | Status |
|---|---|---|---|---|---|---|---|
| 3 | **`RegressionEvaluator` + snapshot compare + real `FULL` mode** | 3 | 2 | 2 | 3 | 10 | ◐ |
| — | *(Claude Agent SDK, LLMJudge, model pin, permissions schema)* | — | — | — | — | — | ✓ done — see §0 |

Rationale: the last P0 gap is that `--mode full` does not yet fail on regressions. Snapshot write + cache already exist; wire the compare path and stop treating FULL as FAST.

### P1 — sprints after P0 close (org unlock + compile depth)

| # | Feature | Block | Demo | Dep | Eff | Sum |
|---|---|---|---|---|---|---|
| 5 | **`bbsctl author` + `skill-creator` reference skill** | 3 | 3 | 2 | 1 | 9 |
| 6 | **Spec-lint compile step** | 2 | 1 | 2 | 3 | 8 |
| 7 | **Dependency-audit compile step** | 2 | 2 | 1 | 3 | 8 |
| 8 | **Reference-freshness compile step** | 2 | 2 | 1 | 3 | 8 |
| 9 | **`TriggerEvaluator` (positive/negative activation)** | 2 | 2 | 1 | 3 | 8 |
| 10 | **Sigstore signing (replace placeholder)** | 3 | 2 | 3 | 1 | 9 |
| 11 | **Install-time signature verification** | 3 | 2 | 2 | 2 | 9 |
| 12 | **`bbsctl strictness org`** | 2 | 2 | 3 | 2 | 9 |
| 13 | **`ownership.yaml` schema + validator** | 2 | 1 | 3 | 2 | 8 |

### P2 — org coverage + Phase 4 instrumentation

| # | Feature | Sum |
|---|---|---|
| 14 | `compatibility-matrix.yaml` schema + validator | 7 |
| 15 | Registry-context trigger validator (`validate --full`) | 7 |
| 16 | Injection corpus on validate path (align with eval injection) | 7 |
| 17 | Semantic fuzzer on validate path | 6 |
| 18 | `skill.yaml` full schema validation | 7 |
| 19 | OCI registry publish target | 7 |
| 20 | `claude-code-remote` publish target | 6 |
| 21 | `mcp-composer` publish target | 6 |
| 22 | Audit JSONL emission (local at team) | 7 |
| 23 | Hook bus | 7 |
| 24 | Cost budget enforcer | 7 |
| 25 | OTel traces | 6 |
| 26 | Claude Code runtime adapter | 6 |
| 27 | Judge calibration corpus + harness | 6 |
| — | Permissions **runtime** enforcement via hook bus | 7 |

### P3 — when a user asks

| # | Feature | Sum |
|---|---|---|
| 28 | `bbsctl strictness regulated` | 5 |
| 29 | Pinned eval-corpus hash in `skill.yaml` | 5 |
| 30 | Regulatory sign-off attachment | 5 |
| 31 | 7-year audit retention metadata | 5 |
| 32 | Strict gates / `fail-closed` hook default | 5 |
| 33 | `marketplace add-tenant / policy / federate` | 4 |
| 34 | MCP Composer federation client | 4 |
| 35 | MCP server runtime adapter | 5 |
| 36 | LangGraph runtime adapter | 5 |

---

## 4. Sprint plan (revised)

Two engineers, two-week sprints. **S1–S2 of the old plan (Claude Agent SDK + LLMJudge + model pin) are treated as done.** Renumber from the remaining P0 gap.

| Sprint | Focus | Demo gain |
|---|---|---|
| **S1′** | #3 `RegressionEvaluator` + `--mode full` compare + docs/recipe touch-up | `bbsctl eval --mode full` fails on regressions vs snapshot |
| **S2′** | #5 `bbsctl author` + #6 Spec-lint | AI-assisted authoring; deeper compile |
| **S3′** | #10 Sigstore (replace placeholder) + #7 Dependency-audit | Real signed evidence / publish artifacts |
| **S4′** | #11 Install-time verify + #8 Reference-freshness + #9 TriggerEvaluator | Closed publish/install signature loop |
| **S5′** | #12 `strictness org` + #13 `ownership.yaml` + #14 compatibility-matrix | First end-to-end org-strictness skill |
| **S6′–S8′** | Validate `--full` suite (#15–17), skill.yaml schema (#18), OCI / remote / mcp-composer targets (#19–21) | Org gate complete; multi-target publish |
| **S9′–S11′** | Audit JSONL + hook bus + cost + OTel + Claude Code runtime (#22–26) | Instrumented runtime |
| **S12′** | Judge calibration (#27) + friction-audit / docs | Phase close |

~12 remaining sprints ≈ 5–6 months to org end-to-end from **today**. Regulated + MCP/LangGraph stay P3.

Local dogfood already available: `make try-pipeline`, recipes under `docs/recipes/`.

---

## 5. Dependency graph

- **#3 RegressionEvaluator** unblocks treating eval as a CI gate (not only smoke).
- **#10 Sigstore** blocks #11 install verify and #12 `strictness org` (signing is an org requirement).
- **#12 `strictness org`** blocks gating validate `--full` by default at org.
- **#23 Hook bus** blocks runtime permissions enforcement, #22 audit JSONL, #24 cost, #25 OTel.
- **#13 `ownership.yaml`** feeds #12 interactive prompts.

Lifecycle (`bbsctl pipeline`) **consumes** these features; it does not block them. There is no separate `skillops` product — orchestration is already inside `bbsctl`.

---

## 6. P0 remaining detail — acceptance criteria

### #3 — `RegressionEvaluator` + snapshot compare + `FULL` mode

**Acceptance criteria:**

- Module `skillctl/eval/regression.py` with `RegressionEvaluator(Evaluator)`.
- Compare current report to `evals/snapshots/<suite>.<model>.json` (paths already produced by `write_snapshot`).
- Comparison key: `(case_id, assertion_index) → passed`. Regression = was pass, now fail.
- `bbsctl eval --mode full` runs behavior (or configured suites) then regression compare; **not** an alias of fast.
- Optional `--baseline <path>` override.
- Tests: round-trip snapshot, detect flipped assertion, stable paths.

**Effort:** ≤ 1 sprint (write path already exists).

---

## 7. What gets demoed after the next sprints

After **S1′**: `bbsctl eval --mode full --baseline …` reports regressions. Eval is a real CI gate.

After **S2′**: `bbsctl author "…"` scaffolds with help; compile grows a real spec-lint step.

After **S3′–S4′**: real Sigstore (or documented interim) on evidence/publish; install verifies.

After **S5′**: first skill climbs to `org` via `bbsctl strictness org` end-to-end through `bbsctl pipeline`.

---

## 8. What this leaves on the table

P3 (~9 features) stays “when a user asks”: regulated tier, marketplace federation, MCP/LangGraph runtimes.

Cross-cutting integrations called out in the whitepaper (Cursor extension, Bolt template) remain out of this roadmap. The GitHub Action and pipeline recipes **have shipped** inside this repo — remove them from any “skillops-layer / different repo” backlog language.

User-facing distribution stays two verbs: **`bbsctl publish`** + **`bbsctl discover`**. Do not reintroduce `marketplace publish` / `marketplace ard`.

---

## 9. Risks and unknowns

- **Judge cost in CI.** Unchanged — prefer `--mode smoke` on PRs; `--mode full` nightly once regression lands.
- **Sigstore UX for local dev.** Still needs a decision before S3′ (OIDC vs cosign local path).
- **Placeholder signatures in evidence today.** `bbsctl verify` must not be mistaken for cryptographic trust until #10 lands.
- **catalog in-place publish depends on curation-repo layout.** Keep `--inplace` / `--repo-root` documented; do not conflate with team `--marketplace`.
- **gh auth.** Public + IBM tokens currently invalid in this environment — issue/project board updates for BBS-200 are blocked until `gh auth refresh`.

---

## 10. Closing

**Done (this cycle):** lifecycle inside `bbsctl` (`pipeline` + stage commands + evidence + GH Action), distribution verbs (`publish` / `discover` / marketplace admin), Claude Agent SDK + Ollama runtimes, `LLMJudge`, eval reproducibility/cache/snapshot write, permissions schema + validators, publish recipes.

**Next:** close P0 with real regression/`FULL` mode, then P1 org unlock (signing, `strictness org`, compile steps, author).

**Still far:** regulated tier, federation, MCP/LangGraph, full Phase 4 hook/OTel/cost stack.

---

### References

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — good first issues + PR workflow
- [`docs/lifecycle.md`](lifecycle.md) — stage map + CI
- [`docs/recipes/how-to-run-pipeline.md`](recipes/how-to-run-pipeline.md)
- [`docs/recipes/how-to-publish.md`](recipes/how-to-publish.md)
- [`docs/strictness-levels.md`](strictness-levels.md)
- [`docs/evaluation.md`](evaluation.md)
- [`docs/permissions.md`](permissions.md)
- GitHub issues (task cards) — session milestones; local `.governance/progress.md` is gitignored
