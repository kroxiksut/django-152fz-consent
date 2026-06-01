# Translation contributions

This guide describes how to contribute RU/EN (and other languages)
localization updates.

## What can be contributed

- New translations for user-facing strings.
- Corrections to existing translations.
- Terminology alignment across docs, templates, and UI.

## Other languages

The project currently ships RU and EN, but translations into **other
languages are welcome** — both for documentation and for module UI strings.

- **Module strings:** add a Django locale catalog under
  `locale/<lang>/LC_MESSAGES/` and provide `.po`/`.mo` files.
- **Documentation:** add a per-module language folder, e.g.
  `docs/consent/<lang>/` and `docs/cookies/<lang>/`, mirroring `en`/`ru`.

Notes:
- Russian is the **canonical, legally authoritative** text (152-FZ context);
  all other languages, including English, are informational and do not
  replace the Russian original.
- Russian remains required for any user-facing string; other languages are
  best-effort and may be partial.

## Forks and modifications

This project is open source — forks are free to add, change, or remove
languages, including dropping the Russian text entirely.

Be aware:
- The Russian text is what ties this project to the 152-FZ legal context.
  A fork that removes it no longer carries that legal grounding, and the
  compliance assumptions of the original no longer apply.
- The original authors provide the project "as is" and are **not
  responsible** for forks or modified copies, their translations, or the
  legal validity of any wording they ship.

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
