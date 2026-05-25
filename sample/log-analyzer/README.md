# log-analyzer (reference plugin)

A `team`-strictness demo skill that analyzes application logs to identify errors, patterns, and anomalies. Used as the primary skill in the `bbsctl` demo walkthrough.

Demonstrates:

- A realistic, filled-in `SKILL.md` with all sections populated
- Guardrails that include credential detection and redaction
- An eval corpus (`evals/behavior.json`) with positive, anomaly, and security cases
- Edge case handling for real-world log analysis scenarios

## Try it

```bash
bbsctl compile reference-plugins/log-analyzer
bbsctl run reference-plugins/log-analyzer
bbsctl eval reference-plugins/log-analyzer
```
