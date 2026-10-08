---
name: pr-review-helper
description: Review pull requests for risky changes, test gaps, and deployment concerns.
allowed-tools: Read
---

## Instructions
1. Read the PR description and changed files.
2. Identify risky changes in auth, config, infra, or migrations.
3. Flag missing tests or rollback concerns.
4. Summarize findings in priority order.

## When to use this skill
- User asks to review a PR
- User asks for risk assessment of code changes

## Guardrails
- Must not approve code automatically
- Must call out uncertainty when files are missing
- Must not invent test results

## Examples
**Input:** Review this PR for production risk
**Output:** High risk: config changes without rollback notes; medium risk: missing tests for auth path
