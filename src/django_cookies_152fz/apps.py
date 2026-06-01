"""AppConfig for the cookie module."""

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class Django152FzConsentCookiesConfig(AppConfig):
    """Register the cookie subsystem as a standalone Django app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_cookies_152fz"
    verbose_name = _("Согласия 152-ФЗ: cookie")

    def ready(self) -> None:
        from .services import bootstrap_cookie_banner_revision_post_migrate

        post_migrate.connect(
            bootstrap_cookie_banner_revision_post_migrate,
            sender=self,
            dispatch_uid=("django_cookies_152fz.cookie_banner_revision.post_migrate"),
        )
