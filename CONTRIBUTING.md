# Contributing

Thanks for contributing to `django-consent-152fz`.

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
conda create -n django152fz-py312 python=3.12 -y
conda activate django152fz-py312
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
```

Example commands (Windows PowerShell, `venv`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
python -m pytest
ruff check src tests
```

Example commands (Windows PowerShell, `conda`):

```powershell
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' run -n py312-152fz python -m pytest
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' run -n py312-152fz ruff check src tests
```

## Before opening a pull request

1. Run tests locally and make sure they pass.
2. Check for regressions across core/cookies/api boundaries.
3. Update documentation to match behavior changes.
4. If file structure changed, update `STRUCTURE.md`.
5. If roadmap status changed, update `TASKS.md`.

## Code and docs rules

- Domain invariants: `ARCHITECTURE.md`.
- Repository development rules: `AI_RULES.md`.
- New behavior must include tests (unit/integration level as needed).
- Translation contributions are welcome and reviewed as first-class changes.
- For translation workflow and requirements, see [docs/i18n/README.md](./docs/i18n/README.md).

## What to commit from AI/meta files

- Commit repository-level guidance that is part of project process (for example: `AGENTS.md`, stable architecture docs, contribution docs).
- Do not commit local tool state or private assistant workspace files.
- Respect `.gitignore` as the source of truth for local/generated artifacts.

## Scope references

Before large changes, check:

- `README.md` (public scope),
- `TASKS.md` (roadmap and statuses),
- `AI_CONTEXT.md` (product boundaries),
- `AI_RULES.md` (architecture and process constraints).

## Commit messages

Preferred prefixes:

- `core: ...`
- `cookies: ...`
- `api: ...`
- `docs: ...`
- `tests: ...`

Each message should state what changed and why.
