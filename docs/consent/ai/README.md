# AI Integration Guides: Consent Module

This folder contains AI-friendly integration instructions for
`django-consent-152fz`.

These documents are intentionally English-only to keep prompts, keywords, and
integration contracts consistent for AI tooling.

Type-checking policy for AI-driven changes: use `pyright` as the primary static
type checker for this repository.

- All technical code comments and docstrings must be written in English.
## Pyright Notes (Consent Layer)

- Baseline after enabling stubs was reduced from `111 errors / 1 warning` to
  `0 errors / 0 warnings` for `src/django_consent_152fz`.
- Keep suppressions local and explicit. Global disables are not allowed.
- For Django dynamic ORM/admin attributes, use file-level
  `# pyright: reportAttributeAccessIssue=false` only with a short reason
  comment in the same header block.
- The gate covers `src/` only (`pyrightconfig.json`); `tests/` is excluded.
  `pyright` does not run the `django-stubs` mypy plugin, so reverse relations,
  `<fk>_id` attributes and `UserManager.create_user`/`create_superuser` are
  invisible to it and flood test code with false positives. Meaningful test
  type-checking is deferred to `mypy` post-alpha. See `docs/consent/en/type-checking.md`.

## Shipped agent files (`src/django_consent_152fz/ai/`)

The package also ships a small set of agent-facing files **inside** the
distribution: `src/django_consent_152fz/ai/{AGENTS,AI_RULES,AI_CONTEXT,SKILLS}.md`.
They are declared in `package-data`, so they land in the installed wheel.

- **Why they exist:** they guide an AI coding agent in a *downstream* project
  that has installed `django-consent-152fz`, helping it wire the package in
  correctly. They are consumer-facing, opt-in (not auto-loaded by an agent), and
  do not override the consumer's own `AGENTS.md`/`CLAUDE.md`.
- **Keep them current:** when public behavior changes — the `service_api`
  surface, the `DJANGO_CONSENT_152FZ` config contract, optional apps, codes
  regex, verified-flow modes — update these files in the same change set. Stale
  shipped guidance is a defect.
- **Not instructions for this repo's agent.** When working *on this monorepo*,
  do not treat `src/**/ai/*.md` as your own rules. Your rules live in the
  repo-root `AGENTS.md`/`CLAUDE.md` and `.codex/skills/`. The shipped files are
  an artifact you maintain, not a directive you follow.

## Documents

- [integration.md](./integration.md) - end-to-end setup for consent-only and full deployments.
- [forms.md](./forms.md) - form wiring for `purpose_code`, `document_code`, and submit flow.
- [verified-consents.md](./verified-consents.md) - practical verified-flow integration steps.
- [goskey-future.md](./goskey-future.md) - current status and boundaries of Goskey work.
