"""Services for the optional `verified_consents` app.

This layer extends `core` without duplicating it:
- `ConsentRecord` and `ConsentEvent` are still created in core;
- verified services only add policy-aware behavior and verified artifacts.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Django dynamic ORM/admin attributes are not fully inferable by pyright.
import hashlib
import logging
import os
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, cast

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from django_consent_152fz import constants
from django_consent_152fz.admin_helpers import has_personal_data_manager_permission
from django_consent_152fz.audit import log_module_operation
from django_consent_152fz.core.models import (
    ConsentEvent,
    ConsentRecord,
    DocumentRevision,
    ModuleOperationAuditLog,
    PersonalDataManagerAssignment,
)
from django_consent_152fz.core.services import (
    VerifiedConsentResolution,
    _apply_verified_legacy_transition_to_record,
    _create_consent_event,
    _flow_requires_consent_for_record,
    _is_confirmation_method_allowed_for_verified_policy,
    _normalize_audit_context,
    _resolve_legacy_web_consent_transition_mode,
    accept_consent,
)
from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.integrations import trigger_verified_consent_notification

from .models import (
    ALLOWED_PAPER_FILE_EXTENSIONS,
    MAX_PAPER_FILE_SIZE_BYTES,
    VerifiedConsentArtifact,
    VerifiedConsentFormPolicy,
    VerifiedConsentPolicy,
    VerifiedConsentSubmission,
)

VERIFIED_CHANNEL_RUNTIME = "runtime"
VERIFIED_CHANNEL_SELF_SERVICE = "self_service"
VERIFIED_CHANNEL_FORM = "form"

VERIFIED_EVENT_DATA_SAVED = "data_saved"
VERIFIED_EVENT_PAPER_UPLOADED = "paper_uploaded"
VERIFIED_EVENT_VERIFIED = "verified"
VERIFIED_EVENT_REJECTED = "rejected"
SELF_UPLOAD_DRAFT_RATE_LIMIT_MAX_REQUESTS = 6
SELF_UPLOAD_DRAFT_RATE_LIMIT_WINDOW_SECONDS = 60
logger = logging.getLogger(__name__)


def get_verified_consent_policy(
    *,
    purpose_code: str,
    document_code: str | None = None,
) -> VerifiedConsentPolicy | None:
    """Return the active verified policy for a flow.

    The function resolves a policy from the flow data. If no policy is found,
    `None` is returned.
    """
    qs = _active_verified_policies_qs().filter(purpose__code=purpose_code)
    if document_code:
        return qs.filter(document__code=document_code).first()

    policies = list(qs.order_by("document__code")[:2])
    if len(policies) > 1:
        raise ConsentError(
            f"Multiple verified consent policies found for purpose '{purpose_code}'. "
            "Specify document_code."
        )
    return policies[0] if policies else None


def resolve_verified_consent_mode(
    *,
    purpose_code: str,
    document_code: str | None = None,
    form_code: str | None = None,
    channel: str = VERIFIED_CHANNEL_RUNTIME,
) -> dict[str, Any]:
    """Resolve the effective verified mode: policy -> form override -> fallback."""
    policy = get_verified_consent_policy(
        purpose_code=purpose_code,
        document_code=document_code,
    )
    fallback = {
        "required": False,
        "verification_mode": VerifiedConsentPolicy.VerificationMode.WEB_ONLY,
        "resolution_source": "runtime_fallback",
        "policy": None,
        "form_policy": None,
        "legacy_web_consent_policy": (
            VerifiedConsentPolicy.LegacyWebConsentPolicy.KEEP_WEB_CURRENT
        ),
        "allow_subject_self_upload": False,
        "allow_draft_data_before_upload": True,
        "pre_upload_access_mode": VerifiedConsentPolicy.PreUploadAccessMode.BLOCK,
        "notification_mode": VerifiedConsentPolicy.NotificationMode.AUDIT_ONLY,
        "notify_on_data_saved": False,
        "notify_on_paper_uploaded": False,
        "notify_on_verified": False,
        "notify_on_rejected": False,
    }
    if policy is None:
        return fallback

    normalized_channel = str(channel or VERIFIED_CHANNEL_RUNTIME).strip()
    if not _policy_applies_to_channel(policy=policy, channel=normalized_channel):
        return {
            **fallback,
            "resolution_source": "policy_scope_skipped",
            "policy": policy,
            "allow_subject_self_upload": bool(policy.allow_subject_self_upload),
        }

    effective_mode = str(policy.verification_mode)
    resolution_source = "policy"
    form_policy = None

    normalized_form_code = str(form_code or "").strip()
    if normalized_form_code and normalized_channel == VERIFIED_CHANNEL_FORM:
        form_policy = get_verified_form_policy(
            purpose_code=purpose_code,
            document_code=document_code,
            form_code=normalized_form_code,
        )
        if (
            form_policy is not None
            and form_policy.verification_mode_override
            != VerifiedConsentFormPolicy.VerificationModeOverride.INHERIT
        ):
            effective_mode = str(form_policy.verification_mode_override)
            resolution_source = "form_override"

    allow_draft_data_before_upload = bool(policy.allow_draft_data_before_upload)
    pre_upload_access_mode = str(policy.pre_upload_access_mode)
    notification_mode = str(policy.notification_mode)
    notification_templates = dict(policy.notification_templates or {})
    if form_policy is not None:
        if (
            form_policy.draft_data_policy_override
            == VerifiedConsentFormPolicy.DraftDataPolicyOverride.ALLOW
        ):
            allow_draft_data_before_upload = True
        elif (
            form_policy.draft_data_policy_override
            == VerifiedConsentFormPolicy.DraftDataPolicyOverride.FORBID
        ):
            allow_draft_data_before_upload = False

        if (
            form_policy.pre_upload_access_mode_override
            != VerifiedConsentFormPolicy.PreUploadAccessModeOverride.INHERIT
        ):
            pre_upload_access_mode = str(form_policy.pre_upload_access_mode_override)

        if (
            form_policy.notification_mode_override
            != VerifiedConsentFormPolicy.NotificationModeOverride.INHERIT
        ):
            notification_mode = str(form_policy.notification_mode_override)

    return {
        "required": effective_mode != VerifiedConsentPolicy.VerificationMode.WEB_ONLY,
        "verification_mode": effective_mode,
        "resolution_source": resolution_source,
        "policy": policy,
        "form_policy": form_policy,
        "legacy_web_consent_policy": str(policy.legacy_web_consent_policy),
        "allow_subject_self_upload": bool(policy.allow_subject_self_upload),
        "allow_draft_data_before_upload": allow_draft_data_before_upload,
        "pre_upload_access_mode": pre_upload_access_mode,
        "notification_mode": notification_mode,
        "notification_templates": notification_templates,
        "notify_on_data_saved": bool(policy.notify_on_data_saved),
        "notify_on_paper_uploaded": bool(policy.notify_on_paper_uploaded),
        "notify_on_verified": bool(policy.notify_on_verified),
        "notify_on_rejected": bool(policy.notify_on_rejected),
    }


def get_verified_transition_state(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
    subject_ref: str = "",
    verification_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the machine-readable state for the web -> verified transition.

    The service helps transport/UI layers interpret the flow consistently:
    - `paper_required`
    - `awaiting_upload`
    - `pending_verification`
    - `verified`
    - `rejected`
    """
    resolved_context = _normalize_verification_context(verification_context)
    resolution = resolve_verified_consent_mode(
        purpose_code=purpose_code,
        document_code=document_code,
        form_code=resolved_context["form_code"],
        channel=resolved_context["channel"],
    )

    payload = {
        "enabled": bool(resolution["required"]),
        "status_code": None,
        "reason_code": None,
        "verification_mode": str(resolution["verification_mode"]),
        "resolution_source": str(resolution["resolution_source"]),
        "channel": resolved_context["channel"],
        "form_code": resolved_context["form_code"],
        "submission_id": None,
        "consent_record_id": None,
    }
    if not bool(resolution["required"]):
        return payload

    policy = _require_verified_policy_from_resolution(
        purpose_code=purpose_code,
        document_code=document_code,
        resolution=resolution,
    )
    normalized_subject_ref = str(subject_ref or "").strip()
    submission = _find_open_submission(
        policy=policy,
        user=user,
        anonymous_token=anonymous_token,
        subject_ref=normalized_subject_ref,
        form_code=resolved_context["form_code"],
    )
    if submission is not None:
        payload["submission_id"] = submission.pk
        payload["consent_record_id"] = submission.consent_record_id

    latest_record = _get_latest_subject_record_for_flow(
        policy=policy,
        user=user,
        anonymous_token=anonymous_token,
        subject_ref=normalized_subject_ref,
    )
    if latest_record is not None:
        payload["consent_record_id"] = latest_record.pk
        if latest_record.status == ConsentRecord.Status.REJECTED:
            payload["status_code"] = constants.VERIFIED_TRANSITION_STATUS_REJECTED
            payload["reason_code"] = constants.VERIFIED_TRANSITION_STATUS_REJECTED
            return payload
        if latest_record.status == ConsentRecord.Status.PENDING_CONFIRMATION:
            payload["status_code"] = (
                constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION
            )
            payload["reason_code"] = (
                constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION
            )
            return payload
        if (
            latest_record.status == ConsentRecord.Status.CURRENT
            and _is_confirmation_method_allowed_for_verified_policy(
                confirmation_method=latest_record.confirmation_method,
                verification_mode=str(resolution["verification_mode"]),
            )
        ):
            payload["status_code"] = constants.VERIFIED_TRANSITION_STATUS_VERIFIED
            payload["reason_code"] = constants.VERIFIED_TRANSITION_STATUS_VERIFIED
            return payload

    if submission is not None:
        if submission.status in {
            VerifiedConsentSubmission.WorkflowStatus.DRAFT_DATA,
            VerifiedConsentSubmission.WorkflowStatus.AWAITING_PAPER_UPLOAD,
        }:
            payload["status_code"] = (
                constants.VERIFIED_TRANSITION_STATUS_AWAITING_UPLOAD
            )
            payload["reason_code"] = (
                constants.VERIFIED_TRANSITION_STATUS_AWAITING_UPLOAD
            )
            return payload
        if submission.status == VerifiedConsentSubmission.WorkflowStatus.PAPER_UPLOADED:
            payload["status_code"] = (
                constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION
            )
            payload["reason_code"] = (
                constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION
            )
            return payload
        if submission.status == VerifiedConsentSubmission.WorkflowStatus.VERIFIED:
            payload["status_code"] = constants.VERIFIED_TRANSITION_STATUS_VERIFIED
            payload["reason_code"] = constants.VERIFIED_TRANSITION_STATUS_VERIFIED
            return payload
        if submission.status == VerifiedConsentSubmission.WorkflowStatus.REJECTED:
            payload["status_code"] = constants.VERIFIED_TRANSITION_STATUS_REJECTED
            payload["reason_code"] = constants.VERIFIED_TRANSITION_STATUS_REJECTED
            return payload

    payload["status_code"] = constants.VERIFIED_TRANSITION_STATUS_PAPER_REQUIRED
    payload["reason_code"] = constants.VERIFIED_TRANSITION_STATUS_PAPER_REQUIRED
    return payload


