# Skill lifecycle management

## What it looks like, what a framework needs, what's missing, what to build

---

## 1. What skill lifecycle management means

A skill is a small, declarative artifact — typically a Markdown file with frontmatter plus supporting files — that controls how an agent behaves in some workflow. Once that artifact shapes production decisions, it is production code. The artifact is non-deterministic at runtime (an LLM executes it), its trigger surface is user-controllable, its dependencies (model versions, tool integrations) drift, and its consequences range from harmless to regulatory. Skill *lifecycle management* is the discipline of moving that artifact through the same operational stages every other piece of production code goes through: authored, validated, evaluated, governed, signed, distributed, instrumented, observed, and eventually retired.

The lifecycle has eight stages, each with a separate concern and a separate failure mode if absent:

1. **Design** — author articulates the workflow, trigger, inputs, success criteria
2. **Decompose** — break the natural-language spec into typed primitives the rest of the lifecycle can reason about
3. **Compile** — render to an executable artifact + a machine-readable report
4. **Validate** — structural checks (spec conformance, trigger quality, output contract)
5. **Evaluate** — behavioral test against a corpus, judged automatically, with reproducible pinning
6. **Certify** — risk identification mapped to declarative policy; compliance classification
7. **Publish** — content-addressed, signed bundle pushed to a registry
8. **Observe** — runtime instrumentation, audit stream, model-upgrade regression detection

Three constituencies see this lifecycle from different sides. The framework only earns its keep if each constituency gets a working loop.

### The developer's view

A developer opens their IDE. The skill panel shows the required frontmatter, lints the description as they type, and offers AI assistance for authoring. They iterate: description, body, references.

They write an evaluation corpus next to the skill — cases with natural-language assertions about how the skill should behave. They click "Run eval." The skill activates against a runtime, a judge scores each assertion, and the panel shows the actual output side-by-side with the expected one. The iteration loop is sub-minute.

`git commit`. A pre-commit hook runs the fast checks — compile, frontmatter validate, trigger quality — in under five seconds; anything broken blocks the commit. The PR opens. CI runs the full eval against the pinned model, regression-compares against the last snapshot, and runs the trigger-collision check against every other skill in the registry. A failing eval blocks the merge.

After merge, the publish pipeline signs the bundle. The developer goes back to authoring.

### The production SRE's view

A signed, digest-pinned bundle lands in the registry. The runtime installs the policy's hooks: every model call goes through a gate, every gate emits an audit log line with model version, prompt hash, hook outcome, latency, cost, user id.

A page fires: the skill's p99 latency spiked. The SRE pulls the audit stream by skill id and time window. Within thirty seconds they can see which model version, which hook fired, which policy rule matched, what the cost spike looked like. Attribution is one query, not a code-archaeology session.

Overnight, the model vendor publishes a new version. The scheduled re-evaluation job runs the pinned corpus against the new model and compares to the baseline. Regression beyond the declared threshold opens a PR back to the skill repository and pins the runtime to the previous model version until the PR merges. No human pages, no production drift.

When the skill is retired, the bundle is marked deprecated. Existing consumers keep running on their pinned digest; new installs are warned. After the grace period, it's delisted but archived for audit.

### The client running it in their workflow

A team consuming the skill in some domain workflow — claims processing, on-call triage, customer support — searches the registry. They filter by strictness, by compliance framework, by archetype, and open the skill they want. The marketplace shows them four pieces of evidence: the eval score against the corpus the publisher pinned, the policy report listing every requirement satisfied, the signature chain, and the cost-per-thousand-activations the publisher recorded.

They install by digest. The installer verifies the bundle against its lockfile, the signature against the publisher's identity, and the publisher's policy report against the org's own baseline policy. The skill drops into the team's agent host.

In their workflow, the skill activates on the trigger they care about. Their own audit stream picks up every activation — the same schema the publisher's stream uses — and feeds their observability system. The team's compliance officer pulls the report quarterly and matches it against the same controls the publisher's policy declared.

When the publisher releases a new version, the team's CI re-runs the publisher's eval corpus against their pinned model and decides whether to upgrade. Their workflow does not stop because someone else released.

### The composite picture

