# bbsctl — planned features roadmap

A prioritized plan for the planned-but-unshipped features in `bbsctl`. Source: source-code phase markers (`Phase 2/3/4/5/6` comments across `skillctl/`), the strictness ladder in `docs/strictness-levels.md`, and the gap analysis in [`docs/skill-lifecycle-framework-whitepaper.md`](skill-lifecycle-framework-whitepaper.md). Roughly 30 distinct features identified, sorted into four tiers, sequenced across 12–15 sprints for a team of two engineers.

---

## 1. Inventory — every planned feature

Status legend: ◐ partial / stub in place but not functionally complete · ✗ not started.

### Phase 2 — team strictness (mostly shipped; three compile steps still missing)

| Feature | Status | Source |
|---|---|---|
| Spec-lint compile step | ✗ | `compile/pipeline.py:9`, `compile/steps.py:13` |
| Dependency-audit compile step | ✗ | `compile/pipeline.py:9`, `compile/steps.py:13` |
| Reference-freshness compile step | ✗ | `compile/pipeline.py:9`, `compile/steps.py:13` |

### Phase 3 — org strictness (not started)

| Feature | Status | Source |
|---|---|---|
| Full validator suite — registry-context trigger | ✗ | `validate/__init__.py:8`, `commands/validate.py:5` |
| Full validator suite — prompt-injection corpus | ✗ | `validate/__init__.py:8`, `validate/basic_trigger.py:8` |
| Full validator suite — semantic fuzzer | ✗ | `validate/basic_trigger.py:8` |
| `skill.yaml` full schema validation | ◐ | `skill_yaml.py:33` (today: dict-only check) |
| `ownership.yaml` schema + validator | ✗ | strictness ladder org row |
| `compatibility-matrix.yaml` schema + validator | ✗ | strictness ladder org row |
| Sigstore signing in publish pipeline | ✗ | strictness ladder org row, `commands/install.py:4` |
| Install-time signature verification | ✗ | `commands/install.py:4` |
| `bbsctl strictness org` command | ✗ | `strictness_cmd.py:48` (today: team only) |
| `claude-code-remote` publish target | ✗ | `commands/publish.py:7` |
| `mcp-composer` publish target | ✗ | `commands/publish.py:7` |
| `oci` publish target | ✗ | `commands/publish.py:7` |
| `marketplace list / add-tenant / policy / federate` subcommands | ✗ | `commands/marketplace_cmd.py:6` |
| MCP Composer federation client | ✗ | `marketplace/__init__.py:8` |
| `TriggerEvaluator` (positive/negative activation suites) | ✗ | `eval/factory.py:49` |
| `InjectionEvaluator` (injection corpus scoring) | ✗ | `eval/factory.py:49` |
| `RegressionEvaluator` + snapshot compare | ✗ | `eval/factory.py:49`, `eval_cmd.py:65` |
| Eval mode `FULL` = FAST + regression compare | ◐ | `eval_cmd.py:65` (today: alias for FAST) |

### Phase 4 — runtime + observability (not started)

| Feature | Status | Source |
|---|---|---|
| Claude Agent SDK runtime adapter | ✗ | `run/__init__.py:7`, `run/factory.py:3` |
| Claude Code runtime adapter | ✗ | `run/__init__.py:8` |
| `LLMJudge` (depends on Claude Agent SDK adapter) | ◐ | `eval/judge.py:14`, `eval/factory.py:79` |
| Hook bus | ✗ | strictness ladder hook-fail-mode rows |
| Cost budget enforcer | ✗ | strictness ladder cost-budget row |
| OTel traces | ✗ | strictness ladder OTel row |

### Phase 5 — regulated strictness (not started)

| Feature | Status | Source |
|---|---|---|
| `bbsctl strictness regulated` command | ✗ | `strictness_cmd.py:48` |
| Pinned eval-corpus hash recording in `skill.yaml` | ✗ | strictness ladder regulated row |
| Regulatory sign-off attachment to publish artifact | ✗ | strictness ladder approver row |
| 7-year audit retention metadata | ✗ | strictness ladder audit-log row |
| Strict gates — `fail-closed` hook fail-mode default | ✗ | strictness ladder hook row |

