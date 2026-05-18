# Friction audit — Phase 1

**Date:** 2026-05-18
**Facilitator:** DX owner (acting)
**Subjects:** AI agent walking docs/quickstart.md as a fresh user
**Scope:** Phase 1 end-to-end (Sprint 1 + Sprint 2 deliverables)

This is the first audit per the protocol in [`docs/friction-audit.md`](../friction-audit.md). It is not a full audit — it lacks the multiple human subjects the protocol calls for and should be re-run with three real developers before Phase 1 formally closes. It does identify one blocker that must be resolved before any external developer touches the framework, plus five severe items.

## Timings observed

All well under the DX charter budgets. Five-minute promise: not even close to threatened.

| Milestone | Observed | Budget | Margin |
|---|---|---|---|
| `skillctl new` | 70 ms | (no explicit budget) | — |
| `skillctl compile` | 63 ms | (no explicit budget) | — |
| `skillctl run` | 61 ms | (no explicit budget) | — |
| `skillctl publish` | 59 ms | (no explicit budget) | — |
| `claude plugin validate` (stock Claude Code) | 233 ms | — | — |
| End-to-end (new → compile → run → publish → validate) | ~0.5 s | 300 s | 99.8% |

## Issues raised

### Blocker

| # | Severity | Summary | Status |
|---|---|---|---|
| F1 | **Blocker** | PyPI namespace conflict — `skillctl` is already an unrelated tool on PyPI. The documented `uvx skillctl`, `uv add skillctl`, `pip install skillctl` all install the wrong package. | OPEN |

### Severe

| # | Severity | Summary | Status |
|---|---|---|---|
| F2 | Severe | `skillctl new --strictness team` (and `org`, `regulated`) silently accepts the flag and produces a `local` skill. Misleading. | OPEN |
| F3 | Severe | `skillctl compile --strictness org` reports `strictness=org` in the header but runs the same steps as `local` because all current steps register at `local`. Misleading. | OPEN |
| F4 | Severe | README + quickstart link to GitHub URL `bulbasaur/bulbasaur` that does not exist. 404 for any curious reader. | OPEN |
| F5 | Severe | `skillctl publish` to an unwritable output dir emits a raw Python `PermissionError` traceback, bypassing the FrameworkError contract. | OPEN |
| F6 | Severe | Multiple docs link to files that don't exist: `docs/recipes/share-with-team.md`, `docs/recipes/ship-to-org.md`, `docs/design-patterns.md`, `docs/spec-guidelines.md`, `docs/best-practices.md`. | OPEN |

### Papercuts