That is what the lifecycle should look like — developers iterating with fast feedback, SREs attributing incidents from a structured stream, clients consuming signed artifacts whose conformance they can independently verify. It is what every other production artifact already gets. Skills are not getting all of it today; parts of it are starting to ship across the open-source ecosystem, which §3 catalogs.

---

## 2. What features a framework needs to support that

Working backward from the lifecycle, the framework's required capabilities cluster into six groups.

**Authoring.** A scaffold command. An AI-assisted authoring path so a developer can co-write the skill with an agent that knows the spec. Edit-time linting in the IDE — not just at save, on every keystroke for the description field where trigger quality matters. An archetype tag (generative artifact, deterministic dispatch, analytical pipeline, constrained reasoning, adversarial classification) so downstream tooling knows what kind of skill it's dealing with.

**Compile and structural validation.** Parse frontmatter, validate against the public spec (agentskills.io), structural lints (bundled-asset-path-resolution, fixtures-loader-contract, output-contract well-formedness), trigger-quality heuristic. Fast — under a second. Emit a machine-readable report so CI can consume it.

**Behavioral evaluation.** A corpus format (JSON, single file per suite). Cases with prompt + expected_output + assertions. A judge that scores assertions (deterministic heuristic for CI smoke, LLM-as-judge for real scoring). Model pinning so eval runs are reproducible. Snapshot baselines for regression compare. A report machine-readable enough for branch-protection checks to gate on.

**Governance.** A strictness rung declaration (local / team / org / regulated) so the framework knows how much certification work to do. Risk identification mapped to standard taxonomies (NIST AI RMF, Credo UCF, Granite Guardian). A declarative policy artifact linking identified risks to runtime hook configurations. Compliance classification (AUTOMATED / PARTIAL / MANUAL) per dimension. All artifacts signed and bundled with the skill.

**Publishing and distribution.** A signed, content-addressed bundle format. A marketplace or registry to push to (stock Claude Code marketplace at minimum; OCI registry for broader interop; Git-backed registries for org-internal). A lockfile so `install` is deterministic.

**Runtime and observability.** Adapter abstraction so the same skill runs in Claude Code, MCP server, LangGraph node, Cursor extension, Bolt embed, custom agent host. Hook-based instrumentation that emits audit JSONL with model version, prompt hash, hook outcome, latency, token count, cost. OTel trace export for SRE consumption. Cost telemetry for FinOps. Model-upgrade detection that triggers re-evaluation.

**Lifecycle integrations.** IDE plugins (Cursor, VS Code, Bolt) that surface the framework's commands in the developer's existing workflow. CI integrations (GitHub Actions, GitLab CI, generic CLI for Jenkins/Buildkite) that run the lifecycle headlessly with structured output. Pre-commit hooks for the fast checks. Branch-protection checks for the slow ones. Scheduled re-eval jobs for model-upgrade regression detection. Webhook integrations for registry events (publish, deprecate, retract).

That is the surface area. No single existing tool covers it.

---

## 3. Requirements — what each role needs

Section 2 describes the framework's required capabilities in categories. This section restates the same surface as concrete user stories — "as a [role] I need [outcome]" — so a reader can match what the framework should do to the role they actually inhabit. The four roles below cover the same lifecycle from authoring through retirement; the framework only earns its keep when every row in this table can be satisfied.

