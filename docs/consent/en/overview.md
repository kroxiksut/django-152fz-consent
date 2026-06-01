# Consent Module: Overview and Current Status

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

The consent layer covers the 152-FZ consent life cycle:
- versioning consent documents;
- recording issued and revoked consents for the `purpose + document` stream;
- auditing changes through events;
- working with authenticated and anonymous subjects;
- viewing and managing consents in self-service.

## What has been implemented

- core domain models (`ConsentPurpose`, `LegalDocument`, `DocumentRevision`, `ConsentRecord`, `ConsentEvent`);
- service layer for issuing, revoking and checking the status of consents;
- linking consent to a specific version of the document;
- re-confirmation and re-consent modes;
- feature flags for additional flows;
- public facade `django_consent_152fz.service_api` for external integrations.

## Related Sections

- [Use and Administration](./operations-admin.md)
- [Creation and filling of consents](./authoring.md)
- [Detailed settings](./configuration.md)
- [Model invariants](./invariants.md)
- [Public integration contracts](./service-api.md)
- [Future integration with Gosklyuch](./goskey.md)
- [Testing](./testing.md)
- [Migration](./migration.md)
