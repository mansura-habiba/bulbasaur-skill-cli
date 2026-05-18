# Troubleshooting

Common errors with copy-pasteable fixes. Every framework error is formatted with the Bulbasaur error contract:

```
ERROR: <one-line summary>
  Detail: <what went wrong, where>
  Fix:    <copy-pasteable remediation>
  Docs:   <link to relevant doc>
```

If you hit an error that does not contain a `Fix:` line, that is itself a bug — please file an issue.

## During `bbsctl new`

### `invalid skill name: must be 1-64 chars`

The agentskills.io spec caps names at 64 chars. Trim or pad. See [spec field rules](https://agentskills.io/specification#name-field).

### `invalid skill name: must be lowercase (no uppercase letters)`

Spec rule: names are lowercase kebab-case. `My-Skill` is not valid; `my-skill` is.

### `invalid skill name: must use hyphens, not underscores`

Spec rule: names use `-`, not `_`. `my_skill` is not valid; `my-skill` is.

### `invalid skill name: must not contain consecutive hyphens`

Spec rule: no `--` in names. `pdf--processing` is not valid; `pdf-processing` is.

### `invalid skill name: must not start or end with a hyphen`

Spec rule: no leading or trailing hyphen.

### `refusing to overwrite existing path`

`bbsctl new` will not write into an existing directory. Choose a different name or remove the existing directory first.

## During `bbsctl compile`

### `SKILL.md not found`

You ran `bbsctl compile` outside a skill directory. Either pass the path (`bbsctl compile ./my-skill`) or `cd` into the skill directory first.

### `frontmatter: failed to parse frontmatter as YAML`

The frontmatter is malformed YAML. Most common cause: an unquoted `:` in a value. Example:

```
# Broken:
description: Use when X: do Y
# Fixed (quote the value):
description: "Use when X: do Y"
```

`bbsctl new` always emits safe-quoted YAML via `ruamel.yaml`, so this only happens when hand-editing.

### `description: must be ≤ 1024 chars`

The agentskills.io spec caps descriptions at 1024 characters. Trim, or split the skill into multiple narrower skills.

### `description: must be non-empty`

`description` is required and must contain at least one non-whitespace character.

### `name: must match the parent directory name`

Spec rule: the `name` field in `SKILL.md` must match the directory name. If your directory is `hello-skill/`, the frontmatter must say `name: hello-skill`. Either rename the directory or change the name.

### `frontmatter: SKILL.md must begin with a "---" frontmatter delimiter on line 1`

Add YAML frontmatter at the top of the file:

```yaml
---
name: my-skill
description: What it does and when to use it.
---

Body text here.
```

### `frontmatter: frontmatter block is not closed by a second "---" delimiter`

You opened a `---` but never closed it. The closing delimiter goes after your last YAML key, before the body.

## During `bbsctl run`

### `unknown runtime: <name>`

Phase 1 ships only `--runtime mock`. Real runtime adapters (Claude Agent SDK, MCP, LangGraph) land in Phase 4. Use `--runtime mock` for now.

### Mock agent reply is `(no body content)`

Your skill's body is empty or contains only headings. Add at least one instruction line (e.g. `Reply with: "..."`).

## During `bbsctl publish`

### `unknown publish target`

Phase 1 ships only `--target claude-code-local`. Run `bbsctl publish --help` to see the registered targets.

### `target requires strictness ≥ ...`

Some targets (Phase 2-3) require the skill to be at `org`+ strictness. Either climb the ladder with `bbsctl strictness org` (Phase 2) or pick a target with a lower floor (`--target claude-code-local`).

### `malformed --option value`

`--option` requires the form `key=value`. E.g. `--option marketplace_name=acme`.

## During `claude plugin validate`

If Claude Code's own validator (`claude plugin validate ./bulbasaur-marketplace`) rejects what `bbsctl publish` produced, that is a Bulbasaur bug. Please open an issue with the exact `bbsctl publish` command, the resulting directory, and the validator output.

## Reporting an unhelpful error

The DX charter requires every user-facing error to carry a copy-pasteable `Fix:` line. If you hit an error that does not, file an issue with:

- The full error output.
- The exact command you ran.
- The `SKILL.md` (if relevant).

That counts as a release-blocker bug under our [DX metrics](../framework-build-plan.md#02-the-success-metrics-these-are-gates-not-aspirations).
