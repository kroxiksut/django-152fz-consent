# Consent Module: Overview and Current Status

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

The consent layer covers the life cycle of consents 152-FZ:
- versioning consent documents;
- recording of issued and revoked consents for the `purpose + document` stream;
- auditing changes through events;
- working with authorized and anonymous entities;
- review and review in self-service.

## What has been implemented

- kernel domain models (`ConsentPurpose`, `LegalDocument`, `DocumentRevision`, `ConsentRecord`, `ConsentEvent`);
- service layer for issuing, revoking and checking the status of consents;
- linking consent to a specific version of the document;
- re-confirmation and re-consent modes;
- capability flags for additional circuits;
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
