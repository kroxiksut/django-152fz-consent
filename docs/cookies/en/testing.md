# Cookie module: testing

- [Go to cookies section](./README.md)
- [To the general documentation index](../README.md)

## Scope of checks

- cookie module routes and page `/cookies/`;
- rendering a banner using a template tag;
- saving category selection;
- banner display and re-display modes;
- event logs and export;
- absence of regressions in the main site.

## Automatic checks

Minimum set:
- `tests/test_cookie_only_router.py`
- `tests/test_cookie_standalone_split.py`
- `tests/test_split_upgrade_path.py`

Additional configuration:
- `tests/test_cookie_banner_settings.py`

## Practice from demo site

For applied testing in the demo, a two-level scheme was used:
- first check only the cookie layer on the live site;
- then check that, after enabling the cookie layer, the basic scenarios of the site did not break.

What to check manually after each change in cookie settings:
- the banner is displayed on public pages;
- actions `Accept all`, `Only required`, `Customize` work;
- the `/cookies/` page opens and saves the selection;
- re-selection is available;
- texts are available in Russian and English;
- there are no errors in the browser console;
- There are no processing errors in the server log.

## Base site regression

After changing the cookie layer, be sure to repeat:
- public pages;
- forms;
- user login and logout;
- access to the administrative panel.

This protects against side effects when changing templates, routes, and environment settings.

## Pre-release checks

Before releasing a cookie module, the following are required:
- automatic cookie layer tests;
- module integration run;
- checking installation in `cookies-only` mode;
- checking the joint installation with the consent module;
- manual checking of scenarios from a demo checklist.

Related checklist: `demo/notes/smoke-checklist.md`.
