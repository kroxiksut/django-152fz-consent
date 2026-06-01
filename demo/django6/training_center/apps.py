from django.apps import AppConfig
from django.conf import settings
from django.core.management import call_command
from django.db.models.signals import post_migrate


def _bootstrap_demo_after_migrate(sender, app_config, using, **kwargs):
    if sender.name != "training_center":
        return
    if not getattr(settings, "TRAINING_CENTER_AUTO_BOOTSTRAP", True):
        return

    call_command("bootstrap_152fz_cookie_defaults", verbosity=0)
    call_command("bootstrap_152fz_sample_documents", database=using, verbosity=0)
    call_command("bootstrap_training_center_demo", database=using, verbosity=0)
    call_command("bootstrap_training_center_verified_demo", database=using, verbosity=0)


class TrainingCenterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "training_center"

    def ready(self) -> None:
        super().ready()
        post_migrate.connect(
            _bootstrap_demo_after_migrate,
            sender=self,
            dispatch_uid="training_center.bootstrap_demo_after_migrate",
        )
