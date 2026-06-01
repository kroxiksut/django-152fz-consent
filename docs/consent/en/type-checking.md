# Consent module: type checking with Pyright

- [Back to consent docs](./README.md)
- [Back to project docs](../../README.md)

## Why Pyright is required

The consent module carries domain-critical logic:
- consent status decisions,
- re-consent transitions,
- withdrawal behavior,
- service API contracts.

Type errors in these paths can create silent runtime regressions.  
`pyright` helps catch mismatched payloads, optional/null handling issues, and broken contracts before tests or production traffic.

## What to check

- Service layer function signatures and return types.
- Model-related helper types (`Optional`, union branches, typed dict payloads).
- Public API boundary payload shapes.
- Integration points where consent and cookie modules exchange structured data.

## Scope: source code only (`src/`), not tests

The gate (`pyrightconfig.json`) covers `src/` only; `tests/` is intentionally excluded. This is a limitation of the tool, not a coverage gap:

- `pyright` reads Django types from the static `django-stubs` package but does **not** run the `django-stubs` *mypy plugin*. That plugin is what teaches a type checker about Django's dynamic ORM surface: reverse relations (`record.events`, `purpose.audience_rules`), auto-generated foreign-key id attributes (`user_id`, `purpose_id`, `document_id`), the default `UserManager.create_user`/`create_superuser`, and custom `ModelAdmin` actions.
- In `src/` those few dynamic accesses are handled with narrow, commented suppressions. Test code uses them pervasively (fixtures create users; assertions read reverse relations and `*_id` fields), which produced ~160 `reportAttributeAccessIssue`/index false positives with **zero** real source bugs — noise that would bury a genuine regression.
- Meaningful type checking of tests therefore needs the `django-stubs` mypy plugin (i.e. `mypy`), which is deferred to post-alpha. Until then `tests/` stays out of the gate to keep the signal clean.

You can still type-check tests ad hoc (expect django-stubs friction):

```bash
pyright tests
```

## Required contributor workflow

Before opening a PR:
1. Run tests.
2. Run lint checks.
3. Run `pyright` and fix reported type issues.

`pyright` is a mandatory quality gate for this repository.

## Typical commands

Linux/macOS:

```bash
python -m pytest
ruff check src tests
pyright
```

Windows PowerShell:

```powershell
python -m pytest
ruff check src tests
pyright
```

## Related documents

- [Contributing to the consent module](./contributing.md)
- [Testing the consent module](./testing.md)
- [Public service API and transport contract](./service-api.md)
