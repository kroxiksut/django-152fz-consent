"""Template tags for the HTML/template integrations from section 5.

The module encapsulates template access to the package core:
- exposes consent requirements and status;
- renders the standard form blocks and notices;
- wires access policies and anonymous contact/preorder hooks;
- safely renders document text.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Django dynamic ORM/admin attributes are not fully inferable by pyright.
from collections.abc import Mapping
from typing import Any, cast

from django import template
from django.template.defaultfilters import linebreaksbr
from django.urls import reverse
from django.utils.html import conditional_escape, format_html, mark_safe
from django.utils.translation import gettext as _

from django_consent_152fz import constants
from django_consent_152fz.contact_hooks import build_anonymous_contact_consent_form
from django_consent_152fz.core.models import DocumentRevision
from django_consent_152fz.core.services import (
    evaluate_consent_access,
    get_consent_status,
    get_current_requirements,
    get_reconsent_notice,
)
from django_consent_152fz.forms import (
    ANONYMOUS_CONSENT_SCENARIO_CONTACT,
    ANONYMOUS_CONSENT_SCENARIO_PREORDER,
    ConsentAcceptanceForm,
)
from django_consent_152fz.request import (
    get_request_consent_subject,
)
from django_consent_152fz.self_service import (
    resolve_subject_consents_capture_settings,
    resolve_subject_consents_ui_settings,
)
from django_consent_152fz.settings import (
    get_fields_config,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def consent_requirements(context: template.Context) -> dict[str, Any]:
    """Surface the requirements for the current subject directly into the template."""

    request = context.get("request")
    if request is None:
        return {"provider_code": constants.PROVIDER_CODE, "requirements": []}
    user, anonymous_token = get_request_consent_subject(request)
    return get_current_requirements(
        user=user,
        anonymous_token=anonymous_token or None,
    )


@register.simple_tag(takes_context=True)
def consent_status(
    context: template.Context,
    purpose_code: str,
    document_code: str | None = None,
) -> dict[str, Any]:
    """P'PsP rotates the consent status for a specific document stream."""

    request = context.get("request")
    if request is None:
        return {
            "purpose_code": purpose_code,
            "document_code": document_code,
            "status": None,
            "requires_consent": True,
            "consent_required_reason": (
                constants.CONSENT_REQUIRED_REASON_MISSING_OR_OTHER
            ),
            "is_current": False,
            "is_outdated": False,
            "latest_revision_id": None,
            "record_revision_id": None,
            "reconsent_mode": None,
            "access_restricted": False,
            "is_applicable": False,
            "verified_transition": {
                "enabled": False,
                "status_code": None,
                "reason_code": None,
                "verification_mode": "web_only",
                "resolution_source": "runtime_fallback",
                "channel": "runtime",
                "form_code": "",
                "submission_id": None,
                "consent_record_id": None,
            },
        }
    user, anonymous_token = get_request_consent_subject(request)
    return get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token or None,
    )


@register.simple_tag(takes_context=True)
def consent_reconsent_notice(
    context: template.Context,
    purpose_code: str,
    document_code: str | None = None,
) -> dict[str, Any] | None:
    """Surface the reconsent notice for soft/hard reconsent mode when needed."""

    request = context.get("request")
    if request is None:
        return None
    user, anonymous_token = get_request_consent_subject(request)
    return get_reconsent_notice(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token or None,
    )


