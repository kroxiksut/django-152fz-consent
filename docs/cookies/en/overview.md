# Cookie module: overview and current status

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

The document records:
- what is already implemented in the cookie module;
- which invariants must not be violated while developing the banner and the execution layer;
- what extension points are available for the project.

## What has been implemented

- cookie categories and policy revisions;
- integration registry and published registry snapshots;
- storing user decisions and cookie audit events;
- a separate banner display state (`CookieBannerState`);
- a public cookie settings page and template banner;
- action scenarios: `accept all`, `required only`, `custom selection`, `dismiss`;
- banner re-display policy and the `cookies_only` mode;
- anonymous record and linking to the user after login;
- an execution layer for loading and cleaning up optional scripts.

## Validation on demo site

Practical integration of the cookie module was tested on demo stands:
- `demo/django5`;
- `demo/django6`.

Working scenario from the demo:
- connecting the cookie module to an already running site;
- single banner insertion into the base template;
- a separate route `/cookies/` for user settings;
- regression check of forms, login and admin panel after changing cookie settings.

## Related Sections

- [Configuration](./configuration.md)
- [Invariants](./invariants.md)
- [Testing](./testing.md)
- [Migration](./migration.md)
