# Friction audit

A per-phase checkpoint the team runs as new users of the framework. The DX charter (framework-build-plan.md §0) treats friction as the framework's top operational risk; the audit is the mechanism for keeping it visible.

## When to run

At the close of every phase, before declaring the phase complete. Also opportunistically when a developer reports a "rough edge" that isn't quite a bug.

A phase does not close until ≥ 80% of audit-raised issues are resolved or explicitly deferred with rationale (per the DX charter success metric).

## Who runs it

- **The DX owner** facilitates.
- **At least three developers** who have not implemented this phase's code (ideally one external to the team) act as the new-user subjects.
- **The framework lead** signs off on the resulting issue list.

## The protocol

1. **Reset the developer's environment.** Fresh shell, no pre-installed framework. They run from the public quickstart (`docs/quickstart.md`) verbatim.
2. **Observe, do not coach.** The DX owner watches over their shoulder (or a screen share). Every time the developer hesitates, swears, opens docs, or types something the docs did not say to type — note it.
3. **Time the milestones.** Record wall-clock for: `pip install` to running skill (target ≤ 5 min); `bbsctl new` to first compile (target ≤ 30 s); errors-to-resolution (qualitative — how long does it take to recover from a typo?).
4. **Catalog every friction point.** A "friction point" is anything that interrupts the developer's flow. Examples: a confusing error message, a missing doc, a command that doesn't work as advertised, an unexpected prompt, a slow step.
5. **Categorize.** Per friction point, classify as: `blocker` (developer cannot proceed), `severe` (developer recovers but with significant time loss or confusion), `papercut` (minor annoyance).
6. **File issues.** Every friction point gets a GitHub issue with `friction-audit` label, the phase tag, and the developer who reported it. Blockers and severe items are P0/P1 respectively.
7. **Close the loop.** Before the phase closes, the team triages the issues. ≥ 80% are resolved or explicitly deferred. The triage decisions go into the phase retrospective.

## What to look for

This is not exhaustive — surface anything that interrupts flow. But these are categories that have consistently surfaced friction in similar frameworks:

### Installation friction
- Does `pip install` work in under 30 seconds? Does `uv add` work? Does `uvx` work?
- Does the install document any prerequisites (Python version, OS-specific deps) clearly?
- Is the first error after a botched install actionable?

### CLI friction
- Does `bbsctl --help` give the developer enough to proceed? Or do they go straight to docs?
- Do command names match developer expectations (compile, run, publish — yes; transmogrify — no)?
- Are `--help` outputs scannable? Can a developer find the right flag in under 10 seconds?

### Error-message friction
- Every error has `ERROR:`, `Detail:`, `Fix:`, `Docs:` lines. Did each error actually fix the problem when the developer applied it?
- Did the error blame the user gracefully or sound accusatory?
- Did the error explain the *why*, not just the *what*?

### Documentation friction
- Did the developer find the doc they needed in the first place they looked?
- Did the docs match what the code actually does?
- Did the docs have stale examples? (CI tests should catch these but humans surface gaps tests miss.)
- Is the strictness-level explanation clear? Does the developer understand the trade-off?

### Conceptual friction
- Did the developer understand the difference between strictness and trust tier?
- Did they understand the difference between skill, plugin, marketplace?
- Did the docs introduce concepts before relying on them? (Or did "see the manifest" appear before "what is a manifest"?)

### Demo-path friction
- Did `bbsctl publish` produce a Claude Code marketplace that actually loaded?
- Did the printed next-steps work verbatim?
- Did `claude plugin validate` accept the output without complaint?

## The audit report template

The output of every audit is a short report committed to `docs/audits/phase-N.md`:

```markdown
# Friction audit — Phase N

**Date:** YYYY-MM-DD
**Facilitator:** <DX owner>
**Subjects:** <list of developers>

## Timings observed
- Fresh install to running skill: <range>
- bbsctl new to first compile: <range>
- (other milestones)

## Issues raised
<table of issue number, severity, summary, status>

## Patterns
<2-3 paragraphs noting recurring friction categories>

## Recommendations
<concrete actions the team will take before the phase closes>

## Outstanding (deferred to next phase)
<issues that the team is consciously choosing not to fix in this phase>
```

## Avoiding theatre

A friction audit is not theatre if and only if:

- The subjects are unbiased (have not built the code).
- The DX owner has independent authority to block the phase close (per the build plan: "the DX owner has independent veto power on releases that regress the success metrics").
- The issues raised are filed publicly, not buried.
- Deferral requires written rationale, not just "we'll do it later."

If any of these slips, the audit becomes a ceremony and friction goes uncaught. The audit's purpose is to surface what the team has stopped seeing because they built it.

## Connection to other practices

- The DX charter (framework-build-plan.md §0) defines the measurable gates.
- The error-message contract test (`skillctl/tests/test_error_contract.py`) catches the lowest-cost regressions automatically.
- The quickstart smoke test (`quickstart/ci.sh` + `.github/workflows/quickstart-smoke.yml`) catches the timing regressions automatically.
- The friction audit catches everything the automated tests cannot.

Together they are the three layers of the DX safety net.
