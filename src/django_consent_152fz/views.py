"""HTML view layer for section 5.1.

These view functions do not duplicate the consent business logic. They are
responsible for:
- HTTP binding and template rendering;
- safe redirects;
- form handling and `audit_context` collection;
- calling the canonical core services from section 4.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentPurpose,
    ConsentRecord,
    DocumentRevision,
)
from django_consent_152fz.core.services import (
    accept_consent,
    get_consent_status,
    get_current_requirements,
    get_reconsent_notice,
    render_document_revision_download_payload,
    withdraw_consent,
)
from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.forms import (
    ConsentAcceptanceForm,
    ConsentWithdrawForm,
    build_verification_context_from_cleaned_data,
)
from django_consent_152fz.request import (
    build_request_audit_context,
    get_request_consent_subject,
    persist_anonymous_token,
)
from django_consent_152fz.self_service import (
    resolve_subject_consents_capture_settings,
    resolve_subject_consents_ui_settings,
)
from django_consent_152fz.settings import (
    get_fields_config,
)

_VERIFICATION_CONTEXT_SELF_SERVICE = {"channel": "self_service"}


def document_detail(
    request: HttpRequest,
    purpose_code: str,
    document_code: str,
) -> HttpResponse:
    """Display the active document revision and consent form."""

    return _render_document_response(
        request,
        purpose_code=purpose_code,
        document_code=document_code,
    )


def document_pdf_download(
    request: HttpRequest,
    purpose_code: str,
    document_code: str,
) -> HttpResponse:
    """Return a PDF version of the active document stream revision."""
    _purpose, revision = _get_flow_or_404(
        purpose_code=purpose_code,
        document_code=document_code,
    )
    try:
        payload = render_document_revision_download_payload(revision=revision)
    except ConsentError as exc:
        return HttpResponse(
            str(exc), status=400, content_type="text/plain; charset=utf-8"
        )

    extension = str(payload["extension"] or "pdf")
    filename = _build_document_download_filename(
        revision=revision,
        fallback_code=document_code,
        extension=extension,
    )
    response = HttpResponse(
        payload["content"],
        content_type=str(payload["content_type"] or "application/octet-stream"),
    )
    response["Content-Disposition"] = _build_attachment_disposition(filename=filename)
    return response


def accept_consent_view(
    request: HttpRequest,
    purpose_code: str,
    document_code: str,
) -> HttpResponse:
    """Accept consent from an HTML form and save it via the core service."""

    if request.method != "POST":
        return redirect(
            reverse(
                "django_consent_152fz:document",
                kwargs={
                    "purpose_code": purpose_code,
                    "document_code": document_code,
                },
            )
        )

    form = ConsentAcceptanceForm(
        request.POST,
        consent_capture_options=_resolve_subject_consents_capture_settings(
            purpose_code=purpose_code
        ),
    )
    if not form.is_valid():
        return _render_document_response(
            request,
            purpose_code=purpose_code,
            document_code=document_code,
            form=form,
            status=400,
        )

    user, anonymous_token = get_request_consent_subject(
        request,
        anonymous_token=form.cleaned_data["anonymous_token"],
        ensure_anonymous_token=True,
    )
    try:
        verification_context = build_verification_context_from_cleaned_data(
            form.cleaned_data,
            default_channel="self_service",
        )
        # Status, repeated-consent, and audience logic live in the core.
        # The view only prepares HTTP context and delegates persistence.
        accept_consent(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token,
            confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
            verification_context=verification_context,
            audit_context=build_request_audit_context(
                request,
                source="template_ui.accept",
                anonymous_token=anonymous_token,
            ),
        )
    except ConsentError as exc:
        form.add_error(None, str(exc))
        return _render_document_response(
            request,
            purpose_code=purpose_code,
            document_code=document_code,
            form=form,
            status=400,
        )

    response = redirect(
        _get_safe_redirect_target(
            request,
            next_url=form.cleaned_data["next"],
            fallback_url=reverse(
                "django_consent_152fz:document",
                kwargs={
                    "purpose_code": purpose_code,
                    "document_code": document_code,
                },
            ),
        )
    )
    if anonymous_token:
        # For anonymous subjects, return the token to the cookie so the next
        # requests stay on the same consent flow.
        persist_anonymous_token(response, anonymous_token=anonymous_token)
    return response


def withdraw_consent_view(
    request: HttpRequest,
    purpose_code: str,
    document_code: str,
) -> HttpResponse:
    """Show the revocation page and handle POST requests to revoke consent."""

    purpose, revision = _get_flow_or_404(
        purpose_code=purpose_code,
        document_code=document_code,
    )
    user, anonymous_token = get_request_consent_subject(request)

    if request.method == "POST":
        form = ConsentWithdrawForm(request.POST)
        if form.is_valid():
            user, anonymous_token = get_request_consent_subject(
                request,
                anonymous_token=form.cleaned_data["anonymous_token"],
            )
            try:
                # Route the operation through the same service layer so status
                # and immutable audit events stay canonical.
                withdraw_consent(
                    purpose_code=purpose_code,
                    document_code=document_code,
                    user=user,
                    anonymous_token=anonymous_token,
                    audit_context=build_request_audit_context(
                        request,
                        source="template_ui.withdraw",
                        anonymous_token=anonymous_token,
                    ),
                )
            except ConsentError as exc:
                form.add_error(None, str(exc))
            else:
                response = redirect(
                    _get_safe_redirect_target(
                        request,
                        next_url=form.cleaned_data["next"],
                        fallback_url=reverse(
                            "django_consent_152fz:withdraw",
                            kwargs={
                                "purpose_code": purpose_code,
                                "document_code": document_code,
                            },
                        ),
                    )
                )
                if anonymous_token:
                    persist_anonymous_token(response, anonymous_token=anonymous_token)
                return response
    else:
        form = ConsentWithdrawForm(
            initial={
                "anonymous_token": anonymous_token,
                "next": request.get_full_path(),
            }
        )

    status_info = get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
        verification_context=_VERIFICATION_CONTEXT_SELF_SERVICE,
    )
    status_info = _with_status_label(status_info)
    context = {
        "purpose": purpose,
        "revision": revision,
        "status_info": status_info,
        "notice": get_reconsent_notice(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token,
        ),
        "withdraw_form": form,
        "document_url": reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose_code,
                "document_code": document_code,
            },
        ),
    }
    return render(
        request,
        "django_consent_152fz/withdraw.html",
        context,
        status=400 if form.errors else 200,
    )


def subject_consents_view(request: HttpRequest) -> HttpResponse:
    """A minimal self-service page with current subject consent flows."""

    user, anonymous_token = get_request_consent_subject(request)
    context = _build_subject_consents_context(
        user=user,
        anonymous_token=anonymous_token,
    )
    return render(
        request,
        "django_consent_152fz/subject_consents.html",
        context,
    )


def subject_consents_withdraw_view(
    request: HttpRequest,
    purpose_code: str,
    document_code: str,
) -> HttpResponse:
    """Self-service withdrawal of consent with a separate audit scenario."""

    if request.method != "POST":
        return redirect(reverse("django_consent_152fz:subject_consents"))

    user, anonymous_token = get_request_consent_subject(
        request,
        ensure_anonymous_token=True,
    )
    try:
        withdraw_consent(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token,
            audit_context=build_request_audit_context(
                request,
                source="self_service.withdraw",
                anonymous_token=anonymous_token,
            ),
        )
    except ConsentError as exc:
        context = _build_subject_consents_context(
            user=user,
            anonymous_token=anonymous_token,
            error_message=str(exc),
        )
        return render(
            request,
            "django_consent_152fz/subject_consents.html",
            context,
            status=400,
        )

    response = redirect(reverse("django_consent_152fz:subject_consents"))
    if anonymous_token:
        persist_anonymous_token(response, anonymous_token=anonymous_token)
    return response


def _build_subject_consents_context(
    *,
    user,
    anonymous_token: str | None,
    error_message: str = "",
) -> dict[str, Any]:
    ui_settings = resolve_subject_consents_ui_settings()
    open_mode = str(ui_settings["open_mode"])
    list_mode = str(ui_settings.get("list_mode") or "all")
    records_qs = (
        _subject_consent_records_qs(user=user, anonymous_token=anonymous_token)
        .select_related("purpose", "document_revision__document")
        .order_by("-created_at", "-id")
    )
    latest_by_stream: dict[tuple[str, str], ConsentRecord] = {}
    for record in records_qs:
        stream_key = (record.purpose.code, record.document_revision.document.code)
        if stream_key not in latest_by_stream:
            latest_by_stream[stream_key] = record

    requirements = get_current_requirements(
        user=user,
        anonymous_token=anonymous_token or None,
        verification_context=_VERIFICATION_CONTEXT_SELF_SERVICE,
    )["requirements"]
    stream_keys: set[tuple[str, str]] = set(latest_by_stream.keys())
    for requirement in requirements:
        stream_keys.add(
            (
                str(requirement["purpose_code"]),
                str(requirement["document_code"]),
            )
        )

    items: list[dict[str, Any]] = []
    for purpose_code, document_code in sorted(
        stream_keys, key=lambda item: (item[0], item[1])
    ):
        status_info = get_consent_status(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token or None,
            verification_context=_VERIFICATION_CONTEXT_SELF_SERVICE,
        )
        record = latest_by_stream.get((purpose_code, document_code))
        if not status_info.get("is_applicable"):
            continue

        needs_sign = bool(status_info.get("requires_consent"))
        can_withdraw = bool(
            status_info.get("status")
            in {ConsentRecord.Status.CURRENT, ConsentRecord.Status.OUTDATED}
        )
        if list_mode == "pending_only" and not needs_sign:
            continue
        if list_mode == "signed_only" and not can_withdraw:
            continue

        if record is not None:
            purpose_title = _resolve_human_title(
                code=record.purpose.code, title=record.purpose.title
            )
            document_title = _resolve_human_title(
                code=record.document_revision.document.code,
                title=record.document_revision.document.title,
            )
            revision_version = record.document_revision.version
            consented_at = record.created_at
            status_label = _get_status_label(record.status)
        else:
            purpose_title = purpose_code
            document_title = document_code
            revision_version = "—"
            consented_at = None
            status_label = _get_status_label(status_info.get("status"))

        show_sign_action = list_mode in {"all", "pending_only"} and needs_sign
        show_withdraw_action = list_mode in {"all", "signed_only"} and can_withdraw
        items.append(
            {
                "purpose_code": purpose_code,
                "purpose_title": purpose_title,
                "document_code": document_code,
                "document_title": document_title,
                "revision_version": revision_version,
                "status": status_label,
                "consented_at": consented_at,
                "document_url": reverse(
                    "django_consent_152fz:document",
                    kwargs={
                        "purpose_code": purpose_code,
                        "document_code": document_code,
                    },
                ),
                "withdraw_self_url": reverse(
                    "django_consent_152fz:subject_consents_withdraw",
                    kwargs={
                        "purpose_code": purpose_code,
                        "document_code": document_code,
                    },
                ),
                "show_sign_action": show_sign_action,
                "show_withdraw_action": show_withdraw_action,
            }
        )

    return {
        "subject_consents": items,
        "error_message": error_message,
        "subject_consents_open_mode": open_mode,
        "subject_consents_list_mode": list_mode,
        "subject_consents_open_mode_new_window": (
            open_mode == constants.SUBJECT_CONSENTS_OPEN_MODE_NEW_WINDOW
        ),
        "subject_consents_open_mode_modal": (
            open_mode == constants.SUBJECT_CONSENTS_OPEN_MODE_MODAL
        ),
    }


def _render_document_response(
    request: HttpRequest,
    *,
    purpose_code: str,
    document_code: str,
    form: ConsentAcceptanceForm | None = None,
    status: int = 200,
) -> HttpResponse:
    """Collects document page context for GET and for POST errors."""

    purpose, revision = _get_flow_or_404(
        purpose_code=purpose_code,
        document_code=document_code,
    )
    user, anonymous_token = get_request_consent_subject(request)
    status_info = get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
        verification_context=_VERIFICATION_CONTEXT_SELF_SERVICE,
    )
    status_info = _with_status_label(status_info)
    requirement = _get_requirement_for_flow(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
    )
    capture_settings = _resolve_subject_consents_capture_settings(
        purpose_code=purpose_code
    )
    if form is None:
        form = ConsentAcceptanceForm(
            consent_capture_options=capture_settings,
            initial={
                "anonymous_token": anonymous_token,
                "next": request.get_full_path(),
            },
        )

    context = {
        "purpose": purpose,
        "revision": revision,
        "requirement": requirement,
        "status_info": status_info,
        "notice": get_reconsent_notice(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token,
        ),
        "accept_form": form,
        "field_descriptors": _build_field_descriptors(revision.fields_snapshot),
        "accept_url": reverse(
            "django_consent_152fz:accept",
            kwargs={
                "purpose_code": purpose_code,
                "document_code": document_code,
            },
        ),
        "withdraw_url": reverse(
            "django_consent_152fz:withdraw",
            kwargs={
                "purpose_code": purpose_code,
                "document_code": document_code,
            },
        ),
        "document_pdf_url": reverse(
            "django_consent_152fz:document_pdf",
            kwargs={
                "purpose_code": purpose_code,
                "document_code": document_code,
            },
        ),
        "document_download_label": _resolve_document_download_label(revision=revision),
        "consent_gate_message": _resolve_consent_gate_message(status_info),
        "consent_capture_settings": capture_settings,
    }
    return render(
        request,
        "django_consent_152fz/document_detail.html",
        context,
        status=status,
    )


def _get_flow_or_404(
    *,
    purpose_code: str,
    document_code: str,
) -> tuple[ConsentPurpose, DocumentRevision]:
    """Find the active `purpose + document_code` stream or raise 404.

    This matters for the architecture in section 4: the document stream is
    identified not by a single purpose, but by the `purpose_code +
    document_code` pair.
    """

    purpose = ConsentPurpose.objects.filter(code=purpose_code).first()
    if purpose is None:
        raise Http404(f"Unknown purpose code '{purpose_code}'.")

    revision = (
        DocumentRevision.objects.select_related("document")
        .filter(
            purpose_code=purpose_code,
            document__code=document_code,
            is_active=True,
            document__is_active=True,
        )
        .order_by("-published_at", "-created_at", "-id")
        .first()
    )
    if revision is None:
        raise Http404(
            "No active document revision found for flow "
            f"'{purpose_code}:{document_code}'."
        )
    return purpose, revision


def _get_requirement_for_flow(
    *,
    purpose_code: str,
    document_code: str,
    user,
    anonymous_token: str,
) -> dict[str, Any] | None:
    """Return the requirement for the current document stream."""

    requirements = get_current_requirements(
        user=user,
        anonymous_token=anonymous_token or None,
        verification_context=_VERIFICATION_CONTEXT_SELF_SERVICE,
    )["requirements"]
    for requirement in requirements:
        if (
            requirement["purpose_code"] == purpose_code
            and requirement["document_code"] == document_code
        ):
            return requirement
    return None


def _subject_consent_records_qs(*, user, anonymous_token: str | None):
    token = (anonymous_token or "").strip()
    qs = ConsentRecord.objects.exclude(status=ConsentRecord.Status.DELETED)
    if user is not None:
        return qs.filter(user=user)
    if token:
        return qs.filter(anonymous_token=token)
    return qs.none()


def _build_field_descriptors(field_codes: list[Any]) -> list[dict[str, str]]:
    """Expand a field snapshot into human-readable labels for the template.

    Both formats are supported:
    - legacy: `["full_name", "email"]`;
    - new snapshot: `[{"name": "full_name", "label": "..."}]`.
    """

    registry = get_fields_config()
    descriptors: list[dict[str, str]] = []
    for item in field_codes or []:
        explicit_label = ""
        if isinstance(item, Mapping):
            code = str(item.get("code") or item.get("name") or "").strip()
            explicit_label = str(item.get("label") or "").strip()
        else:
            code = str(item or "").strip()
        if not code:
            continue

        field_config = registry.get(code, {}) if isinstance(registry, Mapping) else {}
        descriptors.append(
            {
                "code": code,
                "label": str(field_config.get("label") or "").strip()
                or explicit_label
                or code,
            }
        )
    return descriptors


def _get_safe_redirect_target(
    request: HttpRequest,
    *,
    next_url: str,
    fallback_url: str,
) -> str:
    """Accept only safe local redirects and reject open redirects."""

    candidate = (next_url or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
    ):
        return candidate
    return fallback_url


def _with_status_label(status_info: dict[str, Any]) -> dict[str, Any]:
    """Add a localized status label for the template/UI."""

    info = dict(status_info)
    info["status_label"] = _get_status_label(info.get("status"))
    return info


def _resolve_consent_gate_message(status_info: dict[str, Any]) -> str:
    if status_info.get("auth_required_for_consent"):
        return _(
            "Для этого согласия требуется авторизация. Войдите в аккаунт, "
            "чтобы продолжить."
        )
    return ""


def _get_status_label(status_value: Any) -> str:
    """Convert the canonical status code into human-readable text."""

    normalized = str(status_value or "").strip()
    if not normalized:
        return "Нет согласия"

    status_labels = {
        constants.CONSENT_STATUS_CURRENT: "Актуально",
        constants.CONSENT_STATUS_OUTDATED: "Устарело",
        constants.CONSENT_STATUS_WITHDRAWN: "Отозвано",
        constants.CONSENT_STATUS_PENDING_CONFIRMATION: "Ожидает подтверждения",
        constants.CONSENT_STATUS_REJECTED: "Отклонено",
        constants.CONSENT_STATUS_DELETED: "Удалено",
    }
    return status_labels.get(normalized, normalized)


def _build_document_download_filename(
    *,
    revision: DocumentRevision,
    fallback_code: str,
    extension: str,
) -> str:
    raw_title = str(getattr(revision.document, "title", "") or "").strip()
    normalized_title = re.sub(r"[\\/:*?\"<>|]+", " ", raw_title).strip()
    if not normalized_title:
        normalized_title = str(fallback_code or "document").strip() or "document"
    normalized_title = re.sub(r"\s+", " ", normalized_title).strip()
    ext = re.sub(r"[^a-zA-Z0-9]+", "", str(extension or "").strip().lower()) or "pdf"
    return f"{normalized_title} v{revision.version}.{ext}"


def _resolve_document_download_label(*, revision: DocumentRevision) -> str:
    revision_format = str(revision.format or "")
    if revision_format == DocumentRevision.ContentFormat.PDF_FILE:
        return _("Скачать PDF-документ")
    if revision_format == DocumentRevision.ContentFormat.OFFICE_FILE:
        return _("Скачать документ (DOC/DOCX/ODT/ODTX)")
    return _("Скачать PDF-версию")


def _build_attachment_disposition(*, filename: str) -> str:
    ascii_fallback = "".join(
        ch if 32 <= ord(ch) <= 126 and ch not in {'"', "\\"} else "_" for ch in filename
    ).strip()
    if not ascii_fallback:
        ascii_fallback = "document.pdf"
    utf8_name = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_name}"


def _resolve_human_title(*, code: str, title: str) -> str:
    """Hide the technical code if the header has not yet been adapted."""

    normalized_title = (title or "").strip()
    normalized_code = (code or "").strip()
    if normalized_title and normalized_code:
        # Strip legacy "human_title (code)" tails that leak technical identifiers.
        code_suffix_pattern = re.compile(
            rf"^(?P<human>.+?)\s*[\(\[]\s*{re.escape(normalized_code)}\s*[\)\]]\s*$",
            flags=re.IGNORECASE,
        )
        suffix_match = code_suffix_pattern.match(normalized_title)
        if suffix_match:
            normalized_title = suffix_match.group("human").strip()

    if normalized_title and normalized_title != normalized_code:
        return normalized_title

    fallback_titles = {
        "service_account": "Регистрация и обслуживание аккаунта",
        "sample_service_terms_agreement": (
            "Соглашение об условиях обслуживания аккаунта"
        ),
    }
    if normalized_code in fallback_titles:
        return fallback_titles[normalized_code]
    return normalized_title or normalized_code


def _resolve_subject_consents_capture_settings(
    *,
    purpose_code: str = "",
) -> dict[str, object]:
    return resolve_subject_consents_capture_settings(purpose_code=purpose_code)