| # | Role | Requirement |
|---|---|---|
| 1 | Developer | I need to scaffold a new skill with one command at the right strictness rung. |
| 2 | Developer | I need my IDE to surface lint errors on the description field as I type, not only on save. |
| 3 | Developer | I need an AI assistant in my editor that can co-author the skill body and references. |
| 4 | Developer | I need to run the local eval corpus against a mock runtime in under one minute. |
| 5 | Developer | I need to run the same eval against a real model with one flag change — no rewrite. |
| 6 | Developer | I need every assertion's pass/fail result shown next to the actual output the model produced. |
| 7 | Developer | I need a pre-commit hook that runs structural checks in under five seconds. |
| 8 | Developer | I need CI to gate my PR on eval pass/fail without my wiring it per-repo. |
| 9 | Developer | I need the same eval inputs to produce the same eval output on every machine — reproducibility. |
| 10 | Developer | I need to filter eval to a single suite or single case while I'm iterating. |
| 11 | Developer | I need a permissions skeleton I can generate when my skill body uses shell commands. |
| 12 | Developer | I need to see which commands in my skill body will trip a permission rule before I publish. |
| 13 | SRE | I need every runtime activation logged with model version, prompt hash, hook outcome, latency, cost, and user id. |
| 14 | SRE | I need to attribute a production incident to a specific skill + version + model in one query. |
| 15 | SRE | I need model upgrades to trigger automatic re-evaluation against the pinned corpus. |
| 16 | SRE | I need a regression on the pinned eval to block the model rollout — not just notify. |
| 17 | SRE | I need audit logs to survive the org's retention SLA without manual archival. |
| 18 | SRE | I need cost telemetry per skill so FinOps can attribute spend. |
| 19 | SRE | I need hooks to fail closed at regulated strictness — a hook crash must not open a hole. |
| 20 | SRE | I need rollback to a previous skill version that takes effect within minutes. |
| 21 | SRE | I need per-skill cost ceilings that block execution at runtime, not just alert. |
| 22 | SRE | I need health checks per skill that surface skill-level p99 latency separately from host metrics. |
| 23 | Client | I need to discover skills in a registry filtered by compliance framework and archetype. |
| 24 | Client | I need cryptographic verification that the bundle I install matches what the publisher signed. |
| 25 | Client | I need to see the publisher's eval report and policy report before I install. |
| 26 | Client | I need the runtime to refuse any operation the policy denies, with an audit entry. |
| 27 | Client | I need my own audit stream to use the same schema as the publisher's. |
| 28 | Client | I need to pin a specific version of a skill so a publisher update can't silently change my workflow. |
| 29 | Client | I need to layer my org's policy baseline on top of the publisher's policies at install time. |
| 30 | Client | I need the registry to mark deprecated skills clearly so I can plan migrations. |
| 31 | Client | I need installs to be deterministic — same digest in dev and in prod, every time. |
| 32 | Client | I need to re-run the publisher's eval corpus against my pinned model and gate the upgrade on the result. |
| 33 | Compliance officer | I need each policy requirement to map to a regulatory control (NIST, SOC2, HIPAA, …). |
| 34 | Compliance officer | I need a per-skill evidence file recording every policy gate passed, with timestamp and approver. |
| 35 | Platform engineer | I need to enforce an org-wide baseline policy on every skill via the configuration cascade. |
| 36 | Platform engineer | I need to configure default judge backend and model once, applied across every developer's machine. |
| 37 | Platform engineer | I need a quarterly compliance report that aggregates evidence across every skill the org ships. |

The framework satisfies a requirement when it can be enforced (or detected and surfaced) by tooling, not only documented in a runbook. Section 5 catalogs which of these 37 requirements are currently met by the two open-source projects discussed in this paper, partially met, or absent entirely.

---

## 4. The proposal — what to build

A new layer that sits above Bulbasaur and Mellea, orchestrates them, and exposes the lifecycle to the surfaces developers and CI systems actually use. Working name: **`skillops`**. The components:

### 4.1 `skillops` orchestration CLI

A thin CLI that wraps `bbsctl` and `mellea` behind one entry point. Single source of truth for the lifecycle order.

```bash
skillops new <name>                  # → bbsctl new + Mellea archetype prompt
skillops compile                     # → bbsctl compile
skillops validate                    # → bbsctl validate + Mellea structural lints
skillops eval                        # → bbsctl eval with model pinning + caching
skillops certify                     # → mellea certify (at org+ strictness)
skillops publish                     # → bbsctl publish + bundle re-emission with cert artifacts
skillops install <bundle>            # → bbsctl install + signature verify
skillops run                         # → end-to-end, fails fast at first gate
```

`skillops run` is the CI entry point. It takes a `skill.yaml`, walks the lifecycle to the configured rung, and exits non-zero on any failure. Caches eval runs by `(model_version, corpus_hash, judge_config)` so repeat runs are cheap.

### 4.2 IDE integrations

