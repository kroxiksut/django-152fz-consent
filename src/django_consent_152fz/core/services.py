"""Service layer for the main consent flow.

This module ties together the domain models from `core.models` and implements
the behavior described in roadmap item 4:
- purpose registration and document revision publication;
- requirements calculation and status handling;
- consent issue and withdrawal;
- re-consent and audience rules;
- guard-layer behavior for access policies;
- audit-context normalization and immutable event recording;
- the bridge to the optional `verified_consents` app.

Some functions here are intentionally private. They are not "helpers" for
convenience; instead, they encode domain logic around document streams,
audience applicability, access resolution, and audit normalization.
"""

from __future__ import annotations

import html as html_lib
import io
import os
import re
from collections.abc import Mapping
from copy import deepcopy
from html.parser import HTMLParser
from typing import Any, Literal, TypedDict, cast

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentAccessPolicy,
    ConsentAudienceRule,
    ConsentEvent,
    ConsentPurpose,
    ConsentRecord,
    ConsentSelfServiceSettings,
    DocumentRevision,
    LegalDocument,
)
from django_consent_152fz.exceptions import ConsentAccessDenied, ConsentError
from django_consent_152fz.integrations.hooks import (
    trigger_external_cleanup,
    trigger_reconsent_email_reminder,
    trigger_session_termination,
)
from django_consent_152fz.settings import (
    get_api_setting,
    get_document_templates_settings,
    get_purposes_config,
    is_access_policies_enabled,
    is_anonymous_withdraw_enabled,
    is_verified_consents_app_installed,
    is_verified_consents_enabled,
)

_AUDIT_EXTRA_META_NAMESPACES = (
    "client",
    "request",
    "client_hints",
    "integration",
    "custom",
)
_AUDIT_CONTEXT_CORE_FIELDS = {
    "source",
    "ip_address",
    "user_agent",
    "locale",
    "request_id",
    "session_key_hash",
    "occurred_at",
    "extra_meta",
    *_AUDIT_EXTRA_META_NAMESPACES,
}
_SENSITIVE_AUDIT_META_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "cookies",
    "csrf_token",
    "headers",
    "raw_headers",
    "refresh_token",
    "set_cookie",
    "set_cookies",
}

VerifiedTransitionInfo = dict[str, Any]


class VerifiedConsentResolution(TypedDict):
    required: bool
    verification_mode: str
    resolution_source: str
    policy: object | None
    form_policy: object | None
    legacy_web_consent_policy: str
    allow_subject_self_upload: bool
    allow_draft_data_before_upload: bool
    pre_upload_access_mode: str
    notification_mode: str
    notification_templates: dict[str, Any]
    notify_on_data_saved: bool
    notify_on_paper_uploaded: bool
    notify_on_verified: bool
    notify_on_rejected: bool


class ConsentStatusInfo(TypedDict):
    purpose_code: str
    document_code: str | None
    record_id: int | None
    status: str | None
    requires_consent: bool
    consent_required_reason: str
    is_current: bool
    is_outdated: bool
    latest_revision_id: int | None
    record_revision_id: int | None
    reconsent_mode: str
    access_restricted: bool
    is_applicable: bool
    not_applicable_reason: str | None
    auth_required_for_consent: bool
    verified_transition: VerifiedTransitionInfo


def register_purpose(*, code: str, config: Mapping[str, Any]) -> ConsentPurpose:
    """Create or update a processing purpose from normalized config.

    This function does not read Django settings directly. It expects a config
    object that has already been prepared by `settings.py`, so the service
    layer does not repeat structure validation.
    """
    purpose, _ = ConsentPurpose.objects.update_or_create(
        code=code,
        defaults={
            "title": config["title"],
            "description": config["description"],
            "fields_config": config["fields"],
            "withdraw_strategy": config["withdraw_strategy"],
            "reconsent_mode": config["reconsent_mode"],
            "consent_frequency_policy": config["consent_frequency_policy"],
            "subject_availability_policy": config["subject_availability_policy"],
            "is_experimental": config["is_experimental"],
            "is_active": config["is_active"],
        },
    )
    return purpose


@transaction.atomic
def register_purposes_from_config() -> list[ConsentPurpose]:
    """Synchronize all `ConsentPurpose` with project configuration."""
    purposes_config = get_purposes_config()

    registered: list[ConsentPurpose] = []
    for code, purpose_config in purposes_config.items():
        purpose = register_purpose(code=code, config=purpose_config)
        registered.append(purpose)

    return registered


@transaction.atomic
def publish_document_revision(
    *,
    document_code: str,
    purpose_code: str,
    content_format: str,
    content_text: str = "",
    content_file=None,
    fields_snapshot: list[str] | None = None,
    meta: Mapping[str, Any] | None = None,
    is_box_template: bool = False,
    document_title: str | None = None,
    document_type: str = "consent",
    document_description: str = "",
    audit_context: Mapping[str, Any] | None = None,
    actor_user=None,
    actor_type: str | None = None,
) -> DocumentRevision:
    """Publish a new active document revision.

    The publication performs several actions in one transaction:
    - create or update the top-level `LegalDocument`;
    - create a new `DocumentRevision`;
    - deactivate previous revisions of the same document stream;
    - mark current consents as `outdated` when a newer revision now exists.
    """
    purpose = _require_purpose(purpose_code=purpose_code)

    defaults = {
        "title": document_title or document_code,
        "document_type": document_type,
        "description": document_description,
        "is_active": True,
    }
    document, _ = LegalDocument.objects.get_or_create(
        code=document_code,
        defaults=defaults,
    )
    if document_title and document.title != document_title:
        document.title = document_title
    if document.document_type != document_type:
        document.document_type = document_type
    if document.description != document_description:
        document.description = document_description
    if not document.is_active:
        document.is_active = True
    document.save()

    latest_version = (
        DocumentRevision.objects.filter(document=document, purpose_code=purpose.code)
        .aggregate(last_version=Max("version"))
        .get("last_version")
        or 0
    )
    next_version = latest_version + 1
    effective_fields_snapshot = (
        list(fields_snapshot)
        if fields_snapshot is not None
        else list(purpose.fields_config)
    )
    revision = DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=next_version,
        format=content_format,
        content_text=content_text,
        content_file=content_file,
        fields_snapshot=effective_fields_snapshot,
        meta=dict(meta or {}),
        is_active=True,
        is_box_template=is_box_template,
        published_at=timezone.now(),
    )
    DocumentRevision.objects.filter(
        document=document,
        purpose_code=purpose.code,
    ).exclude(pk=revision.pk).update(is_active=False)

    _mark_current_consents_outdated(
        purpose=purpose,
        document_code=document.code,
        payload={"reason": "new_revision_published", "revision_id": revision.pk},
        audit_context=audit_context,
        actor_user=actor_user,
        actor_type=actor_type,
    )

    return revision


def render_document_revision_pdf_bytes(*, revision: DocumentRevision) -> bytes:
    """Render a PDF version of the document revision.

    Basic contract:
    - `pdf_file` is returned as is;
    - `plain_text` and `markdown` go through the built-in
      `Markdown -> HTML -> PDF` pipeline;
    - `html` requires the optional `document_templates.html_to_pdf_hook`.

    Trust boundary:
    - HTML revisions and the hook run without built-in sanitization of
      `body_html`;
    - only trusted roles (administrators or personal data owners) should be
      able to create or edit HTML revisions;
    - the PDF renderer must enforce its own security policy.
    """
    if revision.format == DocumentRevision.ContentFormat.PDF_FILE:
        payload = render_document_revision_download_payload(revision=revision)
        return cast(bytes, payload["content"])

    body_html = _render_revision_text_to_html(revision=revision)
    if revision.format == DocumentRevision.ContentFormat.HTML:
        templates_settings = get_document_templates_settings()
        html_to_pdf_hook = templates_settings[
            constants.CONFIG_DOCUMENT_TEMPLATES_HTML_TO_PDF_HOOK
        ]
        if not html_to_pdf_hook:
            raise ConsentError(
                "HTML document export requires document_templates.html_to_pdf_hook "
                "integration."
            )
        return _call_html_to_pdf_hook(
            hook=html_to_pdf_hook,
            body_html=body_html,
            revision=revision,
        )

    text_payload = _extract_text_from_html(body_html)
    return _build_simple_pdf_bytes(text=text_payload)


def render_document_revision_download_payload(
    *, revision: DocumentRevision
) -> dict[str, str | bytes]:
    """Return bytes/mime/ext to download the active version of the document."""
    file_format_to_meta: dict[str, tuple[str, str]] = {
        DocumentRevision.ContentFormat.PDF_FILE: ("application/pdf", "pdf"),
    }
    if revision.format in file_format_to_meta:
        if not revision.content_file:
            raise ConsentError("content_file is required for selected file format.")
        mime_type, extension = file_format_to_meta[revision.format]
        revision.content_file.open("rb")
        try:
            return {
                "content": bytes(revision.content_file.read() or b""),
                "content_type": mime_type,
                "extension": extension,
            }
        finally:
            revision.content_file.close()

    if revision.format == DocumentRevision.ContentFormat.OFFICE_FILE:
        if not revision.content_file:
            raise ConsentError("content_file is required for selected file format.")
        filename = str(getattr(revision.content_file, "name", "") or "").lower()
        office_mime_map: dict[str, tuple[str, str]] = {
            ".doc": ("application/msword", "doc"),
            ".docx": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "docx",
            ),
            ".odt": ("application/vnd.oasis.opendocument.text", "odt"),
            ".odtx": ("application/vnd.oasis.opendocument.text-template", "odtx"),
        }
        content_type, extension = (
            "application/octet-stream",
            "bin",
        )
        for suffix, payload in office_mime_map.items():
            if filename.endswith(suffix):
                content_type, extension = payload
                break
        revision.content_file.open("rb")
        try:
            return {
                "content": bytes(revision.content_file.read() or b""),
                "content_type": content_type,
                "extension": extension,
            }
        finally:
            revision.content_file.close()

    return {
        "content": render_document_revision_pdf_bytes(revision=revision),
        "content_type": "application/pdf",
        "extension": "pdf",
    }


