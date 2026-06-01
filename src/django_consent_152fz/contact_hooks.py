"""Reusable helpers для безрегистрационных contact/preorder сценариев.

Этот слой появился в пункте 5.4 как мост между уже существующей формой
проекта-хоста и каноническим consent-flow из ядра. Он не хранит контакты
сам по себе, а только:
- валидирует embedded hook-форму;
- определяет `subject_ref`;
- дополняет `audit_context`;
- вызывает `accept_consent()` из ядра.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from django.http import HttpRequest

from django_consent_152fz.core.models import ConsentRecord
from django_consent_152fz.core.services import accept_consent, get_consent_status
from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.forms import (
    ANONYMOUS_CONSENT_SCENARIO_CONTACT,
    ANONYMOUS_CONSENT_SCENARIO_PREORDER,
    AnonymousContactConsentHookForm,
    build_verification_context_from_cleaned_data,
)
from django_consent_152fz.request import (
    build_request_audit_context,
    get_request_consent_subject,
)


def build_anonymous_contact_consent_form(
    data=None,
    *,
    scenario: str = ANONYMOUS_CONSENT_SCENARIO_CONTACT,
    prefix: str = "contact_consent",
    consent_capture_options: Mapping[str, Any] | None = None,
    initial: Mapping[str, Any] | None = None,
) -> AnonymousContactConsentHookForm:
    """Builds a hook form for an anonymous contact/preorder script."""

    normalized_initial = dict(initial or {})
    normalized_initial.setdefault("scenario", scenario)
    return AnonymousContactConsentHookForm(
        data=data,
        prefix=prefix,
        scenario=scenario,
        consent_capture_options=consent_capture_options,
        initial=normalized_initial,
    )


def accept_anonymous_contact_consent_from_form(
    request: HttpRequest,
    form: AnonymousContactConsentHookForm,
    *,
    purpose_code: str,
    document_code: str,
    source: str = "",
) -> ConsentRecord:
    """Принимает анонимное согласие на основе уже валидированной hook-формы.

    Функция гарантирует, что поток остаётся именно анонимным: если в запросе
    уже есть аутентифицированный пользователь, нужно использовать обычный
    core-flow, а не embedded contact hook.
    """

    if not form.is_valid():
        raise ConsentError("Anonymous contact consent form must be valid.")

    cleaned_data = form.cleaned_data
    scenario = str(cleaned_data["scenario"]).strip()
    user, anonymous_token = get_request_consent_subject(
        request,
        anonymous_token=cleaned_data["anonymous_token"],
        ensure_anonymous_token=True,
    )
    if user is not None:
        raise ConsentError(
            "Anonymous contact consent hook is intended for unauthenticated subjects."
        )

    status_info = get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        anonymous_token=anonymous_token,
        verification_context=build_verification_context_from_cleaned_data(
            cleaned_data,
            default_channel="form",
            default_form_code=f"anonymous_hook:{scenario}",
        ),
    )
    if (
        status_info["latest_revision_id"] is not None
        and not status_info["is_applicable"]
    ):
        # The audience rules from paragraph 4.9 are taken into account here: even anonymous
        # the script cannot be applied to a subject for which the flow is not relevant.
        raise ConsentError(
            "This consent flow is not applicable to the current anonymous subject."
        )

    resolved_subject_ref = _resolve_subject_ref(cleaned_data)
    audit_context = build_request_audit_context(
        request,
        source=source or _default_source_for_scenario(scenario),
        anonymous_token=anonymous_token,
    )
    _enrich_audit_context_from_hook_form(
        audit_context=audit_context,
        cleaned_data=cleaned_data,
        subject_ref=resolved_subject_ref,
    )
    return accept_consent(
        purpose_code=purpose_code,
        document_code=document_code,
        anonymous_token=anonymous_token,
        subject_ref=resolved_subject_ref,
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
        verification_context=build_verification_context_from_cleaned_data(
            cleaned_data,
            default_channel="form",
            default_form_code=f"anonymous_hook:{scenario}",
        ),
        audit_context=audit_context,
    )


def submit_anonymous_contact_consent(
    request: HttpRequest,
    *,
    purpose_code: str,
    document_code: str,
    scenario: str = ANONYMOUS_CONSENT_SCENARIO_CONTACT,
    prefix: str = "contact_consent",
    source: str = "",
) -> tuple[ConsentRecord, AnonymousContactConsentHookForm]:
    """Полный helper для POST-сценария.

    Собирает форму, сохраняет согласие и возвращает оба объекта.
    """

    form = build_anonymous_contact_consent_form(
        data=request.POST or None,
        scenario=scenario,
        prefix=prefix,
    )
    record = accept_anonymous_contact_consent_from_form(
        request,
        form,
        purpose_code=purpose_code,
        document_code=document_code,
        source=source,
    )
    return record, form


def _resolve_subject_ref(cleaned_data: Mapping[str, Any]) -> str:
    """Определяет устойчивый `subject_ref` по лучшему доступному идентификатору.

    Для contact-сценария это обычно email/телефон, для preorder — `preorder_id`.
    Такой порядок нужен, чтобы проект мог не подготавливать отдельный идентификатор
    заранее, но при этом запись согласия всё равно можно было связать с субъектом.
    """

    candidates = (
        cleaned_data.get("subject_ref"),
        cleaned_data.get("preorder_id"),
        cleaned_data.get("contact_email"),
        cleaned_data.get("contact_phone"),
        cleaned_data.get("contact_contacts"),
        cleaned_data.get("contact_name"),
    )
    for raw_value in candidates:
        value = str(raw_value or "").strip()
        if value:
            return value
    raise ConsentError("subject_ref or at least one contact identifier is required.")


def _enrich_audit_context_from_hook_form(
    *,
    audit_context: dict[str, Any],
    cleaned_data: Mapping[str, Any],
    subject_ref: str,
) -> None:
    """Переносит данные embedded-формы в канонические `extra_meta.client/custom`.

    Здесь мы сознательно не создаём отдельную произвольную схему для contact hook.
    Всё укладывается в те же namespaces audit-контекста, что и остальные потоки
    пакета, чтобы журналы событий читались единообразно.
    """

    extra_meta = dict(audit_context.get("extra_meta") or {})
    client_meta = dict(extra_meta.get("client") or {})
    custom_meta = dict(extra_meta.get("custom") or {})
    contact_meta = dict(custom_meta.get("contact") or {})

    timezone = str(cleaned_data.get("client_timezone") or "").strip()
    if timezone:
        client_meta["timezone"] = timezone

    languages = _parse_languages(str(cleaned_data.get("client_languages") or ""))
    if languages:
        client_meta["languages"] = languages

    os_locale = str(cleaned_data.get("client_os_locale") or "").strip()
    if os_locale:
        client_meta["os_locale"] = os_locale

    screen: dict[str, int] = {}
    for source_key, output_key in (
        ("client_screen_width", "width"),
        ("client_screen_height", "height"),
    ):
        value = cleaned_data.get(source_key)
        if value:
            screen[output_key] = int(value)
    if screen:
        client_meta["screen"] = screen

    contact_meta["scenario"] = str(cleaned_data.get("scenario") or "").strip()
    contact_meta["subject_ref"] = subject_ref
    for source_key, output_key in (
        ("contact_name", "name"),
        ("contact_email", "email"),
        ("contact_phone", "phone"),
        ("contact_contacts", "contacts"),
        ("contact_address", "address"),
        ("contact_message", "message"),
    ):
        value = str(cleaned_data.get(source_key) or "").strip()
        if value:
            contact_meta[output_key] = value

    preorder_id = str(cleaned_data.get("preorder_id") or "").strip()
    if preorder_id:
        custom_meta["preorder_id"] = preorder_id

    if client_meta:
        extra_meta["client"] = client_meta
    if contact_meta:
        custom_meta["contact"] = contact_meta
    if custom_meta:
        extra_meta["custom"] = custom_meta
    audit_context["extra_meta"] = extra_meta


def _default_source_for_scenario(scenario: str) -> str:
    """Возвращает источник события по сценарию.

    Это нужно, чтобы аудит различал contact и preorder потоки.
    """

    if scenario == ANONYMOUS_CONSENT_SCENARIO_PREORDER:
        return "template_hook.preorder"
    return "template_hook.contact"


def _parse_languages(value: str) -> list[str]:
    """Accepts JSON array of languages ​​and simple CSV format for embedded hook."""

    raw_value = value.strip()
    if not raw_value:
        return []
    if raw_value.startswith("["):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [chunk.strip() for chunk in raw_value.split(",") if chunk.strip()]