### Phase 6 — additional runtimes (not started)

| Feature | Status | Source |
|---|---|---|
| MCP server runtime adapter | ✗ | `run/__init__.py:9` |
| LangGraph runtime adapter | ✗ | `run/__init__.py:10` |

### Cross-cutting (not yet phased in source but in earlier design docs)

| Feature | Status | Source |
|---|---|---|
| `bbsctl author` command + `skill-creator` reference skill | ✗ | this conversation; not in repo |
| Model pinning for reproducible eval | ✗ | derived from `eval.config.yaml` design |
| Judge calibration corpus + harness | ✗ | whitepaper §3, eval gaps |
| Audit JSONL emission (local at team, tamper-evident at org) | ✗ | strictness ladder audit row |

**Total: 30 features. 19 fall under `org` (Phase 3) or below. 11 are Phase 4+.**

---

## 2. Prioritization criteria

Four axes. Each feature scored on a 1–3 scale per axis; total drives the tier.

1. **Adoption blocker (1–3).** Does a real user trip on the absence of this feature in the next 30 days? 3 = yes, immediately; 1 = no, edge case.
2. **Demoability (1–3).** Does shipping it visibly upgrade `bbsctl` in a 7-minute demo? 3 = "wait, that's new" moment; 1 = invisible plumbing.
3. **Dependency footprint (1–3).** Does it unblock other planned features? 3 = blocks ≥3; 1 = standalone.
4. **Effort (inverted, 1–3).** 3 = ≤1 sprint; 2 = 2 sprints; 1 = ≥3 sprints. Inverted so higher is better.

Tier cuts:
- **P0** — sum ≥ 10. Ship next.
- **P1** — sum 8–9. Ship after P0.
- **P2** — sum 6–7. Ship when P1 lands.
- **P3** — sum ≤ 5. Roadmap, not next.

---

## 3. Prioritized feature list

### P0 — ship in the next 2 sprints (sum ≥ 10)

| # | Feature | Block | Demo | Dep | Eff | Sum |
|---|---|---|---|---|---|---|
| 1 | **Claude Agent SDK runtime adapter** | 3 | 3 | 3 | 2 | 11 |
| 2 | **`LLMJudge` against Claude Agent SDK** | 3 | 3 | 2 | 3 | 11 |
| 3 | **`RegressionEvaluator` + snapshot compare + `FULL` mode** | 3 | 2 | 2 | 3 | 10 |
| 4 | **Model pinning for reproducible eval** | 3 | 2 | 2 | 3 | 10 |
| 5 | **`permissions.yaml` — schema + lint + runtime hook + eval integration** ([`docs/permissions.md`](permissions.md)) | 3 | 3 | 2 | 2 | 10 |