def get_verified_form_policy(
    *,
    purpose_code: str,
    document_code: str | None = None,
    form_code: str,
) -> VerifiedConsentFormPolicy | None:
    """Return the active per-form override for a specific thread."""
    normalized_form_code = str(form_code or "").strip()
    if not normalized_form_code:
        return None
    qs = (
        VerifiedConsentFormPolicy.objects.select_related("purpose", "document")
        .filter(
            is_active=True,
            purpose__code=purpose_code,
            form_code=normalized_form_code,
        )
        .order_by("id")
    )
    if document_code:
        return qs.filter(document__code=document_code).first()

    policies = list(qs[:2])
    if len(policies) > 1:
        raise ConsentError(
            f"Multiple verified form policies found for purpose '{purpose_code}' "
            f"and form_code '{normalized_form_code}'. Specify document_code."
        )
    return policies[0] if policies else None


@transaction.atomic
def save_verified_consent_submission_data(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
    subject_ref: str = "",
    form_code: str = "",
    subject_data: Mapping[str, Any] | None = None,
    notes: str = "",
    source: str = "",
    audit_context: Mapping[str, Any] | None = None,
    verification_context: Mapping[str, Any] | None = None,
) -> VerifiedConsentSubmission:
    """Save stage-1 subject data for two-step paper-consent flow."""

    resolved_context = _normalize_verification_context(verification_context)
    effective_form_code = str(form_code or resolved_context["form_code"]).strip()
    if effective_form_code:
        resolved_context["channel"] = VERIFIED_CHANNEL_FORM
        resolved_context["form_code"] = effective_form_code
    elif resolved_context["channel"] == VERIFIED_CHANNEL_RUNTIME:
        resolved_context["channel"] = VERIFIED_CHANNEL_SELF_SERVICE

    resolution = resolve_verified_consent_mode(
        purpose_code=purpose_code,
        document_code=document_code,
        form_code=resolved_context["form_code"],
        channel=resolved_context["channel"],
    )
    policy = _require_verified_policy_from_resolution(
        purpose_code=purpose_code,
        document_code=document_code,
        resolution=resolution,
    )
    if not resolution["required"]:
        raise ConsentError(
            "This consent flow does not require verified submission in current mode."
        )
    if not bool(resolution["allow_draft_data_before_upload"]):
        raise ConsentError(
            "Draft data save before paper upload is disabled for this flow."
        )
    _enforce_self_upload_draft_rate_limit(
        purpose_code=purpose_code,
        document_code=policy.document.code,
        user=user,
        anonymous_token=anonymous_token,
        form_code=resolved_context["form_code"],
        channel=resolved_context["channel"],
    )

    submission = _find_open_submission(
        policy=policy,
        user=user,
        anonymous_token=anonymous_token,
        subject_ref=subject_ref,
        form_code=resolved_context["form_code"],
    )
    if submission is None:
        submission = VerifiedConsentSubmission(
            purpose=policy.purpose,
            document=policy.document,
            user=user,
            anonymous_token=str(anonymous_token or "").strip(),
            subject_ref=str(subject_ref or "").strip(),
            form_code=resolved_context["form_code"],
        )

    submission.subject_data = dict(subject_data or {})
    submission.notes = str(notes or "").strip()
    submission.status = VerifiedConsentSubmission.WorkflowStatus.AWAITING_PAPER_UPLOAD
    submission.extra_meta = _merge_submission_meta(
        current_meta=submission.extra_meta,
        updates={
            "verification_context": dict(resolved_context),
            "pre_upload_access_mode": str(resolution["pre_upload_access_mode"]),
        },
    )
    submission.save()

    generate_verified_consent_blank_file(
        submission=submission,
        regenerate=True,
    )
    _notify_verified_workflow_event(
        event_code=VERIFIED_EVENT_DATA_SAVED,
        submission=submission,
        policy=policy,
        source=source,
        audit_context=audit_context,
        enabled=bool(resolution["notify_on_data_saved"]),
        notification_mode=str(resolution["notification_mode"]),
    )
    return submission


