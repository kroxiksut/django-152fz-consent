# Verified Consents Guide (AI)

## Status

Verified flow is supported as an optional extension module:
`django_consent_152fz.verified_consents`.

## Enablement

1. Add app:
   `django_consent_152fz.verified_consents`
2. Run migrations.
3. Configure `VerifiedConsentPolicy`.
4. Optionally override by form with `VerifiedConsentFormPolicy`.

## Key modes

- `web_only`
- `paper_required`
- `goskey_required` (future direction)
- `paper_or_goskey` (future direction)

## Migration strategy

For existing web consents, use staged transition:

1. dry-run command
2. apply with batch size
3. monitor operation audit logs

## Guardrails

- Verified flow extends consent core; it does not replace it.
- Keep policy-by-stream (`purpose + document`) explicit.
- Treat Goskey modes as reserved unless real provider integration exists.