@transaction.atomic
def clone_box_template_revision(
    *,
    template_revision: DocumentRevision,
) -> DocumentRevision:
    """Create a user draft from a starter template.

    This operation is for admin/UI layers where the starter sample should
    quickly become an editable user revision, but without immediate
    publication or mutation of the source template.

    Invariants:
    - only `is_box_template=True` revisions can be cloned;
    - the clone is always created as `is_box_template=False` and
      `is_active=False`;
    - the source starter template is not changed;
    - file templates are not copied automatically yet to avoid hidden storage
      coupling and duplicate binary artifacts without an explicit project
      decision.
    """
    if not template_revision.is_box_template:
        raise ConsentError("Only box template revisions can be cloned as drafts.")
    if template_revision.content_file:
        raise ConsentError(
            "Box template revisions with content_file must be adapted manually."
        )

    latest_version = (
        DocumentRevision.objects.filter(
            document=template_revision.document,
            purpose_code=template_revision.purpose_code,
        )
        .aggregate(last_version=Max("version"))
        .get("last_version")
        or 0
    )

    clone_meta = deepcopy(template_revision.meta or {})
    clone_meta["starter_template"] = False
    clone_meta["derived_from_box_template"] = True
    clone_meta["box_template_source_revision_id"] = template_revision.pk
    clone_meta["box_template_source_version"] = template_revision.version
    clone_meta["box_template_source_document_code"] = template_revision.document.code
    clone_meta["box_template_source_purpose_code"] = template_revision.purpose_code

    return DocumentRevision.objects.create(
        document=template_revision.document,
        purpose_code=template_revision.purpose_code,
        version=latest_version + 1,
        format=template_revision.format,
        content_text=template_revision.content_text,
        fields_snapshot=list(template_revision.fields_snapshot),
        meta=clone_meta,
        is_active=False,
        is_box_template=False,
        published_at=None,
    )


@transaction.atomic
def clone_legal_document_stream_as_draft(
    *,
    source_document: LegalDocument,
) -> tuple[LegalDocument, int]:
    """Clone the document and all its revision streams into a secure draft."""
    cloned_document_code = _build_unique_clone_code(
        model=LegalDocument,
        source_code=source_document.code,
    )
    cloned_document = LegalDocument.objects.create(
        code=cloned_document_code,
        title=_clone_title(source_document.title),
        document_type=source_document.document_type,
        description=source_document.description,
        is_active=False,
    )

    cloned_revisions_count = 0
    revisions = source_document.revisions.order_by("purpose_code", "version", "pk")  # pyright: ignore[reportAttributeAccessIssue]
    for revision in revisions:
        clone_meta = deepcopy(revision.meta or {})
        clone_meta["starter_template"] = False
        clone_meta["derived_from_document_clone"] = True
        clone_meta["source_document_id"] = source_document.pk
        clone_meta["source_document_code"] = source_document.code
        clone_meta["source_revision_id"] = revision.pk
        clone_meta["source_revision_version"] = revision.version

        DocumentRevision.objects.create(
            document=cloned_document,
            purpose_code=revision.purpose_code,
            version=revision.version,
            format=revision.format,
            content_text=revision.content_text,
            content_file=(
                revision.content_file.name if revision.content_file else None
            ),
            fields_snapshot=list(revision.fields_snapshot),
            meta=clone_meta,
            is_active=False,
            is_box_template=False,
            published_at=None,
        )
        cloned_revisions_count += 1

    return cloned_document, cloned_revisions_count


@transaction.atomic
def clone_access_policy_as_draft(
    *,
    source_policy: ConsentAccessPolicy,
) -> ConsentAccessPolicy:
    """Clone the access policy as an inactive draft with new code."""
    cloned_code = _build_unique_clone_code(
        model=ConsentAccessPolicy,
        source_code=source_policy.code,
    )
    cloned_resource_code = _build_unique_policy_resource_code(
        source_resource_code=source_policy.resource_code,
        action=source_policy.action,
    )
    extra_meta = deepcopy(source_policy.extra_meta or {})
    extra_meta["starter_template"] = False
    extra_meta["derived_from_policy_clone"] = True
    extra_meta["source_policy_id"] = source_policy.pk
    extra_meta["source_policy_code"] = source_policy.code

    return ConsentAccessPolicy.objects.create(
        code=cloned_code,
        title=_clone_title(source_policy.title),
        description=source_policy.description,
        purpose=source_policy.purpose,
        document=source_policy.document,
        resource_code=cloned_resource_code,
        app_label=source_policy.app_label,
        model_name=source_policy.model_name,
        action=source_policy.action,
        on_missing_consent=source_policy.on_missing_consent,
        on_outdated_consent=source_policy.on_outdated_consent,
        is_active=False,
        starts_at=source_policy.starts_at,
        ends_at=source_policy.ends_at,
        notes=_clone_notes(source_policy.notes),
        extra_meta=extra_meta,
    )


@transaction.atomic
def clone_audience_rule_as_draft(
    *,
    source_rule: ConsentAudienceRule,
    created_by=None,
) -> ConsentAudienceRule:
    """Clone the audience rule as an inactive draft."""
    return ConsentAudienceRule.objects.create(
        purpose=source_rule.purpose,
        document=source_rule.document,
        scope_mode=source_rule.scope_mode,
        group=source_rule.group,
        is_required=source_rule.is_required,
        is_active=False,
        starts_at=source_rule.starts_at,
        ends_at=source_rule.ends_at,
        notes=_clone_notes(source_rule.notes),
        created_by=created_by if created_by is not None else source_rule.created_by,
    )


def _build_unique_clone_code(
    *,
    model,
    source_code: str,
) -> str:
    """Collect unique code for clone entities."""
    code_field = model._meta.get_field("code")
    max_length = int(cast(Any, code_field).max_length or 0)
    base_code = source_code.strip() or "clone"

    for index in range(1, 1000):
        clone_suffix = "_copy" if index == 1 else f"_copy_{index}"
        max_base_len = max_length - len(clone_suffix)
        if max_base_len < 1:
            raise ConsentError("Unable to allocate unique clone code.")
        candidate = f"{base_code[:max_base_len]}{clone_suffix}"
        if not model.objects.filter(code=candidate).exists():
            return candidate
    raise ConsentError("Unable to allocate unique clone code.")


def _build_unique_policy_resource_code(
    *,
    source_resource_code: str,
    action: str,
) -> str:
    """Collect a unique `resource_code` for the access policy clone."""
    field = ConsentAccessPolicy._meta.get_field("resource_code")
    max_length = int(cast(Any, field).max_length or 0)
    base_code = source_resource_code.strip() or "resource"

    for index in range(1, 1000):
        clone_suffix = "_copy" if index == 1 else f"_copy_{index}"
        max_base_len = max_length - len(clone_suffix)
        if max_base_len < 1:
            raise ConsentError("Unable to allocate unique cloned resource_code.")
        candidate = f"{base_code[:max_base_len]}{clone_suffix}"
        if not ConsentAccessPolicy.objects.filter(
            resource_code=candidate,
            action=action,
        ).exists():
            return candidate
    raise ConsentError("Unable to allocate unique cloned resource_code.")


def _clone_title(source_title: str) -> str:
    title = (source_title or "").strip()
    if not title:
        return "Копия"
    return f"{title} (копия)"[:255]


def _clone_notes(source_notes: str) -> str:
    notes = (source_notes or "").strip()
    if not notes:
        return "Черновая копия."
    return f"{notes}\n\nЧерновая копия."


