# Cookie Module AI Guide: Adding New Languages

This guide defines the required AI workflow when adding a new language to
`django-cookies-152fz`.

## When to use this guide

- Add a new cookie banner/policy language preset.
- Update existing translated cookie texts.
- Refactor locale fallback logic.

## Required workflow

1. Add default text presets in source:
   - banner presets in `src/django_cookies_152fz/models.py`
   - policy presets in `src/django_cookies_152fz/services.py`
2. Keep fallback deterministic:
   - map locale prefix (`ru`, `en`, etc.) to a default preset code
   - preserve a safe fallback to RU if unknown.
3. Update i18n catalogs:
   - edit `src/django_cookies_152fz/locale/*/LC_MESSAGES/django.po`
   - compile `.mo` in the same change set.
4. Add/adjust tests:
   - verify new presets exist after bootstrap
   - verify fallback does not break existing preset codes.
5. Update docs in both languages:
   - `docs/cookies/en/*`
   - `docs/cookies/ru/*`

## UTF-8 policy

- Use UTF-8 only.
- Do not apply cp1251/latin1 recoding scripts to “fix” text.
- If text is broken, repair source text directly in UTF-8.

## AI instruction mapping

- `AGENTS.md -> $django-152fz-cookie-banner`: banner text and UX presentation.
- `AGENTS.md -> $django-152fz-cookie-runtime`: runtime contracts and event behavior.
- `AGENTS.md -> $django-152fz-settings-checks`: locale-related config defaults and validation.
- `AGENTS.md -> $django-152fz-review`: pre-merge verification for regressions.
