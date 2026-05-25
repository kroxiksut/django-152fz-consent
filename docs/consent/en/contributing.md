# Contributing to the consent module

- [Back to consent docs](./README.md)
- [Back to repository contributing guide](../../../CONTRIBUTING.md)

## Scope

This guide applies to changes in `django-consent-152fz` domain logic, admin flows, service API, and related docs/tests.

## Typical change areas

- Consent lifecycle behavior (`accept`, `withdraw`, status, re-consent).
- Document and revision workflows.
- Subject self-service behavior.
- Access policies and optional verified-consent flow.
- Service API and transport adapters.

## Required checks before PR

1. Add or update tests for behavior changes.
2. Update docs under `docs/consent/en/*` and `docs/consent/ru/*`.
3. Validate that public API contracts remain backward compatible (or clearly document breaking changes).
4. Confirm no unintended impact on cookie-only mode.

## Test focus

- Domain/service tests for consent operations.
- Admin tests for revision and policy workflows when changed.
- Integration checks for form flows and self-service paths.

## Documentation follow-through

- Keep EN and RU docs synchronized for user-visible behavior.
- If changing optional verified-consent behavior, update:
  - `verified-flow.md`
  - `goskey.md` (if integration boundary assumptions changed)
  - `operations-admin.md`

## Translation contributions

If your consent changes include user-facing text updates, follow:

- [Translation contributions](../../i18n/README.md)