def get_current_requirements(
    *,
    user=None,
    anonymous_token: str | None = None,
    verification_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the current consent requirements for a subject.

    This function aggregates data from several layers at once:
    - active processing purposes;
    - active document-stream revisions;
    - audience rules;
    - verified policy;
    - the subject's current consent state.
    """
    requirements: list[dict[str, Any]] = []
    purposes = ConsentPurpose.objects.filter(is_active=True).order_by("code")

    for purpose in purposes:
        active_revisions = list(
            _active_revisions_qs(purpose_code=purpose.code).order_by("document__code")
        )
        if not active_revisions:
            continue

        for latest_revision in active_revisions:
            if not _flow_requires_consent_for_subject(
                purpose=purpose,
                document=latest_revision.document,
                user=user,
                anonymous_token=anonymous_token,
            ):
                continue
            verified_resolution = _get_verified_consent_resolution_for_flow(
                purpose_code=purpose.code,
                document_code=latest_revision.document.code,
                verification_context=verification_context,
            )
            status_info = get_consent_status(
                purpose_code=purpose.code,
                document_code=latest_revision.document.code,
                user=user,
                anonymous_token=anonymous_token,
                verification_context=verification_context,
            )
            requirements.append(
                {
                    "purpose_code": purpose.code,
                    "title": purpose.title,
                    "description": purpose.description,
                    "fields": list(purpose.fields_config),
                    "withdraw_strategy": purpose.withdraw_strategy,
                    "reconsent_mode": purpose.reconsent_mode,
                    "consent_frequency_policy": purpose.consent_frequency_policy,
                    "subject_availability_policy": purpose.subject_availability_policy,
                    "document_code": latest_revision.document.code,
                    "document_title": latest_revision.document.title,
                    "document_type": latest_revision.document.document_type,
                    "verified_consent": {
                        "required": bool(verified_resolution["required"]),
                        "verification_mode": (
                            verified_resolution["verification_mode"]
                            if bool(verified_resolution["required"])
                            else None
                        ),
                    },
                    "latest_revision": {
                        "id": latest_revision.pk,
                        "document_code": latest_revision.document.code,
                        "document_title": latest_revision.document.title,
                        "document_type": latest_revision.document.document_type,
                        "version": latest_revision.version,
                        "format": latest_revision.format,
                        "published_at": latest_revision.published_at,
                        "is_box_template": latest_revision.is_box_template,
                    },
                    "consent_status": status_info["status"],
                    "requires_consent": status_info["requires_consent"],
                    "consent_required_reason": status_info["consent_required_reason"],
                    "is_applicable": status_info["is_applicable"],
                    "verified_transition": status_info.get("verified_transition"),
                }
            )

    return {
        "provider_code": constants.PROVIDER_CODE,
        "requirements": requirements,
    }


@transaction.atomic
def mark_outdated_consents(
    *,
    purpose_code: str | None = None,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
    trigger_email_reminder: bool = False,
    audit_context: Mapping[str, Any] | None = None,
    actor_user=None,
    actor_type: str | None = None,
) -> list[ConsentRecord]:
    """Move matching `current` records to `outdated`.

    Функция используется как отдельный сервис и как часть других сценариев.
    Она не просто сравнивает revision id, а ещё учитывает применимость
    audience rules для конкретного субъекта.
    """
    token = (anonymous_token or "").strip()
    qs = ConsentRecord.objects.select_related(
        "purpose",
        "document_revision__document",
    ).filter(status=ConsentRecord.Status.CURRENT)
    if purpose_code:
        qs = qs.filter(purpose__code=purpose_code)
    if document_code:
        qs = qs.filter(document_revision__document__code=document_code)
    if user is not None and token:
        qs = qs.filter(Q(user=user) | Q(anonymous_token=token))
    elif user is not None:
        qs = qs.filter(user=user)
    elif token:
        qs = qs.filter(anonymous_token=token)

    outdated_records: list[ConsentRecord] = []
    normalized_audit_context = _normalize_audit_context(audit_context=audit_context)
    for record in qs:
        latest_revision = _get_latest_active_revision(
            purpose_code=record.purpose.code,
            document_code=record.document_revision.document.code,
        )
        if latest_revision is None:
            continue
        if not _flow_requires_consent_for_record(
            purpose=record.purpose,
            document=record.document_revision.document,
            record=record,
        ):
            continue
        if record.document_revision_id == latest_revision.pk:  # pyright: ignore[reportAttributeAccessIssue]
            continue

        record.status = ConsentRecord.Status.OUTDATED
        record.save()
        _create_consent_event(
            consent_record=record,
            event_type=ConsentEvent.EventType.OUTDATED,
            actor_user=actor_user,
            actor_type=actor_type or ConsentEvent.ActorType.SYSTEM,
            audit_context=normalized_audit_context,
            payload={
                "reason": "revision_mismatch",
                "latest_revision_id": latest_revision.pk,
                "document_code": latest_revision.document.code,
            },
        )
        if trigger_email_reminder:
            trigger_reconsent_email_reminder(record)
        outdated_records.append(record)

    return outdated_records


@transaction.atomic
def accept_consent(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
    subject_ref: str = "",
    fields_snapshot: list[str] | None = None,
    confirmation_method: str = constants.CONFIRMATION_METHOD_WEB_CHECKBOX,
    source: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    locale: str = "",
    request_id: str = "",
    session_key_hash: str = "",
    extra_meta: Mapping[str, Any] | None = None,
    audit_context: Mapping[str, Any] | None = None,
    confirmed_by=None,
    confirmed_at=None,
    confirmation_note: str = "",
    event_payload: Mapping[str, Any] | None = None,
    event_actor_user=None,
    event_actor_type: str | None = None,
    verified_submission: bool = False,
    verification_context: Mapping[str, Any] | None = None,
) -> ConsentRecord:
    """Record a new subject consent.

    This intentionally brings together:
    - document-stream selection;
    - verified-policy checks;
    - audit-context normalization;
    - creation of `ConsentRecord`;
    - writing the immutable `ConsentEvent`;
    - replacing the previous current record for the same stream.
    """
    purpose = _require_purpose(purpose_code=purpose_code)
    token = (anonymous_token or "").strip()
    resolved_document_code = _resolve_document_code(
        purpose_code=purpose.code,
        document_code=document_code,
    )
    if not _is_subject_allowed_for_purpose(
        purpose=purpose,
        user=user,
        anonymous_token=token,
    ):
        raise ConsentError(
            "Для этой цели требуется авторизация. Войдите в аккаунт, "
            "чтобы подтвердить согласие."
        )
    latest_revision = _require_latest_revision(
        purpose_code=purpose.code,
        document_code=resolved_document_code,
    )
    verified_resolution = _get_verified_consent_resolution_for_flow(
        purpose_code=purpose.code,
        document_code=latest_revision.document.code,
        verification_context=verification_context,
    )
    if (
        confirmation_method == ConsentRecord.ConfirmationMethod.UPLOADED_PAPER
        and not verified_submission
    ):
        raise ConsentError(
            "uploaded_paper flow is available only through "
            "verified_consents.submit_verified_consent()."
        )
    if bool(verified_resolution["required"]) and not (
        _is_confirmation_method_allowed_for_verified_policy(
            confirmation_method=confirmation_method,
            verification_mode=str(verified_resolution["verification_mode"]),
        )
    ):
        raise ConsentError(
            "This consent flow requires verified confirmation. "
            "Use verified_consents services for this purpose/document stream."
        )

    final_fields_snapshot = (
        list(fields_snapshot)
        if fields_snapshot is not None
        else list(latest_revision.fields_snapshot)
    )
    normalized_audit_context = _normalize_audit_context(
        audit_context=audit_context,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        locale=locale,
        request_id=request_id,
        session_key_hash=session_key_hash,
        extra_meta=extra_meta,
    )
    status = _resolve_initial_status(
        purpose=purpose,
        confirmation_method=confirmation_method,
    )
    attempts = 0
    while True:
        attempts += 1
        try:
            with transaction.atomic():
                previous_current_records = list(
                    _subject_records_qs(
                        purpose=purpose,
                        user=user,
                        anonymous_token=token,
                        document_code=latest_revision.document.code,
                    )
                    .select_for_update()
                    .filter(status=ConsentRecord.Status.CURRENT)
                    .order_by("-created_at", "-id")
                )
                if status == ConsentRecord.Status.CURRENT:
                    for previous in previous_current_records:
                        previous.status = ConsentRecord.Status.OUTDATED
                        previous.save(update_fields=["status", "updated_at"])

                record = ConsentRecord.objects.create(
                    user=user,
                    subject_ref=subject_ref or (str(user.pk) if user else ""),
                    anonymous_token=token,
                    purpose=purpose,
                    document_revision=latest_revision,
                    fields_snapshot=final_fields_snapshot,
                    status=status,
                    confirmation_method=confirmation_method,
                    source=normalized_audit_context["source"],
                    ip_address=normalized_audit_context["ip_address"],
                    user_agent=normalized_audit_context["user_agent"],
                    locale=normalized_audit_context["locale"],
                    extra_meta=normalized_audit_context["extra_meta"],
                    confirmed_by=confirmed_by,
                    confirmed_at=confirmed_at,
                    confirmation_note=confirmation_note,
                )
                _create_consent_event(
                    consent_record=record,
                    event_type=_event_type_for_accept(
                        confirmation_method=confirmation_method
                    ),
                    actor_user=(
                        event_actor_user
                        if event_actor_user is not None
                        else _event_actor_user_for_accept(
                            confirmation_method=confirmation_method,
                            user=user,
                            confirmed_by=confirmed_by,
                        )
                    ),
                    actor_type=(
                        event_actor_type
                        if event_actor_type is not None
                        else _actor_type_for_accept(
                            confirmation_method=confirmation_method
                        )
                    ),
                    audit_context=normalized_audit_context,
                    payload={
                        "consent_frequency_policy": purpose.consent_frequency_policy,
                        "repeated_confirmation": bool(previous_current_records),
                        **dict(event_payload or {}),
                    },
                    occurred_at=confirmed_at,
                )

                if record.status == ConsentRecord.Status.CURRENT:
                    for previous in previous_current_records:
                        _create_consent_event(
                            consent_record=previous,
                            event_type=ConsentEvent.EventType.OUTDATED,
                            actor_type=ConsentEvent.ActorType.SYSTEM,
                            audit_context=normalized_audit_context,
                            payload={
                                "reason": "superseded_by_new_accept",
                                "record_id": record.pk,
                            },
                        )
            return record
        except IntegrityError:
            if status != ConsentRecord.Status.CURRENT or attempts >= 3:
                raise


@transaction.atomic
def withdraw_consent(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
    source: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    locale: str = "",
    request_id: str = "",
    session_key_hash: str = "",
    extra_meta: Mapping[str, Any] | None = None,
    audit_context: Mapping[str, Any] | None = None,
) -> ConsentRecord:
    """Withdraw consent and run the post-withdraw strategy.

    Withdrawal does not silently delete the consent record. First the
    canonical `ConsentRecord` status changes, then `withdrawn` is written to
    the immutable log, and only then the `block` or `delete` strategy runs.
    """
    purpose = _require_purpose(purpose_code=purpose_code)
    token = (anonymous_token or "").strip()
    resolved_document_code = _resolve_document_code(
        purpose_code=purpose.code,
        document_code=document_code,
    )
    if user is None and token and not is_anonymous_withdraw_enabled():
        raise ConsentError(
            "Отзыв согласия для анонимного пользователя недоступен. "
            "Войдите в аккаунт для продолжения."
        )
    current_record = (
        _subject_records_qs(
            purpose=purpose,
            user=user,
            anonymous_token=token,
            document_code=resolved_document_code,
        )
        .select_for_update()
        .exclude(status=ConsentRecord.Status.WITHDRAWN)
        .exclude(status=ConsentRecord.Status.DELETED)
        .order_by("-created_at", "-id")
        .first()
    )
    if current_record is None:
        raise ConsentError(
            f"No consent record found for purpose '{purpose.code}' and subject."
        )
    current_record.refresh_from_db(fields=["status"])
    if current_record.status in {
        ConsentRecord.Status.WITHDRAWN,
        ConsentRecord.Status.DELETED,
    }:
        raise ConsentError(
            f"No consent record found for purpose '{purpose.code}' and subject."
        )

    normalized_audit_context = _normalize_audit_context(
        audit_context=audit_context,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        locale=locale,
        request_id=request_id,
        session_key_hash=session_key_hash,
        extra_meta=extra_meta,
    )
    current_record.status = ConsentRecord.Status.WITHDRAWN
    current_record.save()
    _create_consent_event(
        consent_record=current_record,
        event_type=ConsentEvent.EventType.WITHDRAWN,
        actor_user=user if getattr(user, "pk", None) is not None else None,
        actor_type=ConsentEvent.ActorType.SUBJECT,
        audit_context=normalized_audit_context,
    )

    if purpose.withdraw_strategy == ConsentPurpose.WithdrawStrategy.BLOCK:
        _create_consent_event(
            consent_record=current_record,
            event_type=ConsentEvent.EventType.BLOCKED,
            actor_type=ConsentEvent.ActorType.SYSTEM,
            audit_context=normalized_audit_context,
        )
        request_block_after_withdraw(current_record)
    elif purpose.withdraw_strategy == ConsentPurpose.WithdrawStrategy.DELETE:
        _create_consent_event(
            consent_record=current_record,
            event_type=ConsentEvent.EventType.DELETE_REQUESTED,
            actor_type=ConsentEvent.ActorType.SYSTEM,
            audit_context=normalized_audit_context,
        )
        request_delete_after_withdraw(current_record)

    return current_record


def get_consent_status(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
    verification_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute the effective consent status for a `purpose + document` stream.

    The function returns the effective status, not the raw status of the last
    record. It also accounts for:
    - mismatch between the current record and the latest revision;
    - a verified policy layered over an older web consent;
    - whether the stream applies to the subject's audience.
    """
    purpose = _require_purpose(purpose_code=purpose_code)
    token = (anonymous_token or "").strip()
    resolved_document_code = _resolve_document_code(
        purpose_code=purpose.code,
        document_code=document_code,
    )
    latest_revision = _get_latest_active_revision(
        purpose_code=purpose.code,
        document_code=resolved_document_code,
    )
    verified_resolution = _get_verified_consent_resolution_for_flow(
        purpose_code=purpose.code,
        document_code=resolved_document_code,
        verification_context=verification_context,
    )
    verified_transition = _get_verified_transition_state_for_flow(
        purpose_code=purpose.code,
        document_code=resolved_document_code,
        user=user,
        anonymous_token=token or None,
        verification_context=verification_context,
    )

    latest_record = None
    if user is not None or token:
        latest_record = (
            _subject_records_qs(
                purpose=purpose,
                user=user,
                anonymous_token=token,
                document_code=resolved_document_code,
            )
            .order_by("-created_at", "-id")
            .first()
        )

    applicable = latest_revision is not None and _flow_requires_consent_for_subject(
        purpose=purpose,
        document=latest_revision.document,
        user=user,
        anonymous_token=token,
    )
    not_applicable_reason = _resolve_not_applicable_reason(
        purpose=purpose,
        user=user,
        anonymous_token=token,
    )
    if not applicable:
        return {
            "purpose_code": purpose.code,
            "document_code": (
                latest_revision.document.code
                if latest_revision is not None
                else resolved_document_code
            ),
            "record_id": latest_record.pk if latest_record else None,
            "status": None,
            "requires_consent": False,
            "is_current": False,
            "is_outdated": False,
            "latest_revision_id": latest_revision.pk if latest_revision else None,
            "record_revision_id": (
                latest_record.document_revision_id  # pyright: ignore[reportAttributeAccessIssue]
                if latest_record is not None
                else None
            ),
            "reconsent_mode": purpose.reconsent_mode,
            "access_restricted": False,
            "is_applicable": False,
            "not_applicable_reason": not_applicable_reason,
            "auth_required_for_consent": not_applicable_reason == "auth_required",
            "consent_required_reason": constants.CONSENT_REQUIRED_REASON_NOT_APPLICABLE,
            "verified_transition": verified_transition,
        }

    effective_status = latest_record.status if latest_record else None
    if (
        latest_record is not None
        and latest_revision is not None
        and latest_record.document_revision_id != latest_revision.pk  # pyright: ignore[reportAttributeAccessIssue]
        and latest_record.status == ConsentRecord.Status.CURRENT
    ):
        effective_status = ConsentRecord.Status.OUTDATED
    elif (
        bool(verified_resolution["required"])
        and latest_record is not None
        and latest_record.status == ConsentRecord.Status.CURRENT
        and not _is_confirmation_method_allowed_for_verified_policy(
            confirmation_method=latest_record.confirmation_method,
            verification_mode=str(verified_resolution["verification_mode"]),
        )
    ):
        transition_mode = _resolve_legacy_web_consent_transition_mode(
            verified_resolution=verified_resolution
        )
        if transition_mode == "mark_web_outdated":
            latest_record = _apply_verified_legacy_transition_for_subject_stream(
                purpose=purpose,
                user=user,
                anonymous_token=token,
                document_code=resolved_document_code,
                verified_resolution=verified_resolution,
                transition_mode=transition_mode,
            )
            effective_status = (
                latest_record.status if latest_record is not None else None
            )
        elif transition_mode == "withdraw_web_now":
            latest_record = _apply_verified_legacy_transition_for_subject_stream(
                purpose=purpose,
                user=user,
                anonymous_token=token,
                document_code=resolved_document_code,
                verified_resolution=verified_resolution,
                transition_mode=transition_mode,
            )
            effective_status = (
                latest_record.status if latest_record is not None else None
            )
        else:
            effective_status = latest_record.status

    requires_consent = _requires_consent_by_policy(
        effective_status=effective_status,
        purpose=purpose,
    )
    consent_required_reason = _resolve_consent_required_reason(
        purpose=purpose,
        effective_status=effective_status,
        requires_consent=requires_consent,
    )
    return {
        "purpose_code": purpose.code,
        "document_code": (
            latest_revision.document.code
            if latest_revision is not None
            else resolved_document_code
        ),
        "record_id": latest_record.pk if latest_record else None,
        "status": effective_status,
        "requires_consent": requires_consent,
        "consent_required_reason": consent_required_reason,
        "is_current": effective_status == ConsentRecord.Status.CURRENT,
        "is_outdated": effective_status == ConsentRecord.Status.OUTDATED,
        "latest_revision_id": latest_revision.pk if latest_revision else None,
        "record_revision_id": (
            latest_record.document_revision_id  # pyright: ignore[reportAttributeAccessIssue]
            if latest_record is not None
            else None
        ),
        "reconsent_mode": purpose.reconsent_mode,
        "access_restricted": (
            effective_status == ConsentRecord.Status.OUTDATED
            and purpose.reconsent_mode == ConsentPurpose.ReconsentMode.HARD
        ),
        "is_applicable": True,
        "not_applicable_reason": None,
        "auth_required_for_consent": False,
        "verified_transition": verified_transition,
    }


def get_reconsent_notice(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user=None,
    anonymous_token: str | None = None,
) -> dict[str, Any] | None:
    """Collect data for UI notification about the need for repeated consent."""
    status_info = get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
    )
    if status_info["status"] != ConsentRecord.Status.OUTDATED:
        return None

    mode = status_info["reconsent_mode"]
    if mode == ConsentPurpose.ReconsentMode.HARD:
        return {
            "kind": "hard_reconsent",
            "blocking": True,
            "title": "Требуется новое согласие",
            "message": (
                "Доступ к функциональности ограничен до подтверждения новой редакции."
            ),
            "purpose_code": purpose_code,
            "document_code": status_info["document_code"],
        }

    return {
        "kind": "soft_reconsent",
        "blocking": False,
        "title": "Рекомендуем обновить согласие",
        "message": (
            "Доступ к части функциональности может быть ограничен до нового согласия."
        ),
        "purpose_code": purpose_code,
        "document_code": status_info["document_code"],
    }