@transaction.atomic
def submit_verified_consent_for_submission(
    *,
    submission: VerifiedConsentSubmission,
    paper_file,
    subject_signed_at=None,
    source: str = "",
    audit_context: Mapping[str, Any] | None = None,
    artifact_note: str = "",
    artifact_meta: Mapping[str, Any] | None = None,
    performed_by=None,
) -> ConsentRecord:
    """Complete stage-2 upload for a previously saved submission."""

    if submission.status not in {
        VerifiedConsentSubmission.WorkflowStatus.DRAFT_DATA,
        VerifiedConsentSubmission.WorkflowStatus.AWAITING_PAPER_UPLOAD,
        VerifiedConsentSubmission.WorkflowStatus.REJECTED,
    }:
        raise ConsentError("Submission is not ready for paper upload.")

    channel = (
        VERIFIED_CHANNEL_FORM
        if (submission.form_code or "").strip()
        else VERIFIED_CHANNEL_SELF_SERVICE
    )
    resolution = resolve_verified_consent_mode(
        purpose_code=submission.purpose.code,
        document_code=submission.document.code,
        form_code=str(submission.form_code or "").strip(),
        channel=channel,
    )
    policy = _require_verified_policy_from_resolution(
        purpose_code=submission.purpose.code,
        document_code=submission.document.code,
        resolution=resolution,
    )
    verification_context = {
        "channel": channel,
        "form_code": str(submission.form_code or "").strip(),
    }
    fields_snapshot = sorted(
        str(key) for key in dict(submission.subject_data or {}).keys()
    )
    record = submit_verified_consent(
        purpose_code=submission.purpose.code,
        document_code=submission.document.code,
        user=submission.user,
        anonymous_token=str(submission.anonymous_token or "").strip() or None,
        subject_ref=submission.subject_ref,
        fields_snapshot=fields_snapshot or None,
        paper_file=paper_file,
        subject_signed_at=subject_signed_at,
        source=source,
        audit_context=audit_context,
        artifact_note=artifact_note,
        artifact_meta=artifact_meta,
        performed_by=performed_by,
        verification_context=verification_context,
    )

    submission.consent_record = record
    submission.latest_artifact = getattr(record, "verified_artifact", None)
    submission.status = VerifiedConsentSubmission.WorkflowStatus.PAPER_UPLOADED
    submission.extra_meta = _merge_submission_meta(
        current_meta=submission.extra_meta,
        updates={"paper_uploaded_at": timezone.now().isoformat()},
    )
    submission.save()
    _notify_verified_workflow_event(
        event_code=VERIFIED_EVENT_PAPER_UPLOADED,
        submission=submission,
        policy=policy,
        source=source,
        audit_context=audit_context,
        enabled=bool(resolution["notify_on_paper_uploaded"]),
        notification_mode=str(resolution["notification_mode"]),
    )
    return record


def generate_verified_consent_blank_file(
    *,
    submission: VerifiedConsentSubmission,
    regenerate: bool = False,
) -> str:
    """Generate or reuse printable consent blank for submission."""

    if submission.generated_blank_file and not regenerate:
        return str(submission.generated_blank_file.name or "")

    revision = _get_latest_active_revision_for_submission(submission=submission)
    subject_data = dict(submission.subject_data or {})
    blank_text = _render_printable_blank_text(
        submission=submission,
        revision=revision,
        subject_data=subject_data,
    )
    file_bytes = _build_simple_pdf_bytes(text=blank_text)
    file_name = (
        f"verified_blank_{submission.purpose.code}_{submission.document.code}_"
        f"{submission.pk or 'new'}.pdf"
    )
    submission.generated_blank_file.save(file_name, ContentFile(file_bytes), save=False)
    submission.blank_generated_at = timezone.now()
    submission.save(update_fields=["generated_blank_file", "blank_generated_at"])
    return str(submission.generated_blank_file.name or "")


