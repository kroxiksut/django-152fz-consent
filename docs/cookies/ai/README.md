# AI Integration Guides: Cookie Module

This folder contains AI-friendly integration instructions for
`django-cookies-152fz`.

These documents are intentionally English-only to keep prompts, keywords, and
integration contracts consistent for AI tooling.

Type-checking policy for AI-driven changes: use `pyright` as the primary static
type checker for this repository.

- All technical code comments and docstrings must be written in English.
## Pyright Notes (Cookies Layer)

- `src/django_cookies_152fz` is validated with `pyright` at `0 errors / 0 warnings`.
- Keep suppressions local and explicit; do not use global ignore switches.
- For Django dynamic ORM/admin runtime points, use file-level pyright directives
  only with a short reason comment.
- The gate covers `src/` only (`pyrightconfig.json`); `tests/` is excluded.
  `pyright` does not run the `django-stubs` mypy plugin, so reverse relations,
  `<fk>_id` attributes and `UserManager.create_user`/`create_superuser` are
  invisible to it and flood test code with false positives. Meaningful test
  type-checking is deferred to `mypy` post-alpha. See `docs/cookies/en/type-checking.md`.

## Shipped agent files (`src/django_cookies_152fz/ai/`)

The package also ships a small set of agent-facing files **inside** the
distribution: `src/django_cookies_152fz/ai/{AGENTS,AI_RULES,AI_CONTEXT,SKILLS}.md`.
They are declared in `package-data`, so they land in the installed wheel.

- **Why they exist:** they guide an AI coding agent in a *downstream* project
  that has installed `django-cookies-152fz`, helping it wire the package in
  correctly. They are consumer-facing, opt-in (not auto-loaded by an agent), and
  do not override the consumer's own `AGENTS.md`/`CLAUDE.md`.
- **Keep them current:** when public behavior changes — the standalone boundary,
  the `DJANGO_COOKIES_152FZ` config contract, runtime default-deny, banner
  revision branding, locale fallback — update these files in the same change
  set. Stale shipped guidance is a defect.
- **Not instructions for this repo's agent.** When working *on this monorepo*,
  do not treat `src/**/ai/*.md` as your own rules. Your rules live in the
  repo-root `AGENTS.md`/`CLAUDE.md` and `.codex/skills/`. The shipped files are
  an artifact you maintain, not a directive you follow.

## Documents

- [integration.md](./integration.md) - standalone and full cookie module setup.
- [branding.md](./branding.md) - banner personalization workflow and safe theming.
- [runtime.md](./runtime.md) - runtime behavior, strict-default-deny, and cleanup.
- [languages.md](./languages.md) - adding new cookie languages, UTF-8 rules, and i18n workflow.
