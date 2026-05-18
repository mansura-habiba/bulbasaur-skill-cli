# Recipe: share a skill with your team

> **Status:** Placeholder — full recipe lands in Phase 2.
> See [`strictness-levels.md`](../strictness-levels.md) for the strictness ladder this recipe walks.

This recipe will walk a developer through promoting a `local`-strictness skill to `team` strictness and sharing it through a lightweight Git-backed marketplace.

## What this recipe will cover

When written, the recipe ships:

1. **Climb to `team` strictness.** `bbsctl strictness team` (Phase 2 command) walks through generating `skill.yaml`, prompts for an optional ownership stub, and runs the fast validator suite.
2. **Stand up a team marketplace.** `bbsctl marketplace init ./my-team-marketplace` creates a Git-backed marketplace directory with `.claude-plugin/marketplace.json`.
3. **Publish to the team marketplace.** `bbsctl publish <skill> --target claude-code-remote --marketplace <repo>` (Phase 2 target) pushes a signed bundle.
4. **Teammates install.** `bbsctl install <skill>@<marketplace>` resolves and installs into a teammate's `skills.lock`.
5. **Stock Claude Code consumption.** Teammates run `/plugin marketplace add <repo>` and `/plugin install <skill>@<marketplace>` from inside Claude Code.

## What works today

The `claude-code-local` target (Phase 1, available now) gets you halfway: a developer can publish to a local directory, commit it to a shared Git repo, and teammates can `git clone` and run `/plugin marketplace add ./<local-clone>` to use the skill.

See [`docs/quickstart.md`](../quickstart.md) for the Phase 1 publish flow.

## When this doc lands

Phase 2 Sprint 5 per the build plan — when `bbsctl strictness team` and the `claude-code-remote` target ship.