@transaction.atomic
def submit_verified_consent(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
    subject_ref: str = "",
    fields_snapshot: list[str] | None = None,
    paper_file,
    subject_signed_at=None,
    source: str = "",
    audit_context: Mapping[str, Any] | None = None,
    artifact_note: str = "",
    artifact_meta: Mapping[str, Any] | None = None,
    performed_by=None,
    verification_context: Mapping[str, Any] | None = None,
) -> ConsentRecord:
    """Create a pending consent and attach a verified artifact to it.

    At this stage the paper-based path is implemented. `goskey_required` is
    reserved explicitly, but not actively integrated yet.
    """
    resolved_context = _normalize_verification_context(verification_context)
    resolution = resolve_verified_consent_mode(
        purpose_code=purpose_code,
        document_code=document_code,
        form_code=resolved_context["form_code"],
        channel=resolved_context["channel"],
    )
    policy = _require_verified_policy_from_resolution(
        purpose_code=purpose_code,
        document_code=document_code,
        resolution=resolution,
    )
    if not resolution["required"]:
        raise ConsentError(
            "This consent flow does not require verified submission in current mode."
        )
    if (
        resolution["verification_mode"]
        == VerifiedConsentPolicy.VerificationMode.GOSKEY_REQUIRED
    ):
        raise ConsentError(
            "verification_mode='goskey_required' is not implemented yet."
        )
    if paper_file is None:
        raise ConsentError("paper_file is required for submit_verified_consent().")
    actor_user, actor_type = _resolve_submit_actor(
        performed_by=performed_by,
        subject_user=user,
        anonymous_token=anonymous_token,
        action_name="submit_verified_consent",
        allow_subject_self_upload=bool(resolution["allow_subject_self_upload"]),
    )
    paper_document_hash, paper_document_meta = _build_paper_document_proof(
        paper_file=paper_file
    )
    normalized_artifact_meta = _build_artifact_meta(
        artifact_meta=artifact_meta,
        paper_document_hash=paper_document_hash,
        paper_document_meta=paper_document_meta,
    )

    record = accept_consent(
        purpose_code=purpose_code,
        document_code=policy.document.code,
        user=user,
        anonymous_token=anonymous_token,
        subject_ref=subject_ref,
        fields_snapshot=fields_snapshot,
        confirmation_method=ConsentRecord.ConfirmationMethod.UPLOADED_PAPER,
        source=source,
        audit_context=audit_context,
        event_payload={
            "paper_document_hash": paper_document_hash,
            "paper_document_meta": paper_document_meta,
            **(
                {"subject_signed_at": subject_signed_at.isoformat()}
                if subject_signed_at is not None
                else {}
            ),
            **({"confirmation_note": artifact_note} if artifact_note.strip() else {}),
        },
        event_actor_user=actor_user,
        event_actor_type=actor_type,
        verified_submission=True,
        verification_context=resolved_context,
    )
    VerifiedConsentArtifact.objects.create(
        consent_record=record,
        policy=policy,
        artifact_type=VerifiedConsentArtifact.ArtifactType.PAPER_DOCUMENT,
        file=paper_file,
        subject_signed_at=subject_signed_at,
        note=artifact_note,
        extra_meta=normalized_artifact_meta,
    )
    return record


@transaction.atomic
def confirm_verified_consent(
    *,
    consent_record: ConsentRecord,
    confirmed_by,
    confirmation_method: str = ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
    confirmed_at=None,
    confirmation_note: str = "",
    audit_context: Mapping[str, Any] | None = None,
) -> ConsentRecord:
    """Confirm a previously uploaded verified consent.

    The method updates the canonical `ConsentRecord` in `core` and writes an
    audit event. The verified app does not keep a separate state journal.
    """
    artifact = _require_pending_verified_artifact(consent_record=consent_record)
    _ensure_verified_actor_permissions(
        actor_user=confirmed_by,
        action_name="confirm_verified_consent",
    )
    if confirmation_method not in {
        ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED,
        ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
    }:
        raise ConsentError(
            "confirmation_method must be admin_confirmed or employee_confirmed."
        )

    normalized_audit_context = _normalize_audit_context(audit_context=audit_context)
    resolved_confirmed_at = confirmed_at or timezone.now()
    submission = getattr(consent_record, "verified_submission", None)
    resolution = resolve_verified_consent_mode(
        purpose_code=artifact.policy.purpose.code,
        document_code=artifact.policy.document.code,
        form_code=(
            str(submission.form_code or "").strip()
            if isinstance(submission, VerifiedConsentSubmission)
            else None
        ),
        channel=(
            VERIFIED_CHANNEL_FORM
            if (
                isinstance(submission, VerifiedConsentSubmission)
                and (submission.form_code or "").strip()
            )
            else VERIFIED_CHANNEL_SELF_SERVICE
        ),
    )
    transition_mode = _resolve_legacy_web_consent_transition_mode(
        verified_resolution=cast(VerifiedConsentResolution, resolution)
    )
    previous_records = list(
        _get_subject_current_records_for_flow(consent_record=consent_record)
        .select_for_update()
        .exclude(pk=consent_record.pk)
        .order_by("-created_at", "-id")
    )
    for previous in previous_records:
        if transition_mode == "withdraw_after_paper_confirmed":
            _apply_verified_legacy_transition_to_record(
                consent_record=previous,
                transition_mode="withdraw_web_now",
                verified_resolution=cast(VerifiedConsentResolution, resolution),
                audit_context={
                    **dict(normalized_audit_context),
                    "source": "service.confirm_verified_consent",
                },
                occurred_at=resolved_confirmed_at,
            )
            if previous.status == ConsentRecord.Status.WITHDRAWN:
                continue

        previous.status = ConsentRecord.Status.OUTDATED
        previous.save()
        _create_consent_event(
            consent_record=previous,
            event_type=ConsentEvent.EventType.OUTDATED,
            actor_type=ConsentEvent.ActorType.SYSTEM,
            audit_context=normalized_audit_context,
            payload={
                "reason": "superseded_by_verified_confirmation",
                "record_id": consent_record.pk,
                "transition_mode": transition_mode,
            },
            occurred_at=resolved_confirmed_at,
        )

    consent_record.status = ConsentRecord.Status.CURRENT
    consent_record.confirmation_method = confirmation_method
    consent_record.confirmed_by = confirmed_by
    consent_record.confirmed_at = resolved_confirmed_at
    consent_record.confirmation_note = confirmation_note
    consent_record.save()

    payload: dict[str, Any] = {"artifact_id": artifact.pk}
    if artifact.subject_signed_at is not None:
        payload["subject_signed_at"] = artifact.subject_signed_at.isoformat()
    payload.update(_paper_document_payload_from_artifact(artifact=artifact))
    if confirmation_note.strip():
        payload["confirmation_note"] = confirmation_note
    _create_consent_event(
        consent_record=consent_record,
        event_type=(
            ConsentEvent.EventType.ADMIN_CONFIRMED
            if confirmation_method == ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED
            else ConsentEvent.EventType.EMPLOYEE_CONFIRMED
        ),
        actor_user=confirmed_by,
        actor_type=(
            ConsentEvent.ActorType.ADMIN
            if confirmation_method == ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED
            else ConsentEvent.ActorType.EMPLOYEE
        ),
        audit_context=normalized_audit_context,
        payload=payload,
        occurred_at=resolved_confirmed_at,
    )

    if isinstance(submission, VerifiedConsentSubmission):
        submission.status = VerifiedConsentSubmission.WorkflowStatus.VERIFIED
        submission.completed_at = resolved_confirmed_at
        submission.save(update_fields=["status", "completed_at", "updated_at"])
        _notify_verified_workflow_event(
            event_code=VERIFIED_EVENT_VERIFIED,
            submission=submission,
            policy=artifact.policy,
            source="service.confirm_verified_consent",
            audit_context=audit_context,
            enabled=bool(resolution["notify_on_verified"]),
            notification_mode=str(resolution["notification_mode"]),
        )
    return consent_record


