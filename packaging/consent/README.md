# django-consent-152fz

Consent lifecycle for Django projects that must comply with Russian Federal Law
**152-FZ** on personal data. Versioned legal documents, processing purposes,
immutable consent records and audit log, subject self-service, an optional
verified/paper-consent flow, and an optional DRF API.

This package is one of two independent distributions shipped from a single
repository. The companion package `django-cookies-152fz` (cookie banner and
runtime) installs and runs separately — neither requires the other.

## Why

152-FZ requires anyone processing the personal data of people in Russia —
including foreign companies with Russian users — to collect and manage consent,
keep an auditable record of it, and version the legal texts behind it. This
package provides those building blocks so you wire in your purposes, documents
and texts, and it handles the workflow, state and audit.

> Distributed "as is". The package does not by itself guarantee legal
> compliance — the correctness of texts and processing workflows remains the
> operator's responsibility.

## Installation

```bash
pip install django-consent-152fz
```

Optional extras:

```bash
pip install "django-consent-152fz[api]"   # DRF API endpoints
pip install "django-consent-152fz[pdf]"   # PDF generation for paper/verified consents (ReportLab)
```

The core depends only on Django. DRF and ReportLab are pulled in only when you
ask for them.

## Compatibility

- **Python:** 3.10 – 3.12
- **Django:** 5.0, 5.1, 5.2 (LTS), 6.0 — declared as `Django>=5,<7`

Verified in CI on Python 3.10 + Django 5.x and Python 3.12 + Django 6.x, and on
the project demo sites.

## Quick start

Add the app(s) to `INSTALLED_APPS`. Optional features are turned on by adding
their app, not just a flag:

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",                  # core (always)
    "django_consent_152fz.api",              # optional DRF API
    "django_consent_152fz.verified_consents",  # optional verified/paper flow
]
```

Configure via top-level Django settings keys (validated early into a predictable
contract):

```python
DJANGO_CONSENT_152FZ = {
    # purposes, documents, codes, self-service options, ...
}
USE_API_152FZ = True  # mount the API when the api app is installed and DRF is importable
```

Then run migrations. Sample documents and starter purposes are bootstrapped on
`post_migrate`.

External integrations should call the stable facade in
`django_consent_152fz.service_api` rather than importing `core.services`
directly.

## Using with an AI agent

The package ships agent-facing guidance inside the installed distribution at
`django_consent_152fz/ai/` (`AGENTS.md`, `AI_RULES.md`, `AI_CONTEXT.md`,
`SKILLS.md`). If you integrate with the help of an AI coding agent, point it at
those files — for example, reference them from your project's `CLAUDE.md`:

```
@<site-packages>/django_consent_152fz/ai/AGENTS.md
```

They are opt-in: not loaded automatically, and they do not override your own
project's agent rules.

## Documentation

Full bilingual (EN/RU) documentation, configuration reference, invariants,
migration and operations guides live in the project repository:
<https://github.com/kroxiksut/django-152fz-consent> (see `docs/consent/`).

## License

MIT.

---

## Описание (RU)

`django-consent-152fz` — жизненный цикл согласий на обработку персональных
данных для Django-проектов под требования **152-ФЗ**: версионируемые правовые
документы, цели обработки, неизменяемые записи согласий и аудит-лог,
самообслуживание субъекта, опциональный поток верифицированных (бумажных)
согласий и опциональный DRF API.

Пакет — один из двух независимых дистрибутивов репозитория. Соседний пакет
`django-cookies-152fz` (баннер cookie и runtime) устанавливается и работает
отдельно: ни один не требует другого.

**Установка:** `pip install django-consent-152fz`
(extra: `[api]` — DRF API, `[pdf]` — генерация PDF для бумажных согласий).

Ядро зависит только от Django; DRF и ReportLab подключаются опционально.
Поддержка: Python 3.10–3.12, Django 5.0–6.0.

> Пакет распространяется «как есть» и сам по себе не гарантирует юридическое
> соответствие — корректность текстов и процессов остаётся ответственностью
> оператора.

Полная двуязычная документация — в репозитории проекта (`docs/consent/`).
