# Consent Integration Guide (AI)

## Scope

Use this guide when integrating `django-consent-152fz` into a project.

## Required setup

1. Install package:
   `pip install django-consent-152fz`
2. Add app:
   `django_consent_152fz`
3. Include routes:
   `include("django_consent_152fz.urls")`
4. Run migrations:
   `python manage.py migrate`
5. Validate config:
   `python manage.py check`

## Baseline settings

Use `DJANGO_CONSENT_152FZ` for consent module settings.
Use `USE_API_152FZ` only when API transport is needed.

## Data flow

1. Define `ConsentPurpose`.
2. Define `LegalDocument`.
3. Publish `DocumentRevision`.
4. On form submit:
   call `get_consent_status(...)` before business action.
5. If consent is required and provided:
   call `accept_consent(...)`.

## Integration contract

- Keep stable codes:
  `purpose_code`, `document_code`, and optional `form_code`.
- Do not hardcode human-readable names in business logic.
- Use service facade:
  `django_consent_152fz.service_api`.

