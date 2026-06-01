# Cookie module: migration

- [Go to cookies section](./README.md)
- [To the general documentation index](../README.md)

## Purpose

This document captures the update path for the standalone `django_cookies_152fz` cookie package.

## Baseline reset

The historical chain of cookie migrations (`0002+`) has been squashed into a single file
`django_cookies_152fz/migrations/0001_initial.py`.

This simplifies the package structure, but for existing installations it requires
a controlled migration transition.

## Current contract of migrations and models

- canonical application package: `django_cookies_152fz`;
- stable application label in the migration graph and database:
  `django_consent_152fz_cookies`;
- table names and links to historical models do not change;
- cookie migrations can be used in `cookies-only` without mandatory
depending on `django_consent_152fz`.

## Upgrade path for existing installations

1. Update dependencies to compatible versions of `django-consent-152fz` and `django-cookies-152fz`.
2. Use the canonical path `django_cookies_152fz` in `INSTALLED_APPS`.
3. Remove the old application path from `INSTALLED_APPS` if one was specified.
4. Leave the desired route:
   - `django_consent_152fz.urls` for the full scenario;
   - `django_cookies_152fz.urls` for `cookies-only` routing.
5. Execute `python manage.py migrate`.
6. Check cookie routes, banner status and existing cookies.

## Incompatible scenarios

- direct use of `django_consent_152fz.cookies.*` as canonical imports;
- expecting old imports to be auto-redirected.

## New installation and update

- new installation: use `django_cookies_152fz` in `INSTALLED_APPS` for `cookies-only`;
- updating an existing installation: replace old imports/routes with
`django_cookies_152fz.*`.

## Known Limitations

- mixed environments need a separate plan to clean up old imports;
- in custom migrations with direct references to old Python paths,
the references must go through the application label and model name.

## Transition layer status

- legacy transition imports are removed;
- only canonical `django_cookies_152fz` paths are supported.

## Control after update

- check the scenarios from [./testing.md](./testing.md);
- check the integration suite from the `tests` directory.
