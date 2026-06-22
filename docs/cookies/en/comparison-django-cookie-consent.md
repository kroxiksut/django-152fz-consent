# Comparison with django-cookie-consent

- [Go to the cookie section](./README.md)
- [Go to the module overview](./overview.md)

This document helps choose between
[`django-cookie-consent`](https://github.com/django-commons/django-cookie-consent)
and `django-cookies-152fz`. It is not a quality ranking: the packages solve
overlapping but different problems.

The comparison was reviewed against `django-cookie-consent 1.0.0` and
`django-cookies-152fz 1.0.2` as of June 22, 2026. Upstream behavior may change
in later releases.

## In brief

`django-cookie-consent` is a mature general-purpose library for managing cookie
groups and user choices. It is particularly suitable when a project needs a
headless approach, full control over HTML and JavaScript, and explicit cookie
cleanup by name, domain, and path.

`django-cookies-152fz` is a server-backed Django module for an administered
cookie flow: policy revisions, an auditable server-side decision history, an
integration registry, a ready-made banner, a preferences page, and
consent-gated execution.
It targets projects where the cookie process is part of a broader administered
consent system.

## Architectural difference

In `django-cookie-consent`, the current decision is stored in the
`cookie_consent` browser cookie. It records accepted or declined groups and the
accepted group version. Database models describe groups and cookies, while
`LogItem` can record accept and decline actions.

In `django-cookies-152fz`, the server database is the source of truth for the
decision. A browser cookie containing an anonymous token identifies an
anonymous subject but does not replace the server-side decision record. The
anonymous record can be linked to a user after login.

## Feature comparison

| Area | `django-cookie-consent` | `django-cookies-152fz` |
| --- | --- | --- |
| Primary purpose | General-purpose cookie-group and user-choice management | Administered cookie flow: policy, versions, audit, integration registry, banner, and runtime |
| Current decision | In the `cookie_consent` browser cookie | In the server database; anonymous flows use a token |
| Data model | `CookieGroup`, `Cookie`, and `LogItem`; logging can be disabled in settings | Categories, consent records and events, banner state, policy and banner revisions, registry items and snapshots |
| Audit | `LogItem`: action, group, version, and timestamp; the model does not store a subject or request context | Server-side decision records and separate audit events with subject and technical context |
| Versioning | Group version is the creation time of its newest cookie; a new cookie triggers a new prompt | Separate policy revisions, category and registry snapshots, and banner revisions; presentation changes do not have to invalidate a decision |
| Consent mode | Global opt-in and opt-out modes | Default-deny for optional categories; accept all, required only, and custom selection actions |
| Banner | The project supplies its own `<template>`, styles, and JS module invocation | Ready-made template tag, layout and mobile variants, texts, theme, and a public preferences page |
| Script execution | Template checks or `onAccept`/`onDecline` callbacks; the project injects its scripts | The runtime receives allowed registry items and loads registered optional scripts by category |
| Cookie cleanup | Strong built-in mechanism using `is_deletable`, `domain`, `path`, and `CleanCookiesMiddleware` | Registry strategies `best_effort_delete` and `adapter_hook`; complex cleanup belongs in an integration adapter |
| UI customization | Headless approach with maximum project control | Ready-made administered UI configurable through Django admin, with custom CSS/JS extension points |
| Other consent integration | Standalone general-purpose package | Standalone package with optional integration through the `[consent]` extra |
| Ecosystem | ReadTheDocs, separate NPM package, coverage, and Playwright e2e | Bilingual documentation, bundled RU/EN texts, and a shared repository with `django-consent-152fz` |

## Where django-cookie-consent is particularly strong

- A simple and established cookie-group contract.
- Both opt-in and opt-out flows.
- Full project control over markup, styling, and client-side behavior.
- Explicit cookie `domain` and `path` values and cleanup middleware.
- A headless integration model that fits projects with an existing design system
  and frontend architecture.

For a typical international Django site that needs a flexible consent manager
without a ready-made operator workflow, `django-cookie-consent` may be the more
practical choice.

## Where django-cookies-152fz is particularly strong

- Server-side decision history rather than relying only on browser state.
- Separate entities and versions for policy, banner, and integration registry.
- Explicit separation of `dismiss`, user decision, and outdated consent.
- Anonymous decisions that can later be linked to an authenticated user.
- Policy, category, registry, and audit management through Django admin.
- A ready-made banner and preferences page without a mandatory frontend build.
- Default-deny runtime behavior for registered optional scripts.
- Optional integration with `django-consent-152fz` when the project needs a
  shared personal-data consent lifecycle.

## How to choose

Choose `django-cookie-consent` when the main requirements are a flexible
headless banner, opt-out mode, a minimal server-side decision model, and precise
cleanup of known cookies by domain and path.

Choose `django-cookies-152fz` when the main requirements are an auditable
server-side history, policy versioning, an administered integration registry,
operator-facing admin tools, a ready-made UI, and links between cookie decisions
and the project's other consent flows.

Both packages require the operator to define correct categories, purposes,
retention periods, and applicable legal requirements. Installing either package
does not by itself establish legal compliance.

## Primary sources

- [`django-cookie-consent`: concepts](https://django-cookie-consent.readthedocs.io/en/latest/concept.html)
- [`django-cookie-consent`: JavaScript integration](https://django-cookie-consent.readthedocs.io/en/latest/javascript.html)
- [`django-cookie-consent`: settings](https://django-cookie-consent.readthedocs.io/en/latest/settings.html)
- [`django-cookie-consent`: models](https://github.com/django-commons/django-cookie-consent/blob/main/cookie_consent/models.py)
- [`django-cookie-consent`: cleanup middleware](https://github.com/django-commons/django-cookie-consent/blob/main/cookie_consent/middleware.py)
- [`django-cookies-152fz`: key invariants](./invariants.md)
- [`django-cookies-152fz`: overview](./overview.md)
- [`django-cookies-152fz`: administration](./operations-admin.md)