def evaluate_consent_access(
    *,
    resource_code: str,
    action: str,
    user=None,
    anonymous_token: str | None = None,
) -> dict[str, Any]:
    """Compute the final guard-layer decision for a resource and action.

    The service does not raise and does not change state. It only computes a
    normalized result that UI, API, middleware, or the business layer can use.
    """
    normalized_resource_code = resource_code.strip()
    normalized_action = action.strip()
    token = (anonymous_token or "").strip()

    if not normalized_resource_code:
        raise ConsentError("resource_code must be a non-empty string.")
    if not normalized_action:
        raise ConsentError("action must be a non-empty string.")
    if user is None and not token:
        raise ConsentError("Either user or anonymous_token must be provided.")

    if not is_access_policies_enabled():
        return _neutral_access_result(
            enabled=False,
            reason="feature_disabled",
            resource_code=normalized_resource_code,
            action=normalized_action,
        )

    policy = _get_active_access_policy(
        resource_code=normalized_resource_code,
        action=normalized_action,
    )
    if policy is None:
        return _neutral_access_result(
            enabled=True,
            reason="no_matching_policy",
            resource_code=normalized_resource_code,
            action=normalized_action,
        )

    status_info = cast(
        ConsentStatusInfo,
        get_consent_status(
            purpose_code=policy.purpose.code,
            document_code=policy.document.code,
            user=user,
            anonymous_token=token,
        ),
    )
    if not status_info["is_applicable"]:
        return _build_access_result(
            enabled=True,
            policy=policy,
            status_info=status_info,
            resolution=constants.ACCESS_POLICY_RESOLUTION_ALLOW,
            reason="policy_not_applicable",
            resource_code=normalized_resource_code,
            action=normalized_action,
        )

    if status_info["status"] == ConsentRecord.Status.CURRENT:
        return _build_access_result(
            enabled=True,
            policy=policy,
            status_info=status_info,
            resolution=constants.ACCESS_POLICY_RESOLUTION_ALLOW,
            reason="current_consent",
            resource_code=normalized_resource_code,
            action=normalized_action,
        )

    if status_info["status"] == ConsentRecord.Status.OUTDATED:
        resolution, reason = _resolve_outdated_access_resolution(
            policy=policy,
            status_info=status_info,
        )
        return _build_access_result(
            enabled=True,
            policy=policy,
            status_info=status_info,
            resolution=resolution,
            reason=reason,
            resource_code=normalized_resource_code,
            action=normalized_action,
        )

    return _build_access_result(
        enabled=True,
        policy=policy,
        status_info=status_info,
        resolution=_policy_action_to_resolution(action_value=policy.on_missing_consent),
        reason="missing_consent",
        resource_code=normalized_resource_code,
        action=normalized_action,
    )


def assert_consent_access(
    *,
    resource_code: str,
    action: str,
    user=None,
    anonymous_token: str | None = None,
    allow_read_only: bool = False,
) -> dict[str, Any]:
    """Вариант `evaluate_consent_access()`, который бросает исключение.

    Это удобно там, где проект хочет получить fail-fast поведение вместо
    ручной обработки результата guard-layer.
    """
    result = evaluate_consent_access(
        resource_code=resource_code,
        action=action,
        user=user,
        anonymous_token=anonymous_token,
    )
    if result["allowed"] or (allow_read_only and result["read_only"]):
        return result

    policy_hint = (
        f" by consent policy '{result['policy_code']}'" if result["policy_code"] else ""
    )
    raise ConsentAccessDenied(
        (
            f"Access denied for resource '{result['resource_code']}' "
            f"action '{result['action']}'{policy_hint} "
            f"(resolution: {result['resolution']})."
        ),
        result=result,
    )


@transaction.atomic
def attach_anonymous_consents_to_user(
    *,
    user,
    anonymous_token: str,
) -> list[ConsentRecord]:
    """Attach anonymous consent records to a registered user.

    This matters when a user acts anonymously first and then registers or
    logs in, and the package needs to reassign the accumulated consent records
    to that specific user.
    """
    UserModel = get_user_model()
    if not isinstance(user, UserModel):
        raise ConsentError("user must be an instance of AUTH_USER_MODEL.")

    token = anonymous_token.strip()
    if not token:
        raise ConsentError("anonymous_token must be a non-empty string.")

    records = list(
        ConsentRecord.objects.filter(user__isnull=True, anonymous_token=token).order_by(
            "created_at",
            "id",
        )
    )
    for record in records:
        previous_subject_ref = record.subject_ref
        record.user = user
        if not record.subject_ref:
            record.subject_ref = str(user.pk)
        record.save(update_fields=["user", "subject_ref", "updated_at"])
        _create_consent_event(
            consent_record=record,
            event_type=ConsentEvent.EventType.RECONFIRMED,
            actor_user=user,
            actor_type=ConsentEvent.ActorType.SUBJECT,
            audit_context={"source": "service.attach_anonymous_consents_to_user"},
            payload={
                "reason": "subject_attached",
                "attached_user_id": user.pk,
                "previous_subject_ref": previous_subject_ref,
            },
        )

    if bool(get_api_setting(constants.SETTING_ANON_TOKEN_REVOKE_ON_ATTACH)):
        from django_consent_152fz.request import revoke_anonymous_token

        revoke_anonymous_token(anonymous_token=token)

    return records


