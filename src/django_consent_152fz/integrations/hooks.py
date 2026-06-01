"""Integration hook registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django_consent_152fz.core.models import ConsentRecord


SessionTerminationHook = Callable[["ConsentRecord"], None]
ExternalCleanupHook = Callable[["ConsentRecord"], None]
ReconsentEmailReminderHook = Callable[["ConsentRecord"], None]
VerifiedConsentNotificationHook = Callable[[dict[str, object]], None]

_session_termination_hook: SessionTerminationHook | None = None
_external_cleanup_hook: ExternalCleanupHook | None = None
_reconsent_email_reminder_hook: ReconsentEmailReminderHook | None = None
_verified_consent_notification_hook: VerifiedConsentNotificationHook | None = None


def set_session_termination_hook(hook: SessionTerminationHook | None) -> None:
    global _session_termination_hook
    _session_termination_hook = hook


def set_external_cleanup_hook(hook: ExternalCleanupHook | None) -> None:
    global _external_cleanup_hook
    _external_cleanup_hook = hook


def set_reconsent_email_reminder_hook(
    hook: ReconsentEmailReminderHook | None,
) -> None:
    global _reconsent_email_reminder_hook
    _reconsent_email_reminder_hook = hook


def set_verified_consent_notification_hook(
    hook: VerifiedConsentNotificationHook | None,
) -> None:
    global _verified_consent_notification_hook
    _verified_consent_notification_hook = hook


def trigger_session_termination(consent_record: ConsentRecord) -> None:
    if _session_termination_hook is not None:
        _session_termination_hook(consent_record)


def trigger_external_cleanup(consent_record: ConsentRecord) -> None:
    if _external_cleanup_hook is not None:
        _external_cleanup_hook(consent_record)


def trigger_reconsent_email_reminder(consent_record: ConsentRecord) -> None:
    if _reconsent_email_reminder_hook is not None:
        _reconsent_email_reminder_hook(consent_record)


def trigger_verified_consent_notification(payload: dict[str, object]) -> None:
    if _verified_consent_notification_hook is not None:
        _verified_consent_notification_hook(dict(payload))


def reset_hooks() -> None:
    set_session_termination_hook(None)
    set_external_cleanup_hook(None)
    set_reconsent_email_reminder_hook(None)
    set_verified_consent_notification_hook(None)