**Cursor extension.** A skill panel in the sidebar. Real-time lint feedback on the description field. "Run eval" button that surfaces a side-by-side actual-vs-expected diff. "Publish" command that walks the lifecycle and surfaces gate failures inline. Integrates with Cursor's MCP support so the eval can use the user's own model and the user's MCP-exposed tools.

**Bolt integration.** A Bolt template that bootstraps a skill repository with `skillops` pre-wired. Bolt's generated UI handles the editing surface; `skillops` handles validate/eval/publish. The output is a skill bundle ready to install in any host.

**Claude Code plugin.** A `skill-authoring` plugin published to the Claude Code marketplace. Activates whenever the developer is in a directory containing `SKILL.md`. Provides slash commands: `/skill validate`, `/skill eval`, `/skill publish`. Reuses the existing Claude Code plugin format — zero patches to Claude Code itself.

**VS Code extension.** Same shape as Cursor; uses the Anthropic / Continue extension's chat panel for AI-assist authoring.

### 4.3 CI/CD integrations

**GitHub Action — `skillops-action@v1`.** One step: `uses: bulbasaur/skillops-action@v1`. Reads the repo's `skill.yaml`, runs `skillops run`, posts results as a PR check per lifecycle stage. Caches eval runs across pushes. Supports matrix runs across multiple pinned models.

```yaml
- uses: bulbasaur/skillops-action@v1
  with:
    strictness: org
    fail-on: eval,certify
    model-pins: |
      claude-sonnet-4-6
      claude-haiku-4-5-20251001
```

**GitLab CI template.** Same surface, `.gitlab-ci.yml` snippet.

**Generic CLI for Jenkins / Buildkite / CircleCI.** Just `skillops run --output json` — every other CI system can call this.

**Pre-commit hook.** Fast checks only — compile + structural validate + trigger heuristic. Under five seconds. Behavioral eval runs in CI, not in pre-commit (too slow, requires model access).

**Branch protection check.** At `org+`, GitHub branch protection requires `skillops/eval` and `skillops/certify` to pass before merge. The check is the GitHub Action's status output.

### 4.4 Reproducible eval

Three inputs, one output: `(model_version, corpus_hash, judge_config) → eval_report`. Same three inputs always produce the same output. Cache keyed on the hash. Snapshot baselines stored as JSON in the repo so regression compare is a diff.

This is what makes model upgrades safe. The scheduled re-eval job runs the corpus against the new model, compares to the baseline, opens a PR back to the skill repo if regression exceeds the threshold declared in `skill.yaml`. The PR includes the diff per case so the developer can decide: corpus wrong, skill wrong, model wrong.

### 4.5 Bundle registry

A signed, content-addressed bundle store. Options in order of preference:

- **OCI registry** — leverage existing infrastructure (Docker Hub, GitHub Container Registry, Harbor, internal ECR). Bundles are OCI artifacts. `skillops install oci://registry/path/skill:1.2.3`.
- **Git-backed registry** — for org-internal use without OCI infrastructure. A Git repo with bundle directories and a `marketplace.json`. Already supported by Bulbasaur's `team-marketplace` target; extend it.
- **Stock Claude Code marketplace** — preserved as the consumer-facing surface for plugin-style installs.

All three sign bundles with Sigstore. All three are content-addressed. `skills.lock` is extended to record bundle digests so `skillops install` is deterministic.

### 4.6 What it doesn't do

- It does not replace Bulbasaur or Mellea. It orchestrates them.
- It does not become a marketplace UI. Registries handle discovery and browsing.
- It does not try to be an agent framework. Cursor, Bolt, Claude Code, the Claude Agent SDK, MCP, LangGraph all remain the runtime substrates.
- It does not invent governance taxonomies. NIST AI RMF, Credo UCF, Granite Guardian stay authoritative.

---

## 5. What Bulbasaur has, what Mellea has, what is missing

A capability-by-capability matrix grouped by the same lifecycle areas as §2. ✓ shipped, ◐ partial or planned, ✗ absent. The "Gap" column is what needs to be built even taking both libraries together.