@transaction.atomic
def anonymize_subject_consents(
    *,
    user=None,
    anonymous_token: str | None = None,
    purpose_code: str | None = None,
    document_code: str | None = None,
    reason: str = "",
    actor_user=None,
    actor_type: str | None = None,
    audit_context: Mapping[str, Any] | None = None,
) -> list[ConsentRecord]:
    """Обезличить consent-записи субъекта и записать immutable audit events.

    Это не "мягкое скрытие" записи, а именно service-level building block
    для delete/anonymize сценариев:
    - subject identifiers и request-derived ПДн очищаются из `ConsentRecord`;
    - optional verified-артефакт тоже зачищается, если app подключён;
    - история переходов остаётся в `ConsentEvent`;
    - для самой операции создаётся отдельное событие `anonymized`.
    """
    subject_q = _build_subject_lookup_q(user=user, anonymous_token=anonymous_token)
    normalized_audit_context = _normalize_audit_context(audit_context=audit_context)
    resolved_actor_type = _resolve_anonymize_actor_type(
        actor_user=actor_user,
        actor_type=actor_type,
    )

    records_qs = ConsentRecord.objects.select_related(
        "purpose",
        "document_revision__document",
    ).filter(subject_q)
    if purpose_code:
        records_qs = records_qs.filter(purpose__code=purpose_code)
    if document_code:
        records_qs = records_qs.filter(document_revision__document__code=document_code)

    anonymized_records: list[ConsentRecord] = []
    for record in records_qs.order_by("created_at", "id"):
        if record.events.filter(  # pyright: ignore[reportAttributeAccessIssue]
            event_type=ConsentEvent.EventType.ANONYMIZED
        ).exists():
            continue
        _anonymize_consent_record(
            consent_record=record,
            reason=reason,
            actor_user=actor_user,
            actor_type=resolved_actor_type,
            audit_context=normalized_audit_context,
        )
        anonymized_records.append(record)

    return anonymized_records


def request_block_after_withdraw(record: ConsentRecord) -> None:
    """Proxy to session termination hook after revocation."""
    trigger_session_termination(record)


def request_delete_after_withdraw(record: ConsentRecord) -> None:
    """Proxy to external cleanup hook after revocation."""
    trigger_external_cleanup(record)


def _require_purpose(*, purpose_code: str) -> ConsentPurpose:
    """Return `ConsentPurpose` or raise a domain error."""
    purpose = ConsentPurpose.objects.filter(code=purpose_code).first()
    if purpose is None:
        raise ConsentError(f"Unknown purpose code: {purpose_code}")
    return purpose


def _build_subject_lookup_q(*, user, anonymous_token: str | None) -> Q:
    """Collect a Q-condition to search for records of a specific subject."""
    subject_q = Q()
    if user is not None:
        subject_q |= Q(user=user)

    token = str(anonymous_token or "").strip()
    if token:
        subject_q |= Q(anonymous_token=token)

    if not subject_q.children:
        raise ConsentError("Either user or anonymous_token must be provided.")
    return subject_q


def _resolve_anonymize_actor_type(*, actor_user=None, actor_type: str | None = None):
    """Allow actor type for anonymize script."""
    if actor_type:
        return actor_type
    if actor_user is not None:
        return (
            ConsentEvent.ActorType.ADMIN
            if getattr(actor_user, "is_superuser", False)
            else ConsentEvent.ActorType.EMPLOYEE
        )
    return ConsentEvent.ActorType.SUBJECT


def _anonymized_subject_marker(*, consent_record: ConsentRecord) -> str:
    """Construct a synthetic subject marker after depersonalization."""
    return f"anonymized:{consent_record.pk}"


def _anonymize_consent_record(
    *,
    consent_record: ConsentRecord,
    reason: str,
    actor_user,
    actor_type: str,
    audit_context: Mapping[str, Any] | None,
) -> ConsentRecord:
    """Anonymize one entry and record the `anonymized` event."""
    previous_status = consent_record.status
    verified_artifact_scrubbed = _anonymize_verified_artifact_if_present(
        consent_record=consent_record
    )
    anonymized_marker = _anonymized_subject_marker(consent_record=consent_record)

    consent_record.user = None
    consent_record.subject_ref = ""
    consent_record.anonymous_token = anonymized_marker
    consent_record.status = ConsentRecord.Status.DELETED
    consent_record.ip_address = None
    consent_record.user_agent = ""
    consent_record.locale = ""
    consent_record.extra_meta = {"custom": {"anonymized": True}}
    consent_record.confirmation_note = ""
    consent_record.save()

    _create_consent_event(
        consent_record=consent_record,
        event_type=ConsentEvent.EventType.ANONYMIZED,
        actor_user=actor_user,
        actor_type=actor_type,
        audit_context=audit_context,
        payload={
            "reason": reason or "subject_anonymization",
            "document_code": consent_record.document_revision.document.code,
            "revision_id": consent_record.document_revision_id,  # pyright: ignore[reportAttributeAccessIssue]
            "previous_status": previous_status,
            "new_status": consent_record.status,
            "anonymized_fields": [
                "user",
                "subject_ref",
                "anonymous_token",
                "ip_address",
                "user_agent",
                "locale",
                "extra_meta",
                "confirmation_note",
            ],
            "verified_artifact_scrubbed": verified_artifact_scrubbed,
        },
    )
    return consent_record


def _clear_file_field(file_field) -> bool:
    """Delete the file from storage and clear the link to it."""
    if not file_field:
        return False
    file_field.delete(save=False)
    return True


def _anonymize_verified_artifact_if_present(*, consent_record: ConsentRecord) -> bool:
    """Clear the optional verified artifact if it exists.

    `core` does not import the optional app at module level. The bridge to
    `verified_consents` therefore stays lazy and inert if the app is not
    installed.
    """
    if not is_verified_consents_app_installed():
        return False

    try:
        artifact = consent_record.verified_artifact  # pyright: ignore[reportAttributeAccessIssue]
    except ObjectDoesNotExist:
        return False

    _clear_file_field(artifact.file)
    artifact.delete()
    return True


def _require_latest_revision(
    *,
    purpose_code: str,
    document_code: str | None = None,
) -> DocumentRevision:
    """Guaranteed to return the active revision for the selected thread."""
    revision = _get_latest_active_revision(
        purpose_code=purpose_code,
        document_code=document_code,
    )
    if revision is None:
        document_hint = f" and document '{document_code}'" if document_code else ""
        raise ConsentError(
            f"No active document revision found for purpose '{purpose_code}'"
            f"{document_hint}."
        )
    return revision


def _active_revisions_qs(
    *,
    purpose_code: str | None = None,
    document_code: str | None = None,
):
    """Base queryset for active document revisions.

    A revision counts as active only if both the revision itself and the
    related `LegalDocument` are active.
    """
    qs = DocumentRevision.objects.select_related("document").filter(
        is_active=True,
        document__is_active=True,
    )
    if purpose_code:
        qs = qs.filter(purpose_code=purpose_code)
    if document_code:
        qs = qs.filter(document__code=document_code)
    return qs


def _resolve_document_code(
    *,
    purpose_code: str,
    document_code: str | None,
) -> str | None:
    """Resolve `document_code` for document-stream operations.

    If the purpose has exactly one active document, the code may be omitted.
    If there are multiple documents, the service must stop and require the
    caller to choose a specific stream explicitly.
    """
    if document_code:
        return document_code

    active_document_codes = list(
        _active_revisions_qs(purpose_code=purpose_code)
        .order_by("document__code")
        .values_list("document__code", flat=True)[:2]
    )
    if len(active_document_codes) > 1:
        raise ConsentError(
            f"Multiple active documents found for purpose '{purpose_code}'. "
            "Specify document_code."
        )
    if active_document_codes:
        return active_document_codes[0]
    return None


def _get_latest_active_revision(
    *,
    purpose_code: str,
    document_code: str | None = None,
) -> DocumentRevision | None:
    """Return the latest active document revision.

    When multiple active document streams exist and `document_code` is not
    provided, the service raises an error so it never picks one document
    implicitly.
    """
    qs = _active_revisions_qs(
        purpose_code=purpose_code,
        document_code=document_code,
    )
    if document_code:
        return qs.order_by("-published_at", "-created_at", "-id").first()

    revisions = list(qs.order_by("-published_at", "-created_at", "-id")[:2])
    if len(revisions) > 1:
        raise ConsentError(
            f"Multiple active documents found for purpose '{purpose_code}'. "
            "Specify document_code."
        )
    return revisions[0] if revisions else None


def _subject_records_qs(
    *,
    purpose: ConsentPurpose,
    user,
    anonymous_token: str,
    document_code: str | None = None,
):
    """A basic queryset of consent records for a specific subject and purpose."""
    subject_q = Q()
    if user is not None:
        subject_q |= Q(user=user)
    if anonymous_token:
        subject_q |= Q(anonymous_token=anonymous_token)
    if not subject_q.children:
        raise ConsentError("Either user or anonymous_token must be provided.")

    qs = ConsentRecord.objects.filter(subject_q, purpose=purpose)
    if document_code:
        qs = qs.filter(document_revision__document__code=document_code)
    return qs


def _resolve_initial_status(
    *, purpose: ConsentPurpose, confirmation_method: str
) -> str:
    """Determine the initial status for a new consent record.

    At the moment, only the paper-based path goes directly to
    `pending_confirmation`. The other verified scenarios are controlled by the
    optional app and policy layer.
    """
    if confirmation_method == ConsentRecord.ConfirmationMethod.UPLOADED_PAPER:
        return ConsentRecord.Status.PENDING_CONFIRMATION
    return ConsentRecord.Status.CURRENT


def _requires_consent_by_policy(
    *, effective_status: str | None, purpose: ConsentPurpose
) -> bool:
    """Determine whether confirmation is required in the current action."""
    if effective_status != ConsentRecord.Status.CURRENT:
        return True
    return (
        purpose.consent_frequency_policy
        == ConsentPurpose.ConsentFrequencyPolicy.EVERY_TIME
    )


def _resolve_consent_required_reason(
    *,
    purpose: ConsentPurpose,
    effective_status: str | None,
    requires_consent: bool,
) -> str:
    """Normalize signature request reason for UI/API."""
    if not requires_consent:
        return constants.CONSENT_REQUIRED_REASON_NOT_REQUIRED
    if effective_status == ConsentRecord.Status.OUTDATED:
        return constants.CONSENT_REQUIRED_REASON_OUTDATED
    if (
        effective_status == ConsentRecord.Status.CURRENT
        and purpose.consent_frequency_policy
        == ConsentPurpose.ConsentFrequencyPolicy.EVERY_TIME
    ):
        return constants.CONSENT_REQUIRED_REASON_EVERY_TIME
    return constants.CONSENT_REQUIRED_REASON_MISSING_OR_OTHER


def _event_type_for_accept(*, confirmation_method: str) -> str:
    """Select the event type for the accept script."""
    if confirmation_method == ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED:
        return ConsentEvent.EventType.ADMIN_CONFIRMED
    if confirmation_method == ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED:
        return ConsentEvent.EventType.EMPLOYEE_CONFIRMED
    if confirmation_method == ConsentRecord.ConfirmationMethod.UPLOADED_PAPER:
        return ConsentEvent.EventType.PAPER_UPLOADED
    return ConsentEvent.EventType.GIVEN


