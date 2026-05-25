# Consents module: public service API and transport contract

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Public entry point

For external integrations use:

```python
from django_consent_152fz import service_api
```

The stable surface is fixed via `PUBLIC_SERVICE_API_V1` and `__all__`.

## Key Operations of the Consent Core

- `register_purposes_from_config`
- `get_current_requirements`
- `accept_consent`
- `withdraw_consent`
- `anonymize_subject_consents`
- `get_consent_status`
- `attach_anonymous_consents_to_user`

## Limit of responsibility

- There are separate operations available for cookies (`get_cookie_requirements`, `accept_cookie_preferences`, `get_cookie_status`), but the consent core remains a separate domain.
- Direct import of internal `core.services` and `cookies.services` in external integrations is not recommended.

## Routing and transport contract

- Route extensions and API contracts are captured in [../README.md](../README.md).
- Web and API adapters should remain thin and not duplicate the domain logic of the service layer.
- Practical scenarios for integrating forms and paper confirmation are described in [./operations-admin.md](./operations-admin.md).
