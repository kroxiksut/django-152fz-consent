# Cookie Integration Guide (AI)

## Scope

Use this guide to integrate `django-cookies-152fz`.

## Standalone mode

1. Install package:
   `pip install django-cookies-152fz`
2. Add app:
   `django_cookies_152fz`
3. Include routes:
   `include("django_cookies_152fz.urls")`
4. Run migrations and checks.

## Full mode with consent package

When consent package is installed, prefer shared project routing through
consent URLs, while cookie ownership remains in cookie module.

## Core settings namespace

Use `DJANGO_COOKIES_152FZ` for:

- `enable_cookies`
- `cookie_banner`
- `cookie_runtime`
- `cookie_retention`

## Production guardrails

- Keep optional scripts disabled until valid consent state exists.
- Keep bot hiding policy explicit.
- Keep domain/subdomain settings consistent with deployment topology.