Rationale: today `bbsctl eval` runs against a mock runtime with a heuristic judge. That is the single biggest "is this real?" objection from any prospect. Wiring the Claude Agent SDK adapter unblocks both real activation and the `LLMJudge`; reproducible eval and regression compare turn the eval module from a smoke test into a CI-gating artifact. The `permissions.yaml` work (item #5) is the security counterpart — without command/URL/MCP-tool allow-deny rules enforced at compile, publish, and runtime, no DevOps-tier skill is shippable. See [`docs/permissions.md`](permissions.md) for the schema and enforcement design.

### P1 — ship in sprints 3–5 (sum 8–9)

| # | Feature | Block | Demo | Dep | Eff | Sum |
|---|---|---|---|---|---|---|
| 5 | **`bbsctl author` + `skill-creator` reference skill** | 3 | 3 | 2 | 1 | 9 |
| 6 | **Spec-lint compile step** | 2 | 1 | 2 | 3 | 8 |
| 7 | **Dependency-audit compile step** | 2 | 2 | 1 | 3 | 8 |
| 8 | **Reference-freshness compile step** | 2 | 2 | 1 | 3 | 8 |
| 9 | **`TriggerEvaluator` (positive/negative activation)** | 2 | 2 | 1 | 3 | 8 |
| 10 | **Sigstore signing in publish pipeline** | 3 | 2 | 3 | 1 | 9 |
| 11 | **Install-time signature verification** | 3 | 2 | 2 | 2 | 9 |
| 12 | **`bbsctl strictness org` command** | 2 | 2 | 3 | 2 | 9 |
| 13 | **`ownership.yaml` schema + validator** | 2 | 1 | 3 | 2 | 8 |

Rationale: P1 unblocks the `org` strictness rung end-to-end. Signing + signature verify close the publish/install loop. Compile-step additions are individually small and shippable per sprint. `bbsctl author` is short effort but high adoption impact — every new user immediately asks for it.

### P2 — ship in sprints 6–9 (sum 6–7)

| # | Feature | Block | Demo | Dep | Eff | Sum |
|---|---|---|---|---|---|---|
| 14 | **`compatibility-matrix.yaml` schema + validator** | 2 | 1 | 2 | 2 | 7 |
| 15 | **Registry-context trigger validator** | 2 | 2 | 1 | 2 | 7 |
| 16 | **`InjectionEvaluator` + corpus** | 2 | 2 | 1 | 2 | 7 |
| 17 | **Semantic fuzzer** | 1 | 2 | 1 | 2 | 6 |
| 18 | **`skill.yaml` full schema validation** | 2 | 1 | 1 | 3 | 7 |
| 19 | **OCI registry publish target** | 2 | 2 | 2 | 1 | 7 |
| 20 | **`claude-code-remote` publish target** | 1 | 2 | 1 | 2 | 6 |
| 21 | **`mcp-composer` publish target** | 1 | 2 | 1 | 2 | 6 |
| 22 | **Audit JSONL emission (local at team)** | 1 | 2 | 2 | 2 | 7 |
| 23 | **Hook bus** | 2 | 1 | 3 | 1 | 7 |
| 24 | **Cost budget enforcer** | 1 | 2 | 2 | 2 | 7 |
| 25 | **OTel traces** | 1 | 2 | 1 | 2 | 6 |
| 26 | **Claude Code runtime adapter** | 1 | 2 | 1 | 2 | 6 |
| 27 | **Judge calibration corpus + harness** | 1 | 1 | 1 | 3 | 6 |

Rationale: P2 is the `org` strictness gate's full coverage and the Phase 4 runtime instrumentation layer. None of these is an immediate adoption blocker for a `team`-strictness user, but they are all needed before an `org`-strictness user can run end-to-end.

### P3 — roadmap, not next (sum ≤ 5)

| # | Feature | Block | Demo | Dep | Eff | Sum |
|---|---|---|---|---|---|---|
| 28 | `bbsctl strictness regulated` | 1 | 1 | 1 | 2 | 5 |
| 29 | Pinned eval-corpus hash in `skill.yaml` | 1 | 1 | 1 | 2 | 5 |
| 30 | Regulatory sign-off attachment | 1 | 1 | 1 | 2 | 5 |
| 31 | 7-year audit retention metadata | 1 | 1 | 1 | 2 | 5 |
| 32 | Strict gates / `fail-closed` hook default | 1 | 1 | 1 | 2 | 5 |
| 33 | `marketplace list / add-tenant / policy / federate` | 1 | 1 | 1 | 1 | 4 |
| 34 | MCP Composer federation client | 1 | 1 | 1 | 1 | 4 |
| 35 | MCP server runtime adapter | 1 | 2 | 1 | 1 | 5 |
| 36 | LangGraph runtime adapter | 1 | 2 | 1 | 1 | 5 |

Rationale: P3 features serve a regulated-tier audience that does not exist as an adopter yet, or runtime adapters whose demand depends on which agent host the framework wins inside first. Build when there is a user asking.

---

## 4. Sprint plan

Two engineers, two-week sprints. The plan front-loads P0 to get eval out of mock-only state inside the first month, then sequences P1 to unblock `org` strictness inside the first quarter.

| Sprint | Engineer A | Engineer B | Demo gain |
|---|---|---|---|
| **S1** | #1 Claude Agent SDK adapter (core) | #4 Model pinning for eval | First real model in `bbsctl run` |
| **S2** | #1 Claude Agent SDK adapter (polish + tests) + #2 `LLMJudge` | #3 `RegressionEvaluator` + snapshot compare + FULL mode | `bbsctl eval --full` with real judging and regression detection |
| **S3** | #5 `bbsctl author` + `skill-creator` reference skill | #6 Spec-lint compile step | AI-assisted authoring in the CLI; deeper compile |
| **S4** | #10 Sigstore signing in publish | #7 Dependency-audit compile step | Signed bundles in `claude-code-local` target |
| **S5** | #11 Install-time signature verification | #8 Reference-freshness compile step + #9 TriggerEvaluator | Closed publish/install signature loop |
| **S6** | #12 `bbsctl strictness org` + #13 `ownership.yaml` | #14 `compatibility-matrix.yaml` | First end-to-end `org`-strictness skill |
| **S7** | #15 Registry-context trigger validator | #16 InjectionEvaluator + corpus | `--full` validate suite ships substantively |
| **S8** | #19 OCI registry publish target | #18 `skill.yaml` full schema validation | Bundles published to OCI; full skill.yaml gates |
| **S9** | #22 Audit JSONL (local at team) + #23 Hook bus (scaffold) | #20 `claude-code-remote` + #21 `mcp-composer` targets | Hook-emitted audit; multi-target publish |
| **S10** | #24 Cost budget enforcer | #25 OTel traces | Cost gates + OTel-instrumented runtime |
| **S11** | #26 Claude Code runtime adapter | #17 Semantic fuzzer | Native Claude Code execution + adversarial eval |
| **S12** | #27 Judge calibration corpus + harness | Stabilization / friction-audit / docs | Calibrated judge; phase close |

12 sprints = ~24 weeks ≈ 5.5 months. End state: `local`, `team`, and `org` strictness usable end-to-end; eval is real (LLM-judged, model-pinned, regression-aware); publish/install is signed; runtime is instrumented with cost + OTel + audit; Phase 4 runtime substrate is in place. `regulated` and the additional MCP/LangGraph runtimes (P3) remain as a documented backlog.

---

## 5. Dependency graph

Critical-path dependencies that shape the sprint order:

- **#1 Claude Agent SDK adapter** blocks #2 `LLMJudge`, #11 signature verify (via real runtime), and meaningfully #5 `bbsctl author` (the authoring agent needs a runtime adapter).
- **#4 Model pinning** blocks #3 regression compare (you cannot compare without a pinned model).
- **#10 Sigstore signing** blocks #11 signature verify and #12 `bbsctl strictness org` (signing is a Phase 3 requirement).
- **#12 `bbsctl strictness org`** blocks #15 registry-context trigger and the `--full` validate suite gating (validators run at org by default).
- **#23 Hook bus** blocks #22 audit JSONL emission, #24 cost budget enforcer, and #25 OTel traces — all three are hooks layered on top.
- **#13 `ownership.yaml`** is independently small but is read by #12 `bbsctl strictness org`'s interactive prompts.

No cross-team dependencies outside `bbsctl`. The `skillops` layer in the lifecycle paper consumes these features but does not block them.

---

## 6. P0 sprint detail — acceptance criteria

For the first two sprints, here is what "done" looks like per item.

### #1 — Claude Agent SDK runtime adapter

**Acceptance criteria:**
- New module `skillctl/run/claude_agent_sdk.py` with `ClaudeAgentSDKAdapter(AgentRuntime)`.
- Constructor reads `ANTHROPIC_API_KEY` from env; raises `FrameworkError` with copy-pasteable `Fix:` if missing.
- `activate(skill, prompt)` calls the Claude Agent SDK with the skill body as a system prompt and the user prompt as the first message. Returns a `RuntimeResponse` with the model's reply and a trace including the model version and token count.
- Registered via `register_runtime("claude-agent-sdk", ClaudeAgentSDKAdapter)` in `run/__init__.py`.
- Listed in `bbsctl run --runtime` choices.
- Listed in `bbsctl eval --runtime` choices (the eval command's vapor-options guard picks this up automatically once registered).
- Adapter is an `[project.optional-dependencies]` `runtime` group install — base install stays stdlib + ruamel.yaml.
- Tests: mock the SDK at the HTTP boundary; verify activate produces a non-empty reply, traces include the model version, missing API key emits the right `FrameworkError`.

**Effort: 1.5 sprints.**

### #2 — `LLMJudge` against Claude Agent SDK adapter

**Acceptance criteria:**
- New class `LLMJudge(Judge)` in `skillctl/eval/judge.py` (or a new file).
- Constructor accepts a model name (defaulting to `claude-haiku-4-5-20251001` — fast and cheap for judging).
- `score(assertion, actual_output, expected_output)` builds a single-turn judge prompt: "Given the expected behaviour and the actual output, did the system satisfy this assertion? Reply JSON: `{pass: bool, reason: str}`." Parses the reply; returns a `JudgeVerdict`.
- Defensive parsing: if the reply is not valid JSON, retry once with a stricter prompt, then fall back to a failing verdict with the parse error as the reason.
- Registered via `register_judge("llm", LLMJudge)`.
- Listed in `bbsctl eval --judge` choices.
- Same `runtime` optional-deps group as #1.
- Tests: mock the SDK; verify pass/fail verdicts, JSON parse failure recovery, and that `--judge llm` works end-to-end against the `mq-executor` reference corpus.

**Effort: 0.5 sprint.**

### #3 — `RegressionEvaluator` + snapshot compare + `FULL` mode

**Acceptance criteria:**
- New module `skillctl/eval/regression.py` with `RegressionEvaluator(Evaluator)`.
- The evaluator compares the current eval-report against a baseline snapshot file in `evals/snapshots/<suite>.<model-version>.json`.
- The comparison key is `(case_id, assertion_index) → passed`. A regression is a case-assertion pair that was passing in the baseline and is failing now.
- Outputs a `SuiteResult` whose cases include only the regressions; the `actual_output` field includes both old and new outputs side-by-side for the user to inspect.
- New CLI flag: `bbsctl eval --baseline <snapshot-path>` — when set, the `FULL` mode runs `BehaviorEvaluator` first, then `RegressionEvaluator` against the snapshot.
- `bbsctl eval --mode full` is no longer an alias for `fast` — the comment in `eval_cmd.py:65` is removed.
- New CLI subcommand: `bbsctl eval snapshot` — writes the current eval-report to `evals/snapshots/<suite>.<model-version>.json` so the next run has a baseline.
- Tests: round-trip snapshot write/read, regression detection on a contrived corpus where one assertion is flipped between runs, snapshot path conventions.

**Effort: 1 sprint.**

### #4 — Model pinning for reproducible eval

**Acceptance criteria:**
- New `evals/eval.config.yaml` schema (or a `[eval]` block in `skill.yaml`).
- Required fields: `runtime` (name of a registered runtime), `model` (string passed to the runtime), `judge` (name of a registered judge), `judge_model` (string), `threshold` (float, default 1.0).
- The runner reads `eval.config.yaml` if present; CLI flags override.
- The eval report's `metadata` field records the model and judge versions plus the corpus hash (SHA-256 over the concatenation of all suite files in lexicographic order).
- Caching: if `~/.cache/bbsctl/eval/<corpus-hash>.<model>.<judge-model>.json` exists, reuse it. `bbsctl eval --no-cache` forces re-run. `bbsctl eval --refresh-cache` re-runs and overwrites.
- Tests: cache hit on identical input, cache miss when model changes, cache miss when corpus changes, the cache key is stable across machines (no absolute paths or timestamps in the hash).

**Effort: 1 sprint.**

---

## 7. What gets demoed after each P0 sprint

After **S1**: `bbsctl run --runtime claude-agent-sdk --prompt "..."` against `mq-executor` returns a real reply. The five-minute promise extends to "five minutes including a real model run."

After **S2**: `bbsctl eval --judge llm --runtime claude-agent-sdk --mode full --baseline evals/snapshots/behavior.claude-sonnet-4-6.json` runs the corpus, scores assertions through a real judge, compares against a snapshot, and reports regressions. This is the demo moment where Bulbasaur stops looking like a wrapper and starts looking like a real lifecycle tool.

After **S3**: `bbsctl author "I want a skill that restarts an OpenShift deployment"` walks the developer through scaffolding interactively. The `skill-creator` reference skill is installed in any Claude Code instance via `bbsctl publish` + `/plugin install`.

After **S4–S5**: signed bundles in the marketplace; signature verification on install. The publish/install loop is closed.

After **S6**: the first skill at `org` strictness ships end-to-end. The strictness ladder is no longer aspirational.

---

## 8. What this leaves on the table

The P3 backlog (~10 features) is deferred to "when a user asks." That covers regulated-tier features (which need a regulated adopter to inform the work), additional MCP/LangGraph runtimes (which depend on which agent host wins inside first), and the marketplace-federation subcommands (which depend on a federated marketplace existing).

The cross-cutting lifecycle integrations described in [`docs/skill-lifecycle-framework-whitepaper.md`](skill-lifecycle-framework-whitepaper.md) — Cursor extension, Bolt template, GitHub Action, pre-commit hook — are out of scope for this roadmap. They belong to the `skillops` layer, which orchestrates `bbsctl` plus Mellea rather than living inside `bbsctl`.

---

## 9. Risks and unknowns

- **Claude Agent SDK API stability.** The adapter is the linchpin of P0. If the SDK changes shape during S1, slip by 0.5–1 sprint.
- **Judge cost in CI.** `LLMJudge` runs one model call per assertion per case. A 20-case corpus with 5 assertions each is 100 calls per eval run. CI cost is real; the cache in #4 mitigates but does not eliminate. A separate `--mode smoke` (already wired) becomes the default for PR checks; `--mode full` runs nightly.
- **Sigstore signing UX.** Free-tier Sigstore requires an OIDC identity (GitHub Actions, Google, etc.). The local-dev story (no OIDC) is not free. Options: ship the local-dev path with `cosign-piv` or `cosign --identity-token`. Decision needs to be made before S4.
- **`bbsctl author` against a real model.** Cost-per-skill-authored is the friction. The first version should run against a cheap model by default and let the user opt up.
- **Snapshot file size.** A 50-case corpus with assertion-level outputs can be megabytes per snapshot. Versioned in Git is fine; recorded in eval reports is fine; but watch for storage bloat at `regulated` where every model upgrade pins a new snapshot.

---

## 10. Closing

30 planned features. 4 in P0, 9 in P1, 14 in P2, 9 in P3 (one feature appears in two tiers due to scope overlap). 12 sprints across two engineers gets through P0, P1, and most of P2. End state at sprint 12 is a `bbsctl` that runs real models, judges real assertions, gates real publishes, instruments real runtimes, and ships at `org` strictness end-to-end. Everything past S12 is either a regulated-tier escalation (P3) or a `skillops`-layer integration that belongs in a different repo.

---

### References

- Source-code phase markers — see §1 file references
- [`docs/strictness-levels.md`](strictness-levels.md) — the strictness ladder requirements per rung
- [`docs/evaluation.md`](evaluation.md) — eval module current shape
- [`docs/skill-lifecycle-framework-whitepaper.md`](skill-lifecycle-framework-whitepaper.md) — broader framework context
- `framework-build-plan.md` — original phase plan (at repo root)
