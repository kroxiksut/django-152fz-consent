"""System checks for the optional API app."""

from __future__ import annotations

from django.conf import settings as django_settings
from django.core.checks import Error, Tags, register

from django_consent_152fz import constants


@register(Tags.compatibility)
def check_api_base_app(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Ensure the optional API app is installed together with the base app."""
    installed_apps = set(getattr(django_settings, "INSTALLED_APPS", []))
    if "django_consent_152fz" in installed_apps:
        return []

    return [
        Error(
            f"'{constants.API_APP}' requires 'django_consent_152fz' in INSTALLED_APPS.",
            id="django_consent_152fz_api.E001",
        )
    ]
