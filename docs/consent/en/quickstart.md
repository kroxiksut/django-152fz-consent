# Consent module: quick start

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

This guide takes `django-consent-152fz` from an empty install to a working
consent flow with subject self-service. For the full settings contract see
[configuration.md](./configuration.md); for authoring documents and texts see
[authoring.md](./authoring.md).

> Distributed "as is". A working install does not by itself make a project
> 152-FZ compliant — the legal correctness of your texts, documents and
> processing workflows remains the operator's responsibility.

## 1. Install

```bash
pip install django-consent-152fz
```

Optional extras (add only what you need):

```bash
pip install "django-consent-152fz[api]"   # DRF API endpoints
pip install "django-consent-152fz[pdf]"   # PDF for the verified/paper flow (ReportLab)
```

The core depends only on Django (`Django>=5,<7`, Python 3.10–3.12). DRF and
ReportLab are pulled in only through the extras above.

## 2. Enable the app(s)

Optional features are turned on by **adding their Django app** to
`INSTALLED_APPS`, not just by a flag:

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",                      # core (always)
    "django_consent_152fz.api",                  # optional: DRF API
    "django_consent_152fz.verified_consents",    # optional: verified/paper flow
]
```

For the minimal setup, just `"django_consent_152fz"` is enough.

## 3. Configure

All behavior is configured through a single validated contract. Invalid config
raises `ConsentConfigurationError` early.

```python
DJANGO_CONSENT_152FZ = {
    "enable_core": True,
    "sample_documents": {
        # "command" -> load sample documents via a management command (below);
        # "auto"    -> bootstrap them on post_migrate.
        "load_mode": "command",
    },
    "subject_consents": {
        "open_mode": "page",
        "allow_anonymous_withdraw": True,
    },
}

# Mount the API only if the api app is installed and DRF is importable.
USE_API_152FZ = True
```

Codes (purpose / document / field codes) must match `^[a-z][a-z0-9_]*$`. See
[configuration.md](./configuration.md) for purposes, the PD field register,
policy contracts and audit context.

## 4. Wire the URLs

The template UI mounts independently of the API; the API is mixed in only when
the API app is installed **and** DRF is importable.

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    path(
        "",
        include(
            ("django_consent_152fz.urls", "django_consent_152fz"),
            namespace="django_consent_152fz",
        ),
    ),
]
```

This exposes, among others:

- `consent/documents/<purpose_code>/<document_code>/` — document detail
- `consent/accept/<purpose_code>/<document_code>/` — accept
- `consent/withdraw/<purpose_code>/<document_code>/` — withdraw
- `consent/self-service/` — subject self-service

## 5. Migrate and load starter data

```bash
python manage.py migrate
python manage.py bootstrap_152fz_sample_documents   # only if load_mode = "command"
```

With `load_mode: "auto"` the sample documents and starter purposes are seeded on
`post_migrate` and you can skip the command.

## 6. Use the service facade

External integrations should call the stable facade rather than importing
`core.services` directly:

```python
from django_consent_152fz import service_api
```

Changing its signatures is a contract change — see
[service-api.md](./service-api.md).

## Next steps

- [Configuration and policy contract](./configuration.md)
- [Creating and authoring consents](./authoring.md)
- [Subject self-service scenarios](./self-service.md)
- [Public service API and transport contract](./service-api.md)
- [Verified / paper-consent flow](./verified-flow.md)
- [Key invariants of the consent lifecycle](./invariants.md)
- [Demo environments](./demo.md)
