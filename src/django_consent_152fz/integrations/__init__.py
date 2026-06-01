"""Public integration extension points."""

from .hooks import (
    reset_hooks,
    set_external_cleanup_hook,
    set_reconsent_email_reminder_hook,
    set_session_termination_hook,
    set_verified_consent_notification_hook,
    trigger_external_cleanup,
    trigger_reconsent_email_reminder,
    trigger_session_termination,
    trigger_verified_consent_notification,
)

__all__ = [
    "reset_hooks",
    "set_external_cleanup_hook",
    "set_reconsent_email_reminder_hook",
    "set_session_termination_hook",
    "set_verified_consent_notification_hook",
    "trigger_external_cleanup",
    "trigger_reconsent_email_reminder",
    "trigger_session_termination",
    "trigger_verified_consent_notification",
]
