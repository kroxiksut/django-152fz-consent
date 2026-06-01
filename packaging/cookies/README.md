# django-cookies-152fz

Cookie banner and runtime for Django projects that must comply with Russian
Federal Law **152-FZ**. Consent-gated script execution, a runtime cookie
registry, versioned policy revisions, a cookie audit, flexible branding and
mobile-friendly banner variants.

This package is deliberately standalone: it holds its own integration contract
and config and never imports the consent layer, so it installs and runs without
`django-consent-152fz`. It is one of two independent distributions shipped from
a single repository.

## Why

152-FZ (and Russian cookie-consent practice) requires sites serving users in
Russia to obtain and record cookie consent and to gate non-essential scripts
behind it. This package provides a ready banner, a consent-aware runtime, and an
audit trail — you supply the policy text and the cookie inventory.

> Distributed "as is". The package does not by itself guarantee legal
> compliance — the correctness of texts and the cookie inventory remains the
> operator's responsibility.

## Installation

```bash
pip install django-cookies-152fz
```

Optional integration with the consent package:

```bash
pip install "django-cookies-152fz[consent]"   # pulls in django-consent-152fz
```

## Compatibility

- **Python:** 3.10 – 3.12
- **Django:** 5.0, 5.1, 5.2 (LTS), 6.0 — declared as `Django>=5,<7`

Verified in CI on Python 3.12 + Django 6.x (standalone, without the consent
package installed) and on the project demo sites.

## Quick start

```python
INSTALLED_APPS = [
    # ...
    "django_cookies_152fz",
]

DJANGO_COOKIES_152FZ = {
    # banner branding, cookie inventory, policy options, ...
}
```

Run migrations — the initial cookie banner revision is bootstrapped on
`post_migrate`. Render the banner and gate scripts through the package's
consent-aware runtime (see the docs).

## Using with an AI agent

The package ships agent-facing guidance inside the installed distribution at
`django_cookies_152fz/ai/` (`AGENTS.md`, `AI_RULES.md`, `AI_CONTEXT.md`,
`SKILLS.md`). If you integrate with the help of an AI coding agent, point it at
those files — for example, reference them from your project's `CLAUDE.md`:

```
@<site-packages>/django_cookies_152fz/ai/AGENTS.md
```

They are opt-in: not loaded automatically, and they do not override your own
project's agent rules.

## Documentation

Full bilingual (EN/RU) documentation, configuration reference, inventory and
operations guides live in the project repository:
<https://github.com/kroxiksut/django-152fz-consent> (see `docs/cookies/`).

## License

MIT.

---

## Описание (RU)

`django-cookies-152fz` — баннер cookie и runtime для Django-проектов под
требования **152-ФЗ**: запуск скриптов с учётом согласия, runtime-реестр cookie,
версионирование редакций политики, аудит cookie, гибкий брендинг и
мобильные варианты баннера.

Пакет намеренно автономен: содержит собственный контракт интеграции и конфиг,
не импортирует слой согласий и работает без `django-consent-152fz`. Это один из
двух независимых дистрибутивов репозитория.

**Установка:** `pip install django-cookies-152fz`
(extra: `[consent]` — подключает `django-consent-152fz` для совместной работы).

Поддержка: Python 3.10–3.12, Django 5.0–6.0.

> Пакет распространяется «как есть» и сам по себе не гарантирует юридическое
> соответствие — корректность текстов и инвентаризации cookie остаётся
> ответственностью оператора.

Полная двуязычная документация — в репозитории проекта (`docs/cookies/`).
