# Cookie Branding Guide (AI)

## Goal

Personalize banner look and text without breaking runtime contracts.

## Primary mechanism

Use `CookieBannerRevision` as the source of truth for:

- variants (`banner_variant`, `consent_ui_variant`)
- text presets
- color preset and custom colors
- spacing and overlay
- mobile overrides

## Safe workflow

1. Clone starter revision into custom draft.
2. Set variant and text preset.
3. Tune colors and spacing.
4. Validate mobile overrides.
5. Publish revision.
6. Only then add custom CSS if needed.

## When to use custom CSS/JS

- Use custom CSS for design-system alignment.
- Use custom JS only for project-specific behavior on top of module contract.
- Do not replace consent-state logic with front-end-only code.

