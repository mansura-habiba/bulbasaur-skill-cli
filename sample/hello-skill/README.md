# hello-skill (reference plugin)

The minimal `local`-strictness skill. Four lines of `SKILL.md`. Demonstrates the framework's smallest viable shape.

This is a *copy* of `quickstart/hello-skill/SKILL.md`. The duplication is intentional:

- `quickstart/hello-skill/` is what the quickstart docs reference. It is the file the CI smoke test (`quickstart/ci.sh`) reads. It must stay simple and frozen.
- `reference-plugins/hello-skill/` is the cataloged reference plugin that lives alongside future reference plugins (cloud-migration-planner, incident-triage, etc.) per the build-plan §2 repo layout.

Both files are identical today. If they drift, the quickstart copy is authoritative.

## Try it

```bash
bbsctl compile reference-plugins/hello-skill
bbsctl run reference-plugins/hello-skill
```
