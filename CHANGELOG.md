# Changelog

This is the shared changelog for both packages shipped from this repository.
They are versioned and released independently and may diverge in later releases.

| Package | PyPI | Repository | Docs |
| --- | --- | --- | --- |
| `django-consent-152fz` | [pypi.org/project/django-consent-152fz](https://pypi.org/project/django-consent-152fz/) | [GitHub](https://github.com/kroxiksut/django-consent-152fz) | [docs/consent](https://github.com/kroxiksut/django-consent-152fz/tree/main/docs/consent) |
| `django-cookies-152fz` | [pypi.org/project/django-cookies-152fz](https://pypi.org/project/django-cookies-152fz/) | [GitHub](https://github.com/kroxiksut/django-consent-152fz) | [docs/cookies](https://github.com/kroxiksut/django-consent-152fz/tree/main/docs/cookies) |

The format is based on [Keep a Changelog](https://keepachangelog.com/), and the
packages follow [Semantic Versioning](https://semver.org/).

---

## [django-cookies-152fz 1.0.1] - 2026-06-06

### Added

- Added locale-aware automatic cookie-banner text preset selection.
- Added demo cookie registry items to the idempotent cookie defaults bootstrap.
- Added synchronization of category and registry snapshots for cookie policy
  revisions.
- Added clearer cookie-policy variant controls and revision fieldsets in the
  Django admin.

### Fixed

- Updated Russian and English cookie-package translations and compiled locale
  files.
- Fixed cookie-banner close-control choice initialization and validation in the
  Django admin.

### Documentation

- Expanded the Russian and English cookie-module guides, including quickstart,
  administration, and banner presentation documentation.
- Added Russian and English screenshots covering banner variants, settings,
  categories, registry items, consent records, policy text presets, and event
  export, plus a sample cookie-consent event CSV.

## [django-consent-152fz 1.0.1] - 2026-06-06

### Fixed

- Corrected English interface translations and rebuilt the compiled locale
  catalog.

### Documentation

- Expanded the Russian and English consent-module guides, including quickstart,
  administration, authoring, configuration, self-service, and verified-consent
  flows.
- Added Russian and English screenshots covering consent workflows, documents,
  purposes, settings, audit records, and verified consents, plus sample consent
  and operation-audit CSV exports.

## [1.0.0] - 2026-06-02

First public release of both packages. Reusable Django building blocks for
152-FZ personal-data workflows: a versioned consent lifecycle with an immutable
audit trail, and a consent-aware cookie banner and runtime. The two distributions
install and run independently — neither requires the other.

**Compatibility:** Python 3.10–3.12, Django 5.0 / 5.1 / 5.2 (LTS) / 6.0
(`Django>=5,<7`). Verified in CI on Python 3.10 + Django 5.x and Python 3.12 +
Django 6.x, including standalone (single-package) and integration runs. MIT
license. Boxed/sample legal texts default to Russian; UI localization ships for
Russian (`ru`) and English (`en`). Configuration keys, enum values and the
public API are English.

### django-consent-152fz 1.0.0

Consent lifecycle for projects that process the personal data of people in
Russia.

- **Legal documents and revisions** — versioned legal documents (`LegalDocument`)
  with immutable revisions (`DocumentRevision`); consent is always bound to the
  exact text revision it was given against.
- **Processing purposes** — declarative configuration of processing purposes and
  the document/field codes behind them, validated early against the
  `^[a-z][a-z0-9_]*$` code contract.
- **Consent records and immutable audit log** — consent records plus an
  append-only audit event log of every grant/withdraw/change.
- **Subject self-service** — template UI for a data subject to review and manage
  their own consents.
- **Optional verified / paper-consent flow** — opt-in app
  (`django_consent_152fz.verified_consents`) for verified and paper consents;
  GosKey (Госключ)-related modes are reserved for future integration, but no
  production GosKey client ships yet; optional `[pdf]` extra (ReportLab)
  generates consent PDFs.
- **Optional DRF API** — opt-in app (`django_consent_152fz.api`) plus the
  `[api]` extra; mounted only when the app is installed and DRF is importable.
- **Stable service facade** — `django_consent_152fz.service_api` is the public
  API for external integrations; the raw `core.services` layer is internal.
- **Single config contract** — all behavior is configured through
  `DJANGO_CONSENT_152FZ` (legacy alias `DJANGO_152FZ_CONSENT`) and `USE_API_152FZ`,
  normalized and validated in one place with early `ConsentConfigurationError`s.
- **Feature gating by app presence** — optional pieces are enabled by adding their
  Django app to `INSTALLED_APPS`, not just by a flag.
- **Bootstrapping on `post_migrate`** — sample documents and starter purposes are
  seeded after migrations, never at import time.
- Core depends only on Django; DRF and ReportLab are pulled in only via extras.

Install: `pip install django-consent-152fz`
(`[api]` for the DRF API, `[pdf]` for paper-consent PDFs).

### django-cookies-152fz 1.0.0

Cookie banner and consent-aware runtime, deliberately standalone — it holds its
own integration contract and never imports the consent layer.

- **Cookie banner** — ready-to-render banner with flexible branding and
  mobile-friendly variants.
- **Consent-gated script execution** — non-essential scripts run only after the
  matching cookie consent is given.
- **Runtime cookie registry** — a runtime registry of cookies / categories used
  by the site.
- **Versioned policy revisions** — versioned cookie-policy revisions, with the
  initial banner revision bootstrapped on `post_migrate`.
- **Cookie audit** — an audit trail of cookie-consent decisions.
- **Standalone with optional integration** — runs without the consent package;
  the `[consent]` extra pulls in `django-consent-152fz` for joint use.
- **Single config contract** — configured through `DJANGO_COOKIES_152FZ`
  (legacy alias `DJANGO_152FZ_COOKIES`).
- Largely jurisdiction-neutral mechanics (categories, policy revisions,
  consent-gated execution, audit); adapting to another jurisdiction is mostly a
  matter of texts and locale.

Install: `pip install django-cookies-152fz`
(`[consent]` to integrate with the consent package).

### Shared across both packages

- **Bilingual** — Russian (`ru`) and English (`en`) via Django `gettext`; adding
  a locale is just a new `.po`/`.mo` pair.
- **Bundled AI-agent guidance** — each distribution ships opt-in agent docs under
  `<package>/ai/` (`AGENTS.md`, `AI_RULES.md`, `AI_CONTEXT.md`, `SKILLS.md`),
  not loaded automatically.
- **Independent distributions** — built as separate wheels from a single
  src-layout monorepo; CI proves each works without the other installed.

> Distributed "as is". Installing these packages does not by itself make a
> project 152-FZ compliant — the legal correctness of texts, documents, the
> cookie inventory and processing workflows remains the operator's
> responsibility.
