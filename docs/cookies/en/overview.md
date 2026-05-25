# Cookie module: overview and current status

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

The document records:
- what is already implemented in the cookie module;
- what invariants cannot be violated during the development of the banner and executing layer;
- what extension points are available for the project.

## What has been implemented

- cookie categories and policy editions;
- Integration registry and published registry snapshots;
- storing user decisions and cookie audit events;
- separate banner display state (`CookieBannerState`);
- public cookie settings page and template banner;
- action scenarios: `accept all`, `required only`, `custom selection`, `dismiss`;
- banner re-display policy and mode `cookies_only`;
- anonymous script and binding to the user after login;
- execution layer for loading and cleaning up optional scripts.

## Validation on demo site

Practical integration of the cookie module was tested on demo stands:
- `demo/django5`;
- `demo/django6`.

Working script from demo:
- connecting a cookie module to an already running site;
- single banner insertion into the base template;
- separate route `/cookies/` for user settings;
- Regression check of forms, login and admin panel after changing cookie settings.

## Related Sections

- [Configuration](./configuration.md)
- [Invariants](./invariants.md)
- [Testing](./testing.md)
- [Migration](./migration.md)