### Authoring

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| CLI scaffold | ✓ `bbsctl new` (local + team templates) | ◐ via `/mellea-fy` (requires Claude Code) | Consolidate behind one entry point |
| AI-assist authoring (skill-creator agent) | ◐ planned `bbsctl author` | ◐ via Claude Code slash command | **Build cross-IDE authoring surface** |
| Archetype tagging | ✗ | ✓ five archetypes in `classification.json` | Surface Mellea's archetypes in Bulbasaur authoring |
| Edit-time linting (IDE) | ◐ designed in `docs/ide-integration.md` (LSP server) | ✗ | **Implement `bbsctl lsp`** |
| MCP server for IDE agent integration | ◐ designed in `docs/ide-integration.md` (12 tools) | ✗ | **Implement `bbsctl mcp`** |

### Compile and structural validation

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Frontmatter parse + spec validate | ✓ | ✓ (re-parses) | Consolidate — one source of truth |
| Structural lints | ✓ 5 validators (enterprise-spec, basic-trigger, output-contract, permissions, ownership, policy) | ✓ 16 lints (2 Python, 14 LLM) | Merge lint sets behind one runner |
| Typed IR emission | ✗ | ✓ 6 JSON IRs | Adopt Mellea's IRs as the canonical IR |
| Compile report (machine-readable) | ✓ `dist/compile-report.json` | ◐ no standard report | Standardize on Bulbasaur format |
| Validate report (machine-readable) | ✓ `validate-report.json` with errors/warnings/notes per validator | ✗ | Adopt across both |
| FrameworkError contract (summary / detail / fix / docs) | ✓ ≥90% fix-line coverage; top-level wrapper for OSError + unexpected | ✗ | Adopt across both |
| Vapor-options guard (CLI honesty) | ✓ argparse `choices` driven by support registry; lint test on every build | ✗ | Adopt across both |

### Behavioral evaluation

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Corpus format | ✓ `evals/*.json` with assertions | ✗ (fixtures are smoke-check only) | Adopt Bulbasaur's corpus across both |
| Case schema (id, prompt, expected_output, files, assertions) | ✓ | ✗ | Adopt across both |
| `Evaluator` Strategy + Factory (per-suite-name plug-in) | ✓ `behavior` + `injection` + `fuzz` registered; fallback for unknown suites | ✗ | Add `TriggerEvaluator` |
| `Judge` Strategy + Factory | ✓ `HeuristicJudge` + `LLMJudge` | ✗ | None |
| Judge (heuristic, deterministic, no API key) | ✓ keyword overlap with stopwords, configurable threshold | ✗ | None |
| Judge (LLM-as-judge) | ✓ `LLMJudge` with multi-backend (Ollama / Anthropic / OpenAI); JSON-mode prompt + retry; backend errors → failing verdicts | ✗ | None |
| Eval modes — SMOKE / FAST / FULL | ✓ all three; FULL adds snapshot regression compare | ✗ | None |
| CLI filter flags (`--suite NAME`, `--case ID`) | ✓ for fast iteration | ✗ | None |
| Per-case `actual_output` + duration + runtime_error capture | ✓ | ✗ | None |
| Case score = fraction of assertions passing; suite score = mean | ✓ + suite pass-threshold gating | ✗ | None |
| Machine-readable report (`--output json`) | ✓ structured `EvalReport` with full pinning metadata | ✗ | None |
| Exit-code convention (0 pass · 1 case-fail · 2 framework-error) | ✓ | ✗ | None |
| Load-error contract (`EvalLoadError` → `FrameworkError` shape) | ✓ structured fix lines | ✗ | None |
| Reference corpus (hello-skill + mq-executor patterns) | ✓ `reference-plugins/hello-skill/evals/behavior.json` | ✗ | Add per-archetype reference corpus |
| Model pinning for reproducibility | ✓ `evals/eval.config.yaml` + `EvalConfig` (runtime, runtime_model, judge, judge_backend, judge_model, threshold) | ◐ runtime defaults | None |
| Eval-result caching by (skill_hash, corpus_hash, runtime, models, judge, mode, filters) | ✓ `~/.cache/bbsctl/eval/` keyed by SHA-256 of canonical tuple | ✗ | None |
| Snapshot baselines | ✓ `bbsctl eval --snapshot SUITE` writes `evals/snapshots/<suite>.<model>.json` | ✗ | None |
| Regression compare (FULL mode against baseline) | ✓ via `RegressionEvaluator` + snapshot diff | ✗ | None |
| **InjectionEvaluator + bundled 15-case corpus** | ✓ 7 categories × 4 severities; severity-weighted scoring | ✗ | None |
| **SemanticFuzzer (LLM-generated rephrasings + stability score)** | ✓ N variants per case; stability = baseline-matching ratio | ✗ | None |
| **Multi-backend LLM adapter (`LLMBackend` interface)** | ✓ OllamaBackend, AnthropicBackend, OpenAIBackend; `register_backend` for plug-ins | ✗ | None |
| Judge calibration (precision/recall vs human) | ✗ | ✗ | **Build calibration corpus and harness** |
| Permission-denial assertions (deterministic, audit-driven) | ◐ designed in `docs/permissions.md`; runtime hooks land with the hook bus | ✗ | **Wire `permission_assertions` once runtime hooks ship** |