def _actor_type_for_accept(*, confirmation_method: str) -> str:
    """Select actor type for the accept script."""
    if confirmation_method == ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED:
        return ConsentEvent.ActorType.ADMIN
    if confirmation_method == ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED:
        return ConsentEvent.ActorType.EMPLOYEE
    return ConsentEvent.ActorType.SUBJECT


def _event_actor_user_for_accept(*, confirmation_method: str, user, confirmed_by):
    """Determine who should be considered the actor of the accept event."""
    if confirmation_method in {
        ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED,
        ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
    }:
        return confirmed_by
    if getattr(user, "pk", None) is not None:
        return user
    return None


def _mark_current_consents_outdated(
    *,
    purpose: ConsentPurpose,
    document_code: str,
    payload: Mapping[str, Any] | None = None,
    audit_context: Mapping[str, Any] | None = None,
    actor_user=None,
    actor_type: str | None = None,
) -> None:
    """Массово перевести текущие записи потока в `outdated`.

    Эту функцию удобно использовать при публикации новой редакции: она уже
    знает, как проверить применимость потока и как корректно записать событие.
    """
    normalized_audit_context = _normalize_audit_context(audit_context=audit_context)
    records = ConsentRecord.objects.filter(
        purpose=purpose,
        document_revision__document__code=document_code,
        status=ConsentRecord.Status.CURRENT,
    )
    for record in records:
        if not _flow_requires_consent_for_record(
            purpose=purpose,
            document=record.document_revision.document,
            record=record,
        ):
            continue
        record.status = ConsentRecord.Status.OUTDATED
        record.save()
        _create_consent_event(
            consent_record=record,
            event_type=ConsentEvent.EventType.OUTDATED,
            actor_user=actor_user,
            actor_type=actor_type or ConsentEvent.ActorType.SYSTEM,
            audit_context=normalized_audit_context,
            payload=dict(payload or {}),
        )


def _flow_requires_consent_for_record(
    *, purpose: ConsentPurpose, document: LegalDocument, record: ConsentRecord
) -> bool:
    """Understand whether the flow is required for an already-created consent record."""
    return _flow_requires_consent_for_subject(
        purpose=purpose,
        document=document,
        user=record.user,
        anonymous_token=record.anonymous_token,
    )


def _flow_requires_consent_for_subject(
    *,
    purpose: ConsentPurpose,
    document: LegalDocument,
    user,
    anonymous_token: str | None,
) -> bool:
    """Check whether the stream is needed by a specific subject using audience rules."""
    if not _is_subject_allowed_for_purpose(
        purpose=purpose,
        user=user,
        anonymous_token=anonymous_token,
    ):
        return False

    all_rules_qs = ConsentAudienceRule.objects.filter(
        purpose=purpose,
        document=document,
    )
    if not all_rules_qs.exists():
        return True
    active_rules = list(_active_audience_rules_qs(purpose=purpose, document=document))
    if not active_rules:
        return False

    matching_rules = [
        rule
        for rule in active_rules
        if _audience_rule_matches_subject(
            rule=rule,
            user=user,
            anonymous_token=anonymous_token,
        )
    ]
    if not matching_rules:
        return False
    return any(rule.is_required for rule in matching_rules)