@transaction.atomic
def reject_verified_consent(
    *,
    consent_record: ConsentRecord,
    rejected_by,
    actor_type: str = ConsentEvent.ActorType.EMPLOYEE,
    rejected_at=None,
    rejection_note: str = "",
    audit_context: Mapping[str, Any] | None = None,
) -> ConsentRecord:
    """Reject pending verified-consent and write it to the core audit-log."""
    artifact = _require_pending_verified_artifact(consent_record=consent_record)
    _ensure_verified_actor_permissions(
        actor_user=rejected_by,
        action_name="reject_verified_consent",
    )
    if actor_type not in {
        ConsentEvent.ActorType.ADMIN,
        ConsentEvent.ActorType.EMPLOYEE,
    }:
        raise ConsentError("actor_type must be admin or employee.")
    if not rejection_note.strip():
        raise ConsentError("rejection_note is required for reject_verified_consent().")

    resolved_rejected_at = rejected_at or timezone.now()
    consent_record.status = ConsentRecord.Status.REJECTED
    consent_record.confirmed_by = rejected_by
    consent_record.confirmed_at = resolved_rejected_at
    consent_record.confirmation_note = rejection_note
    consent_record.save()

    payload: dict[str, Any] = {
        "artifact_id": artifact.pk,
        "confirmation_note": rejection_note,
    }
    if artifact.subject_signed_at is not None:
        payload["subject_signed_at"] = artifact.subject_signed_at.isoformat()
    payload.update(_paper_document_payload_from_artifact(artifact=artifact))
    _create_consent_event(
        consent_record=consent_record,
        event_type=ConsentEvent.EventType.REJECTED,
        actor_user=rejected_by,
        actor_type=actor_type,
        audit_context=_normalize_audit_context(audit_context=audit_context),
        payload=payload,
        occurred_at=resolved_rejected_at,
    )

    submission = getattr(consent_record, "verified_submission", None)
    if isinstance(submission, VerifiedConsentSubmission):
        submission.status = VerifiedConsentSubmission.WorkflowStatus.REJECTED
        submission.completed_at = resolved_rejected_at
        submission.save(update_fields=["status", "completed_at", "updated_at"])
        resolution = resolve_verified_consent_mode(
            purpose_code=submission.purpose.code,
            document_code=submission.document.code,
            form_code=str(submission.form_code or "").strip(),
            channel=(
                VERIFIED_CHANNEL_FORM
                if (submission.form_code or "").strip()
                else VERIFIED_CHANNEL_SELF_SERVICE
            ),
        )
        _notify_verified_workflow_event(
            event_code=VERIFIED_EVENT_REJECTED,
            submission=submission,
            policy=artifact.policy,
            source="service.reject_verified_consent",
            audit_context=audit_context,
            enabled=bool(resolution["notify_on_rejected"]),
            notification_mode=str(resolution["notification_mode"]),
        )
    return consent_record


def preview_verified_legacy_transition(
    *,
    purpose_code: str,
    document_code: str | None = None,
    form_code: str | None = None,
    channel: str = VERIFIED_CHANNEL_RUNTIME,
) -> dict[str, Any]:
    """Build a dry-run assessment for the legacy web-consent -> verified mode transition.

    The preview does not change data and shows:
    - how many stream records may be affected;
    - how many will be changed immediately depending on the transition mode;
    - how many will fall into the deferred `withdraw_after_paper_confirmed` scenario.
    """
    resolution = resolve_verified_consent_mode(
        purpose_code=purpose_code,
        document_code=document_code,
        form_code=form_code,
        channel=channel,
    )
    policy = _require_verified_policy_from_resolution(
        purpose_code=purpose_code,
        document_code=document_code,
        resolution=resolution,
    )
    transition_mode = _resolve_legacy_web_consent_transition_mode(
        verified_resolution=cast(VerifiedConsentResolution, resolution)
    )
    candidate_ids, candidates_count = _collect_verified_transition_candidate_ids(
        policy=policy
    )
    immediate_modes = {"mark_web_outdated", "withdraw_web_now"}
    immediate_count = candidates_count if transition_mode in immediate_modes else 0
    deferred_count = (
        candidates_count if transition_mode == "withdraw_after_paper_confirmed" else 0
    )
    return {
        "purpose_code": policy.purpose.code,
        "document_code": policy.document.code,
        "channel": str(channel or VERIFIED_CHANNEL_RUNTIME),
        "form_code": str(form_code or "").strip(),
        "verification_mode": str(resolution["verification_mode"]),
        "transition_mode": transition_mode,
        "required": bool(resolution["required"]),
        "affected_candidates": candidates_count,
        "would_change_immediately": immediate_count,
        "would_defer_until_confirmation": deferred_count,
        "candidate_ids": list(candidate_ids),
    }


