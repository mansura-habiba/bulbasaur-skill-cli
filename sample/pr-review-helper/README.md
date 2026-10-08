# pr-review-helper (sample skill)

The repository's first `team`-strictness reference skill. Demonstrates the
enterprise overlay files that `local`-strictness examples (`hello-skill`,
`log-analyzer`) do not include.

Demonstrates:

- `skill.yaml` — strictness declaration, ownership metadata, risk classification
- `permissions.yaml` — explicit deny-all for shell commands and HTTP
- `evals/behavior.json` — behavioral eval corpus with auth-risk and deployment-risk cases

## Try it

```bash
bbsctl compile sample/pr-review-helper
bbsctl eval    sample/pr-review-helper
```
