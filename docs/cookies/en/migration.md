# Cookie module: migration

- [Go to cookies section](./README.md)
- [To the general documentation index](../README.md)

## Purpose

The document captures the update path for the individual `django_cookies_152fz` cookie.

## Baseline reset

The historical chain of cookie migrations (`0002+`) has been compiled into a single file
`django_cookies_152fz/migrations/0001_initial.py`.

This simplifies the package structure, but for existing installations it requires
controlled migration transition.

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
   - `django_consent_152fz.urls` for complete script;
   - `django_consent_152fz.cookies.urls` for `cookies-only` routing.
5. Execute `python manage.py migrate`.
6. Check cookie routes, banner status and existing cookies.

## Backward Compatibility

Supported:
- old imports `django_consent_152fz.cookies.*`;
- old template paths in `django_consent_152fz/templates/...` space
through the transition layer in `django_cookies_152fz`.

## Incompatible scenarios after removing the transition layer

- direct use of `django_consent_152fz.cookies.*` as canonical imports;
- expecting templates and static cookie resources to remain in space
`consent` without compatibility layer.

## New installation and update

- new setting: use `django_cookies_152fz` in `INSTALLED_APPS` for `cookies-only`;
- updating an existing installation: transient imports are allowed temporarily,
but the application path must be canonical.

## Known Limitations

- mixed environments need a separate plan to clean up old imports before deleting
transition layer;
- in custom migrations with direct links to old python paths
you need to go to the links through the application label and model name.

## Removing Backward Compatibility

- initially, transitional imports are supported as a temporary measure;
- then warnings are published about the deprecation of old paths;
- After the ruler has stabilized, transitional aliases are removed.

Removal condition: at least one stable release cycle without regressions in
`cookies-only`, `consent-only` and joint installation.

## Control after update

- check scripts from [./testing.md](./testing.md);
- check the integration kit from the `tests` directory.