def apply_verified_legacy_transition(
    *,
    purpose_code: str,
    document_code: str | None = None,
    form_code: str | None = None,
    channel: str = VERIFIED_CHANNEL_RUNTIME,
    batch_size: int = 500,
    dry_run: bool = False,
    actor_user=None,
    source: str = "service.verified.apply_legacy_transition",
) -> dict[str, Any]:
    """Apply transition-mode to legacy web-consent records in batch mode."""
    if isinstance(batch_size, bool) or int(batch_size) <= 0:
        raise ConsentError("batch_size must be a positive integer.")

    preview = preview_verified_legacy_transition(
        purpose_code=purpose_code,
        document_code=document_code,
        form_code=form_code,
        channel=channel,
    )
    transition_mode = str(preview["transition_mode"])
    candidate_ids = list(preview["candidate_ids"])
    immediate_modes = {"mark_web_outdated", "withdraw_web_now"}
    batch_size_value = int(batch_size)

    summary: dict[str, Any] = {
        "purpose_code": str(preview["purpose_code"]),
        "document_code": str(preview["document_code"]),
        "channel": str(preview["channel"]),
        "form_code": str(preview["form_code"]),
        "verification_mode": str(preview["verification_mode"]),
        "transition_mode": transition_mode,
        "dry_run": bool(dry_run),
        "batch_size": batch_size_value,
        "affected_candidates": int(preview["affected_candidates"]),
        "would_change_immediately": int(preview["would_change_immediately"]),
        "would_defer_until_confirmation": int(
            preview["would_defer_until_confirmation"]
        ),
        "changed_records": 0,
        "batches_processed": 0,
        "status": "dry_run" if dry_run else "success",
    }

    if dry_run or transition_mode not in immediate_modes or not candidate_ids:
        log_module_operation(
            operation_code="service.verified.apply_legacy_transition",
            actor_user=actor_user,
            source=source,
            status=(
                ModuleOperationAuditLog.Status.DRY_RUN
                if dry_run
                else ModuleOperationAuditLog.Status.SUCCESS
            ),
            target_model="verified_consents.VerifiedConsentPolicy",
            target_id=f"{summary['purpose_code']}:{summary['document_code']}",
            summary=(
                "Verified legacy transition preview only."
                if dry_run
                else "Verified legacy transition has no immediate records to change."
            ),
            payload={
                "transition_mode": transition_mode,
                "channel": summary["channel"],
                "form_code": summary["form_code"],
                "candidate_ids_count": len(candidate_ids),
            },
            result=dict(summary),
        )
        return summary

    resolution = resolve_verified_consent_mode(
        purpose_code=summary["purpose_code"],
        document_code=summary["document_code"],
        form_code=summary["form_code"] or None,
        channel=summary["channel"],
    )
    for batch_number, batch_ids in enumerate(
        _iter_id_batches(candidate_ids, batch_size_value),
        start=1,
    ):
        changed_in_batch = 0
        batch_records = list(
            ConsentRecord.objects.filter(pk__in=batch_ids).order_by("pk")
        )
        for record in batch_records:
            previous_status = record.status
            _apply_verified_legacy_transition_to_record(
                consent_record=record,
                transition_mode=transition_mode,
                verified_resolution=cast(VerifiedConsentResolution, resolution),
                audit_context={"source": source},
            )
            if record.status != previous_status:
                changed_in_batch += 1
        summary["changed_records"] += changed_in_batch
        summary["batches_processed"] = batch_number
        log_module_operation(
            operation_code="service.verified.apply_legacy_transition.batch",
            actor_user=actor_user,
            source=source,
            status=ModuleOperationAuditLog.Status.SUCCESS,
            target_model="core.ConsentRecord",
            target_id=f"{summary['purpose_code']}:{summary['document_code']}",
            summary="Verified legacy transition batch applied.",
            payload={
                "batch_number": batch_number,
                "batch_size": len(batch_ids),
                "transition_mode": transition_mode,
                "channel": summary["channel"],
                "form_code": summary["form_code"],
            },
            result={
                "changed_in_batch": changed_in_batch,
                "batch_ids": list(batch_ids),
            },
        )

    log_module_operation(
        operation_code="service.verified.apply_legacy_transition",
        actor_user=actor_user,
        source=source,
        status=ModuleOperationAuditLog.Status.SUCCESS,
        target_model="verified_consents.VerifiedConsentPolicy",
        target_id=f"{summary['purpose_code']}:{summary['document_code']}",
        summary="Verified legacy transition applied.",
        payload={
            "transition_mode": transition_mode,
            "channel": summary["channel"],
            "form_code": summary["form_code"],
            "batch_size": batch_size_value,
        },
        result=dict(summary),
    )
    return summary


def _require_verified_consent_policy(
    *,
    purpose_code: str,
    document_code: str | None,
) -> VerifiedConsentPolicy:
    """Return policy or raise a domain error with a clear message."""
    policy = get_verified_consent_policy(
        purpose_code=purpose_code,
        document_code=document_code,
    )
    if policy is None:
        document_hint = f" and document '{document_code}'" if document_code else ""
        raise ConsentError(
            f"No active verified consent policy found for purpose '{purpose_code}'"
            f"{document_hint}."
        )
    return policy


def _require_verified_policy_from_resolution(
    *,
    purpose_code: str,
    document_code: str | None,
    resolution: Mapping[str, Any],
) -> VerifiedConsentPolicy:
    policy = resolution.get("policy")
    if isinstance(policy, VerifiedConsentPolicy):
        return policy
    document_hint = f" and document '{document_code}'" if document_code else ""
    raise ConsentError(
        f"No active verified consent policy found for purpose '{purpose_code}'"
        f"{document_hint}."
    )


def _require_pending_verified_artifact(
    *,
    consent_record: ConsentRecord,
) -> VerifiedConsentArtifact:
    """Check that the record has a verified artifact and is still pending."""
    artifact = getattr(consent_record, "verified_artifact", None)
    if artifact is None:
        raise ConsentError("Consent record has no verified artifact.")
    if consent_record.status != ConsentRecord.Status.PENDING_CONFIRMATION:
        raise ConsentError("Consent record is not pending confirmation.")
    return artifact


def _ensure_verified_actor_permissions(*, actor_user, action_name: str) -> None:
    """Check that the action is performed by the Person Responsible for PD or superuser."""
    if actor_user is None or not has_personal_data_manager_permission(
        actor_user,
        permission_flags="can_handle_verified_consents",
    ):
        raise ConsentError(
            f"{action_name} requires active staff user with "
            "'can_handle_verified_consents' permission."
        )


def _resolve_submit_actor(
    *,
    performed_by,
    subject_user,
    anonymous_token: str | None,
    action_name: str,
    allow_subject_self_upload: bool,
) -> tuple[Any, str]:
    """Define a submit_verified_consent actor for staff and self-service scenarios."""
    if performed_by is not None:
        _ensure_verified_actor_permissions(
            actor_user=performed_by,
            action_name=action_name,
        )
        return performed_by, _resolve_staff_actor_type(actor_user=performed_by)

    if not allow_subject_self_upload:
        raise ConsentError(
            f"{action_name} requires active staff user with "
            "'can_handle_verified_consents' permission."
        )
    if (
        getattr(subject_user, "pk", None) is None
        and not (anonymous_token or "").strip()
    ):
        raise ConsentError("Verified self-submission requires subject identity.")
    return subject_user, ConsentEvent.ActorType.SUBJECT


def _resolve_staff_actor_type(*, actor_user) -> str:
    """Define actor type for verified-flow staff operations."""
    if getattr(actor_user, "is_superuser", False):
        return ConsentEvent.ActorType.ADMIN
    return ConsentEvent.ActorType.EMPLOYEE


def _normalize_verification_context(
    verification_context: Mapping[str, Any] | None,
) -> dict[str, str]:
    data = dict(verification_context or {})
    channel = str(data.get("channel") or VERIFIED_CHANNEL_RUNTIME).strip()
    if channel not in {
        VERIFIED_CHANNEL_RUNTIME,
        VERIFIED_CHANNEL_SELF_SERVICE,
        VERIFIED_CHANNEL_FORM,
    }:
        channel = VERIFIED_CHANNEL_RUNTIME
    return {
        "channel": channel,
        "form_code": str(data.get("form_code") or "").strip(),
    }


def _policy_applies_to_channel(
    *,
    policy: VerifiedConsentPolicy,
    channel: str,
) -> bool:
    if channel == VERIFIED_CHANNEL_FORM:
        return policy.flow_scope in {
            VerifiedConsentPolicy.FlowScope.BOTH,
            VerifiedConsentPolicy.FlowScope.FORMS_ONLY,
        }
    if channel == VERIFIED_CHANNEL_SELF_SERVICE:
        return policy.flow_scope in {
            VerifiedConsentPolicy.FlowScope.BOTH,
            VerifiedConsentPolicy.FlowScope.SELF_SERVICE_ONLY,
        }
    return True


