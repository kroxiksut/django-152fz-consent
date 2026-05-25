# Goskey Future Guide (AI)

## Current state

Goskey integration is not implemented in the package at this stage.

## What is available today

- Policy modes reserve Goskey direction:
  `goskey_required`, `paper_or_goskey`.
- No production API client, no callback handling, no provider runtime.

## Why this is deferred

The maintainers do not currently have:

- a legal entity operating this flow in production,
- a real onboarding path to validate provider contracts end-to-end.

## Contribution policy

If a team has real business need and provider access:

- maintainers are open to review a focused pull request,
- maintainers are open to collaborate on implementation and testing.

## Implementation expectation

A valid integration proposal should include:

- provider onboarding constraints,
- API lifecycle/state machine design,
- error/retry/cancel handling,
- audit and artifact handling strategy,
- test plan for staged rollout.

