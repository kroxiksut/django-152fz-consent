# SKILLS — django-consent-152fz

Task recipes for integrating the package. Obey [`AI_RULES.md`](./AI_RULES.md)
throughout; background in [`AI_CONTEXT.md`](./AI_CONTEXT.md).

## Install and enable

```bash
pip install django-consent-152fz          # core (Django only)
pip install "django-consent-152fz[api]"   # + DRF API
pip install "django-consent-152fz[pdf]"   # + PDF for paper/verified consents
```

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",                    # core (always)
    "django_consent_152fz.api",                # optional DRF API
    "django_consent_152fz.verified_consents",  # optional verified/paper flow
]
```

Then `include("django_consent_152fz.urls")` in your URLconf, run
`python manage.py migrate`, and `python manage.py check`.

## Define a consent stream

1. Define a `ConsentPurpose` with a stable `purpose_code`.
2. Define a `LegalDocument` with a stable `document_code`.
3. Publish a `DocumentRevision` for that document.
4. Reference the stream by `purpose_code` + `document_code` everywhere — never
   by display name.

## Wire a project form to consent

1. Choose stable `purpose_code`, `document_code`, and a `form_code`
   (recommended, required for verified policies).
2. Build a verification context, e.g.
   `{"channel": "form", "form_code": "<form_code>"}`.
3. Call `get_consent_status(...)` **before** the form's business logic.
4. If consent is required, block submit until explicit user confirmation.
5. After confirm, call `accept_consent(...)` with an `audit_context`.
6. For anonymous subjects, persist the returned `anonymous_token` in the
   response so consent can later upgrade to a full account.
7. Always render a link to the document view route; for printable flows, link
   the PDF route. Keep the consent UI independent of domain form fields.

## Enable the verified / paper flow

1. Add `django_consent_152fz.verified_consents` to `INSTALLED_APPS`; migrate.
2. Configure a `VerifiedConsentPolicy`; optionally override per form with a
   `VerifiedConsentFormPolicy`.
3. Pick a mode: `web_only` or `paper_required`. Treat `goskey_required` /
   `paper_or_goskey` as reserved (no production provider client exists).
4. Migrating existing web consents: dry-run command → apply in batches →
   monitor the operation audit log.

## Enable the API

1. Install the `[api]` extra and add `django_consent_152fz.api` to
   `INSTALLED_APPS`.
2. Set `USE_API_152FZ = True`. The API mounts only when its app is installed and
   DRF is importable.

## Always

- Call through `django_consent_152fz.service_api`, not `core.services`.
- Run `python manage.py check` after any config change.
- Update `.po`/`.mo` in the same change set when you touch user-facing strings.
