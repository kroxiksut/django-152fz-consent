# Cookie Runtime Guide (AI)

## Purpose

Define runtime behavior for consent-gated script loading and cleanup.

## Required principles

- Default deny for optional scripts.
- Explicit allow only after valid consent state.
- Re-apply deny behavior on outdated/withdrawn states.

## Runtime settings focus

Use `DJANGO_COOKIES_152FZ["cookie_runtime"]` for:

- `force_banner`
- `preview_param`
- `custom_css_url`
- `custom_js_url`
- `hide_for_bots`
- `bot_patterns`
- `user_agent_mode`
- shared domain options

## Cleanup and retention

Use `cookie_retention` settings for lifecycle cleanup policies.
Keep cleanup idempotent and auditable.

## Integration safety

- Avoid direct mutation of internal runtime payload contracts.
- Keep DOM event contract stable for project hooks.
- Validate behavior in desktop/mobile regressions before release.