### Governance and certification

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Strictness rung declaration | ✓ `skill.yaml` (local / team / org / regulated) | ✗ | None |
| **`permissions.yaml` schema + Guardrails engine** | ✓ 6 rule groups (commands, namespaces, network, filesystem, env, mcp_tools); deny-wins; auto-generated rule ids; layered org+skill resolution | ✗ | None |
| **`ownership.yaml` full schema + `OwnershipValidator`** | ✓ team / contact / runbook / on_call / escalation / business_owner / cost_owner / last_reviewed with age window enforcement | ✗ | None |
| **Data-driven policy YAML (`policies/*.yaml`)** | ✓ `Policy` data model covering required artifacts, ownership, eval, permissions, audit, approval, cost, compliance mappings | ✗ | None |
| **PolicyEngine — per-section requirement checks** | ✓ PASS/FAIL/SKIP/UNKNOWN per requirement; effective-window enforcement; strictness applicability | ✗ | None |
| **Multi-policy merge (deny-wins)** | ✓ union artifacts, tightest review window, strictest fail-mode, max approver count per role | ✗ | None |
| **Bundled reference policies** | ✓ HIPAA-baseline, SOC2 Type II baseline, internal-tier-1 (catalog discoverable via `bbsctl policy list`) | ✗ | Add FedRAMP, PCI, GDPR baselines |
| **`bbsctl policy {list, show, lint, validate}` CLI** | ✓ catalog discovery, per-requirement attribution, file lint, skill validation | ✗ | None |
| **`skill.yaml` `policies:` field + `PolicyValidator`** | ✓ resolves catalog short names + paths; required at org+; integrated into validate chain | ✗ | None |
| **Configuration cascade (CLI > env > skill > project > user > org > defaults)** | ✓ `~/.config/bbsctl/config.yaml` + `/etc/bbsctl/config.yaml` + `BBSCTL_*` env vars; per-field resolution | ✗ | None |
| Risk identification (Nexus-style) | ✗ | ✓ | Bridge Mellea Nexus → bbsctl policy `compliance_frameworks` |
| PolicyManifest runtime contract | ✗ | ✓ | Mellea owns runtime; bbsctl policy owns publish-time conformance |
| NIST AI RMF mapping | ◐ declarative via policy `compliance_frameworks` (HIPAA / SOC2 / NIST listed) | ✓ static YAML | Ground-truth validation (open question) |
| Credo UCF mapping | ✗ | ✓ static YAML | Ground-truth validation (open question) |
| Compliance classification (AUTOMATED / PARTIAL / MANUAL) | ✗ | ✓ | Adopt Mellea's classifier |
| Certification report | ✗ | ✓ | Mellea owns; bbsctl policy report feeds it |

