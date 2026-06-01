# Cookie module: type checking with Pyright

- [Back to cookie docs](./README.md)
- [Back to project docs](../../README.md)

## Why Pyright is required

The cookie module contains runtime-sensitive behavior:
- consent-gated script decisions,
- banner state transitions,
- policy/revision wiring,
- event contract payload composition.

Type drift in these paths can break runtime behavior without immediate syntax errors.  
`pyright` catches these issues early by validating typed contracts.

## What to check

- Runtime payload structures and event data objects.
- Service signatures for cookie decisions and registry usage.
- View/form data types for preferences and banner actions.
- Boundaries between cookie runtime and shared/public service APIs.

## Scope: source code only (`src/`), not tests

The gate (`pyrightconfig.json`) covers `src/` only; `tests/` is intentionally excluded. This is a limitation of the tool, not a coverage gap:

- `pyright` reads Django types from the static `django-stubs` package but does **not** run the `django-stubs` *mypy plugin*. That plugin is what teaches a type checker about Django's dynamic ORM surface: reverse relations (`record.events`, `policy.registry_items`), auto-generated foreign-key id attributes (`user_id`, `policy_revision_id`, `registry_item_id`), the default `UserManager.create_user`/`create_superuser`, and custom `ModelAdmin` actions.
- In `src/` those few dynamic accesses are handled with narrow, commented suppressions. Test code uses them pervasively (fixtures create users; assertions read reverse relations and `*_id` fields), which produced false positives with **zero** real source bugs — noise that would bury a genuine regression.
- Meaningful type checking of tests therefore needs the `django-stubs` mypy plugin (i.e. `mypy`), which is deferred to post-alpha. Until then `tests/` stays out of the gate to keep the signal clean.

A known source-side typing weakness tracked separately: `get_cookie_banner_configuration()` returns `dict[str, object]`, so nested config keys are not type-safe yet — a `TypedDict` contract is planned.

You can still type-check tests ad hoc (expect django-stubs friction):

```bash
pyright tests
```

## Required contributor workflow

Before opening a PR:
1. Run tests.
2. Run lint checks.
3. Run `pyright` and resolve type issues.

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

- [Contributing to the cookie module](./contributing.md)
- [Testing the cookie module](./testing.md)
- [Event contract and integration hooks](./contracts.md)
