# Skill lifecycle management

## What it looks like, what a framework needs, what's missing, what to build

---

## 1. What skill lifecycle management looks like

A skill's life — from authored draft to running-in-production to retired — has the same operational shape as any other piece of code that ships behind a CI/CD pipeline. The artifact is different (a Markdown file with frontmatter, plus optional supporting files), and the runtime is different (an LLM in an agent host), but the operational stages are the same.

A working day looks like this:

A developer opens their IDE — Cursor, Bolt, Claude Code, VS Code with the Continue extension, JetBrains with the Anthropic plugin — and scaffolds a new skill. Their IDE has a panel that shows them what fields are required, lints the description in real time, and offers an AI assistant that knows how to author skills correctly. The developer iterates: writes the description, edits the body, adds reference files.

The developer wants to test the skill locally. They author an `evals/` corpus next to the skill — a JSON file of prompts with natural-language assertions. They click "Run eval" in their IDE. The skill activates against a mock runtime (or a real model if they want), the assertions are scored by a judge, the IDE shows a pass/fail breakdown per case with the actual output side-by-side. The iteration loop is sub-minute.

The developer commits and pushes. A pre-commit hook runs the fast checks (structural compile, frontmatter validation, trigger quality heuristics) — under five seconds, fails the commit if something's broken. The PR opens. CI runs the slow checks: the full eval corpus against the pinned model, a regression compare against the last passing baseline, the trigger-collision check against every other skill in the org's registry. The PR shows a check per lifecycle stage. A failing eval blocks the merge.

If the skill is high-risk — DevOps, customer-facing, or anything tagged at `org+` strictness — the PR also runs a certification step. Risk identification surfaces what the skill might do wrong, a policy manifest gets generated linking each risk to a runtime hook configuration, the manifest gets attached to the build artifact, and the certification report becomes a publish prerequisite.

The skill merges. The publish pipeline signs a content-addressed bundle (SKILL.md + skill.yaml + eval corpus + eval report + certification artifacts) and pushes it to a registry. Consumers — IDEs, agent hosts, MCP composers — pull from the registry by digest. The same bundle that left CI is what lands in production.

The skill runs. The runtime is instrumented: every model call goes through a hook, every hook emits an audit JSONL line, every audit line includes the model version. When the runtime's model upgrades, a scheduled job re-runs the eval corpus against the new model and the pinned baseline. A regression beyond the declared threshold opens a PR back to the skill repository. The lifecycle loops.

A skill gets retired. Its bundle is marked deprecated in the registry. Existing consumers keep running; new installs are warned. After a grace period, the bundle is delisted but archived for audit purposes.

That is the lifecycle. It is what every other production artifact already gets. Skills are not getting any of it today.

---

## 2. What features a framework needs to support that

Working backward from the lifecycle, the framework's required capabilities cluster into six groups.

**Authoring.** A scaffold command. An AI-assist authoring path (skill-creator agent). Edit-time linting in the IDE — not just at save, on every keystroke for the description field where trigger quality matters. An archetype prompt (which of the five interaction patterns is this? — generative, dispatch, analytical, reasoning, classification) so the downstream tooling knows what kind of skill it's dealing with.

**Compile and structural validation.** Parse frontmatter, validate against the public spec (agentskills.io), structural lints (bundled-asset-path-resolution, fixtures-loader-contract, output-contract well-formedness), trigger-quality heuristic. Fast — under a second. Emit a machine-readable report so CI can consume it.

**Behavioral evaluation.** A corpus format (JSON, single file per suite). Cases with prompt + expected_output + assertions. A judge that scores assertions (deterministic heuristic for CI smoke, LLM-as-judge for real scoring). Model pinning so eval runs are reproducible. Snapshot baselines for regression compare. A report machine-readable enough for branch-protection checks to gate on.

**Governance.** A strictness rung declaration (local / team / org / regulated) so the framework knows how much certification work to do. Risk identification mapped to standard taxonomies (NIST AI RMF, Credo UCF, IBM Granite Guardian). A `PolicyManifest` linking identified risks to runtime hook configurations. Compliance classification (AUTOMATED / PARTIAL / MANUAL) per dimension. All artifacts signed and bundled with the skill.

**Publishing and distribution.** A signed, content-addressed bundle format. A marketplace or registry to push to (stock Claude Code marketplace at minimum; OCI registry for broader interop; Git-backed registries for org-internal). A lockfile so `install` is deterministic.

