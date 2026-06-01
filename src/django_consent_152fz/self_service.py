from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from django.conf import settings
from django.db import DatabaseError

from django_consent_152fz import constants
from django_consent_152fz.core.models import ConsentPurpose, ConsentSelfServiceSettings
from django_consent_152fz.settings import (
    get_subject_consents_capture_settings,
    get_subject_consents_open_mode,
)


def resolve_subject_consents_ui_settings() -> dict[str, object]:
    capture = dict(get_subject_consents_capture_settings())
    data: dict[str, object] = {
        "open_mode": get_subject_consents_open_mode(),
        "list_mode": ConsentSelfServiceSettings.SubjectConsentsListMode.ALL,
        "capture": capture,
    }
    try:
        local_settings = ConsentSelfServiceSettings.objects.order_by(
            "-updated_at", "-id"
        ).first()
    except DatabaseError:
        return data

    if local_settings is None:
        return _apply_explicit_settings_override(data)

    data["open_mode"] = local_settings.subject_consents_open_mode
    data["list_mode"] = local_settings.subject_consents_list_mode
    data["capture"] = {
        "input_mode": local_settings.consent_input_mode,
        "checkbox_required": local_settings.checkbox_required,
        "decline_action": local_settings.decline_action,
        "decline_warning_enabled": local_settings.decline_warning_enabled,
        "decline_warning_text": local_settings.decline_warning_text.strip()
        or capture["decline_warning_text"],
    }
    return _apply_explicit_settings_override(data)


def resolve_subject_consents_capture_settings(
    *,
    purpose_code: str | None = None,
) -> dict[str, object]:
    """Return capture settings with an optional purpose-level override."""

    capture_raw = resolve_subject_consents_ui_settings().get("capture", {})
    capture = dict(cast(Mapping[str, Any], capture_raw))
    normalized_purpose_code = str(purpose_code or "").strip()
    if not normalized_purpose_code:
        return capture

    try:
        purpose = (
            ConsentPurpose.objects.filter(code=normalized_purpose_code)
            .only(
                "consent_input_mode_override",
                "checkbox_required_override",
                "decline_action_override",
                "decline_warning_enabled_override",
                "decline_warning_text_override",
            )
            .first()
        )
    except DatabaseError:
        return capture
    if purpose is None:
        return capture

    if (
        purpose.consent_input_mode_override
        != ConsentPurpose.ConsentInputModeOverride.INHERIT
    ):
        capture["input_mode"] = purpose.consent_input_mode_override
    if purpose.checkbox_required_override is not None:
        capture["checkbox_required"] = bool(purpose.checkbox_required_override)
    if (
        purpose.decline_action_override
        != ConsentPurpose.ConsentDeclineActionOverride.INHERIT
    ):
        capture["decline_action"] = purpose.decline_action_override
    if purpose.decline_warning_enabled_override is not None:
        capture["decline_warning_enabled"] = bool(
            purpose.decline_warning_enabled_override
        )
    if str(purpose.decline_warning_text_override or "").strip():
        capture["decline_warning_text"] = purpose.decline_warning_text_override.strip()
    return capture


def _apply_explicit_settings_override(data: dict[str, object]) -> dict[str, object]:
    configured = getattr(settings, "DJANGO_CONSENT_152FZ", None)
    if configured is None:
        configured = getattr(settings, "DJANGO_152FZ_CONSENT", {})
    configured = configured or {}
    subject_consents = configured.get("subject_consents", {})
    if not isinstance(subject_consents, dict):
        return data

    if "open_mode" in subject_consents:
        data["open_mode"] = subject_consents["open_mode"]
    capture = dict(cast(Mapping[str, Any], data.get("capture") or {}))
    for key in (
        "consent_input_mode",
        "checkbox_required",
        "decline_action",
        "decline_warning_enabled",
        "decline_warning_text",
    ):
        if key not in subject_consents:
            continue
        target_key = "input_mode" if key == "consent_input_mode" else key
        capture[target_key] = subject_consents[key]
    data["capture"] = capture
    return data


def is_decline_block_submit(capture_settings: dict[str, object]) -> bool:
    return (
        str(capture_settings.get("input_mode") or "")
        == constants.SUBJECT_CONSENTS_INPUT_MODE_RADIO
        and str(capture_settings.get("decline_action") or "")
        == constants.SUBJECT_CONSENTS_DECLINE_ACTION_BLOCK_SUBMIT
    )
