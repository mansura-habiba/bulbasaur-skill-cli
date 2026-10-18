# Contributing

Thanks for wanting to help. This repo ships **`bbsctl`** (agent skill lifecycle CLI) and is governed with [SDD++](https://github.com/mansura-habiba/sdd-plus-plus). Every change is anchored to a GitHub issue task card before code lands on `main`.

## Where to start (good first issues)

1. Read the roadmap: [`docs/bbsctl-roadmap.md`](docs/bbsctl-roadmap.md).  
   It lists what is already shipped (**✓**), partial (**◐**), and not started (**✗**). Prefer items marked **◐** or small **✗** rows over large P1/P3 epics.
2. Pick a starter issue:  
   [good first issues](https://github.com/mansura-habiba/bulbasaur-skill-cli/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)  
   or [help wanted](https://github.com/mansura-habiba/bulbasaur-skill-cli/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22).
3. If nothing fits, open a **Good first issue** from the [issue templates](https://github.com/mansura-habiba/bulbasaur-skill-cli/issues/new/choose) and link the roadmap row you want to take. Maintainers will confirm scope before you invest a large PR.
4. For any real implementation, also file (or use) a **Task Card** issue. That YAML-shaped body is what CI and AI assistants treat as the contract. See [`.governance/README.md`](.governance/README.md).

**Good first issue shape.** One observable outcome, one area of the tree (`docs/`, a single command, a focused test), no new top-level dependency, and a clear “done looks like” you can demo in under an hour of review.

Examples that usually fit:

- Docs or recipe fixes that match shipped behavior
- A missing test for behavior already documented
- A small compile/validate/eval gap called out as **◐** on the roadmap
- CLI help / error-message clarity (include a friction note in the PR)

Avoid as a first PR: Sigstore/signing, regulated tier, marketplace federation, new runtimes (MCP/LangGraph), or anything that needs a new third-party dependency without discussion.

## Dev setup

```bash
git clone https://github.com/mansura-habiba/bulbasaur-skill-cli.git
cd bulbasaur-skill-cli
make install          # or: cd bbsctl && uv sync
make test             # unit tests in bbsctl/
# contract gates used by governance CI:
cd bbsctl && uv run pytest ../tests/contract/ -q
```

Optional engines (inspect / mellea-certify): see [`docs/recipes/how-to-commands.md`](docs/recipes/how-to-commands.md#models-inspect-vs-mellea-certify) and `bbsctl doctor`.

## Workflow

1. **Issue first.** Comment on an existing task card / good-first-issue, or open one. Branch names like `task/BBS-123` or `docs/…` help CI and humans cross-link.
2. **Read the card.** `AGENTS.md` tells assistants to load the issue body, `required_reading`, and the parent capability under `.governance/capabilities/`.
3. **Stay in scope.** Honor `scope.non_goals` and `ai_context.do_not_modify` on the task card. Expand scope only with a follow-up issue.
4. **PR against `main`.** Use the PR template. Body must include `Closes #<issue>` (required by governance CI).
5. **Prove it.** Paste local contract-test output when the card lists `acceptance.contract_tests`. Prefer `make test` for unit coverage of the area you touched.

`main` is protected: PRs need green governance + pylint checks. The sample `bbsctl-pipeline` workflow runs when `bbsctl/` / `sample/` / `Makefile` change; docs-only PRs do not need that job.

## PR expectations

- **Friction note** if you touch the CLI surface or user-facing errors: walk the flow as a new user and say where you hesitated.
- **No vapor options.** An argparse `choices=` value must work end-to-end (enforced by tests).
- **Small diffs.** Prefer the smallest change that meets the task card’s `goal.done_looks_like`.
- **Do not edit** `.governance/*.schema.yaml` unless the PR is labeled `chore-framework` with approver intent.

## Repo map (short)

| Path | Why it matters |
|---|---|
| `bbsctl/` | Product CLI (`skillctl` module) |
| `docs/bbsctl-roadmap.md` | What to build next |
| `AGENTS.md` + `.governance/` | SDD++ contracts for humans and agents |
| `tests/contract/` | Executable acceptance gates |
| `.github/workflows/governance.yml` | PR compliance bot |

More layout detail: root [`README.md`](README.md#repo-structure-and-why-sdd-is-here).

## Code of conduct / license

Be respectful in issues and reviews. Contributions are under the same [Apache 2.0](LICENSE) license as the project.