**Runtime and observability.** Adapter abstraction so the same skill runs in Claude Code, MCP server, LangGraph node, Cursor extension, Bolt embed, custom agent host. Hook-based instrumentation that emits audit JSONL with model version, prompt hash, hook outcome, latency, token count, cost. OTel trace export for SRE consumption. Cost telemetry for FinOps. Model-upgrade detection that triggers re-evaluation.

**Lifecycle integrations.** IDE plugins (Cursor, VS Code, Bolt) that surface the framework's commands in the developer's existing workflow. CI integrations (GitHub Actions, GitLab CI, generic CLI for Jenkins/Buildkite) that run the lifecycle headlessly with structured output. Pre-commit hooks for the fast checks. Branch-protection checks for the slow ones. Scheduled re-eval jobs for model-upgrade regression detection. Webhook integrations for registry events (publish, deprecate, retract).

That is the surface area. No single existing tool covers it.

---

## 3. What Bulbasaur has, what Mellea has, what is missing

A capability-by-capability matrix. ✓ shipped, ◐ partial or planned, ✗ absent. The "Gap" column is what needs to be built even taking both libraries together.

### Authoring

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| CLI scaffold | ✓ `bbsctl new` | ◐ via `/mellea-fy` (requires Claude Code) | Consolidate behind one entry point |
| AI-assist authoring (skill-creator agent) | ◐ planned `bbsctl author` | ◐ via Claude Code slash command | **Build cross-IDE authoring surface** |
| Archetype tagging | ✗ | ✓ five archetypes in `classification.json` | Surface Mellea's archetypes in Bulbasaur authoring |
| Edit-time linting (IDE) | ✗ | ✗ | **Build IDE plugin** |

### Compile and structural validation

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Frontmatter parse + spec validate | ✓ | ✓ (re-parses) | Consolidate — one source of truth |
| Structural lints | ◐ 3 validators | ✓ 16 lints (2 Python, 14 LLM) | Merge lint sets behind one runner |
| Typed IR emission | ✗ | ✓ 6 JSON IRs | Adopt Mellea's IRs as the canonical IR |
| Compile report (machine-readable) | ✓ `dist/compile-report.json` | ◐ no standard report | Standardize on Bulbasaur format |

### Behavioral evaluation

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Corpus format | ✓ `evals/*.json` with assertions | ✗ (fixtures are smoke-check only) | Adopt Bulbasaur's corpus across both |
| Case schema (id, prompt, expected_output, files, assertions) | ✓ | ✗ | Adopt across both |
| `Evaluator` Strategy + Factory (per-suite-name plug-in) | ✓ `behavior` registered; fallback for unknown suites | ✗ | Add `TriggerEvaluator`, `InjectionEvaluator`, `RegressionEvaluator` |
| `Judge` Strategy + Factory | ✓ `HeuristicJudge` | ✗ | Add `LLMJudge` |
| Judge (heuristic, deterministic, no API key) | ✓ keyword overlap with stopwords, threshold 0.5 | ✗ | None |
| Judge (LLM-as-judge) | ◐ planned `LLMJudge` | ✗ | **Wire LLM judge against Claude Agent SDK** |
| Eval modes — SMOKE (one case / suite) | ✓ | ✗ | None |
| Eval modes — FAST (every case) | ✓ default | ✗ | None |
| Eval modes — FULL (FAST + regression compare) | ◐ stub (currently identical to FAST) | ✗ | **Wire RegressionEvaluator behind FULL** |
| CLI filter flags (`--suite NAME`, `--case ID`) | ✓ for fast iteration | ✗ | None |
| Per-case `actual_output` + duration + runtime_error capture | ✓ | ✗ | None |
| Case score = fraction of assertions passing; suite score = mean | ✓ | ✗ | None |
| Machine-readable report (`--output json`) | ✓ structured `EvalReport` | ✗ | None |
| Exit-code convention (0 pass · 1 case-fail · 2 framework-error) | ✓ | ✗ | None |
| Load-error contract (`EvalLoadError` → `FrameworkError` shape) | ✓ structured fix lines | ✗ | None |
| Reference corpus (hello-skill + mq-executor patterns) | ✓ `reference-plugins/hello-skill/evals/behavior.json` | ✗ | Add per-archetype reference corpus |
| Model pinning for reproducibility | ✗ | ◐ runtime defaults | **Build reproducible eval runner** |
| Eval-result caching by (model, corpus_hash, judge) | ✗ | ✗ | **Build cache layer** |
| Snapshot baselines + regression compare | ◐ planned | ✗ | **Build snapshot manager** |
| Judge calibration (precision/recall vs human) | ✗ | ✗ | **Build calibration corpus and harness** |
| Permission-denial assertions (deterministic, audit-driven) | ✗ (designed in `docs/permissions.md`) | ✗ | **Add `permission_assertions` to case schema** |

