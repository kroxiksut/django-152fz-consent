# Consent Module: Key Invariants

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Domain invariants

- each consent is tied to a specific `DocumentRevision`;
- the consent stream is treated as a pair `purpose_code + document_code`;
- history is stored in immutable audit events;
- the `outdated` status occurs when the relevant document or policy revision is changed.

## Subject invariants

- authenticated and anonymous subjects are supported;
- anonymous consents can be linked to the user after login;
- anonymous revocation is controlled by a separate policy and is not enabled implicitly.

## Transport invariants

- views, template tags, and APIs remain a thin adapter layer on top of services;
- external integrations are not recommended to directly import internal modules `core.services`;
- the stable contract for integrations goes through `service_api`.

## Scope invariants

- optional additions should not be made mandatory for core flows;
- the experimental verified consent flow does not replace the core or form a separate consent domain.
