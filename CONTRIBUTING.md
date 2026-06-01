# Contributing

Thanks for contributing to `django-consent-152fz`.

> **Security issues:** do not report vulnerabilities through public issues or pull
> requests. Follow the [security policy](./SECURITY.md) for private reporting.

## Environment

- Python: `>=3.10`
- Supported Django: `5.x`, `6.x`
- Any environment manager is allowed (`venv`, `virtualenv`, `conda`, `poetry`, etc.).

## Environment setup

### Linux/macOS (`venv`)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
```

### Windows PowerShell (`venv`)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
```

### Any OS (`conda`)

```bash
conda create -n py312-152fz python=3.12 -y
conda activate py312-152fz
python -m pip install -U pip
python -m pip install -e .[dev]
```

Optional matrix checks:
- For Django 5: Python `3.10+`
- For Django 6: Python `3.12+`

Example commands (Linux/macOS, `venv`):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
python -m pytest
ruff check src tests
pyright
```

Example commands (Windows PowerShell, `venv`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
python -m pytest
ruff check src tests
pyright
```

Example commands (Windows PowerShell, `conda`):

```powershell
conda run -n py312-152fz python -m pytest
conda run -n py312-152fz ruff check src tests
conda run -n py312-152fz pyright
```

## Before opening a pull request

1. Run tests locally and make sure they pass.
2. Check for regressions across core/cookies/api boundaries.
3. Update documentation to match behavior changes.
4. If file structure changed, update `STRUCTURE.md`.
5. Run `pyright` locally. Type checking is a required gate.

## Code and docs rules

- New behavior must include tests (unit/integration level as needed).
- Translation contributions are welcome and reviewed as first-class changes.
- For translation workflow and requirements, see [docs/i18n/README.md](./docs/i18n/README.md).
- If `.po` files were changed, rebuild locale binaries before package build/publish:
  `python -m django compilemessages --ignore .venv --ignore node_modules --ignore build --ignore dist`.
- A change that updates `.po` is incomplete without updated `.mo` files in the same change set.

## Scope references

Before large changes, check:

- `README.md` (public scope),
- module docs under `docs/`,
- contribution and translation guides.

## Commit messages

Preferred prefixes:

- `core: ...`
- `cookies: ...`
- `api: ...`
- `docs: ...`
- `tests: ...`

Each message should state what changed and why.