### Governance and certification

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Strictness rung declaration | ✓ `skill.yaml` | ✗ | None |
| Risk identification (Nexus-style) | ✗ | ✓ | None |
| PolicyManifest data model | ✗ | ✓ | None |
| NIST AI RMF mapping | ✗ | ✓ static YAML | Ground-truth validation (open question) |
| Credo UCF mapping | ✗ | ✓ static YAML | Ground-truth validation (open question) |
| Compliance classification | ✗ | ✓ AUTOMATED/PARTIAL/MANUAL | None |
| Certification report | ✗ | ✓ | None |

### Publishing and distribution

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Marketplace bundle (Claude Code-compatible) | ✓ `claude-code-local` | ✗ | None |
| Marketplace bundle (Claude Code remote) | ◐ planned | ✗ | **Wire it** |
| MCP Composer publish target | ◐ planned | ✗ via `export --target mcp` | **Reconcile** |
| OCI registry publish target | ◐ planned | ✗ | **Wire it** |
| Sigstore signing | ◐ planned at `org+` | ✗ | **Implement signing in publish pipeline** |
| Content-addressed lockfile | ✓ `skills.lock` | ✗ | Extend `skills.lock` to bundle digests |
| Bundle re-emission with cert artifacts | ✗ | ✗ | **Build bundle update protocol** |

### Runtime and observability

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| `AgentRuntime` interface | ✓ ABC + mock | ✗ | None |
| Claude Agent SDK adapter | ◐ planned Phase 4 | ✗ | **Build adapter** |
| Claude Code adapter | ◐ planned Phase 4 | ◐ via export | Reconcile and build |
| MCP server adapter | ◐ planned Phase 6 | ◐ via export | **Build native adapter** |
| LangGraph adapter | ◐ planned Phase 6 | ◐ via export | **Build native adapter** |
| Cursor adapter | ✗ | ✗ | **Build adapter** |
| Bolt adapter | ✗ | ✗ | **Build adapter** |
| Hook-based instrumentation | ✗ | ✓ | Adopt Mellea's hook system across adapters |
| Audit JSONL emission | ✗ | ✓ | Standardize schema |
| OTel trace export | ◐ planned | ◐ | **Wire it** |
| Cost telemetry | ◐ planned | ◐ | **Wire it** |
| Model-upgrade regression detector | ✗ | ✗ | **Build scheduled re-eval job** |

### Lifecycle integrations

| Capability | Bulbasaur | Mellea | Gap to close |
|---|---|---|---|
| Cursor extension | ✗ | ✗ | **Build it** |
| Bolt template / integration | ✗ | ✗ | **Build it** |
| Claude Code plugin (skill-authoring) | ◐ via marketplace | ✗ | **Build authoring plugin** |
| VS Code extension | ✗ | ✗ | **Build it** |
| GitHub Action | ✗ | ✗ | **Build it** |
| GitLab CI template | ✗ | ✗ | **Build it** |
| Pre-commit hook | ✗ | ✗ | **Build it** |
| Branch-protection check | ✗ | ✗ | **Build it** |
| Webhook / registry-event integration | ✗ | ✗ | **Build it** |

### The score

- **Bulbasaur covers** authoring (CLI), structural compile, behavioral eval, marketplace publish to Claude Code, the strictness ladder, and the FrameworkError/vapor-options engineering discipline.
- **Mellea covers** typed IR decomposition, formal governance mapping, certification, and hook-based runtime instrumentation with audit JSONL.
- **Both gap** on IDE integrations, CI/CD integrations, signed bundle distribution beyond Claude Code, judge calibration, reproducible model-pinned eval, and cross-runtime adapter breadth.

The two libraries together cover roughly 60% of what the lifecycle needs. The remaining 40% is what to build.

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

## 5. What this looks like in practice

### A developer in Cursor

