# Consent module: settings and policy contract

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Basic configuration

The main configuration is set in `DJANGO_CONSENT_152FZ`:
- `fields_mode` and `fields` for the register of PD fields;
- `purposes` for processing purposes;
- `subject_consents` for self-service behavior;
- feature flags to enable additional flows.

## Feature flags

- `enable_core` - main life cycle of consents;
- `enable_access_policies` — resource access restrictions;
- `enable_verified_consents` is a compatibility flag for the experimental verified consent flow.

## Contract policy

- `ConsentPurpose.consent_frequency_policy`: `once_until_outdated` | `every_time`;
- `ConsentPurpose.subject_availability_policy`: `authenticated_only` | `authenticated_and_anonymous`;
- `subject_consents.allow_anonymous_withdraw` enables or disables anonymous withdrawal in self-service;
- in the transport layer and API, `consent_required_reason` is used:
  `not_required`, `every_time`, `outdated`, `missing_or_other`, `not_applicable`.

## Support practices

- changes to policy logic and feature flags must be accompanied by an update to
[./service-api.md](./service-api.md) and tests;
- changes to the scenarios for linking documents to forms and to paper confirmation
are synchronized with [./operations-admin.md](./operations-admin.md);
- when new user-facing strings are added, `.po/.mo` is updated.

## Audit context: country and client metadata

`build_request_audit_context(...)` for the consent flow now additionally fills:
- `extra_meta.client.country_code` (best-effort ISO alpha-2);
- `extra_meta.client.country_source` (`header:<name>` or `locale`);
- `extra_meta.client.browser_name`, `extra_meta.client.browser_version_major`;
- `extra_meta.client.os_family`, `extra_meta.client.os_version_major`.

Important:
- This is best-effort enrichment without guaranteeing that each field will be filled in;
- the structure remains backwards compatible: new data is written to `extra_meta.client`.