def _build_paper_document_proof(*, paper_file) -> tuple[str, dict[str, Any]]:
    """Validate the paper file and return hash/meta for auditing."""
    _validate_paper_file(paper_file=paper_file)
    return (
        _compute_uploaded_file_sha256(paper_file=paper_file),
        _build_paper_document_meta(paper_file=paper_file),
    )


def _validate_paper_file(*, paper_file) -> None:
    """Check the format and size of the paper artifact."""
    filename = str(getattr(paper_file, "name", "") or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_PAPER_FILE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_PAPER_FILE_EXTENSIONS))
        raise ConsentError(
            f"Unsupported paper_file extension '{ext or '<empty>'}'. "
            f"Allowed extensions: {allowed}."
        )
    size = int(getattr(paper_file, "size", 0) or 0)
    if size <= 0:
        raise ConsentError("paper_file must not be empty.")
    if size > MAX_PAPER_FILE_SIZE_BYTES:
        raise ConsentError(
            f"paper_file exceeds maximum size of {MAX_PAPER_FILE_SIZE_BYTES} bytes."
        )


def _compute_uploaded_file_sha256(*, paper_file) -> str:
    """Calculate sha256 of the downloaded file and restore the reading position."""
    hasher = hashlib.sha256()
    original_position = None
    if hasattr(paper_file, "tell"):
        try:
            original_position = paper_file.tell()
        except (AttributeError, OSError, ValueError) as exc:
            logger.warning(
                "Unable to read uploaded file cursor position before hashing: %s",
                exc,
            )
            original_position = None

    for chunk in paper_file.chunks():
        hasher.update(chunk)

    if hasattr(paper_file, "seek"):
        try:
            paper_file.seek(0 if original_position is None else original_position)
        except (AttributeError, OSError, ValueError) as exc:
            logger.warning(
                "Unable to restore uploaded file cursor position after hashing: %s",
                exc,
            )
    return hasher.hexdigest()


def _build_paper_document_meta(*, paper_file) -> dict[str, Any]:
    """Collect a minimal meta-snapshot of the file for the payload and artifact."""
    filename = str(getattr(paper_file, "name", "") or "")
    ext = os.path.splitext(filename)[1].lower()
    return {
        "name": filename,
        "size_bytes": int(getattr(paper_file, "size", 0) or 0),
        "content_type": str(getattr(paper_file, "content_type", "") or ""),
        "extension": ext,
    }


