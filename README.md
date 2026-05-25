<p align="center">
  <img src="docs/assets/logo/dj-152fz-logo.png" alt="django-152fz" width="220">
</p>

<h1 align="center">django-152fz</h1>

<p align="center">
  <img alt="Consent package" src="https://img.shields.io/badge/django--152fz--consent-0.1.0-blue">
  <img alt="Cookies package" src="https://img.shields.io/badge/django--152fz--cookies-0.1.0-blue">
  <img alt="Project status" src="https://img.shields.io/badge/status-alpha-orange">
  <img alt="Python versions" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="Django versions" src="https://img.shields.io/badge/django-5.x%20%7C%206.x-0C4B33">
  <img alt="Tests" src="https://img.shields.io/badge/tests-pytest-0A9EDC">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

`django-152fz` is a set of Django packages for projects that need a server-side consent workflow under the Russian 152-FZ legal context and a separate cookie layer with a banner, registry, and consent-aware runtime.

The repository is split into two installable packages:

- `django-consent-152fz` - consent lifecycle, documents, audits, subject self-service, access policies, service API;
- `django-cookies-152fz` - cookie banner, cookie categories, policy revisions, runtime registry, cookie audit, and `cookies-only` scenarios.

Main project links:

- [English documentation](./docs/README.md)
- [Russian documentation](./docs/README.ru.md)
- [Russian README](./README.ru.md)
- [AI-friendly integration guides (English only)](./docs/consent/ai/README.md)

## Package Scope

### `django-consent-152fz`

The consent package covers:

- `ConsentPurpose`, `LegalDocument`, `DocumentRevision`, `ConsentRecord`, `ConsentEvent`;
- issue, withdrawal, status checks, and re-consent flows for the `purpose + document` path;
- immutable event audit;
- anonymous and authenticated scenarios;
- subject self-service;
- optional `verified_consents` contract;
- optional access policies;
- public Python facade `django_consent_152fz.service_api`.

### `django-cookies-152fz`

The cookie package covers:

- `CookieCategory`, `CookiePolicyRevision`, `CookieBannerRevision`;
- a standalone cookie banner and user preferences page;
- `cookies-only` deployment without the consent package being mandatory;
- storage of cookie decisions and cookie audit;
- cookie/script registry;
- strict deny-by-default behavior for optional scripts;
- cleanup and retention rules;
- anonymous and authenticated flows.

### How They Work Together

In the full setup:

- the consent package owns the consent lifecycle;
- the cookie package owns the cookie domain, banner UI, and runtime layer;
- `django_consent_152fz.urls` wires the consent UI and cookie package routes under the shared `consent/` prefix;
- external integrations consume cookie functionality through the service layer rather than by coupling to internal models.

## Supported Scenarios

The project currently supports three deployment modes:

1. `consent-only`
   Only `django-consent-152fz` is installed.
2. `cookies-only`
   Only `django-cookies-152fz` is installed.
3. `full`
   Both packages are installed and work together.

This matches the split repository layout and the docs structure under `docs/consent/*` and `docs/cookies/*`.

## Installation

### Consent only

```bash
pip install django-consent-152fz
```

### Cookies only

```bash
pip install django-cookies-152fz
```

### Full setup

```bash
pip install django-consent-152fz django-cookies-152fz
```

### Optional API

```bash
pip install "django-consent-152fz[api]"
```

### Convenience extra

```bash
pip install "django-consent-152fz[cookies]"
```

That extra pulls in the cookie package as a dependency for consent-first projects.

## Quick Start

### Consent only

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",
]

DJANGO_152FZ_CONSENT = {
    "enable_core": True,
    "enable_access_policies": False,
    "enable_verified_consents": False,
}

USE_API_152FZ = False
```

```python
from django.urls import include, path

urlpatterns = [
    path("", include("django_consent_152fz.urls")),
]
```

### Cookies only

```python
INSTALLED_APPS = [
    # ...
    "django_cookies_152fz",
]

DJANGO_152FZ_COOKIES = {
    "enable_cookies": True,
}
```

```python
from django.urls import include, path

urlpatterns = [
    path("", include("django_cookies_152fz.urls")),
]
```

### Full setup: consent + cookies

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",
    "django_cookies_152fz",
]

DJANGO_152FZ_CONSENT = {
    "enable_core": True,
    "enable_access_policies": False,
    "enable_verified_consents": False,
}

DJANGO_152FZ_COOKIES = {
    "enable_cookies": True,
}

USE_API_152FZ = False
```

```python
from django.urls import include, path

urlpatterns = [
    path("", include("django_consent_152fz.urls")),
]
```

## Notes

- The project is oriented toward the Russian legal context, but it does not replace legal review.
- Texts, categories, and templates are starting points and should be adapted to the target implementation.
- The authoritative project documentation is split by language:
  - [English docs](./docs/README.md)
  - [Russian docs](./docs/README.ru.md)
