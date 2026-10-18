# Draft: CUGA upstream contribution (do not open until bbsctl is on PyPI)

## Proposal

Make skill-contract evaluation a **CUGA CLI command**, not a “run bbsctl yourself” footnote.

CUGA already has:

| Command | Object |
|---|---|
| `cuga evaluate` | Agent / API test cases (`src/cuga/evaluation`) |
| `load_skill` (runtime) | Loads `SKILL.md` into the agent |

Gap: compile / validate / eval corpora for a skill **folder** before it is loaded.

### Suggested command

```bash
# default: compile + validate against a skill under the configured skills root
cuga skill-eval demo-skill

# explicit path + stage
cuga skill-eval ./path/to/skill --stage compile
cuga skill-eval ./path/to/skill --stage validate
cuga skill-eval ./path/to/skill --stage eval
cuga skill-eval ./path/to/skill --stage all   # compile → validate → eval
```

Naming note: keep **`skill-eval`** as its own verb so it is never confused with **`cuga evaluate`** (agent runs). Pattern matches other Typer groups already on `cuga` (`policy`, `knowledge`, …). If maintainers prefer a group, `cuga skills eval` is fine; same behavior.

### Implementation shape (thin adapter)

1. Optional extra installs PyPI `bbsctl` (same Python marker as today: `>=3.11,<3.14`).
2. New module under `src/cuga/cli/` (e.g. `skill_eval.py`) registered on the root Typer `app`.
3. Resolve skill directory:
   - positional name → `<skills.root>/<name>` (default root `.cuga/skills`)
   - or an absolute/relative path that contains `SKILL.md`
4. Shell out to `bbsctl <stage> <dir>` (public CLI). Do not vendor `skillctl` source.
5. Exit non-zero if bbsctl is missing and print `uv sync --extra skill-eval` (or equivalent).
6. Docs in Agent skills: point at `cuga skill-eval`, and one line that this is **not** `cuga evaluate`.

### Optional extra (`pyproject.toml`)

```toml
[project.optional-dependencies]
skill-eval = [
  "bbsctl>=0.1.1; python_version>='3.11' and python_version<'3.14'",
]
```

Then `uv lock` at the CUGA repo root.

### Docs blurb (Agent skills section)

> **Skill contract evaluation.** After authoring a `SKILL.md` under `.cuga/skills`,
> run `cuga skill-eval <name>` (requires `uv sync --extra skill-eval`) to compile
> and validate the skill folder before `load_skill` uses it at runtime.
> This is separate from `cuga evaluate`, which scores agent/API test cases.

## Non-goals for the PR

- Do not change `load_skill` / the skills loader
- Do not vendor bbsctl source
- Do not make bbsctl a core (non-optional) dependency
- Do not replace or rename `cuga evaluate`
- Do not teach `cuga skill-eval` as “install a skill” (that remains `npx skills` / copy into `.cuga/skills`)
