# SKILLS — django-cookies-152fz

Task recipes for integrating the package. Obey [`AI_RULES.md`](./AI_RULES.md)
throughout; background in [`AI_CONTEXT.md`](./AI_CONTEXT.md).

## Install and enable (standalone)

```bash
pip install django-cookies-152fz                 # Django only
pip install "django-cookies-152fz[consent]"      # + umbrella consent integration
```

```python
INSTALLED_APPS = [
    # ...
    "django_cookies_152fz",
]

DJANGO_COOKIES_152FZ = {
    # cookie_banner, cookie_runtime, cookie_retention, ...
}
```

Then `include("django_cookies_152fz.urls")`, run `python manage.py migrate`
(bootstraps the initial banner revision), and render the banner.

## Full mode with the consent package

When `django-consent-152fz` is also installed, prefer shared project routing
through the consent URLs, while cookie ownership stays in the cookie module. The
cookie package still must not import the consent layer.

## Brand the banner

1. Clone the starter `CookieBannerRevision` into a custom draft.
2. Set `banner_variant` / `consent_ui_variant` and a text preset.
3. Tune color preset / custom colors, spacing and overlay.
4. Validate mobile overrides.
5. Publish the revision.
6. Only then add custom CSS (`custom_css_url`) if design-system alignment needs
   it. Use custom JS (`custom_js_url`) only for behavior on top of the module
   contract — never to replace consent-state logic.

## Gate scripts at runtime

1. Register optional cookies/scripts in the runtime registry.
2. Rely on default-deny: optional scripts run only after a valid consent state;
   deny is re-applied on outdated/withdrawn states.
3. Configure bot handling explicitly via `cookie_runtime`
   (`hide_for_bots`, `bot_patterns`, `user_agent_mode`).
4. Keep the DOM event contract stable; hook project behavior onto it.

## Add a language

1. Add default text presets in source: banner presets in the models layer,
   policy presets in the services layer.
2. Keep fallback deterministic: map the locale prefix (`ru`, `en`, …) to a
   default preset code, with a safe fallback to RU for unknown locales.
3. Update `locale/*/LC_MESSAGES/django.po` and recompile `.mo` in the same
   change set.
4. Add tests: presets exist after bootstrap; fallback does not break existing
   preset codes.
5. Update docs in both languages under `docs/cookies/en/` and
   `docs/cookies/ru/`.

## Always

- Keep the package standalone — do not import the consent layer.
- UTF-8 only; repair broken text at source, never recode.
