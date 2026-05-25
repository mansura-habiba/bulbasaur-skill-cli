<!--
This PR template is part of the governance framework. See .governance/README.md.
The CI workflow .github/workflows/governance.yml validates that every section below is populated.
-->

## Task card

**Closes** # <!-- issue number; required -->

**Parent capability:** <!-- e.g. .governance/capabilities/skill-registry.yaml; required -->

## What changed (one line)

<!-- The goal.one_liner from the task card. If this differs from the task card, update the task card first. -->

## Compliance checklist

Run before requesting review. CI will re-run these gates — the human reviewer focuses on judgment, not compliance.

- [ ] Every test in `acceptance.contract_tests` from the task card **passes locally**. Paste output below.
- [ ] Diff touches **no path** in `ai_context.do_not_modify`.
- [ ] No code in this PR implements anything listed in `scope.non_goals`.
- [ ] No dependency added that's in `capability.tasks_must.avoid_dependencies`.
- [ ] `goal.done_looks_like` from the task card is **observably true** with this diff.
- [ ] Task card itself was not modified by this PR (changes to the task card require a separate PR).

### Contract test output

```
$ pytest tests/contract/ -k <test_id>
<paste here>
```

## Scope check

**Did the diff stay within the in-scope list from the task card?**

- [ ] Yes — every changed file maps to an `in_scope` entry.
- [ ] No — see explanation below. If anything is out-of-scope, file a follow-up issue and link it; **do not expand this PR**.

If "no," explain why and link the follow-up issue: <!-- e.g. "Spotted a typo in adjacent file; filed BBS-128, will fix there" -->

## Notes for the reviewer

<!--
What you'd like the human reviewer to focus on. Things compliance gates can't catch:
- Is the architecture choice right for the area?
- Are there edge cases the contract tests don't exercise?
- Does this fit the wider direction in `goal.bigger_picture`?
-->

## AI assistance disclosure

<!--
Honest: where did AI help, and what did you verify yourself?
This is for traceability, not judgment. AI-assisted PRs are fine — silent AI use is not.
-->

- [ ] AI assistant used: <!-- Claude / Copilot / Cursor / none -->
- [ ] I read every line of AI-generated code in this diff before pushing.
- [ ] I ran the contract tests locally; AI did not just claim they pass.