@register.simple_tag(takes_context=True)
def consent_access(
    context: template.Context,
    resource_code: str,
    action: str,
) -> dict[str, Any]:
    """Surface the section 4.11 guard-layer result into the template.

    If the request is absent, the tag returns an explicit negative result and
    does not silently "allow everything". This makes it easier to diagnose
    incorrect use of the tag outside a request-aware context.
    """

    request = context.get("request")
    if request is None:
        return {
            "enabled": False,
            "matched_policy": False,
            "allowed": False,
            "resolution": constants.ACCESS_POLICY_RESOLUTION_DENY,
            "read_only": False,
            "redirect_to_consent": False,
            "reason": "missing_request",
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
    user, anonymous_token = get_request_consent_subject(
        request,
        ensure_anonymous_token=True,
    )
    return evaluate_consent_access(
        resource_code=resource_code,
        action=action,
        user=user,
        anonymous_token=anonymous_token or None,
    )


@register.inclusion_tag(
    "django_consent_152fz/includes/consent_form_block.html",
    takes_context=True,
)
def render_consent_form(
    context: template.Context,
    purpose_code: str,
    document_code: str,
    next_url: str = "",
    form_code: str = "",
) -> dict[str, Any]:
    """Prepare the context of the standard consent form block for the host page."""

    verification_context = _build_verification_context(form_code=form_code)
    request = context.get("request")
    anonymous_token = ""
    status_info = None
    requirement = None
    if request is not None:
        user, anonymous_token = get_request_consent_subject(request)
        status_info = get_consent_status(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token or None,
            verification_context=verification_context,
        )
        requirement = _find_requirement(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token,
            verification_context=verification_context,
        )
        if not next_url:
            next_url = request.get_full_path()

    field_registry = get_fields_config()
    descriptors = []
    if requirement is not None:
        for field_code in requirement["fields"]:
            descriptors.append(
                {
                    "code": field_code,
                    "label": str(
                        field_registry.get(field_code, {}).get("label") or field_code
                    ),
                }
            )

    capture_settings = resolve_subject_consents_capture_settings(
        purpose_code=purpose_code
    )
    return {
        "request": request,
        "requirement": requirement,
        "status_info": status_info,
        "field_descriptors": descriptors,
        "accept_url": reverse(
            "django_consent_152fz:accept",
            kwargs={
                "purpose_code": purpose_code,
                "document_code": document_code,
            },
        ),
        "accept_form": ConsentAcceptanceForm(
            consent_capture_options=capture_settings,
            initial={
                "anonymous_token": anonymous_token,
                "next": next_url,
                "verification_channel": (
                    str(verification_context.get("channel") or "")
                    if verification_context
                    else ""
                ),
                "verification_form_code": (
                    str(verification_context.get("form_code") or "")
                    if verification_context
                    else ""
                ),
            },
        ),
        "consent_capture_settings": capture_settings,
    }


@register.inclusion_tag(
    "django_consent_152fz/includes/reconsent_notice.html",
    takes_context=True,
)
def render_reconsent_notice(
    context: template.Context,
    purpose_code: str,
    document_code: str | None = None,
) -> dict[str, Any]:
    """Expose the reconsent notice as an inclusion tag for templates."""

    return {
        "notice": consent_reconsent_notice(context, purpose_code, document_code),
    }


@register.inclusion_tag(
    "django_consent_152fz/includes/contact_consent_hook.html",
    takes_context=True,
)
def render_contact_consent_hook(
    context: template.Context,
    purpose_code: str,
    document_code: str,
    next_url: str = "",
    prefix: str = "contact_consent",
) -> dict[str, Any]:
    """Build the inclusion context for the embedded contact-consent hook."""

    return _build_anonymous_contact_hook_context(
        context,
        purpose_code=purpose_code,
        document_code=document_code,
        scenario=ANONYMOUS_CONSENT_SCENARIO_CONTACT,
        next_url=next_url,
        prefix=prefix,
    )


@register.inclusion_tag(
    "django_consent_152fz/includes/contact_consent_hook.html",
    takes_context=True,
)
def render_preorder_consent_hook(
    context: template.Context,
    purpose_code: str,
    document_code: str,
    next_url: str = "",
    prefix: str = "preorder_consent",
) -> dict[str, Any]:
    """Build the inclusion context for the embedded preorder-consent hook."""

    return _build_anonymous_contact_hook_context(
        context,
        purpose_code=purpose_code,
        document_code=document_code,
        scenario=ANONYMOUS_CONSENT_SCENARIO_PREORDER,
        next_url=next_url,
        prefix=prefix,
    )


@register.filter
def render_consent_document(revision: DocumentRevision) -> str:
    """Render the document revision as safe HTML.

    For `plain_text` and `markdown` we deliberately use conservative rendering
    without a full HTML sanitizer. For the `html` format we currently show the
    source as plain text, to avoid trusting arbitrary markup.
    """

    if revision is None:
        return ""

    if revision.format in {
        DocumentRevision.ContentFormat.PDF_FILE,
        DocumentRevision.ContentFormat.OFFICE_FILE,
    }:
        if revision.format == DocumentRevision.ContentFormat.PDF_FILE:
            link_label = _("Открыть PDF-документ")
        else:
            link_label = _("Открыть документ (DOC/DOCX/ODT/ODTX)")
        if revision.content_file:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">{}</a>',
                revision.content_file.url,
                link_label,
            )
        return ""

    content = revision.content_text or ""
    escaped = conditional_escape(content)
    if revision.format == DocumentRevision.ContentFormat.PLAIN_TEXT:
        return format_html('<pre class="consent-document__pre">{}</pre>', escaped)
    if revision.format == DocumentRevision.ContentFormat.MARKDOWN:
        return format_html(
            '<div class="consent-document__markdown">{}</div>',
            mark_safe(linebreaksbr(escaped)),
        )
    return format_html('<pre class="consent-document__html-source">{}</pre>', escaped)


