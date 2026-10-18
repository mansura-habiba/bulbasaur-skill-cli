# Draft: CUGA upstream contribution (do not open until bbsctl is on PyPI)

## Optional extra (`pyproject.toml`)

```toml
[project.optional-dependencies]
skill-eval = [
  "bbsctl>=0.1.1; python_version>='3.11' and python_version<'3.14'",
]
```

Then `uv lock` at the CUGA repo root.

## Docs (Agent skills section)

Add beside the `npx skills` installer notes:

> **Skill contract evaluation.** CUGA loads `SKILL.md` at runtime. To compile,
> validate, and eval a skill folder before shipping it, install the optional
> `skill-eval` extra (`uv sync --extra skill-eval`) and run `bbsctl compile`
> / `bbsctl validate` / `bbsctl eval` against `.cuga/skills/<name>`. This is
> separate from `cuga evaluate`, which scores agent/API test cases.

## Non-goals for the PR

- Do not change `load_skill` / the skills loader
- Do not vendor bbsctl source
- Do not make bbsctl a core (non-optional) dependency
- Do not replace `cuga evaluate`
