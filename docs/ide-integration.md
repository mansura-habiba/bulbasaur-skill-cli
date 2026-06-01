# IDE integration design

How `bbsctl` integrates with Cursor, VS Code, Claude Code, Bolt, and other developer environments. The design is layered: one universal surface (MCP), one universal-but-different surface (LSP), and per-IDE extensions where the universal surfaces are not enough.

---

## 1. The integration model

A skill author works inside an editor. They are writing `SKILL.md`, `skill.yaml`, `permissions.yaml`, an `evals/behavior.json` corpus, and possibly references. They want the same loop as for any other code:

- **As they type** — diagnostics inline (trigger heuristic flags a vague description; permissions YAML schema lints; the eval corpus's JSON validates).
- **On save** — quick checks run automatically (fast validate, compile).
- **On demand** — heavier actions run via a command palette (run eval, publish, sign, init permissions, certify with Mellea).
- **In context** — when authoring a permission rule the editor knows which commands appear in the skill body and can autocomplete them.

`bbsctl` ships as a CLI. To plug it into an editor, two universal protocols cover ~80% of IDEs and ~95% of the developer surface; native extensions cover the last mile.

### The three integration surfaces

| Surface | Protocol | Covered IDEs | Use case |
|---|---|---|---|
| MCP server (`bbsctl mcp`) | Model Context Protocol | Cursor, Claude Code, Claude Desktop, Continue, Cline, any MCP host | Action-shaped operations: validate, eval, publish, init-permissions |
| LSP server (`bbsctl lsp`) | Language Server Protocol | VS Code, Cursor, IntelliJ (via plugin), Neovim, Vim, Emacs, Helix, Zed | Editor-feedback-shaped: diagnostics, hover, completion, code actions |
| Native extension | IDE-specific API | Cursor sidebar panel, VS Code activity bar, Claude Code plugin | Rich UX: eval result panel, snapshot diff viewer, marketplace browser |

Most IDEs cover both protocols. Cursor speaks MCP and LSP. VS Code speaks LSP and (via extensions) MCP. Claude Code speaks MCP natively. Bolt has a different model — it's browser-based — so the integration there is a project template that pre-wires `bbsctl` and ships the bundle to a registry on save.

---

## 2. The MCP server — `bbsctl mcp`

`bbsctl mcp` starts an MCP server over stdio. The host (Cursor, Claude Code, Claude Desktop) connects to it; the host's AI agent can then invoke `bbsctl`'s lifecycle operations as tools.

### Tools the server exposes

| Tool | What it does | Inputs | Output |
|---|---|---|---|
| `skill_new` | Scaffold a new skill | `name`, optional `strictness`, optional `directory` | path of created SKILL.md |
| `skill_compile` | Run the compile pipeline | `skill_dir` | `compile-report.json` |
| `skill_validate` | Run `bbsctl validate --fast` | `skill_dir`, optional `strictness` | `validate-report.json` with errors/warnings |
| `skill_eval` | Run `bbsctl eval` | `skill_dir`, optional `suite`, optional `case`, optional `runtime_model`, optional `judge_*` | `eval-report.json` |
| `skill_eval_snapshot` | Write regression baseline | `skill_dir`, `suite` | snapshot path |
| `skill_publish` | Publish to marketplace | `skill_dir`, `marketplace` path, optional `target` | bundle path + signature |
| `skill_install` | Install from marketplace | `bundle_or_spec` | install cache path |
| `permissions_init` | Generate `permissions.yaml` skeleton | `skill_dir`, optional `archetype` | path of created file |
| `permissions_check` | Dry-run a command/URL through the rules | `skill_dir`, `op_type`, `op_value` | Decision + rule_id + reason |
| `injection_corpus_init` | Drop default injection corpus | `skill_dir` | path |
| `bundle_verify` | Verify a published bundle's signature + lock | `bundle_path` | ok + errors |
| `config_show` | Show the resolved config cascade | optional `skill_dir` | resolved config dict |

Each tool is a thin wrapper over the existing CLI subcommand. Returned JSON matches the CLI's `--output json` format so the agent can reason about the result the same way a CI step would.

### Why MCP works for the AI surface

The developer is working with Claude (or another model) in the IDE. The model wants to *do* things: scaffold this skill, run this eval, fix this validation error. MCP gives the model a tool it can invoke. The user does not need to know which CLI command to type; they ask the agent and the agent calls the tool.

A typical flow in Cursor with the agent:

> "Add a kubernetes-restart skill in this repo and write an eval corpus that checks it refuses to touch kube-system."

The agent calls `skill_new`, then writes the SKILL.md and permissions.yaml content directly, then calls `skill_validate` and `skill_eval` to verify. The developer reviews the diff. No CLI invocation by hand.

### What MCP cannot do

MCP is action-shaped, not editor-shaped. It cannot:

- Highlight a problem at the line where it occurred while the user types.
- Hover-show the resolved permission for a command the user just wrote.
- Autocomplete a permission pattern based on the commands present in the skill body.

For those, LSP.

---

## 3. The LSP server — `bbsctl lsp`

`bbsctl lsp` starts a language server over stdio. The editor's LSP client connects and consumes:

### Diagnostics (inline errors and warnings)

- `SKILL.md` description fails trigger-quality heuristics → warning at the description line.
- `permissions.yaml` rule has a syntactic regex error → error at the rule's line.
- `permissions.yaml` allow rule widens the org default → warning at the rule's line.
- `evals/*.json` schema violations → error at the offending key.
- `evals/behavior.json` references a skill name that doesn't match `SKILL.md` → warning.
- A shell command in the SKILL.md body matches no `permissions.yaml` allow rule → warning at that line.
- `ownership.yaml` missing required fields at the declared strictness → error.

Diagnostics refresh on every save (or on every keystroke for the description field, which is the cheapest validation).

### Hover

- Hover a shell command in the SKILL.md body → show the matching `permissions.yaml` rule and verdict.
- Hover a permission pattern → show the rule's reason + which other commands in the body match it.
- Hover a strictness rung → show what that rung requires.

### Completion

- Inside `permissions.yaml` `commands.allow` — suggest patterns derived from commands present in the skill body.
- Inside `evals/behavior.json` — suggest assertions phrased like passing assertions from other cases.
- Inside `skill.yaml` `strictness:` — show the four valid values with their requirement summaries.
- Inside `permissions.yaml` `mcp_tools.allow` — list MCP tools declared by installed MCP servers (resolved from project config).

### Code actions

- "Add allow rule for this command" — generates an anchored regex for the command the cursor is on.
- "Add this case to evals/behavior.json" — when the cursor is on a `Reply with:` directive in the skill body.
- "Bump strictness to team" — runs `bbsctl strictness team` and shows the resulting diff.
- "Generate ownership.yaml" — scaffolds the file from the user's git identity + repo URL.

### Why LSP for the editor surface

LSP is the universal contract every modern editor speaks. One server, every editor. Diagnostics happen at the speed of typing because the server holds state in-process; no spawn cost per check.

---

## 4. Per-IDE integration

### Cursor

Cursor speaks both MCP and LSP. The integration ships as:

1. **An MCP server entry** — the user adds `bbsctl mcp` to their Cursor settings; the chat panel's agent gets the toolset above.
2. **An LSP-backed VS Code extension** — Cursor runs VS Code extensions, so the same extension that lights up VS Code lights up Cursor.

The Cursor-specific UX win is its sidebar agent panel — once `bbsctl mcp` is registered, the developer asks the agent to "run the eval" and the agent surfaces results inline. No menu navigation.

### VS Code

Native LSP via a VS Code extension (`vscode-bbsctl`). The extension:

- Activates on `SKILL.md`, `skill.yaml`, `permissions.yaml`, `ownership.yaml`, `evals/**/*.json`.
- Spawns `bbsctl lsp` as a child process.
- Adds an "Eval" command palette entry that calls `bbsctl eval` and renders the report in a webview.
- Adds a status bar item showing the current skill's strictness rung and last eval score.
- Hosts the MCP server entry for VS Code's MCP-enabled agent extensions (Continue, Cline).

### Claude Code

Claude Code already speaks the marketplace protocol natively. Two integrations:

1. **A skill-authoring plugin** published to the Claude Code marketplace. Activates whenever the developer opens a directory containing `SKILL.md`. Provides slash commands: `/skill validate`, `/skill eval`, `/skill publish`. Reuses the existing Claude Code plugin format — zero patches to Claude Code itself.
2. **MCP server registration** — same `bbsctl mcp` as above. Claude Code is an MCP host; the integration is one config line.

### Bolt

Bolt is browser-based — the developer is not editing files on their machine, they are editing in StackBlitz's WebContainer. The integration model is different:

1. **A Bolt template** — `bolt.new/templates/bbsctl-skill` (a generated link). Bootstraps a skill repository with `bbsctl` pre-wired (lockfile, eval.config.yaml, evals/, sample SKILL.md).
2. **An eval-runner on save** — Bolt runs `bbsctl eval --output json` after every save and displays the report in a panel below the editor. The mock runtime + heuristic judge are the default since Bolt has no API key context.
3. **Publish-to-registry button** — Bolt projects can be exported as a signed bundle and pushed to a configured OCI registry. The publish target uses the user-level config from `~/.bbsctl/config.yaml` baked into the Bolt project via environment variables.

The Bolt model is less rich than Cursor's, but it covers the "browser-only" developer who wants to try authoring a skill without installing anything.

### IntelliJ / JetBrains

LSP via the JetBrains LSP API (Ultimate edition). The same `bbsctl lsp` server backs the diagnostic experience. Code actions surface through JetBrains' intentions menu.

### Neovim, Vim, Emacs, Zed, Helix

LSP via each editor's LSP client. No editor-specific code; `bbsctl lsp` is sufficient.

---

## 5. The configuration model

Every IDE integration consumes the same configuration cascade documented in [`docs/configuration.md`](configuration.md). The LSP server picks up the user's `~/.config/bbsctl/config.yaml` and uses those defaults for diagnostics; the MCP server's `skill_eval` tool reads CLI-equivalent overrides from its tool inputs and falls back to the cascade.

This means a platform team can:

- Set `judge_backend: ollama` and `judge_model: llama3:8b` in `/etc/bbsctl/config.yaml`.
- Every developer's IDE — Cursor, VS Code, Claude Code, JetBrains — runs evals against the same backend automatically, without per-repo configuration.
- A developer who wants to try Anthropic for a quick experiment overrides via `BBSCTL_JUDGE_BACKEND=anthropic` in their shell or `--judge-backend anthropic` in a one-off CLI invocation. The IDE picks up the override on the next `bbsctl eval`.

The IDE integration does not add new configuration; it consumes the cascade everything else uses.

---

## 6. Roadmap — what to build first

Phased so each phase delivers something a developer can use end-to-end.

### Phase A — universal foundation (4 weeks)

- `bbsctl mcp` MCP server with the 12 tools above. Stdio transport.
- `bbsctl lsp` LSP server with: diagnostics for the four file types, hover for permissions, completion for permission patterns.
- Documentation: `docs/ide-integration.md` (this file), `docs/configuration.md`.

Outcome: any MCP host (Cursor, Claude Code, Claude Desktop, Continue) and any LSP-capable editor (VS Code, Neovim, JetBrains via plugin) gets a working integration the day Phase A ships.

### Phase B — Cursor + VS Code extension (3 weeks)

- VS Code extension that bundles the LSP launcher, webview-based eval result viewer, status bar item, and command palette entries.
- Ship the same extension to the Cursor marketplace.
- Add the MCP server registration to the extension's first-run prompt.

Outcome: Cursor + VS Code users get a single-click install that delivers the full inline + on-demand UX.

### Phase C — Claude Code authoring plugin (2 weeks)

- A `skill-authoring` plugin published to Claude Code's marketplace.
- Slash commands: `/skill validate`, `/skill eval`, `/skill publish`.
- Hooks into the existing `bbsctl publish --target claude-code-local` so the plugin can publish skills the developer authored inside Claude Code itself.

Outcome: Claude Code users can author Bulbasaur skills without leaving the editor.

### Phase D — Bolt template + registry (3 weeks)

- A Bolt template (`bolt.new/?bbsctl-skill`).
- Browser-compatible OCI publish path (bundles uploaded directly from the WebContainer via signed credentials in `BBSCTL_PUBLISH_TOKEN`).
- Inline eval-runner that shows the report below the editor.

Outcome: zero-install authoring path. A developer can write a skill in a browser tab and publish it to an OCI registry without ever touching a terminal.

### Phase E — Polish (ongoing)

- IntelliJ plugin wrapping the LSP server (Ultimate-only).
- Snapshot diff viewer in the VS Code extension (regression visualization).
- Marketplace browser in Cursor/VS Code (browse, install, pin versions).
- LSP code actions for "generate skill body from this prompt" via the configured LLM backend.

---

## 7. What this leaves out

- **Live runtime debugging.** The LSP gives you diagnostics for the skill artifact. It does not let you step through an activation. That belongs to the runtime adapter's instrumentation layer (audit JSONL, OTel traces), surfaced separately as a Phase-4 observability tool.
- **Cross-skill collision detection in the editor.** Showing "your trigger collides with `mq-executor`'s trigger" requires querying the registry; the LSP can support it once the registry index is available.
- **Multi-user collaboration on a skill.** Authoring is single-user today. CRDT-based collaboration is a separate concern — Bolt's WebContainer already handles it for the file-editing layer; the LSP server's diagnostic state would need to be made per-session.

These are honest gaps. The integration model above gives a developer the same loop they have for any other production code; closing the remaining gaps is sequenced behind the marketplace adoption and the runtime observability work.

---

## See also

- [`docs/configuration.md`](configuration.md) — the cascade IDE integrations consume
- [`docs/evaluation.md`](evaluation.md) — eval module surface that the MCP `skill_eval` tool wraps
- [`docs/permissions.md`](permissions.md) — permission model the LSP diagnoses against
- [`docs/bbsctl-roadmap.md`](bbsctl-roadmap.md) — phased plan; this doc adds the IDE phases A-E
- Model Context Protocol — [modelcontextprotocol.io](https://modelcontextprotocol.io)
- Language Server Protocol — [microsoft.github.io/language-server-protocol](https://microsoft.github.io/language-server-protocol/)