def _active_audience_rules_qs(*, purpose: ConsentPurpose, document: LegalDocument):
    """Return active audience rules taking into account the validity period."""
    now = timezone.now()
    return (
        ConsentAudienceRule.objects.select_related("group")
        .filter(
            purpose=purpose,
            document=document,
            is_active=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )


def _audience_rule_matches_subject(
    *,
    rule: ConsentAudienceRule,
    user,
    anonymous_token: str | None,
) -> bool:
    """Check if the subject matches a specific audience rule."""
    if rule.scope_mode == ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS:
        return _is_registered_subject(user)
    if rule.scope_mode == ConsentAudienceRule.ScopeMode.DJANGO_GROUP:
        return (
            _is_registered_subject(user)
            and rule.group_id is not None  # pyright: ignore[reportAttributeAccessIssue]
            and user.groups.filter(pk=rule.group_id).exists()  # pyright: ignore[reportAttributeAccessIssue]
        )
    return not _is_registered_subject(user)


def _is_registered_subject(user) -> bool:
    """A small helper so as not to smear the user.pk check throughout the code."""
    return user is not None and getattr(user, "pk", None) is not None


def _is_subject_allowed_for_purpose(
    *,
    purpose: ConsentPurpose,
    user,
    anonymous_token: str | None,
) -> bool:
    """Check target availability using policy auth/anon."""
    if (
        purpose.subject_availability_policy
        == ConsentPurpose.SubjectAvailabilityPolicy.AUTHENTICATED_ONLY
    ):
        return _is_registered_subject(user)
    return True


def _resolve_not_applicable_reason(
    *,
    purpose: ConsentPurpose,
    user,
    anonymous_token: str | None,
) -> str | None:
    """Return the reason why the stream is not applicable, if known."""
    if _is_subject_allowed_for_purpose(
        purpose=purpose,
        user=user,
        anonymous_token=anonymous_token,
    ):
        return None
    return "auth_required"


def _get_active_access_policy(
    *,
    resource_code: str,
    action: str,
) -> ConsentAccessPolicy | None:
    """Return the first matching active access policy."""
    return (
        _active_access_policies_qs()
        .filter(resource_code=resource_code, action=action)
        .order_by("id")
        .first()
    )


def _active_access_policies_qs():
    """Basic queryset of active access policies by time windows."""
    now = timezone.now()
    return (
        ConsentAccessPolicy.objects.select_related("purpose", "document")
        .filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )


def _policy_action_to_resolution(*, action_value: str) -> str:
    """Translate action policy models into normalized service result."""
    if action_value == ConsentAccessPolicy.MissingConsentAction.READ_ONLY:
        return constants.ACCESS_POLICY_RESOLUTION_READ_ONLY
    if action_value == ConsentAccessPolicy.MissingConsentAction.REDIRECT_TO_CONSENT:
        return constants.ACCESS_POLICY_RESOLUTION_REDIRECT_TO_CONSENT
    return constants.ACCESS_POLICY_RESOLUTION_DENY


def _resolve_outdated_access_resolution(
    *,
    policy: ConsentAccessPolicy,
    status_info: ConsentStatusInfo,
) -> tuple[str, str]:
    """Allow legacy consent into the final access solution."""
    if (
        policy.on_outdated_consent
        == ConsentAccessPolicy.OutdatedConsentAction.RESPECT_RECONSENT_MODE
    ):
        if status_info["access_restricted"]:
            return (
                constants.ACCESS_POLICY_RESOLUTION_DENY,
                "outdated_hard_reconsent",
            )
        return (
            constants.ACCESS_POLICY_RESOLUTION_ALLOW,
            "outdated_soft_reconsent",
        )

    return (
        _policy_action_to_resolution(action_value=policy.on_outdated_consent),
        "outdated_consent",
    )


def _neutral_access_result(
    *,
    enabled: bool,
    reason: str,
    resource_code: str,
    action: str,
) -> dict[str, Any]:
    """Generate a neutral result for a disabled policy-layer."""
    return {
        "enabled": enabled,
        "matched_policy": False,
        "allowed": True,
        "resolution": constants.ACCESS_POLICY_RESOLUTION_ALLOW,
        "read_only": False,
        "redirect_to_consent": False,
        "reason": reason,
        "policy_id": None,
        "policy_code": None,
        "resource_code": resource_code,
        "action": action,
        "purpose_code": None,
        "document_code": None,
        "consent_status": None,
        "requires_consent": False,
        "is_applicable": False,
        "reconsent_mode": None,
        "access_restricted": False,
    }


def _build_access_result(
    *,
    enabled: bool,
    policy: ConsentAccessPolicy,
    status_info: ConsentStatusInfo,
    resolution: str,
    reason: str,
    resource_code: str,
    action: str,
) -> dict[str, Any]:
    """Collect the complete normalized result of the access policy calculation."""
    return {
        "enabled": enabled,
        "matched_policy": True,
        "allowed": resolution == constants.ACCESS_POLICY_RESOLUTION_ALLOW,
        "resolution": resolution,
        "read_only": resolution == constants.ACCESS_POLICY_RESOLUTION_READ_ONLY,
        "redirect_to_consent": (
            resolution == constants.ACCESS_POLICY_RESOLUTION_REDIRECT_TO_CONSENT
        ),
        "reason": reason,
        "policy_id": policy.pk,
        "policy_code": policy.code,
        "resource_code": resource_code,
        "action": action,
        "purpose_code": policy.purpose.code,
        "document_code": policy.document.code,
        "consent_status": status_info["status"],
        "requires_consent": status_info["requires_consent"],
        "is_applicable": status_info["is_applicable"],
        "reconsent_mode": status_info["reconsent_mode"],
        "access_restricted": status_info["access_restricted"],
    }


def _get_verified_consent_resolution_for_flow(
    *,
    purpose_code: str,
    document_code: str | None,
    verification_context: Mapping[str, Any] | None = None,
) -> VerifiedConsentResolution:
    """Bridge to the optional `verified_consents` app.

    It is important not to import the optional app at module level so `core`
    remains importable even without the verified app installed.
    """
    fallback_resolution: VerifiedConsentResolution = {
        "required": False,
        "verification_mode": "web_only",
        "resolution_source": "runtime_fallback",
        "policy": None,
        "form_policy": None,
        "legacy_web_consent_policy": "keep_web_current",
        "allow_subject_self_upload": False,
        "allow_draft_data_before_upload": True,
        "pre_upload_access_mode": "block",
        "notification_mode": "audit_only",
        "notification_templates": {},
        "notify_on_data_saved": False,
        "notify_on_paper_uploaded": False,
        "notify_on_verified": False,
        "notify_on_rejected": False,
    }
    if not is_verified_consents_enabled():
        return fallback_resolution

    from django_consent_152fz.verified_consents.services import (
        resolve_verified_consent_mode,
    )

    context = dict(verification_context or {})
    resolved = resolve_verified_consent_mode(
        purpose_code=purpose_code,
        document_code=document_code,
        form_code=str(context.get("form_code") or "").strip() or None,
        channel=str(context.get("channel") or "runtime").strip() or "runtime",
    )
    return cast(VerifiedConsentResolution, resolved)


def _get_verified_transition_state_for_flow(
    *,
    purpose_code: str,
    document_code: str | None,
    user=None,
    anonymous_token: str | None = None,
    verification_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the verified transition runtime signal for the transport/UI layer."""
    fallback = {
        "enabled": False,
        "status_code": None,
        "reason_code": None,
        "verification_mode": "web_only",
        "resolution_source": "runtime_fallback",
        "channel": str((verification_context or {}).get("channel") or "runtime"),
        "form_code": str((verification_context or {}).get("form_code") or "").strip(),
        "submission_id": None,
        "consent_record_id": None,
    }
    if not is_verified_consents_enabled():
        return fallback

    from django_consent_152fz.verified_consents.services import (
        get_verified_transition_state,
    )

    context = dict(verification_context or {})
    return get_verified_transition_state(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
        verification_context={
            "channel": str(context.get("channel") or "runtime").strip() or "runtime",
            "form_code": str(context.get("form_code") or "").strip(),
        },
    )


def _is_confirmation_method_allowed_for_verified_policy(
    *,
    confirmation_method: str,
    verification_mode: str,
) -> bool:
    """Check if the confirmation method is valid for verified-policy."""
    allowed_paper_methods = {
        ConsentRecord.ConfirmationMethod.UPLOADED_PAPER,
        ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED,
        ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
    }
    if verification_mode == "paper_required":
        return confirmation_method in allowed_paper_methods
    if verification_mode == "paper_or_goskey":
        return confirmation_method in allowed_paper_methods
    return False


def _resolve_legacy_web_consent_transition_mode(
    *,
    verified_resolution: VerifiedConsentResolution,
) -> str:
    """Normalize the transition mode for legacy web-consent records.

    Both the new 16.10.3 values and the legacy aliases (`keep_current`,
    `require_reconsent`) are supported for backward compatibility.
    """
    raw_mode = str(verified_resolution.get("legacy_web_consent_policy") or "").strip()
    if raw_mode in {"keep_web_current", "keep_current"}:
        return "keep_web_current"
    if raw_mode in {"mark_web_outdated", "require_reconsent"}:
        return "mark_web_outdated"
    if raw_mode == "withdraw_web_now":
        return "withdraw_web_now"
    if raw_mode == "withdraw_after_paper_confirmed":
        return "withdraw_after_paper_confirmed"
    return "keep_web_current"


@transaction.atomic
def _apply_verified_legacy_transition_to_record(
    *,
    consent_record: ConsentRecord,
    transition_mode: str,
    verified_resolution: VerifiedConsentResolution,
    audit_context: Mapping[str, Any] | None = None,
    occurred_at=None,
) -> ConsentRecord:
    """Apply transition-mode to the current legacy web-consent with an audit trail."""

    def _sync_and_return(record: ConsentRecord) -> ConsentRecord:
        consent_record.status = record.status
        return record

    locked_record = (
        ConsentRecord.objects.select_for_update()
        .select_related("document_revision")
        .filter(pk=consent_record.pk)
        .first()
    )
    if locked_record is None:
        return consent_record
    if locked_record.status != ConsentRecord.Status.CURRENT:
        return _sync_and_return(locked_record)
    if transition_mode not in {"mark_web_outdated", "withdraw_web_now"}:
        return _sync_and_return(locked_record)

    if transition_mode == "mark_web_outdated":
        target_status = ConsentRecord.Status.OUTDATED
        event_type = ConsentEvent.EventType.OUTDATED
        reason = "verified_policy_mark_web_outdated"
    else:
        target_status = ConsentRecord.Status.WITHDRAWN
        event_type = ConsentEvent.EventType.WITHDRAWN
        reason = "verified_policy_withdraw_web_now"

    if locked_record.status == target_status:
        return _sync_and_return(locked_record)

    locked_record.status = target_status
    locked_record.save(update_fields=["status", "updated_at"])
    normalized_audit_context = _normalize_audit_context(
        audit_context=audit_context,
        source="service.verified_legacy_transition",
    )
    _create_consent_event(
        consent_record=locked_record,
        event_type=event_type,
        actor_type=ConsentEvent.ActorType.SYSTEM,
        audit_context=normalized_audit_context,
        payload={
            "reason": reason,
            "transition_mode": transition_mode,
            "verification_mode": str(
                verified_resolution.get("verification_mode") or ""
            ),
            "policy_id": (
                getattr(verified_resolution.get("policy"), "pk", None)
                if verified_resolution.get("policy") is not None
                else None
            ),
            "form_policy_id": (
                getattr(verified_resolution.get("form_policy"), "pk", None)
                if verified_resolution.get("form_policy") is not None
                else None
            ),
        },
        occurred_at=occurred_at,
    )
    return _sync_and_return(locked_record)


@transaction.atomic
def _apply_verified_legacy_transition_for_subject_stream(
    *,
    purpose: ConsentPurpose,
    user,
    anonymous_token: str,
    document_code: str | None,
    verified_resolution: VerifiedConsentResolution,
    transition_mode: str,
) -> ConsentRecord | None:
    """Idempotently apply transition to the current entry of the thread under the block."""
    latest_record = (
        _subject_records_qs(
            purpose=purpose,
            user=user,
            anonymous_token=anonymous_token,
            document_code=document_code,
        )
        .select_for_update()
        .order_by("-created_at", "-id")
        .first()
    )
    if latest_record is None:
        return None
    if latest_record.status != ConsentRecord.Status.CURRENT:
        return latest_record
    if not bool(verified_resolution["required"]):
        return latest_record
    if _is_confirmation_method_allowed_for_verified_policy(
        confirmation_method=latest_record.confirmation_method,
        verification_mode=str(verified_resolution["verification_mode"]),
    ):
        return latest_record

    return _apply_verified_legacy_transition_to_record(
        consent_record=latest_record,
        transition_mode=transition_mode,
        verified_resolution=verified_resolution,
    )


def _normalize_audit_context(
    *,
    audit_context: Mapping[str, Any] | None = None,
    source: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    locale: str = "",
    request_id: str = "",
    session_key_hash: str = "",
    extra_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal wrapper over the public builder audit context."""
    return build_audit_context(
        audit_context=audit_context,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        locale=locale,
        request_id=request_id,
        session_key_hash=session_key_hash,
        extra_meta=extra_meta,
    )


def build_audit_context(
    *,
    audit_context: Mapping[str, Any] | None = None,
    source: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    locale: str = "",
    request_id: str = "",
    session_key_hash: str = "",
    occurred_at=None,
    extra_meta: Mapping[str, Any] | None = None,
    client: Mapping[str, Any] | None = None,
    request: Mapping[str, Any] | None = None,
    client_hints: Mapping[str, Any] | None = None,
    integration: Mapping[str, Any] | None = None,
    custom: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical audit context for record/event storage.

    The builder accepts both the old loose input (`extra_meta` with dotted
    keys) and the new namespaced input (`client`, `request`, `client_hints`,
    ...), but always emits normalized nested JSON.
    """
    base = dict(audit_context or {})
    merged_extra_meta = _merge_extra_meta(
        _extract_extra_meta_from_audit_context(base),
        _build_extra_meta_override(
            extra_meta=extra_meta,
            client=client,
            request=request,
            client_hints=client_hints,
            integration=integration,
            custom=custom,
        ),
    )
    normalized = {
        "source": source or str(base.get("source") or ""),
        "ip_address": ip_address if ip_address is not None else base.get("ip_address"),
        "user_agent": user_agent or str(base.get("user_agent") or ""),
        "locale": locale or str(base.get("locale") or ""),
        "request_id": request_id or str(base.get("request_id") or ""),
        "session_key_hash": (
            session_key_hash or str(base.get("session_key_hash") or "")
        ),
        "extra_meta": merged_extra_meta,
    }
    resolved_occurred_at = (
        occurred_at if occurred_at is not None else base.get("occurred_at")
    )
    if resolved_occurred_at is not None:
        normalized["occurred_at"] = resolved_occurred_at
    return normalized


def _render_revision_text_to_html(*, revision: DocumentRevision) -> str:
    content = str(revision.content_text or "")
    if revision.format == DocumentRevision.ContentFormat.PLAIN_TEXT:
        escaped = html_lib.escape(content)
        return "<br/>\n".join(escaped.splitlines())
    if revision.format == DocumentRevision.ContentFormat.MARKDOWN:
        return _markdown_to_html(content)
    if revision.format == DocumentRevision.ContentFormat.HTML:
        return content
    raise ConsentError(
        f"Unsupported document format for text rendering: {revision.format}"
    )


def _markdown_to_html(markdown_text: str) -> str:
    lines = str(markdown_text or "").splitlines()
    if not lines:
        return ""

    html_lines: list[str] = []
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            html_lines.append(f"<p>{' '.join(paragraph_buffer)}</p>")
            paragraph_buffer.clear()

    def flush_list() -> None:
        if list_buffer:
            html_lines.append("<ul>")
            html_lines.extend(list_buffer)
            html_lines.append("</ul>")
            list_buffer.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            heading_text = html_lib.escape(heading_match.group(2).strip())
            html_lines.append(f"<h{level}>{heading_text}</h{level}>")
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet_match:
            flush_paragraph()
            item_text = html_lib.escape(bullet_match.group(1).strip())
            list_buffer.append(f"<li>{item_text}</li>")
            continue

        flush_list()
        paragraph_buffer.append(html_lib.escape(stripped))

    flush_paragraph()
    flush_list()
    return "\n".join(html_lines)


def _call_html_to_pdf_hook(
    *, hook: object, body_html: str, revision: DocumentRevision
) -> bytes:
    """Call project-provided HTML->PDF renderer.

    Security note: `body_html` is passed to integration hook as-is (no sanitization).
    Treat HTML revision authoring and hook implementation as trusted boundary.
    """
    if isinstance(hook, str):
        from django.utils.module_loading import import_string

        hook_callable = import_string(hook)
    elif callable(hook):
        hook_callable = hook
    else:
        raise ConsentError("document_templates.html_to_pdf_hook must be callable.")

    try:
        result = hook_callable(body_html=body_html, revision=revision)
    except Exception as exc:  # pragma: no cover - defensive runtime contract.
        raise ConsentError(f"HTML->PDF hook failed: {exc}") from exc

    if not isinstance(result, (bytes, bytearray)):
        raise ConsentError("document_templates.html_to_pdf_hook must return PDF bytes.")
    return bytes(result)


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML->text extractor for built-in PDF fallback."""

    _BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag.lower() == "br":
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag.lower() in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        text = str(data or "")
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        raw = "".join(self._chunks)
        lines = [line.strip() for line in raw.splitlines()]
        normalized = [line for line in lines if line]
        return "\n".join(normalized)


def _extract_text_from_html(body_html: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(str(body_html or ""))
    return extractor.get_text()


def _build_simple_pdf_bytes(*, text: str) -> bytes:
    """Build a PDF for plain-text or markdown content.

    1. Try rendering Unicode text through ReportLab+TTF (text-based PDF).
    2. If ReportLab or the font is unavailable, fall back to a minimal ASCII PDF.
    """
    reportlab_pdf = _build_simple_pdf_bytes_with_reportlab(text=text)
    if reportlab_pdf is not None:
        return reportlab_pdf

    # We do not silently give away “broken” PDF for Cyrillic/Unicode via ASCII fallback.
    # Otherwise, crooks like “So...” (Tj/TJ) appear in the content stream.
    if any(ord(ch) > 127 for ch in str(text or "")):
        # In the production stream we do not break the download due to the environment:
        # if the Unicode renderer is not available, send a fallback and fix the problem
        # via ASCII-safe content.
        return _build_simple_pdf_bytes_ascii_fallback(
            text=(
                "Unicode-text PDF is unavailable in the current environment. "
                "Check that ReportLab and the TTF font are installed."
            )
        )

    return _build_simple_pdf_bytes_ascii_fallback(text=text)


def _build_simple_pdf_bytes_with_reportlab(*, text: str) -> bytes | None:
    """Render PDF as a text document (not an image) via ReportLab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, A5, LETTER
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except Exception:
        return None

    settings_payload = _resolve_printable_pdf_settings()
    paper_size = str(settings_payload["paper_size"])
    font_family = str(settings_payload["font_family"])
    font_size_pt = int(cast(int, settings_payload["font_size"]))
    text_align = str(settings_payload["text_align"])
    show_signature_footer = bool(settings_payload["show_signature_footer"])
    signature_align = str(settings_payload["signature_align"])

    page_size_map = {
        "a4": A4,
        "a5": A5,
        "letter": LETTER,
    }
    page_size = page_size_map.get(paper_size, A4)

    font_path = _resolve_pdf_text_font_path(font_family=font_family)
    if not font_path:
        return None

    font_name = f"ConsentFont-{font_family}"
    try:
        pdfmetrics.getFont(font_name)
    except Exception:
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
        except Exception:
            return None

    alignment_map: dict[str, Literal[0, 1, 2, 4]] = {
        "left": 0,
        "center": 1,
        "right": 2,
        "justify": 4,
    }
    alignment: Literal[0, 1, 2, 4] = alignment_map.get(text_align, 0)

    left_margin = 18 * mm
    right_margin = 18 * mm
    top_margin = 18 * mm
    bottom_margin = 18 * mm
    if show_signature_footer:
        bottom_margin = 34 * mm

    base_style = ParagraphStyle(
        "ConsentBody",
        fontName=font_name,
        fontSize=max(8, min(24, font_size_pt)),
        leading=max(12, int(font_size_pt * 1.5)),
        alignment=alignment,
        textColor=colors.black,
        spaceAfter=2,
    )

    story: list[Any] = []
    paragraphs = str(text or "").splitlines()
    for raw in paragraphs:
        line = raw.strip()
        if not line:
            story.append(Spacer(1, max(4, int(font_size_pt * 0.65))))
            continue
        safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe_line, base_style))

    def _draw_footer(canv, _doc) -> None:
        if not show_signature_footer:
            return
        canv.saveState()
        canv.setFont(font_name, max(8, font_size_pt))
        y0 = 16 * mm
        canv.drawString(left_margin, y0 + 10 * mm, "__.__.20__ г.")
        signature_line = "_____________________/_________________________"
        canv.drawString(left_margin, y0 + 4 * mm, signature_line)
        label = "(SIGNATURE/FULL NAME)"
        sig_w = canv.stringWidth(signature_line, font_name, max(8, font_size_pt))
        label_w = canv.stringWidth(label, font_name, max(8, font_size_pt))
        if signature_align == "left":
            x_label = left_margin
        elif signature_align == "right":
            x_label = left_margin + max(0, sig_w - label_w)
        else:
            x_label = left_margin + max(0, (sig_w - label_w) / 2)
        canv.drawString(x_label, y0, label)
        canv.restoreState()

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title="Consent document",
        author="django-consent-152fz",
    )
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return output.getvalue()


def _build_simple_pdf_bytes_ascii_fallback(*, text: str) -> bytes:
    """Minimal ASCII-fallback PDF without external libraries."""
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


def _resolve_printable_pdf_settings() -> dict[str, object]:
    defaults: dict[str, object] = {
        "paper_size": "a4",
        "font_family": "times_new_roman",
        "font_size": 12,
        "text_align": "left",
        "show_signature_footer": True,
        "signature_align": "center",
    }
    try:
        local_settings = ConsentSelfServiceSettings.objects.order_by(
            "-updated_at", "-id"
        ).first()
    except DatabaseError:
        return defaults
    if local_settings is None:
        return defaults
    return {
        "paper_size": str(local_settings.printable_pdf_paper_size or "a4"),
        "font_family": str(
            local_settings.printable_pdf_font_family or "times_new_roman"
        ),
        "font_size": int(local_settings.printable_pdf_font_size or 12),
        "text_align": str(local_settings.printable_pdf_text_align or "left"),
        "show_signature_footer": bool(
            local_settings.printable_pdf_show_signature_footer
        ),
        "signature_align": str(
            local_settings.printable_pdf_signature_align or "center"
        ),
    }


def _resolve_pdf_text_font_path(*, font_family: str) -> str:
    """Find a TTF font with Cyrillic for PDF rendering."""
    family = str(font_family or "times_new_roman")
    if family == "arial":
        candidates = (
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\ARIAL.TTF",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\tahoma.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        )
    else:
        candidates = (
            r"C:\Windows\Fonts\times.ttf",
            r"C:\Windows\Fonts\timesbd.ttf",
            r"C:\Windows\Fonts\Times New Roman.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def _build_extra_meta_override(
    *,
    extra_meta: Mapping[str, Any] | None,
    client: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
    client_hints: Mapping[str, Any] | None,
    integration: Mapping[str, Any] | None,
    custom: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the extra_meta override block from explicit namespace arguments."""
    override: dict[str, Any] = {}
    override = _merge_nested_dicts(override, _normalize_extra_meta(extra_meta))
    for namespace, value in (
        ("client", client),
        ("request", request),
        ("client_hints", client_hints),
        ("integration", integration),
        ("custom", custom),
    ):
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise ConsentError(f"audit_context.{namespace} must be a mapping.")
        override[namespace] = _merge_nested_dicts(
            override.get(namespace, {}),
            _sanitize_extra_meta_value(value),
        )
    return override


def _extract_extra_meta_from_audit_context(
    audit_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract `extra_meta` from the top level of `audit_context`.

    Besides `extra_meta`, the function supports direct top-level namespaces
    and moves all unknown project keys into `custom`.
    """
    extracted = _normalize_extra_meta(audit_context.get("extra_meta"))

    for namespace in _AUDIT_EXTRA_META_NAMESPACES:
        value = audit_context.get(namespace)
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise ConsentError(f"audit_context.{namespace} must be a mapping.")
        extracted[namespace] = _merge_nested_dicts(
            extracted.get(namespace, {}),
            _sanitize_extra_meta_value(value),
        )

    unknown_items = {
        key: value
        for key, value in audit_context.items()
        if key not in _AUDIT_CONTEXT_CORE_FIELDS
    }
    if unknown_items:
        extracted["custom"] = _merge_nested_dicts(
            extracted.get("custom", {}),
            _sanitize_extra_meta_value(unknown_items),
        )

    return extracted


def _merge_extra_meta(
    base_extra_meta: Any,
    override_extra_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge two extra_meta blocks into one canonical nested JSON."""
    normalized_base = _normalize_extra_meta(base_extra_meta)
    normalized_override = _normalize_extra_meta(override_extra_meta)
    return _merge_nested_dicts(normalized_base, normalized_override)


def _normalize_extra_meta(extra_meta: Any) -> dict[str, Any]:
    """Normalize `extra_meta` into a consistent nested JSON schema.

    Rules:
    - dotted keys are expanded into nested dictionaries;
    - unknown top-level keys are moved into `custom`;
    - sensitive keys such as cookies/tokens/headers are stripped.
    """
    if not extra_meta:
        return {}
    if not isinstance(extra_meta, Mapping):
        raise ConsentError("audit_context.extra_meta must be a mapping.")

    normalized: dict[str, Any] = {}
    for key, value in deepcopy(dict(extra_meta)).items():
        key_str = str(key)
        if "." in key_str:
            path = key_str.split(".")
            if path[0] not in _AUDIT_EXTRA_META_NAMESPACES:
                path = ["custom", *path]
            _assign_nested_value(normalized, path, value)
            continue
        if key_str in _AUDIT_EXTRA_META_NAMESPACES:
            if value is None:
                continue
            if not isinstance(value, Mapping):
                raise ConsentError(
                    f"audit_context.extra_meta['{key_str}'] must be a mapping."
                )
            normalized[key_str] = _sanitize_extra_meta_value(value)
            continue
        if _is_sensitive_audit_meta_key(key_str):
            continue
        _assign_nested_value(normalized, ["custom", key_str], value)
    return _sanitize_extra_meta_value(normalized)


def _sanitize_extra_meta_value(value: Any) -> Any:
    """Recursively clear sensitive keys from an arbitrary structure."""
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in deepcopy(dict(value)).items():
            key_str = str(key)
            if _is_sensitive_audit_meta_key(key_str):
                continue
            normalized[key_str] = _sanitize_extra_meta_value(item)
        return normalized
    if isinstance(value, list):
        return [_sanitize_extra_meta_value(item) for item in value]
    return deepcopy(value)


def _is_sensitive_audit_meta_key(key: str) -> bool:
    """Determine whether the key belongs to prohibited audit data."""
    normalized_key = key.strip().lower().replace("-", "_")
    return normalized_key in _SENSITIVE_AUDIT_META_KEYS


def _merge_nested_dicts(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Recursively merge two nested dictionaries without mutating the original data."""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_nested_dicts(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _assign_nested_value(target: dict[str, Any], path: list[str], value: Any) -> None:
    """Write the value along the path like `client -> os_family`."""
    cursor = target
    for segment in path[:-1]:
        existing = cursor.get(segment)
        if not isinstance(existing, dict):
            existing = {}
            cursor[segment] = existing
        cursor = existing
    cursor[path[-1]] = deepcopy(value)


def _create_consent_event(
    *,
    consent_record: ConsentRecord,
    event_type: str,
    actor_user=None,
    actor_type: str | None = None,
    audit_context: Mapping[str, Any] | None = None,
    payload: Mapping[str, Any] | None = None,
    occurred_at=None,
) -> ConsentEvent:
    """Create an immutable audit event from a normalized audit context."""
    normalized_audit_context = _normalize_audit_context(audit_context=audit_context)
    event_kwargs = {
        "consent_record": consent_record,
        "event_type": event_type,
        "actor_user": actor_user,
        "actor_type": actor_type or ConsentEvent.ActorType.SYSTEM,
        "source": normalized_audit_context["source"],
        "ip_address": normalized_audit_context["ip_address"],
        "user_agent": normalized_audit_context["user_agent"],
        "locale": normalized_audit_context["locale"],
        "request_id": normalized_audit_context["request_id"],
        "session_key_hash": normalized_audit_context["session_key_hash"],
        "payload": dict(payload or {}),
        "extra_meta": normalized_audit_context["extra_meta"],
    }
    resolved_occurred_at = occurred_at or normalized_audit_context.get("occurred_at")
    if resolved_occurred_at is not None:
        event_kwargs["occurred_at"] = resolved_occurred_at
    return ConsentEvent.objects.create(
        **event_kwargs,
    )