### Publishing and distribution

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Marketplace bundle (Claude Code-compatible) | ✓ `claude-code-local`, verified by stock `claude plugin validate` | ✗ | None |
| Git-backed team marketplace (`bbsctl publish --marketplace`) | ✓ `GitMarketplace.publish_plugin` propagates `permissions.yaml` + `ownership.yaml` + `evals/` + `dist/` | ✗ | None |
| Marketplace bundle (Claude Code remote) | ◐ planned | ✗ | **Wire it** |
| MCP Composer publish target | ◐ planned | ✗ via `export --target mcp` | **Reconcile** |
| OCI registry publish target | ◐ planned | ✗ | **Wire it** |
| **`bundle.lock` (SHA-256 per file, byte-stable JSON)** | ✓ written automatically on publish; tolerates pyache/.git skipping | ✗ | None |
| **`bundle.sig` (Sigstore-shaped placeholder)** | ◐ placeholder JSON `{kind: placeholder, lock_digest}`; schema-stable for Phase-3 Sigstore swap | ✗ | **Wire Sigstore signing** |
| **`GitMarketplace.verify_plugin` digest verification** | ✓ catches tamper, missing files, unexpected files | ✗ | None |
| Content-addressed lockfile (consumer side) | ✓ `skills.lock` with SHA-256 digests | ✗ | Bridge `bundle.lock` → `skills.lock` |
| Bundle re-emission with cert artifacts | ✗ | ✗ | **Build bundle update protocol (Mellea cert sections)** |

### Runtime and observability

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| `AgentRuntime` interface | ✓ ABC + `MockAgent` (deterministic, no API key) | ✗ | None |
| **Claude Agent SDK adapter** | ✓ `ClaudeAgentSDKAdapter` over `AnthropicBackend`; model pinning; backend errors → `RuntimeResponse` with `[runtime error]` reply; trace records model + tokens + latency | ✗ | None |
| **Runtime model pinning via `build_runtime(model, max_tokens, temperature)`** | ✓ forwarded with TypeError-tolerant fallback | ✗ | None |
| Claude Code adapter | ◐ planned Phase 4 | ◐ via export | Reconcile and build |
| MCP server adapter | ◐ planned Phase 6 | ◐ via export | **Build native adapter** |
| LangGraph adapter | ◐ planned Phase 6 | ◐ via export | **Build native adapter** |
| Cursor adapter | ◐ designed in `docs/ide-integration.md` (Phase B) | ✗ | **Implement Cursor extension** |
| Bolt adapter | ◐ designed in `docs/ide-integration.md` (Phase D template) | ✗ | **Implement Bolt template** |
| Hook-based instrumentation | ◐ designed as `PermissionsHook` in `docs/permissions.md` | ✓ | Adopt Mellea's hook bus + share schema |
| Audit JSONL emission | ✗ runtime; ✓ schema declared in `permissions.yaml` design | ✓ | Standardize schema |
| OTel trace export | ◐ planned | ◐ | **Wire it** |
| Cost telemetry | ◐ planned | ◐ | **Wire it** |
| Model-upgrade regression detector | ◐ `bbsctl eval --snapshot` + regression-compare in place; scheduled-job orchestration remains | ✗ | **Build scheduled job (skillops layer)** |

### Lifecycle integrations

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Cursor extension | ◐ designed in `docs/ide-integration.md` Phase B | ✗ | **Implement** |
| Bolt template / integration | ◐ designed in `docs/ide-integration.md` Phase D | ✗ | **Implement** |
| Claude Code plugin (skill-authoring) | ◐ designed Phase C + via marketplace | ✗ | **Implement** |
| VS Code extension | ◐ designed Phase B | ✗ | **Implement** |
| `bbsctl mcp` server (MCP protocol — 12 tools) | ◐ designed | ✗ | **Implement** |
| `bbsctl lsp` server (LSP protocol — diagnostics + hover + completion + code actions) | ◐ designed | ✗ | **Implement** |
| GitHub Action | ◐ designed (`skillops-action@v1`) | ✗ | **Implement** |
| GitLab CI template | ◐ designed | ✗ | **Implement** |
| Pre-commit hook | ◐ designed | ✗ | **Implement** |
| Branch-protection check | ◐ designed | ✗ | **Implement** |
| Webhook / registry-event integration | ✗ | ✗ | **Build it** |

### The score

