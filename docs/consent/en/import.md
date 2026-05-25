# Consent Module: Importing Historical Data

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

The import layer is designed to provide controlled transfer of existing consent data into the kernel model.

## Tools

- control command: `import_152fz_core_consents`;
- import service layer: `core/importers.py`;
- external system adapters: `imports/adapters.py`.

## Basic principles

- import is performed separately from other modules;
- prefer `dry-run` before actual application;
- the import preserves audit context and should not bypass service layer domain checks.

## Escort

- import contract changes are synchronized with [./configuration.md](./configuration.md), [./service-api.md](./service-api.md) and tests;
- For vendor-specific scenarios, extensible adapters are used rather than hard-wired logic in the kernel.
