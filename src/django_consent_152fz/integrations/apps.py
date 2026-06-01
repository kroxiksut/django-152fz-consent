"""AppConfig for the integrations subpackage."""

from django.apps import AppConfig


class Django152FzConsentIntegrationsConfig(AppConfig):
    """Register the extension points layer as a separate app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_consent_152fz.integrations"
    label = "django_consent_152fz_integrations"
    verbose_name = "152-FZ Consent Integrations"
