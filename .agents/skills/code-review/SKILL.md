---
name: code-review
description: Review code, pull requests, commits, and local changes for actionable bugs, regressions, and security flaws. Use when the user requests a code review, not for ordinary implementation tasks.
---

# Code Review

Provide an evidence-based review in the user's language, preserving symbol names and file paths exactly.

## Scope

- Read repository instructions and identify the requested files or changes. When reviewing a branch, verify the base branch and the appropriate merge base for comparison.
- If the user does not specify a scope, inspect Git status, staged and unstaged changes, and relevant new files. Ask for clarification only when material ambiguity remains.
- Review without modifying files or publishing comments outside the conversation unless the user requests those actions.

## Inspection

1. Understand the intended behavior from the change description, tests, and existing contracts.
2. Read the diff and surrounding context, then trace affected callers, consumers, and data flows. Do not judge a line in isolation.
3. Inspect concerns relevant to the change: correctness, null values and boundaries, failure handling, permissions, data exposure, concurrency, transactions, interface compatibility, and data migrations. Tie performance findings to a realistic workload and a clear mechanism for degradation.
4. For each potential issue, identify its triggering condition and impact. Look for validation or handling elsewhere before accepting it as a finding.
5. Run focused tests or a reproduction when doing so increases confidence. Do not run operations that affect production or real data without appropriate authorization. Distinguish tested results from conclusions drawn through inspection.

## Finding Criteria

- Report specific, actionable issues with a clear impact. Do not invent findings to meet a quota.
- When reviewing a change, focus on bugs introduced or exposed by it. Do not attribute a pre-existing issue to the change; mention it separately only when relevant to the scope.
- Exclude stylistic preferences and optional refactoring unless the user requests their evaluation. A missing test alone is not evidence of a bug; connect coverage concerns to important untested behavior when assessing coverage.
- Do not present an unverified possibility as fact. Put unresolved assumptions that materially affect a conclusion under questions or review limitations.
- Consolidate symptoms with the same root cause into one finding.

## Priority

- P0 Critical: A confirmed widespread outage or data-loss issue requiring immediate action, without relying on unverified assumptions.
- P1 High: A significant defect in a primary workflow or an exploitable vulnerability requiring urgent repair.
- P2 Medium: A real bug under specific conditions that should be addressed during the normal development cycle.
- P3 Low: A limited-impact defect worth fixing as priorities allow.

Assign priority based on impact and likelihood, not the size of the change.

## Output

Present findings first, ordered by priority. Each finding should include:

- A short title prefixed with its priority, such as: [P1] Verify record ownership before updating it.
- The file path and the narrowest line range that demonstrates the issue, with a link when available. Anchor pull request comments to a line in the diff.
- A paragraph explaining the trigger, actual behavior, impact, and evidence, followed by a brief suggested fix direction when clear.

Finish with material questions, tests performed, and verification limitations. If no issue meets the criteria, state that explicitly and describe the scope inspected; do not claim that the code is bug-free or completely secure. Follow any output format specified by the user or project.
