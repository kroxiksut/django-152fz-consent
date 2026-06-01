"""AppConfig for the optional verified consents app.

This app does not live on its own: it extends `core` with stricter consent
verification flows and is only enabled when the project turns it on explicitly.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from django_consent_152fz import constants


class VerifiedConsentsConfig(AppConfig):
    """Django app configuration for verified consents."""

    default_auto_field = "django.db.models.BigAutoField"
    name = constants.VERIFIED_CONSENTS_APP
    verbose_name = _("Подтверждённые согласия 152-ФЗ")

    def ready(self) -> None:
        """Connect system checks for the optional app when Django starts."""
        from . import checks  # noqa: F401