The developer opens a project. The Cursor extension detects `SKILL.md` files and lights up. The sidebar shows the skill's strictness rung, the last eval score, the certification status. The developer edits the description. The extension shows a real-time trigger-quality score. The developer clicks "Run eval" — the extension runs `skillops eval` headlessly, streams the case-by-case output back to the panel. A failing case is clickable; the actual output shows next to the expected output. The developer commits. The pre-commit hook runs the fast checks. The PR opens. CI runs `skillops run`. The PR check page shows seven status lines, one per lifecycle stage. The developer merges. The publish pipeline pushes the signed bundle to the org's OCI registry. A consumer in another repo runs `skillops install` and the same bundle lands by digest.

### A platform team in CI/CD

A platform team adopts `skillops-action@v1` across every repo that ships a skill. They configure branch protection to require the eval and certify checks. They wire the scheduled re-eval job to run nightly against the latest model release. They wire the audit JSONL stream from production runtimes into their existing SIEM. The team has end-to-end skill governance with no custom code — three configuration files and one GitHub Action.

### A regulated business unit

A regulated BU sets strictness to `regulated` in `skill.yaml`. The lifecycle now requires named approvers on the PR, pinned eval corpora (the corpus hash is recorded in `skill.yaml`), 7-year audit retention, regulatory sign-off attached to the certification report. The publish pipeline refuses to upload until all gates pass. The bundle, once published, is immutable; any change requires a new version and a new certification run. The audit JSONL stream is signed and exported to the BU's compliance system on a SLA-bound schedule.

Same framework, same CLI, same IDE integrations. The strictness rung is the dial.

---

## 6. Roadmap — what to build first

**Phase 1 (4–6 weeks). Orchestration + CI.** Ship `skillops` CLI as a thin wrapper. Ship the GitHub Action. Ship the pre-commit hook. Ship the documentation. Outcome: a developer can adopt the lifecycle from any GitHub-hosted repo with three lines of YAML.

**Phase 2 (4–6 weeks). IDE + reproducibility.** Ship the Cursor extension. Ship the reproducible eval runner with caching. Ship OCI bundle registry support. Outcome: the lifecycle is usable in the developer's primary editing surface, and eval runs are reproducible across machines and time.

**Phase 3 (4–6 weeks). Distribution + observability.** Ship the Bolt integration template. Ship the branch-protection check. Ship Sigstore signing in the publish pipeline. Wire the audit JSONL schema across runtime adapters. Outcome: the lifecycle is governed end-to-end at the `org` rung with signed artifacts and standardized observability.

**Phase 4 (ongoing). Calibration + ground-truth.** Seed the judge calibration corpus with human-reviewed labels. Begin the regulatory-partner work on NIST/Credo ground-truth validation. Outcome: the framework's claims about behavior and compliance can be audited.

Roughly 12–18 weeks to a usable Phase 3 release across two or three engineers. The two libraries that already exist do the heavy lifting; `skillops` is the glue.

---

## 7. What this gets the world

- A developer can ship a skill with the same disciplines they ship a microservice with: commit hooks, PR checks, signed artifacts, model-pinned reproducibility, audit trail.
- An organization can require those disciplines through branch protection and registry policy — no custom code per repo.
- A regulated business unit can run the same flow with strict gates and pinned corpora — no fork of the toolchain.
- An agent host (Cursor, Bolt, Claude Code, custom) can consume signed bundles by digest, run them under instrumented hooks, and emit audit evidence its customer's compliance team can use.

None of that exists today end-to-end. Two of the three components do. The third — `skillops` — is the thing to build.

---

### References

- Bulbasaur Skill CLI — [`README.md`](../README.md), [`docs/strictness-levels.md`](strictness-levels.md), [`docs/evaluation.md`](evaluation.md)- Mellea Skills Compiler — `README.md`, `FAQ.md`, `src/mellea_skills_compiler/cli.py`, `src/mellea_skills_compiler/certification/data/`, `src/mellea_skills_compiler/export/targets/`
- agentskills.io specification — [agentskills.io/specification](https://agentskills.io/specification)
- NIST AI RMF 1.0 — [NIST.AI.100-1](https://www.nist.gov/itl/ai-risk-management-framework)
- IBM Granite Guardian model card
- Credo AI Unified Control Framework
- OCI Artifacts specification
- Sigstore — [sigstore.dev](https://www.sigstore.dev)
