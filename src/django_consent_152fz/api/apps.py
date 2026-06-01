"""AppConfig for the optional API app."""

from django.apps import AppConfig
from django.conf import settings as django_settings

from django_consent_152fz import constants


class Django152FzConsentApiConfig(AppConfig):
    """AppConfig for the optional API app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = constants.API_APP
    label = "django_consent_152fz_api"
    verbose_name = "152-FZ Consent API"

    def ready(self) -> None:
        from . import checks  # noqa: F401

        if getattr(django_settings, constants.SETTING_USE_API, False) is not True:
            return

        from .dependencies import require_drf

        require_drf()
