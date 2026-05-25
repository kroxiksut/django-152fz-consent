# Consent module: settings and policy contract

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Basic configuration

The main configuration is set in `DJANGO_152FZ_CONSENT`:
- `fields_mode` and `fields` for the register of PD fields;
- `purposes` for processing purposes;
- `subject_consents` for self-service behavior;
- feature flags to enable additional circuits.

## Feature Flags

- `enable_core` - main life cycle of consents;
- `enable_access_policies` — resource access restrictions;
- `enable_verified_consents` is a compatibility flag for the experimental confirmed consent loop.

## Contract policy

- `ConsentPurpose.consent_frequency_policy`: `once_until_outdated` | `every_time`;
- `ConsentPurpose.subject_availability_policy`: `authenticated_only` | `authenticated_and_anonymous`;
- `subject_consents.allow_anonymous_withdraw` enables or disables anonymous feedback in self-service;
- in the transport layer and API, `consent_required_reason` is used:
  `not_required`, `every_time`, `outdated`, `missing_or_other`, `not_applicable`.

## Practice of support

- changes to policy logic and capability flags must be accompanied by an update
[./service-api.md](./service-api.md) and tests;
- changes in scenarios for linking documents to forms and paper confirmation
synchronized with [./operations-admin.md](./operations-admin.md);
- When new user strings are added, `.po/.mo` is updated.

## Audit-context: country and client metadata

`build_request_audit_context(...)` for consent-flow now additionally fills:
- `extra_meta.client.country_code` (best-effort ISO alpha-2);
- `extra_meta.client.country_source` (`header:<name>` or `locale`);
- `extra_meta.client.browser_name`, `extra_meta.client.browser_version_major`;
- `extra_meta.client.os_family`, `extra_meta.client.os_version_major`.

Important:
- This is best-effort enrichment without guaranteeing that each field will be filled in;
- the structure remains backwards compatible: new data is written to `extra_meta.client`.
