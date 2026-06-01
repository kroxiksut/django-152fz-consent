"""AppConfig core consent-flow."""

from django.apps import AppConfig


class Django152FzConsentCoreConfig(AppConfig):
    """Registering a basic domain application."""

    # A separate `label` makes the internal application name stable and eliminates
    # intersections with other app labels in large Django projects.
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_consent_152fz.core"
    label = "django_consent_152fz_core"
    verbose_name = "152-FZ Consent Core"
