"""Root AppConfig for the package.

This module was introduced during the initial scaffold stage (section 3.1),
but its role is not limited to registering the Django application. Through
`ready()`, we connect system checks and post-migrate hooks that validate the
optional-module configuration in advance and, when needed, perform a safe
bootstrap of starter data after migrations have been applied.
"""

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class Django152FzConsentConfig(AppConfig):
    """Home AppConfig for the entire consent package."""

    # BigAutoField is the default modern behavior for all new package models.
    # This avoids carrying legacy settings forward from older versions.
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_consent_152fz"
    verbose_name = _("152-FZ Consent")

    def ready(self) -> None:
        # Import for side effects only: the `@register(...)` decorators in checks.py
        # must run when Django starts, otherwise `manage.py check` will not see them.
        from . import checks  # noqa: F401
        from .box_templates.documents import bootstrap_sample_documents_post_migrate
        from .core.starter_purposes import bootstrap_starter_purposes_post_migrate

        # Sample documents are loaded only after application migrations.
        # Otherwise `ready()` could touch tables that do not exist yet on first start.
        post_migrate.connect(
            bootstrap_sample_documents_post_migrate,
            sender=self,
            dispatch_uid="django_consent_152fz.sample_documents.post_migrate",
        )
        post_migrate.connect(
            bootstrap_starter_purposes_post_migrate,
            sender=self,
            dispatch_uid="django_consent_152fz.starter_purposes.post_migrate",
        )
