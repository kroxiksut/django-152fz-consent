# Consent Module: Experimental Confirmed Consent Circuit

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

## Graduation practice

Recommended gradual inclusion of `web_only -> paper_required`:
1. `dry-run` without `--apply`;
2. limited `apply` with `--batch-size`;
3. monitoring `ModuleOperationAuditLog`.

Jump command:

```bash
python manage.py transition_152fz_verified_legacy_web \
  --purpose-code <purpose_code> \
  --document-code <document_code> \
  --channel form \
  --form-code <form_code> \
  --dry-run
```

## Borders

- the confirmation loop does not replace the underlying consent lifecycle;
- the acknowledgment loop does not add a separate consent domain;
- The verification loop does not promise production-ready integrations with third-party signature providers.

Separately according to State Key:
- modes `goskey_required` and `paper_or_goskey` are reserved as a direction
extensions;
- working integration with an external service has not yet been implemented;
- The detailed position of the project is listed in [./goskey.md](./goskey.md).

Detailed operation and step-by-step scenarios:
- [./operations-admin.md](./operations-admin.md);
- [./README.md](./README.md).
