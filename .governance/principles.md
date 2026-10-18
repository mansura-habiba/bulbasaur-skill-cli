# Design principles

Standing principles for this repo. Co-canonical with `.governance/philosophy.md`.

1. **Governance is embedded, not sidecar** — rules and contracts live in-repo and gate CI.
2. **Contracts are executable** — capability specs + contract tests beat prose-only specs.
3. **Authority is bounded** — task cards declare `non_goals` and `do_not_modify` before work.
4. **Evidence is required for trust** — lifecycle claims need digests, manifests, and (later) signatures.
5. **Engines are swappable seams** — lifecycle adapters normalise to `StageResult`; never hard-wire a vendor artifact format into the pipeline core.
6. **Keep the five-minute promise** — base `bbsctl` install stays stdlib + ruamel.yaml; heavy engines stay optional / subprocess.
7. **Mutating operations are idempotent** — derive the desired end state from current inputs; write via temp + `os.replace`; a double-run or mid-crash retry must converge. See `.governance/wiki/idempotency-audit.md`.
