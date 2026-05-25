# Translation contributions

This guide describes how to contribute RU/EN localization updates.

## What can be contributed

- New translations for user-facing strings.
- Corrections to existing translations.
- Terminology alignment across docs, templates, and UI.

## Required workflow for string changes

If your change adds or modifies user-facing strings (labels, help texts, template texts, field names, choices, etc.), do all of the following in one change set:

1. Update source strings in code/templates/docs.
2. Update relevant `.po` catalogs.
3. Rebuild `.mo` files.
4. Verify RU/EN UI rendering and no encoding issues.

## Quality rules

- Keep UTF-8 encoding only.
- Avoid mixed-language placeholders in final UI strings.
- Keep legal wording consistent with the module context.

## Where translation files live

- Demo shared locale files: `demo/common/locale/*/LC_MESSAGES/`.
- Package locale catalogs: in corresponding package locale directories.

## Related docs

- [Repository contributing guide](../../CONTRIBUTING.md)
- [Русская версия](./README.ru.md)
