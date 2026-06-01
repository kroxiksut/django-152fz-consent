# Demo Site: Training Center

[Русская версия](./README.ru.md)

This directory contains the demo project and materials used to validate integration of:

- `django-cookies-152fz` (cookie module),
- `django-consent-152fz` (consent layer adapted to Russian 152-FZ scenarios).

## What this demo shows

- Public pages for a training center website.
- Courses catalog.
- Two-step course signup flow (`django-formtools`).
- Contact form.
- Registration, login, logout, and profile (`django-allauth`).
- Bootstrap-based UI (`django-bootstrap5`).
- RU/EN localization.
- Package integration after baseline site readiness.
- Consent capture in course signup, contact, and account-related flows.
- Verification of records in Django admin.

## Delivery order (important)

Work is split into three phases for each Django version.

### Phase A. Baseline site (without consent/cookies modules)

Install only:

- Django,
- `django-allauth`,
- `django-formtools`,
- `django-bootstrap5`.

At this stage do not add package apps, package URLs, or consent/cookie logic.
Forms and account flows must work standalone.

### Phase B. Cookie layer integration

Only after baseline smoke tests pass, add integration:

- editable dependency `-e ../..`,
- `django_cookies_152fz` in `INSTALLED_APPS`,
- `DJANGO_COOKIES_152FZ` settings,
- package URLs,
- package migrations,
- cookie banner and preferences UI,
- regression check that baseline site still works.

Documentation:

- Cookies (EN): [../docs/cookies/en/README.md](../docs/cookies/en/README.md)
- Cookies AI guides: [../docs/cookies/ai/README.md](../docs/cookies/ai/README.md)

At this stage consent capture in business forms can still remain disabled.

### Phase C. Consent layer integration

Only after cookie layer validation, enable consent scenarios:

- consent blocks in forms and account flows,
- linking demo submissions with consent records,
- admin verification of consent records.

Documentation:

- Consent (EN): [../docs/consent/en/README.md](../docs/consent/en/README.md)
- Consent AI guides: [../docs/consent/ai/README.md](../docs/consent/ai/README.md)

## Directory structure

```text
demo/
  README.md
  README.ru.md
  common/
    templates/
    static/
    fixtures/
    texts/
    locale/
  django5/
    manage.py
    requirements.txt
    demo_site/
    training_center/
  django6/
    manage.py
    requirements.txt
    demo_site/
    training_center/
  notes/
```

## Main directories

- `common/`: shared templates, static files, fixtures, texts, locales.
- `django5/`: dedicated Django 5.x demo instance.
- `django6/`: dedicated Django 6.x demo instance.
- `notes/`: smoke-checklist and version-difference notes.

## Shared layer policy

Both Django 5.x and 6.x must validate the same shared website behavior.
Common UI/text/fixtures should be reused from `common/`.
Version-specific settings and Python app code stay in `django5/` and `django6/`.

## Localization policy

- Short UI strings: Django i18n (`{% trans %}`, `.po/.mo`).
- Long legal/demo texts: stored under `common/texts/ru/` and `common/texts/en/`.

## Quick start

### Django 5 (Linux/macOS)

```bash
cd demo/django5
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Django 5 (Windows PowerShell)

```powershell
cd demo\django5
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Django 6 (Linux/macOS)

```bash
cd demo/django6
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Django 6 (Windows PowerShell)

```powershell
cd demo\django6
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Optional: conda workflow

If you prefer conda, run the same commands via your conda environment.