def _build_artifact_meta(
    *,
    artifact_meta: Mapping[str, Any] | None,
    paper_document_hash: str,
    paper_document_meta: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge custom artifact metadata with proof system fields."""
    merged_meta = dict(artifact_meta or {})
    merged_meta["paper_document_hash"] = paper_document_hash
    merged_meta["paper_document_meta"] = dict(paper_document_meta)
    return merged_meta


def _paper_document_payload_from_artifact(
    *, artifact: VerifiedConsentArtifact
) -> dict[str, Any]:
    """Extract paper hash/meta from artifact.extra_meta for audit payload."""
    payload: dict[str, Any] = {}
    if not isinstance(artifact.extra_meta, Mapping):
        return payload
    if "paper_document_hash" in artifact.extra_meta:
        payload["paper_document_hash"] = artifact.extra_meta["paper_document_hash"]
    if "paper_document_meta" in artifact.extra_meta:
        payload["paper_document_meta"] = artifact.extra_meta["paper_document_meta"]
    return payload


def _find_open_submission(
    *,
    policy: VerifiedConsentPolicy,
    user,
    anonymous_token: str | None,
    subject_ref: str,
    form_code: str,
) -> VerifiedConsentSubmission | None:
    qs = VerifiedConsentSubmission.objects.filter(
        purpose=policy.purpose,
        document=policy.document,
        form_code=str(form_code or "").strip(),
        status__in=[
            VerifiedConsentSubmission.WorkflowStatus.DRAFT_DATA,
            VerifiedConsentSubmission.WorkflowStatus.AWAITING_PAPER_UPLOAD,
            VerifiedConsentSubmission.WorkflowStatus.REJECTED,
        ],
    )
    token = str(anonymous_token or "").strip()
    if getattr(user, "pk", None) is not None:
        qs = qs.filter(user=user)
    elif token:
        qs = qs.filter(anonymous_token=token)
    elif str(subject_ref or "").strip():
        qs = qs.filter(subject_ref=str(subject_ref or "").strip())
    else:
        return None
    return qs.order_by("-updated_at", "-id").first()


def _get_latest_subject_record_for_flow(
    *,
    policy: VerifiedConsentPolicy,
    user,
    anonymous_token: str | None,
    subject_ref: str,
) -> ConsentRecord | None:
    qs = ConsentRecord.objects.select_related("document_revision__document").filter(
        purpose_id=policy.purpose_id,
        document_revision__document_id=policy.document_id,
    )
    token = str(anonymous_token or "").strip()
    if getattr(user, "pk", None) is not None:
        qs = qs.filter(user=user)
    elif token:
        qs = qs.filter(anonymous_token=token)
    elif str(subject_ref or "").strip():
        qs = qs.filter(subject_ref=str(subject_ref or "").strip())
    else:
        return None
    return qs.order_by("-created_at", "-id").first()


def _merge_submission_meta(
    *,
    current_meta: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = dict(current_meta or {})
    result.update(dict(updates or {}))
    return result


def _get_latest_active_revision_for_submission(
    *,
    submission: VerifiedConsentSubmission,
) -> DocumentRevision:
    revision = (
        DocumentRevision.objects.filter(
            document=submission.document,
            purpose_code=submission.purpose.code,
            is_active=True,
        )
        .order_by("-version", "-id")
        .first()
    )
    if revision is None:
        raise ConsentError(
            "No active document revision found for verified submission flow."
        )
    return revision


def _render_printable_blank_text(
    *,
    submission: VerifiedConsentSubmission,
    revision: DocumentRevision,
    subject_data: Mapping[str, Any],
) -> str:
    lines = [
        "Согласие на обработку персональных данных",
        "",
        f"Цель: {submission.purpose.title or submission.purpose.code}",
        f"Документ: {submission.document.title or submission.document.code}",
        "",
        "Данные субъекта:",
    ]
    for key in sorted(subject_data.keys()):
        value = subject_data.get(key)
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "Текст согласия:",
            str(revision.content_text or "").strip(),
            "",
            "Подпись субъекта: ____________________",
            "Дата: ____________________",
        ]
    )
    return "\n".join(lines).strip()


def _build_simple_pdf_bytes(*, text: str) -> bytes:
    """Build minimal one-page PDF without extra dependencies."""
    normalized_lines = [line[:110] for line in str(text or "").splitlines()]
    if not normalized_lines:
        normalized_lines = [""]

    stream_lines = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for idx, line in enumerate(normalized_lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx == 0:
            stream_lines.append(f"({escaped}) Tj")
        else:
            stream_lines.append(f"T* ({escaped}) Tj")
    stream_lines.append("ET")
    stream_data = ("\n".join(stream_lines) + "\n").encode("utf-8")

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    objects.append(
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )
    objects.append(
        b"5 0 obj\n<< /Length "
        + str(len(stream_data)).encode("ascii")
        + b" >>\nstream\n"
        + stream_data
        + b"endstream\nendobj\n"
    )

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = b""
    offsets: list[int] = [0]
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        body += obj
        cursor += len(obj)

    xref_start = len(header) + len(body)
    xref_lines = [f"xref\n0 {len(offsets)}\n".encode("ascii")]
    xref_lines.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    xref = b"".join(xref_lines)
    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
    ).encode("ascii")
    return header + body + xref + trailer


def _notify_verified_workflow_event(
    *,
    event_code: str,
    submission: VerifiedConsentSubmission,
    policy: VerifiedConsentPolicy,
    source: str,
    audit_context: Mapping[str, Any] | None,
    enabled: bool,
    notification_mode: str,
) -> None:
    if not enabled:
        return
    recipients: list[int] = []
    if notification_mode == VerifiedConsentPolicy.NotificationMode.ASSIGNMENT_USERS:
        recipients = list(
            PersonalDataManagerAssignment.objects.filter(
                is_active=True,
                can_handle_verified_consents=True,
                user__is_active=True,
            ).values_list("user_id", flat=True)
        )
    payload = {
        "event": event_code,
        "purpose_code": submission.purpose.code,
        "document_code": submission.document.code,
        "submission_id": submission.pk,
        "consent_record_id": submission.consent_record_id,
        "recipients_user_ids": recipients,
        "notification_mode": notification_mode,
        "audit_context": _to_json_safe(
            dict(_normalize_audit_context(audit_context=audit_context))
        ),
    }
    message = _resolve_notification_message(
        policy=policy,
        event_code=event_code,
        submission=submission,
    )
    if message:
        payload["message"] = message
    log_module_operation(
        operation_code=f"service.verified.notification.{event_code}",
        source=str(source or "service.verified"),
        status="success",
        target_model="VerifiedConsentSubmission",
        target_id=str(submission.pk or ""),
        summary="Verified consent workflow notification.",
        payload=payload,
        result={"dispatched": True},
    )
    trigger_verified_consent_notification(payload)


def _resolve_notification_message(
    *,
    policy: VerifiedConsentPolicy,
    event_code: str,
    submission: VerifiedConsentSubmission,
) -> str:
    templates = dict(policy.notification_templates or {})
    event_key_map = {
        VERIFIED_EVENT_DATA_SAVED: "data_saved",
        VERIFIED_EVENT_PAPER_UPLOADED: "paper_uploaded",
        VERIFIED_EVENT_VERIFIED: "verified",
        VERIFIED_EVENT_REJECTED: "rejected",
    }
    template_key = event_key_map.get(event_code, "")
    template = str(templates.get(template_key, "") or "").strip()
    if not template:
        return ""
    context = {
        "submission_id": submission.pk or "",
        "purpose_code": submission.purpose.code,
        "document_code": submission.document.code,
        "form_code": str(submission.form_code or ""),
        "status": str(submission.status or ""),
        "event": event_code,
    }
    try:
        return template.format(**context)
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning(
            "Failed to render verified consent notification template for event=%r: %s",
            event_code,
            exc,
        )
        return template


def _enforce_self_upload_draft_rate_limit(
    *,
    purpose_code: str,
    document_code: str,
    user,
    anonymous_token: str | None,
    form_code: str,
    channel: str,
) -> None:
    """Rate-limit draft saves that regenerate printable PDF blanks."""

    subject_marker = _build_submission_rate_limit_subject_marker(
        user=user,
        anonymous_token=anonymous_token,
    )
    cache_key = (
        "django_consent_152fz:verified:self_upload_draft:"
        f"{purpose_code}:{document_code}:{channel}:{form_code}:{subject_marker}"
    )
    if cache.add(
        cache_key,
        1,
        timeout=SELF_UPLOAD_DRAFT_RATE_LIMIT_WINDOW_SECONDS,
    ):
        return
    try:
        current_count = int(cache.incr(cache_key))
    except ValueError:
        cache.set(
            cache_key,
            1,
            timeout=SELF_UPLOAD_DRAFT_RATE_LIMIT_WINDOW_SECONDS,
        )
        current_count = 1
    if current_count <= SELF_UPLOAD_DRAFT_RATE_LIMIT_MAX_REQUESTS:
        return
    raise ConsentError(
        "Too many verified draft saves. Please wait a minute before trying again."
    )


def _build_submission_rate_limit_subject_marker(
    *,
    user,
    anonymous_token: str | None,
) -> str:
    if getattr(user, "pk", None) is not None:
        return f"user:{user.pk}"
    token = str(anonymous_token or "").strip()
    if not token:
        return "anonymous:missing"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"anonymous:{token_hash}"


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _collect_verified_transition_candidate_ids(
    *,
    policy: VerifiedConsentPolicy,
) -> tuple[list[int], int]:
    """Collect ids of current web-consent records subject to transition evaluation."""
    qs = (
        ConsentRecord.objects.select_related("document_revision__document")
        .filter(
            purpose_id=policy.purpose_id,
            document_revision__document_id=policy.document_id,
            status=ConsentRecord.Status.CURRENT,
            confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
        )
        .order_by("pk")
    )
    result_ids: list[int] = []
    for record in qs.iterator(chunk_size=1000):
        if not _flow_requires_consent_for_record(
            purpose=policy.purpose,
            document=policy.document,
            record=record,
        ):
            continue
        result_ids.append(int(record.pk))
    return result_ids, len(result_ids)


def _iter_id_batches(ids: list[int], batch_size: int):
    for index in range(0, len(ids), batch_size):
        yield ids[index : index + batch_size]


def _get_subject_current_records_for_flow(*, consent_record: ConsentRecord):
    """Return current records of the same subject and document-flow."""
    subject_filter = Q()
    if consent_record.user_id:
        subject_filter |= Q(user_id=consent_record.user_id)
    if consent_record.anonymous_token:
        subject_filter |= Q(anonymous_token=consent_record.anonymous_token)
    if not subject_filter.children:
        raise ConsentError("Consent record has no subject identity.")

    return ConsentRecord.objects.filter(
        subject_filter,
        purpose_id=consent_record.purpose_id,
        document_revision__document_id=consent_record.document_revision.document_id,
        status=ConsentRecord.Status.CURRENT,
    )


def _active_verified_policies_qs():
    """Basic queryset of active verified-policy, taking into account the time window."""
    now = timezone.now()
    return (
        VerifiedConsentPolicy.objects.select_related("purpose", "document")
        .filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )
