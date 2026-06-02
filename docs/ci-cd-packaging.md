# CI/CD: separate package builds

This repository builds packages separately in CI/CD for the monorepo layout.

## Why builds are split

The repository contains two independent distributions:

- `django-consent-152fz`
- `django-cookies-152fz`

They can have different versions and release cadence.  
Separate CI jobs keep boundaries explicit and prevent accidental cross-package leaks.

## The three `pyproject.toml` files

The repository has three `pyproject.toml` files with distinct, non-overlapping roles:

| File | Builds | Published to PyPI? |
|------|--------|--------------------|
| `packaging/consent/pyproject.toml` | only the `django-consent-152fz` wheel | **yes** |
| `packaging/cookies/pyproject.toml` | only the `django-cookies-152fz` wheel | **yes** |
| root `pyproject.toml` | both packages from `src/` together | **no** |

The **root** `pyproject.toml` is for **development and tooling**, not for release:

- editable install for development — `pip install -e ".[dev,test,api]"` (installs both
  packages from `src/` so tests can import consent and cookies together);
- it is what every CI lint/test job installs from;
- it holds the shared tool config that the per-package files do not need:
  `[tool.ruff]` (lint + format) and `[tool.pytest.ini_options]`
  (`DJANGO_SETTINGS_MODULE = "tests.settings"`, markers).

The two **`packaging/*`** files are **release-only build configs**: each produces exactly
one wheel for PyPI. Release artifacts come from these, never from the root file.

## What CI does

In `.github/workflows/ci.yml`, CI runs dedicated jobs:

- `package-consent`: builds consent wheel from `packaging/consent`.
- `package-cookies`: builds cookies wheel from `packaging/cookies`.
- `package-install-smoke`: installs both built wheels and runs a smoke check.

CI also validates artifact contents so that:

- consent wheel contains `django_consent_152fz/*` and does not include cookies package files;
- cookies wheel contains `django_cookies_152fz/*` and does not include consent package files.

CI also runs a dedicated `coverage` job in a single reference environment
(Python `3.12` + Django `6.x`), generates `coverage.xml` with `pytest-cov`,
and uploads the report to Codecov. The README coverage badge reads from that
Codecov project instead of a hard-coded value.

## Why this matters

- Reduces release risk for module-isolated changes.
- Keeps install contracts predictable for users.
- Supports independent module evolution in one repository.

## Local equivalent checks

```bash
python -m pip install -U build
python -m build --wheel --no-isolation --outdir dist/consent packaging/consent
python -m build --wheel --no-isolation --outdir dist/cookies packaging/cookies
```

Then validate wheel contents and run install smoke checks.

## Related docs

- [Project documentation index](./README.md)
- [Consent module docs](./consent/en/README.md)
- [Cookie module docs](./cookies/en/README.md)