- **Bulbasaur covers** authoring (CLI), structural compile, the full validator chain (spec / trigger / output-contract / permissions / ownership / policy), behavioral eval with LLM-as-judge and reproducible model pinning + cache + snapshot regression, injection corpus + semantic fuzzer, the data-driven policy layer (catalog of HIPAA / SOC2 / internal-tier-1 plus a custom-policy extension point), the configuration cascade (CLI > env > skill > project > user > org > defaults), git-backed marketplace publishing with `bundle.lock` + signature placeholder, the Claude Agent SDK runtime, and the FrameworkError / vapor-options engineering discipline.
- **Mellea covers** typed IR decomposition, formal governance taxonomy mapping (NIST + Credo + Granite Guardian), risk identification, certification with AUTOMATED / PARTIAL / MANUAL classification, hook-based runtime instrumentation with audit JSONL, and export to MCP / LangGraph / Claude Code.
- **Both gap** on actual IDE integration code (designed but not implemented in either repo), CI/CD integration code, signed bundle distribution beyond Claude Code's marketplace format, judge calibration, audit-stream schema standardization, and cross-runtime adapter breadth (MCP server, LangGraph, Cursor, Bolt as native adapters).

The two libraries together now cover roughly 75% of the requirements in §3 — up from the ~60% in the original draft of this paper. The remaining 25% is the IDE + CI + cross-runtime integration work §4 describes as joint extension of the two existing libraries.

### What shipped in Bulbasaur since the original matrix

For readers who saw the previous version of this paper: `permissions.yaml` + Guardrails engine, `ownership.yaml` full schema + validator, the policy module + reference catalog + `bbsctl policy` CLI, the multi-backend LLM adapter (Ollama / Anthropic / OpenAI), `LLMJudge`, `InjectionEvaluator` + 15-case bundled corpus, `SemanticFuzzer`, model-pinned reproducible eval + cache + snapshots, the Claude Agent SDK runtime adapter, the full configuration cascade including `~/.config/bbsctl/config.yaml` + `/etc/bbsctl/config.yaml`, `bundle.lock` content-addressing + signature placeholder, and `GitMarketplace.verify_plugin` digest verification. The IDE + CI/CD surfaces are designed (`docs/ide-integration.md`, `docs/configuration.md`, `docs/user-guide.md`) but their server implementations (`bbsctl mcp`, `bbsctl lsp`) remain.

---

### References

**Open-source projects discussed in this paper**

- Bulbasaur Skill CLI — repo: [github.com/mansura-habiba/bulbasaur-skill-cli](https://github.com/mansura-habiba/bulbasaur-skill-cli) · in-repo docs: [`README.md`](../README.md), [`docs/strictness-levels.md`](strictness-levels.md), [`docs/evaluation.md`](evaluation.md), [`docs/permissions.md`](permissions.md), [`docs/configuration.md`](configuration.md), [`docs/ide-integration.md`](ide-integration.md), [`docs/user-guide.md`](user-guide.md), [`docs/bbsctl-roadmap.md`](bbsctl-roadmap.md)
- Mellea Skills Compiler — repo: [github.com/generative-computing/mellea-skills-compiler](https://github.com/generative-computing/mellea-skills-compiler) · in-repo source cited: `README.md`, `FAQ.md`, `src/mellea_skills_compiler/cli.py`, `src/mellea_skills_compiler/certification/data/`, `src/mellea_skills_compiler/export/targets/`

**Specifications and standards**

- agentskills.io specification — [agentskills.io/specification](https://agentskills.io/specification)
- NIST AI Risk Management Framework 1.0 — [NIST.AI.100-1](https://www.nist.gov/itl/ai-risk-management-framework)
- IBM Granite Guardian model card
- Credo AI Unified Control Framework
- HIPAA Security Rule — 45 CFR §164.308, §164.310, §164.312
- SOC 2 Trust Services Criteria
- OCI Artifacts specification — [github.com/opencontainers/image-spec](https://github.com/opencontainers/image-spec)
- Sigstore — [sigstore.dev](https://www.sigstore.dev)
- Model Context Protocol — [modelcontextprotocol.io](https://modelcontextprotocol.io)
- Language Server Protocol — [microsoft.github.io/language-server-protocol](https://microsoft.github.io/language-server-protocol/)
