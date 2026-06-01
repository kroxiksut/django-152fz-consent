# Consent Module: Experimental Verified Consent Flow

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Status

`verified_consents` is an experimental optional module for enhanced confirmation scenarios for individual consent streams.

## Basic contract

- single `verification_mode`:
`web_only | paper_required | goskey_required | paper_or_goskey`;
- `flow_scope`:
`both | self_service_only | forms_only`;
- Behavior for previously issued web consents:
`keep_web_current | mark_web_outdated | withdraw_web_now | withdraw_after_paper_confirmed`;
- overriding for a specific form via `VerifiedConsentFormPolicy`.

## Rollout practice

Recommended gradual transition `web_only -> paper_required`:
1. `dry-run` without `--apply`;
2. a limited `apply` with `--batch-size`;
3. monitoring `ModuleOperationAuditLog`.

Transition command:

```bash
python manage.py transition_152fz_verified_legacy_web \
  --purpose-code <purpose_code> \
  --document-code <document_code> \
  --channel form \
  --form-code <form_code> \
  --dry-run
```

## Boundaries

- the verified consent flow does not replace the underlying consent lifecycle;
- the verified consent flow does not add a separate consent domain;
- the verified consent flow does not promise production-ready integrations with third-party signature providers.

Specifically regarding Gosklyuch:
- the `goskey_required` and `paper_or_goskey` modes are reserved as a direction
for extension;
- a working integration with an external service has not yet been implemented;
- the detailed project position is described in [./goskey.md](./goskey.md).

Detailed operation and step-by-step scenarios:
- [./operations-admin.md](./operations-admin.md);
- [./README.md](./README.md).