| # | Severity | Summary | Status |
|---|---|---|---|
| F7 | Papercut | When `parse-frontmatter` fails, `emit-report` still runs and prints `✓ emit-report`. Correct behavior, but the green checkmark next to the red ✗ confuses the eye. | OPEN |
| F8 | Papercut | `reference-plugins/hello-skill/` and `reference-plugins/cloud-migration-planner/` are empty directories — referenced in the build plan as Phase 1 deliverables but not populated. | OPEN |
| F9 | Papercut | `templates/team/`, `templates/org/`, `templates/regulated/` are empty directories — `docs/strictness-levels.md` implies they exist. | OPEN |
| F10 | Papercut | `examples/uv-project/` and `examples/poetry-project/` directories still exist on disk (sandbox couldn't delete them in an earlier turn). Harmless if `git rm` happens before any external publish. | OPEN |

## Patterns

**Pattern 1 — Vapor-options.** Several CLI surfaces advertise capabilities that the underlying implementation does not yet honor: `--strictness {local,team,org,regulated}` choices include three levels with no scaffolding behind them, and `--target` will grow the same problem as Phase 2-3 targets are pre-announced. The pattern: argparse-level choices outrun the implementation, the user gets a successful exit code, the framework's mental model is silently broken. Rule of thumb proposal: a choice value is only added to the CLI when its end-to-end path works.

**Pattern 2 — Missing-docs links.** Six links across README and quickstart point at files that don't exist yet. Each is "a Phase 2 deliverable" in the build plan — none of which is a defense for shipping a 404. Either the link comes out of the doc or a placeholder doc exists at the path. Rule of thumb proposal: every link in a shipped doc must resolve, even if the linked content is a one-paragraph "this lands in Phase N — see issue #X" stub.

**Pattern 3 — Naming-collision risk.** The `skillctl` PyPI conflict is one instance of a broader issue: the framework is choosing names (CLI binary, marketplace identifier, package name) without checking the existing public-namespace state. The `bulbasaur` brand is also unverified. The default marketplace name `bulbasaur-local` may collide with reserved Claude Code marketplace names (the spec reserves several). A namespace audit before any external release is overdue.

**Pattern 4 — FrameworkError contract has uncovered cases.** Filesystem-permission errors during `skillctl publish` bypass the error contract entirely. The lint test catches construction sites, not unhandled exceptions. The contract needs a complementary mechanism that wraps the top of every command function in a try/except that converts unexpected exceptions into the FrameworkError shape.

## What worked well

The audit is not all bad news. Things that held up:

- **Timings.** Every individual step is two orders of magnitude under any plausible DX budget. The five-minute promise has comically large margin.
- **Bad-name errors.** Camel-case, snake-case, leading-hyphen all produce clear, actionable errors with exact `Fix:` lines that match `docs/troubleshooting.md` verbatim. The agentskills.io rule implementation is solid.
- **Stock Claude Code interop.** `claude plugin validate ./bulbasaur-marketplace` returns `✔ Validation passed` on the output of `skillctl publish` — the strongest possible confirmation that the demo adapter is correct.
- **Pure-Python agentskills.io rules.** No `skills-ref` vendoring required, no Node toolchain dependency, no upstream blocker. ADR 0004 is working.
- **Strategy/factory patterns hold up.** Adding the `claude-code-local` publish target was a straightforward extension; the abstraction did not feel like overhead.
- **Error-message contract test.** 100% Fix-line coverage on construction sites today. The mechanism for keeping the metric honest is in place.

## Recommendations (concrete actions before Phase 1 closes)

### Must-fix before any external release

**Action 1 (F1, blocker).** Rename the PyPI package. Recommended sequence:

1. Pick a name that is not on PyPI today. Candidates: `bulbasaur-cli`, `bbsctl`, `bulbasaur-skillctl`.
2. Update `pyproject.toml` `name` field, all docs that say `pip install skillctl` / `uv add skillctl` / `uvx skillctl`, and the GitHub Actions workflow's `SKILLCTL_SRC` references.
3. Keep the binary name `skillctl` (entry point), since that's a local install concern not a PyPI namespace concern. Document explicitly: "package name is X; CLI binary is `skillctl`."
4. New ADR (`docs/adr/0006-pypi-package-name.md`) capturing the decision.

**Action 2 (F2, F3 — severe).** Restrict `--strictness` choices in `skillctl new` and `skillctl compile` to the levels with working scaffolding. Phase 1 = `local` only. When the user passes anything else, produce a clear "Phase N feature; not available in current version" error. Add the other levels back to the choices in the phase that ships them.

**Action 3 (F4 — severe).** Replace the `bulbasaur/bulbasaur` GitHub URL with one of: (a) a real repo URL once the project moves to GitHub, or (b) a placeholder marker like `<repo-url>` until then. Run a sweep across README, all docs, the CLI epilog, and `pyproject.toml`.

**Action 4 (F5 — severe).** Wrap the `main()` entry in `skillctl/cli.py` in a top-level try/except that converts unexpected exceptions into a FrameworkError. The wrapped error should include a short "this is a framework bug" note and the original traceback in a `Detail:` block so we don't lose debugging information. Add a regression test that runs `skillctl publish` against an unwritable directory and asserts a FrameworkError-shaped output, not a Python traceback.

**Action 5 (F6 — severe).** For every link in README and shipped docs that points at a non-existent file, either remove the link or write a one-paragraph placeholder doc at the linked path. Recommended approach: write the placeholders. Each placeholder has the file header, a one-sentence "this is a Phase N deliverable" note, and a link back to the relevant build-plan section.

### Should-fix before Phase 1 retrospective

**Action 6 (F7 — papercut).** Update the `TextReporter` to stop printing `✓` for steps that ran after a `✗` step, when those steps are explicitly downstream (depend on the failed step). The `emit-report` step legitimately ran, but the visual reads as "everything's fine in the end" when it isn't. Two options: print `(degraded)` next to the icon, or suppress the icon and print only the step name when the overall pipeline has failed earlier.

**Action 7 (F8 — papercut).** Populate `reference-plugins/hello-skill/` with the same `SKILL.md` as `quickstart/hello-skill/SKILL.md` (or a symlink). The directory was promised by the build plan and is currently empty.

**Action 8 (F9 — papercut).** Either populate `templates/team/`, `templates/org/`, `templates/regulated/` with at least an empty `.gitkeep` and a `README.md` explaining "Phase N template — placeholder", or remove them until Phase 2 ships their contents.

**Action 9 (F10 — papercut).** `git rm` the empty `examples/uv-project/` and `examples/poetry-project/` directories before any external publish. (The sandbox could not remove them; a developer working outside the sandbox can.)

### Process improvements

**Action 10 — Add a "vapor-options" check.** Pattern 1 deserves an automated check: the CLI argparse choices for `--strictness`, `--target`, `--runtime`, etc. should match the set of implementations actually registered, not the full enum. Either the choices come from `list_targets()` / `list_runtimes()` (already true for `--target` and `--runtime`) or the unsupported choices reject at runtime with a clear "not available yet" message. The lint candidate: a test that walks every argparse `choices=...` and asserts each value is supported.

**Action 11 — Add a "doc-link-resolution" CI check.** Every relative link in `*.md` files must resolve to a file on disk. Run as part of `quickstart-smoke.yml` or a new `docs-lint.yml` workflow. Stops Pattern 2 from re-occurring.

**Action 12 — Run the audit with three real developers before Phase 1 formally closes.** This run had a single AI subject, which is honest but not the protocol. The DX owner schedules a session with three developers (one external to the team per the protocol).

## Outstanding (deferred to Phase 2)

None of the issues from this audit are being deferred. All ten action items are pre-conditions for Phase 1 close.

## Coverage notes (transparency)

What this audit did NOT probe, and should be revisited:

- **Multi-user collaboration flow.** What happens when two developers `skillctl publish` to the same `bulbasaur-marketplace/` directory? Conflict semantics undefined.
- **Re-publish behavior.** What happens to existing files when `skillctl publish` runs a second time? Verified that the directory tolerates pre-existing contents, but didn't verify that updates land in `marketplace.json` cleanly (e.g. updated description).
- **Concurrent operation.** No probing of what happens under concurrent `skillctl compile` invocations in the same directory.
- **Large skills.** All testing used the 4-line hello-skill. Skills near the 500-line body cap and 1024-char description cap may surface different behavior.
- **OS coverage.** Linux only. macOS and Windows surfaces are unaudited (the CI matrix tests them, but a human friction audit on those platforms has not happened).
- **Non-ASCII content.** Skill names are ASCII-only by spec, but descriptions and bodies are not. Unicode behavior untested in the human-flow sense.

These belong on the Phase 2 audit's coverage list.

## Sign-off

| Role | Signature | Date |
|---|---|---|
| DX owner | — | — |
| Framework lead | — | — |

The audit closes when both signatures are recorded and Actions 1–9 are resolved (or formally deferred with rationale per the friction-audit protocol).
