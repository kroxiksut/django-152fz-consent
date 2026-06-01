# Consents Module: Migration

- [To the consent section](./README.md)
- [To the general documentation index](../README.md)

## Purpose

The document captures the basic schema update procedure for the core consent module (`django_consent_152fz`).

## Basic scenario

1. Update the package to the target version.
2. Make sure `django_consent_152fz` is included in `INSTALLED_APPS`.
3. Execute `python manage.py migrate`.
4. Check availability:
   - documents and revisions;
   - consent records and events;
   - administrative forms of the consent module.

## What is important to control

- changes in `core` models must be accompanied by migrations and tests;
- changes to the API/consent contract must be accompanied by updated documentation;
- cookie module migrations are provided separately: [cookie module migration guide](../../cookies/en/migration.md).
- The step-by-step transition to paper confirmation is described in [./operations-admin.md](./operations-admin.md).
