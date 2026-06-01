<p align="center">
  <img src="docs/assets/logo/dj-152fz-logo.png" alt="django-152fz" width="220">
</p>

<h1 align="center">django-consent-152fz repository: consent and cookie modules for 152-FZ workflows</h1>

<p align="center">
  <img alt="Consent package" src="https://img.shields.io/badge/django--consent--152fz-1.0.0-blue">
  <img alt="Cookies package" src="https://img.shields.io/badge/django--cookies--152fz-1.0.0-blue">
  <img alt="Package status" src="https://img.shields.io/badge/status-stable-blue">
  <img alt="Python versions" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="Django versions" src="https://img.shields.io/badge/django-5.x%20%7C%206.x-0C4B33">
  <img alt="Type checking" src="https://img.shields.io/badge/type%20checking-pyright-2E6BE6">
  <img alt="Test coverage" src="https://img.shields.io/badge/coverage-pending-lightgrey">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

`django-consent-152fz` is a repository with two independent Django packages:

- `django-consent-152fz`: consent lifecycle, document revisions, audit, subject self-service, optional verified-consent flow, service API.
- `django-cookies-152fz`: cookie banner, policy revisions, runtime registry, consent-aware script execution, cookie audit, flexible branding, and mobile-friendly variants.

The two packages work independently - install either one on its own. If you only need the consent lifecycle, you can keep any cookie banner you already use (or any other cookie solution); if you only need a cookie banner, you can install the cookies package without the consent module. They align under a common 152-FZ context but do not require each other.

> **Disclaimer:** this package is a technical tool, not legal advice. Installing it does not by itself make a project 152-FZ compliant - the legal correctness of your texts, documents, and processing workflows remains the operator's responsibility (directly or through legal counsel). See [Legal notice](#legal-notice) and [Commercial support](#commercial-support).

## Why this project

Russia's Federal Law 152-FZ requires anyone who processes the personal data of people in Russia - including foreign companies with Russian users or a presence in the Russian market - to collect and manage consent, keep an auditable record of it, and handle cookie consent. Building those controls from scratch in Django is repetitive and easy to get wrong.

This repository provides ready-made, reusable building blocks for exactly that: a versioned consent lifecycle with an immutable audit log, a cookie banner with consent-gated script execution, an optional verified-consent flow, and admin and self-service tooling. You wire in your purposes, documents, and texts; the package handles the workflow, state, and audit - so an international team ships 152-FZ controls faster instead of reinventing them.

Related legal context references:

- [DLA Piper Data Protection Laws of the World (Russia)](https://www.dlapiperdataprotection.com/?c=RU)
- [Russia Data Localization Law overview](https://captaincompliance.com/education/russia-data-localization-law)

## Versioning note

`django-consent-152fz` and `django-cookies-152fz` can have different versions and release cadence.  
They are functionally separated modules and do not hard-couple each other's lifecycle, while still being aligned under a common 152-FZ legal implementation context.

## Installation

Consent only:

```bash
pip install django-consent-152fz
```

Cookies only:

```bash
pip install django-cookies-152fz
```

Both modules:

```bash
pip install django-consent-152fz django-cookies-152fz
```

If API endpoints are needed:

```bash
pip install "django-consent-152fz[api]"
```

## Documentation

- [Project documentation (EN)](./docs/README.md)
- [Project documentation (RU)](./docs/README.ru.md)
- [Russian README](./README.ru.md)
- [AI-friendly guides (English only)](./docs/consent/ai/README.md)
- [Changelog](./CHANGELOG.md)
- [Contributing](./CONTRIBUTING.md)
- [Security policy](./SECURITY.md)
- [Translation contributions](./docs/i18n/README.md)
- [Legal text inventory and review map](./docs/legal-texts.md)

Russian legal texts and cookie policy templates can be replaced with texts for other jurisdictions. See the [legal text inventory and review map](./docs/legal-texts.md) for where these texts live and how to review them, and the module docs for authoring and configuration.

## Translations and internationalization

The packages ship with Russian (`ru`) and English (`en`) and use Django's `gettext`, so adding a locale is just a new `.po`/`.mo` pair - no code changes required.

How portable each package is differs, though:

- **`django-cookies-152fz` is largely jurisdiction-neutral.** It implements generic mechanics (cookie categories, policy revisions, consent-gated script execution, audit), so adapting it to another jurisdiction is mostly a matter of texts and locale.
- **`django-consent-152fz` is more specific to 152-FZ.** Its core (documents, revisions, consent records, immutable audit, self-service) is reusable, but some parts are deliberately Russia-oriented - notably the verified/paper-consent flow and the Госключ (GosKey) e-signature path - which have no direct equivalent elsewhere and would need rework, not just translation.

Translations into other languages and adaptations for other jurisdictions (PIPL, GDPR, and similar) are welcome - open an issue to coordinate, then send a pull request. See [Translation contributions](./docs/i18n/README.md) for the workflow, and the [legal text inventory](./docs/legal-texts.md) for which texts are jurisdiction-specific.

**Note:** a translation localizes the user interface, not legal compliance. Using the package in another jurisdiction requires that jurisdiction's own legal review (see [Legal notice](#legal-notice)).

## Support

- Community support - GitHub Issues
- Commercial support - contact author
- Legal & technical consulting - on request

## Commercial support

This project is distributed as open-source.

The authors may provide commercial implementation and adaptation services for this package.

Possible engagement areas:

- technical integration into existing systems;
- adaptation to business processes;
- consent and cookie workflow setup;
- implementation architecture and rollout support;
- adaptation for websites, mobile applications, and other platforms;
- integration into existing CMS and frameworks;
- technical implementation support and, where needed, legal advisory on applying 152-FZ together with practicing lawyers;
- adaptation for different jurisdictions;
- custom solution development and support.

Authors allow adaptation of ideas and implementations from this project for other languages, platforms, engines, and technology stacks when required.

The package is built with reference to the requirements of Russian personal data law (152-FZ) and to the practice of comparable solutions, as current at the time of each release. Compliance, however, depends on how the operator configures and uses the package and which texts and processes it adopts - so the package is distributed "as is" and does not by itself guarantee automatic legal compliance. The legal correctness of documents, texts, and processing workflows is the operator's responsibility - directly or through their legal counsel.

The paid implementation and legal-support services described above are provided separately and are not part of the package: the authors cover the technical side, practicing lawyers cover the legal side.

For implementation and support requests, contact the project authors.

## Legal notice

This project is not affiliated with any government authority.

Users remain responsible for determining applicable legal requirements and obtaining independent legal advice where necessary.

