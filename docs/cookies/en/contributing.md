# Contributing to the cookie module

- [Back to cookie docs](./README.md)
- [Back to repository contributing guide](../../../CONTRIBUTING.md)

## Scope

This guide applies to changes in `django-cookies-152fz` runtime behavior, banner/policy workflows, integration registry, and related docs/tests.

## Typical change areas

- Banner rendering and interaction flow.
- Cookie preferences and persistence behavior.
- Script/category registry and consent-gated runtime execution.
- Policy/banner revision publication logic.
- Audit events, retention, and export behavior.

## Required checks before PR

1. Add or update tests for behavior changes.
2. Update docs under `docs/cookies/en/*` and `docs/cookies/ru/*`.
3. Validate runtime contract/event changes against existing integration points.
4. Verify that consent-only mode remains unaffected by cookie-module internals.

## Test focus

- Runtime/service tests for category decisions and script gating.
- Template/tag and view checks for banner/preferences routes.
- Admin workflow checks for policy and banner revisions.
- Audit event checks including retention/cleanup paths when modified.

## Documentation follow-through

- Keep EN and RU docs aligned.
- If changing UI contract or runtime hooks, update:
  - `contracts.md`
  - `presentation.md`
  - `operations-admin.md`

## Translation contributions

If your cookie changes include user-facing text updates, follow:

- [Translation contributions](../../i18n/README.md)
