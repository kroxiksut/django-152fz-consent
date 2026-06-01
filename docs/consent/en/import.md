# Consent Module: Importing Historical Data

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

The import layer is designed to provide controlled transfer of existing consent data into the core model.

## Tools

- control command: `import_152fz_core_consents`;
- import service layer: `core/importers.py`;
- external system adapters: `imports/adapters.py`.

## Basic principles

- import is performed separately from other modules;
- prefer `dry-run` before actual application;
- the import preserves audit context and should not bypass service layer domain checks.

## Maintenance

- import contract changes are synchronized with [./configuration.md](./configuration.md), [./service-api.md](./service-api.md) and tests;
- for vendor-specific scenarios, extensible adapters are used rather than hard-wired logic in the core.
