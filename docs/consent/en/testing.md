# Consent module: testing

- [To the consent section](./README.md)
- [To the general documentation index](../README.md)

## Scope of checks

- domain consent model (`LegalDocument`, `DocumentRevision`, `ConsentRecord`, `ConsentEvent`);
- kernel service layer (`core.services`);
- public facade `service_api` regarding consent operations;
- access policies and subject self-service.
- scenarios for linking a document to a form and switching to paper confirmation.

## Minimum set

- `tests/test_document_models.py`
- `tests/test_consent_record_model.py`
- `tests/test_consent_event_model.py`
- `tests/test_core_services.py`
- `tests/test_service_api.py`
- `tests/test_feature_flags_config.py`

## End-to-end checks

- integration set from the `tests` directory;
- migration scenarios are described in [./migration.md](./migration.md).
- practical operating scenarios are described in [./operations-admin.md](./operations-admin.md).

## Pre-release checks

To release the consent module, the following are required:
- `consent-standalone`;
- `integration`;
- building packages and checking metadata and content of artifacts.
