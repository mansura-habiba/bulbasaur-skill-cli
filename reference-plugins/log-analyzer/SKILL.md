---
name: log-analyzer
description: Analyze application log files to identify errors, warnings, and anomalies. Use when the user asks to investigate logs, find error patterns, or diagnose application issues from log output.
# license: Apache-2.0
# compatibility: Designed for Claude Code (or similar products)
# metadata:
#   author: bulbasaur-team
#   version: 1.0
# allowed-tools: Bash(grep:*) Read
---

## Instructions

1. Read the provided log file or log snippet from the user's input.
2. Parse each log entry and classify by severity: ERROR, WARN, INFO, DEBUG.
3. Group related errors by stack trace or error code to identify distinct issues.
4. For each distinct issue, summarize: what failed, how many times, first and last occurrence.
5. If a pattern suggests a root cause (e.g. connection timeouts preceding crashes), call it out.
6. Present a structured report: critical errors first, then warnings, then anomalies.

## When to use this skill

- User asks to "look at", "analyze", or "investigate" a log file
- User pastes log output and asks "what went wrong?"
- User mentions error spikes, crashes, or application restarts
- User asks to find patterns in log data
- Do NOT activate for metric dashboards or structured query results — those are not logs

## Guardrails

- **Must never:** Modify or delete the original log files
- **Must reject:** Log snippets containing credentials, API keys, or tokens — flag and redact before analysis
- **Must fallback:** If the log format is unrecognized, report "unrecognized format" with a sample line and ask the user to clarify

## Examples

**Input:** "Analyze this log file and tell me why the service keeps crashing"

**Output:** A structured report showing 3 distinct crash patterns: OOM kills at 14:00–14:30 (5 occurrences), connection pool exhaustion at 14:15 (2 occurrences), and an unhandled NullPointerException in PaymentService.process() (1 occurrence). Recommended investigation order: OOM first — it correlates with the connection pool failures.

## Edge cases

- Interleaved logs from multiple services: group by service name before analyzing
- Partial log lines (truncated by buffer): warn the user and skip incomplete entries
- Massive log files (>100MB): suggest filtering by time range or severity before full analysis
