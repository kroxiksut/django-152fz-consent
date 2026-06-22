# Cookie module: quick start

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

This guide takes `django-cookies-152fz` from an empty install to a rendered,
consent-aware cookie banner. For the full settings reference see
[configuration.md](./configuration.md); for texts and visual variants see
[presentation.md](./presentation.md).

This package is deliberately standalone — it never imports the consent layer and
runs without `django-consent-152fz`.

> Distributed "as is". A working banner does not by itself make a project 152-FZ
> compliant — the legal correctness of the policy text and the cookie inventory
> remains the operator's responsibility.

## 1. Install

```bash
pip install django-cookies-152fz
```

Optional integration with the consent package:

```bash
pip install "django-cookies-152fz[consent]"   # pulls in django-consent-152fz
```

Compatibility: Python 3.10–3.14, Django 5.0 / 5.1 / 5.2 / 6.0 (`Django>=5,<7`).
Python 3.14 requires Django 5.2.8+ or Django 6.x.

## 2. Enable the app

```python
INSTALLED_APPS = [
    # ...
    "django_cookies_152fz",
]
```

## 3. Configure

Configured through the `DJANGO_COOKIES_152FZ` dictionary. A minimal working
profile:

```python
DJANGO_COOKIES_152FZ = {
    "enable_cookies": True,
    "cookie_banner": {
        "bootstrap_initial_revision": True,
        "banner_variant": "card",        # bar | card | modal
        "consent_ui_variant": "panel",   # inline | panel
        "text_preset": "ru_balanced",    # ru_balanced | ru_formal | ru_compact
    },
}
```

Banner, presentation and runtime keys (domains, bot handling, retention) are
documented in [configuration.md](./configuration.md). Cookie categories, the
integration registry and policy/banner revisions are managed in the Django admin.

## 4. Wire the URLs

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    path(
        "cookies/",
        include(
            ("django_cookies_152fz.urls", "django_cookies_152fz"),
            namespace="django_cookies_152fz",
        ),
    ),
]
```

This exposes the preferences page at `/cookies/`.

## 5. Migrate

```bash
python manage.py migrate
```

With `bootstrap_initial_revision: True` the initial cookie banner revision is
seeded on `post_migrate`. (The `bootstrap_152fz_cookie_defaults` management
command is also available.)

## 6. Render the banner

Load the tag library and render the banner once in your base template, just
before `</body>`:

```django
{% load cookies_tags %}
...
{% render_cookie_banner %}
</body>
```

The runtime gates non-essential scripts behind the matching consent. For the
DOM-event and server contract see [contracts.md](./contracts.md).

## Next steps

- [Lifecycle and server-layer configuration](./configuration.md)
- [Versioned texts and presentation](./presentation.md)
- [Usage, admin menu and settings](./operations-admin.md)
- [DOM events and server interception contract](./contracts.md)
- [Recommended inventory and restrictions](./inventory.md)
- [Key invariants](./invariants.md)
- [Demo environments](./demo.md)
