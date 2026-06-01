from __future__ import annotations

from django.core.checks import Error
from django.test import override_settings

from django_cookies_152fz import checks


@override_settings(
    INSTALLED_APPS=[
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "django_cookies_152fz",
    ]
)
def test_cookie_checks_do_not_require_consent_app_in_standalone_mode() -> None:
    result = checks.check_cookies_base_app(None)
    assert not any(isinstance(item, Error) for item in result)