def _find_requirement(
    *,
    purpose_code: str,
    document_code: str,
    user,
    anonymous_token: str,
    verification_context: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Searches for PI requirements exactly the one that matches the current template."""

    requirements = get_current_requirements(
        user=user,
        anonymous_token=anonymous_token or None,
        verification_context=verification_context,
    )["requirements"]
    for requirement in requirements:
        if (
            requirement["purpose_code"] == purpose_code
            and requirement["document_code"] == document_code
        ):
            return requirement
    return None


def _build_anonymous_contact_hook_context(
    context: template.Context,
    *,
    purpose_code: str,
    document_code: str,
    scenario: str,
    next_url: str,
    prefix: str,
) -> dict[str, Any]:
    """Build the shared inclusion context for contact/preorder hooks.

    The helper is deliberately generic: both scenarios use the same consent
    storage form and differ only by the scenario machine code, the field
    prefix and the confirmation text.
    """

    request = context.get("request")
    verification_context = _build_verification_context(
        form_code=f"anonymous_hook:{scenario}"
    )
    user = None
    anonymous_token = ""
    status_info = None
    requirement = None
    if request is not None:
        user, anonymous_token = get_request_consent_subject(request)
        status_info = get_consent_status(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token or None,
            verification_context=verification_context,
        )
        requirement = _find_requirement(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token,
            verification_context=verification_context,
        )
        if not next_url:
            next_url = request.get_full_path()

    field_descriptors: list[dict[str, str]] = []
    if requirement is not None:
        field_descriptors = _build_field_descriptors(requirement["fields"])
    ui_settings = resolve_subject_consents_ui_settings()
    capture_settings = dict(cast(Mapping[str, Any], ui_settings.get("capture", {})))

    return {
        "request": request,
        "scenario": scenario,
        "status_info": status_info,
        "requirement": requirement,
        "field_descriptors": field_descriptors,
        "document_url": reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose_code,
                "document_code": document_code,
            },
        ),
        "hook_form": build_anonymous_contact_consent_form(
            scenario=scenario,
            prefix=prefix,
            consent_capture_options=capture_settings,
            initial={
                "anonymous_token": anonymous_token,
                "next": next_url,
                "verification_channel": (
                    str(verification_context.get("channel") or "")
                    if verification_context
                    else ""
                ),
                "verification_form_code": (
                    str(verification_context.get("form_code") or "")
                    if verification_context
                    else ""
                ),
            },
        ),
        "consent_capture_settings": capture_settings,
    }


def _build_field_descriptors(field_codes: list[str]) -> list[dict[str, str]]:
    registry = get_fields_config()
    descriptors: list[dict[str, str]] = []
    for code in field_codes:
        field_config = registry.get(code, {})
        descriptors.append(
            {
                "code": code,
                "label": str(field_config.get("label") or code),
            }
        )
    return descriptors


def _build_verification_context(*, form_code: str) -> dict[str, str] | None:
    normalized_form_code = str(form_code or "").strip()
    if not normalized_form_code:
        return None
    return {"channel": "form", "form_code": normalized_form_code}
