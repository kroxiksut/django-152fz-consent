import hashlib
import json
import re
from typing import Any, cast
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import get_language
from formtools.wizard.views import SessionWizardView

from django_consent_152fz import constants
from django_consent_152fz.audit import log_module_operation
from django_consent_152fz.core.models import ConsentRecord
from django_consent_152fz.core.services import (
    accept_consent,
    get_consent_status,
    get_current_requirements,
)
from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.request import (
    build_request_audit_context,
    get_request_consent_subject,
    persist_anonymous_token,
)
from django_consent_152fz.self_service import (
    resolve_subject_consents_capture_settings,
    resolve_subject_consents_ui_settings,
)
from django_consent_152fz.verified_consents.services import submit_verified_consent

from .forms import (
    CertificateRequestForm,
    ContactForm,
    CourseSignupConfirmForm,
    CourseSignupStepOneForm,
    VerifiedPaperConsentUploadForm,
)
from .models import Course, CourseSignup


def _msg(ru: str, en: str) -> str:
    """Return RU or EN flash/UI text for the active language (demo uses inline i18n)."""
    return en if (get_language() or "").startswith("en") else ru


def _status_label(status_code: str) -> str:
    normalized = str(status_code or "").strip()
    labels = {
        "missing": _msg("Нет согласия", "No consent"),
        constants.CONSENT_STATUS_CURRENT: _msg("Актуально", "Current"),
        constants.CONSENT_STATUS_OUTDATED: _msg("Устарело", "Outdated"),
        constants.CONSENT_STATUS_WITHDRAWN: _msg("Отозвано", "Withdrawn"),
        constants.CONSENT_STATUS_PENDING_CONFIRMATION: _msg(
            "Ожидает подтверждения", "Pending confirmation"
        ),
        constants.CONSENT_STATUS_REJECTED: _msg("Отклонено", "Rejected"),
        constants.CONSENT_STATUS_DELETED: _msg("Удалено", "Deleted"),
    }
    return labels.get(normalized, normalized or _msg("Нет согласия", "No consent"))


def _verified_transition_message(status_code: str) -> str:
    normalized = str(status_code or "").strip()
    messages_map = {
        constants.VERIFIED_TRANSITION_STATUS_PAPER_REQUIRED: _msg(
            "Для этого потока требуется бумажное подтверждение согласия.",
            "This flow requires paper confirmation of consent.",
        ),
        constants.VERIFIED_TRANSITION_STATUS_AWAITING_UPLOAD: _msg(
            "Сначала загрузите подписанный бумажный документ.",
            "Upload the signed paper document first.",
        ),
        constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION: _msg(
            "Документ загружен и ожидает проверки оператором ПДн.",
            "The document has been uploaded and is awaiting review by the personal-data operator.",
        ),
        constants.VERIFIED_TRANSITION_STATUS_REJECTED: _msg(
            "Предыдущее подтверждение отклонено. Загрузите новый документ.",
            "The previous confirmation was rejected. Upload a new document.",
        ),
    }
    return messages_map.get(
        normalized,
        _msg(
            "Подписание через web-форму недоступно для этого потока согласия.",
            "Web-form signing is unavailable for this consent flow.",
        ),
    )


def _build_verified_transition_ui(
    *,
    request: HttpRequest,
    status_info: dict[str, Any],
    purpose_code: str,
    document_code: str,
    verification_context: dict[str, str] | None,
) -> dict[str, Any]:
    transition = dict((status_info or {}).get("verified_transition") or {})
    status_code = str(transition.get("status_code") or "").strip()
    enabled = bool(transition.get("enabled"))
    blocking = enabled and status_code != constants.VERIFIED_TRANSITION_STATUS_VERIFIED

    upload_url = ""
    if blocking and request.user.is_authenticated:
        query = {
            "purpose_code": purpose_code,
            "document_code": document_code,
        }
        if verification_context and verification_context.get("form_code"):
            query["form_code"] = str(verification_context["form_code"])
        upload_url = "{}?{}".format(
            reverse("pages:verified_paper_consent"),
            urlencode(query),
        )

    return {
        "enabled": enabled,
        "status_code": status_code,
        "blocking": blocking,
        "message": _verified_transition_message(status_code),
        "upload_url": upload_url,
    }


def _get_status_for_request(
    *,
    request: HttpRequest,
    purpose_code: str,
    document_code: str,
    verification_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    user, anonymous_token = get_request_consent_subject(
        request,
        ensure_anonymous_token=True,
    )
    return get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
        verification_context=verification_context,
    )


def _human_title(*, code: str, title: str) -> str:
    normalized_code = str(code or "").strip()
    normalized_title = str(title or "").strip()

    if normalized_title and normalized_code:
        suffix = re.compile(
            rf"^(?P<human>.+?)\s*[\(\[]\s*{re.escape(normalized_code)}\s*[\)\]]\s*$",
            flags=re.IGNORECASE,
        )
        match = suffix.match(normalized_title)
        if match:
            normalized_title = match.group("human").strip()

    fallback_titles = {
        "service_account": "Регистрация и обслуживание аккаунта",
        "sample_service_terms_agreement": (
            "Соглашение об условиях обслуживания аккаунта"
        ),
    }
    if normalized_title and normalized_title != normalized_code:
        return normalized_title
    return fallback_titles.get(normalized_code, normalized_title or normalized_code)


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/home.html")


def about(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/about.html")


def course_list(request: HttpRequest) -> HttpResponse:
    courses = Course.objects.filter(is_active=True).order_by("starts_at", "title")
    return render(request, "pages/courses.html", {"courses": courses})


def contact(request: HttpRequest) -> HttpResponse:
    purpose_code = "feedback_contact"
    document_code = "sample_feedback_contact_consent"
    consent_capture_settings = resolve_subject_consents_capture_settings(
        purpose_code=purpose_code
    )
    consent_document_url = reverse(
        "django_consent_152fz:document",
        kwargs={
            "purpose_code": purpose_code,
            "document_code": document_code,
        },
    )

    verification_context = {
        "channel": "form",
        "form_code": "demo.contact",
    }
    status_info = _get_status_for_request(
        request=request,
        purpose_code=purpose_code,
        document_code=document_code,
        verification_context=verification_context,
    )
    consent_required = bool(status_info.get("requires_consent"))
    verified_transition = _build_verified_transition_ui(
        request=request,
        status_info=status_info,
        purpose_code=purpose_code,
        document_code=document_code,
        verification_context=verification_context,
    )

    if request.method == "POST":
        form = ContactForm(request.POST)
        if not consent_required:
            _strip_consent_fields(form)
        if verified_transition["blocking"]:
            form.add_error(None, verified_transition["message"])
            return render(
                request,
                "pages/contact.html",
                {
                    "form": form,
                    "consent_document_url": consent_document_url,
                    "consent_capture_settings": consent_capture_settings,
                    "consent_required": consent_required,
                    "verified_transition": verified_transition,
                },
                status=400,
            )
        if form.is_valid():
            user, anonymous_token = get_request_consent_subject(
                request, ensure_anonymous_token=True
            )
            if consent_required:
                try:
                    accept_consent(
                        purpose_code=purpose_code,
                        document_code=document_code,
                        user=user,
                        anonymous_token=anonymous_token,
                        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
                        verification_context=verification_context,
                        audit_context=build_request_audit_context(
                            request,
                            source="demo.contact.form",
                            anonymous_token=anonymous_token,
                        ),
                    )
                except ConsentError as exc:
                    _log_demo_operation(
                        request=request,
                        operation_code="demo.contact.consent_error",
                        source="demo.contact.form",
                        status="error",
                        purpose_code=purpose_code,
                        summary="Contact form consent check failed.",
                        payload={"document_code": document_code},
                        result={"error": str(exc)},
                    )
                    consent_field = (
                        "confirm" if "confirm" in form.fields else "consent_decision"
                    )
                    form.add_error(consent_field, str(exc))
                    return render(
                        request,
                        "pages/contact.html",
                        {
                            "form": form,
                            "consent_document_url": consent_document_url,
                            "consent_capture_settings": consent_capture_settings,
                            "consent_required": consent_required,
                            "verified_transition": verified_transition,
                        },
                        status=400,
                    )

            message = form.save()
            _log_demo_operation(
                request=request,
                operation_code="demo.contact.submit",
                source="demo.contact.form",
                status="success",
                purpose_code=purpose_code,
                summary="Contact form submitted.",
                payload={
                    "document_code": document_code,
                    "consent_required": consent_required,
                },
                result={"contact_message_id": message.pk},
            )
            messages.success(
                request, _msg("Сообщение успешно отправлено.", "Message sent successfully.")
            )
            response = redirect("pages:contact")
            if anonymous_token:
                persist_anonymous_token(response, anonymous_token=anonymous_token)
            return response

        messages.error(
            request,
            _msg("Пожалуйста, исправьте ошибки в форме.", "Please correct the errors in the form."),
        )
    else:
        form = ContactForm()
        if not consent_required:
            _strip_consent_fields(form)

    return render(
        request,
        "pages/contact.html",
        {
            "form": form,
            "consent_document_url": consent_document_url,
            "consent_capture_settings": consent_capture_settings,
            "consent_required": consent_required,
            "verified_transition": verified_transition,
        },
    )


@login_required(login_url="account_login")
def consents(request: HttpRequest) -> HttpResponse:
    user, anonymous_token = get_request_consent_subject(
        request,
        ensure_anonymous_token=True,
    )
    configured_list_mode = str(
        resolve_subject_consents_ui_settings().get("list_mode") or "all"
    )
    requested_list_mode = str(request.GET.get("list_mode") or "").strip()
    allowed_list_modes = {"all", "pending_only", "signed_only"}
    list_mode = (
        requested_list_mode
        if requested_list_mode in allowed_list_modes
        else configured_list_mode
    )
    requirements_payload = get_current_requirements(
        user=user,
        anonymous_token=anonymous_token,
    )
    rows: list[dict[str, object]] = []
    for item in requirements_payload.get("requirements", []):
        purpose_code = str(item.get("purpose_code") or "")
        document_code = str(item.get("document_code") or "")
        subject_record_qs = ConsentRecord.objects.filter(
            purpose__code=purpose_code,
            document_revision__document__code=document_code,
        ).exclude(status=ConsentRecord.Status.DELETED)
        if user is not None and anonymous_token:
            subject_record_qs = subject_record_qs.filter(
                Q(user=user) | Q(anonymous_token=anonymous_token)
            )
        elif user is not None:
            subject_record_qs = subject_record_qs.filter(user=user)
        else:
            subject_record_qs = subject_record_qs.filter(
                anonymous_token=anonymous_token
            )
        latest_signed_at = (
            subject_record_qs.exclude(
                status__in=[
                    ConsentRecord.Status.WITHDRAWN,
                    ConsentRecord.Status.DELETED,
                ]
            )
            .order_by("-created_at", "-id")
            .values_list("created_at", flat=True)
            .first()
        )
        status = get_consent_status(
            purpose_code=purpose_code,
            document_code=document_code,
            user=user,
            anonymous_token=anonymous_token,
        )
        requires_consent = bool(status.get("requires_consent"))
        can_withdraw = str(status.get("status") or "") in {
            ConsentRecord.Status.CURRENT,
            ConsentRecord.Status.OUTDATED,
        }
        if list_mode == "pending_only" and not requires_consent:
            continue
        if list_mode == "signed_only" and not can_withdraw:
            continue
        rows.append(
            {
                "purpose_code": purpose_code,
                "purpose_title": _human_title(
                    code=purpose_code,
                    title=str(item.get("purpose_title") or purpose_code),
                ),
                "document_code": document_code,
                "document_title": _human_title(
                    code=document_code,
                    title=str(item.get("document_title") or document_code),
                ),
                "status": _status_label(str(status.get("status") or "missing")),
                "is_current": bool(status.get("is_current")),
                "requires_consent": requires_consent,
                "can_withdraw": can_withdraw,
                "signed_at": latest_signed_at,
                "show_sign_action": list_mode in {"all", "pending_only"}
                and requires_consent,
                "show_withdraw_action": list_mode in {"all", "signed_only"}
                and can_withdraw,
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
            }
        )
    return render(
        request,
        "pages/consents.html",
        {
            "consent_rows": rows,
            "consent_list_mode": list_mode,
            "consent_list_mode_options": ("all", "signed_only", "pending_only"),
            "subject_consents_url": reverse("django_consent_152fz:subject_consents"),
        },
    )


class CourseSignupWizard(SessionWizardView):
    form_list = [
        ("details", CourseSignupStepOneForm),
        ("confirm", CourseSignupConfirmForm),
    ]
    template_name = "pages/course_signup.html"
    dedupe_session_key = "course_signup_last_signature"

    def get_consent_document_url(self) -> str:
        return reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": "course_enrollment",
                "document_code": "sample_course_enrollment_consent",
            },
        )

    def get_context_data(self, form: Any, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(form=form, **kwargs)
        context["consent_document_url"] = self.get_consent_document_url()
        verification_context = {
            "channel": "form",
            "form_code": "demo.course_signup",
        }
        status_info = _get_status_for_request(
            request=self.request,
            purpose_code="course_enrollment",
            document_code="sample_course_enrollment_consent",
            verification_context=verification_context,
        )
        consent_required = bool(status_info.get("requires_consent"))
        verified_transition = _build_verified_transition_ui(
            request=self.request,
            status_info=status_info,
            purpose_code="course_enrollment",
            document_code="sample_course_enrollment_consent",
            verification_context=verification_context,
        )
        if self.steps.current == "confirm" and not consent_required:
            _strip_consent_fields(form)
        context["consent_capture_settings"] = resolve_subject_consents_capture_settings(
            purpose_code="course_enrollment"
        )
        context["consent_required"] = consent_required
        context["verified_transition"] = verified_transition
        if self.steps.current == "confirm":
            context["signup_preview"] = self.get_cleaned_data_for_step("details") or {}
        return context

    def get_form_initial(self, step: str) -> dict[str, Any]:
        initial = super().get_form_initial(step)
        if step == "details":
            course_id = self.request.GET.get("course")
            if course_id and str(course_id).isdigit():
                initial["course"] = int(course_id)
        return initial

    def done(self, form_list: list[Any], **kwargs: Any) -> HttpResponse:
        purpose_code = "course_enrollment"
        document_code = "sample_course_enrollment_consent"
        details_raw = self.get_cleaned_data_for_step("details") or {}
        details = cast(
            dict[str, Any], details_raw if isinstance(details_raw, dict) else {}
        )
        if not details:
            messages.error(
                self.request,
                _msg(
                    "Данные записи не найдены. Попробуйте снова.",
                    "Signup data was not found. Please try again.",
                ),
            )
            return redirect("pages:course_signup")

        signature_payload = {
            "course_id": details["course"].pk,
            "full_name": details["full_name"].strip(),
            "email": details["email"].strip().lower(),
            "phone": details["phone"].strip(),
            "comment": (details.get("comment") or "").strip(),
        }
        signature = hashlib.sha256(
            json.dumps(
                signature_payload,
                sort_keys=True,
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()

        if self.request.session.get(self.dedupe_session_key) == signature:
            _log_demo_operation(
                request=self.request,
                operation_code="demo.course_signup.duplicate",
                source="demo.course_signup.form",
                status="dry_run",
                purpose_code=purpose_code,
                summary="Duplicate course signup prevented by demo dedupe guard.",
                payload={"document_code": document_code},
                result={"duplicate": True},
            )
            messages.info(
                self.request,
                _msg(
                    "Такая заявка уже была отправлена.",
                    "This signup has already been submitted.",
                ),
            )
            return redirect("pages:course_signup")

        user, anonymous_token = get_request_consent_subject(
            self.request,
            ensure_anonymous_token=True,
        )
        verification_context = {
            "channel": "form",
            "form_code": "demo.course_signup",
        }
        status_info = _get_status_for_request(
            request=self.request,
            purpose_code=purpose_code,
            document_code=document_code,
            verification_context=verification_context,
        )
        consent_required = bool(status_info.get("requires_consent"))
        verified_transition = _build_verified_transition_ui(
            request=self.request,
            status_info=status_info,
            purpose_code=purpose_code,
            document_code=document_code,
            verification_context=verification_context,
        )
        if verified_transition["blocking"]:
            messages.error(self.request, verified_transition["message"])
            return redirect("pages:course_signup")
        if consent_required:
            try:
                accept_consent(
                    purpose_code=purpose_code,
                    document_code=document_code,
                    user=user,
                    anonymous_token=anonymous_token,
                    confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
                    verification_context=verification_context,
                    audit_context=build_request_audit_context(
                        self.request,
                        source="demo.course_signup.form",
                        anonymous_token=anonymous_token,
                    ),
                )
            except ConsentError as exc:
                _log_demo_operation(
                    request=self.request,
                    operation_code="demo.course_signup.consent_error",
                    source="demo.course_signup.form",
                    status="error",
                    purpose_code=purpose_code,
                    summary="Course signup consent check failed.",
                    payload={"document_code": document_code},
                    result={"error": str(exc)},
                )
                messages.error(self.request, str(exc))
                return redirect("pages:course_signup")

        user = self.request.user if self.request.user.is_authenticated else None
        signup = CourseSignup.objects.create(
            full_name=details["full_name"],
            email=details["email"],
            phone=details["phone"],
            course=details["course"],
            comment=details.get("comment", ""),
            user=user,
        )
        _log_demo_operation(
            request=self.request,
            operation_code="demo.course_signup.submit",
            source="demo.course_signup.form",
            status="success",
            purpose_code=purpose_code,
            summary="Course signup submitted.",
            payload={
                "document_code": document_code,
                "consent_required": consent_required,
            },
            result={"course_signup_id": signup.pk},
        )
        self.request.session[self.dedupe_session_key] = signature
        messages.success(
            self.request,
            _msg(
                "Заявка на курс успешно отправлена.",
                "Course signup submitted successfully.",
            ),
        )
        response = redirect("pages:course_signup")
        if anonymous_token:
            persist_anonymous_token(response, anonymous_token=anonymous_token)
        return response


course_signup = CourseSignupWizard.as_view()


@login_required(login_url="account_login")
def profile(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/profile.html")


@login_required(login_url="account_login")
def certificate_request(request: HttpRequest) -> HttpResponse:
    purpose_code = "certificate_issue"
    document_code = "sample_certificate_issue_consent"
    verification_context = {
        "channel": "form",
        "form_code": "demo.certificate_request",
    }
    consent_capture_settings = resolve_subject_consents_capture_settings(
        purpose_code=purpose_code
    )
    consent_document_url = reverse(
        "django_consent_152fz:document",
        kwargs={
            "purpose_code": purpose_code,
            "document_code": document_code,
        },
    )
    consent_document_pdf_url = reverse(
        "django_consent_152fz:document_pdf",
        kwargs={
            "purpose_code": purpose_code,
            "document_code": document_code,
        },
    )
    status_info = _get_status_for_request(
        request=request,
        purpose_code=purpose_code,
        document_code=document_code,
        verification_context=verification_context,
    )
    consent_required = bool(status_info.get("requires_consent"))
    verified_transition = _build_verified_transition_ui(
        request=request,
        status_info=status_info,
        purpose_code=purpose_code,
        document_code=document_code,
        verification_context=verification_context,
    )
    show_web_consent = consent_required and not bool(verified_transition.get("enabled"))
    verified_upload_url = "{}?{}".format(
        reverse("pages:verified_paper_consent"),
        urlencode(
            {
                "purpose_code": purpose_code,
                "document_code": document_code,
                "form_code": str(verification_context.get("form_code") or ""),
            }
        ),
    )

    if request.method == "POST":
        form = CertificateRequestForm(request.POST, user=request.user)
        if not show_web_consent:
            _strip_consent_fields(form)
        course_name_field = form.fields.get("course_name")
        available_courses = bool(getattr(course_name_field, "choices", []))
        if not available_courses:
            form.add_error(
                "course_name",
                _msg(
                    "Сначала оставьте заявку на курс, затем подайте заявку на сертификат.",
                    "Submit a course signup first, then request a certificate.",
                ),
            )
        if verified_transition["blocking"]:
            form.add_error(None, verified_transition["message"])
            return render(
                request,
                "pages/certificate_request.html",
                {
                    "form": form,
                    "consent_document_url": consent_document_url,
                    "consent_document_pdf_url": consent_document_pdf_url,
                    "consent_capture_settings": consent_capture_settings,
                    "consent_required": consent_required,
                    "show_web_consent": show_web_consent,
                    "verified_transition": verified_transition,
                    "verified_upload_url": verified_upload_url,
                    "has_available_courses": available_courses,
                },
                status=400,
            )
        if form.is_valid():
            user, anonymous_token = get_request_consent_subject(
                request,
                ensure_anonymous_token=True,
            )
            if show_web_consent and consent_required:
                try:
                    accept_consent(
                        purpose_code=purpose_code,
                        document_code=document_code,
                        user=user,
                        anonymous_token=anonymous_token,
                        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
                        verification_context=verification_context,
                        audit_context=build_request_audit_context(
                            request,
                            source="demo.certificate_request.form",
                            anonymous_token=anonymous_token,
                        ),
                    )
                except ConsentError as exc:
                    _log_demo_operation(
                        request=request,
                        operation_code="demo.certificate_request.consent_error",
                        source="demo.certificate_request.form",
                        status="error",
                        purpose_code=purpose_code,
                        summary="Certificate request consent check failed.",
                        payload={"document_code": document_code},
                        result={"error": str(exc)},
                    )
                    consent_field = (
                        "confirm" if "confirm" in form.fields else "consent_decision"
                    )
                    form.add_error(consent_field, str(exc))
                    return render(
                        request,
                        "pages/certificate_request.html",
                        {
                            "form": form,
                            "consent_document_url": consent_document_url,
                            "consent_document_pdf_url": consent_document_pdf_url,
                            "consent_capture_settings": consent_capture_settings,
                            "consent_required": consent_required,
                            "show_web_consent": show_web_consent,
                            "verified_transition": verified_transition,
                            "verified_upload_url": verified_upload_url,
                            "has_available_courses": available_courses,
                        },
                        status=400,
                    )

            request_obj = form.save(commit=False)
            request_obj.user = request.user
            request_obj.save()
            _log_demo_operation(
                request=request,
                operation_code="demo.certificate_request.submit",
                source="demo.certificate_request.form",
                status="success",
                purpose_code=purpose_code,
                summary="Certificate request submitted.",
                payload={
                    "document_code": document_code,
                    "consent_required": consent_required,
                },
                result={"certificate_request_id": request_obj.pk},
            )
            messages.success(
                request,
                _msg(
                    "Заявка на получение сертификата отправлена.",
                    "Certificate request submitted.",
                ),
            )
            response = redirect("pages:certificate_request")
            if anonymous_token:
                persist_anonymous_token(response, anonymous_token=anonymous_token)
            return response
        messages.error(
            request,
            _msg("Пожалуйста, исправьте ошибки в форме.", "Please correct the errors in the form."),
        )
    else:
        request_user = cast(Any, request.user)
        initial = {
            "full_name": str(request_user.get_full_name() or ""),
            "email": str(getattr(request_user, "email", "") or ""),
        }
        form = CertificateRequestForm(initial=initial, user=request.user)
        if not show_web_consent:
            _strip_consent_fields(form)
        course_name_field = form.fields.get("course_name")
        available_courses = bool(getattr(course_name_field, "choices", []))
        if not available_courses:
            messages.info(
                request,
                _msg(
                    "Сначала отправьте заявку на курс. После этого курс появится в списке для сертификата.",
                    "Submit a course signup first. After that the course will appear in the list for the certificate.",
                ),
            )

    return render(
        request,
        "pages/certificate_request.html",
        {
            "form": form,
            "consent_document_url": consent_document_url,
            "consent_document_pdf_url": consent_document_pdf_url,
            "consent_capture_settings": consent_capture_settings,
            "consent_required": consent_required,
            "show_web_consent": show_web_consent,
            "verified_transition": verified_transition,
            "verified_upload_url": verified_upload_url,
            "has_available_courses": available_courses,
        },
    )


@login_required(login_url="account_login")
def verified_paper_consent(request: HttpRequest) -> HttpResponse:
    purpose_code = str(
        request.POST.get("_purpose_code")
        or request.GET.get("purpose_code")
        or "verified_paper_demo"
    ).strip()
    document_code = str(
        request.POST.get("_document_code")
        or request.GET.get("document_code")
        or "sample_verified_paper_consent"
    ).strip()
    form_code = str(
        request.POST.get("_form_code") or request.GET.get("form_code") or ""
    ).strip()
    verification_context = {
        "channel": "form" if form_code else "self_service",
        "form_code": form_code,
    }
    consent_document_url = reverse(
        "django_consent_152fz:document",
        kwargs={
            "purpose_code": purpose_code,
            "document_code": document_code,
        },
    )
    consent_document_pdf_url = reverse(
        "django_consent_152fz:document_pdf",
        kwargs={
            "purpose_code": purpose_code,
            "document_code": document_code,
        },
    )

    user, anonymous_token = get_request_consent_subject(
        request,
        ensure_anonymous_token=True,
    )
    status = get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
        verification_context=verification_context,
    )

    if request.method == "POST":
        form = VerifiedPaperConsentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            performed_by = request.user
            try:
                submit_verified_consent(
                    purpose_code=purpose_code,
                    document_code=document_code,
                    user=user,
                    anonymous_token=anonymous_token,
                    fields_snapshot=[
                        str(form.cleaned_data["full_name"]).strip(),
                        str(form.cleaned_data["email"]).strip(),
                    ],
                    paper_file=form.cleaned_data["paper_file"],
                    source="demo.verified_paper.form",
                    audit_context=build_request_audit_context(
                        request,
                        source="demo.verified_paper.form",
                        anonymous_token=anonymous_token,
                    ),
                    artifact_note=str(form.cleaned_data.get("note") or "").strip(),
                    performed_by=performed_by
                    if bool(getattr(performed_by, "is_staff", False))
                    else None,
                    verification_context=verification_context,
                )
            except ConsentError as exc:
                form.add_error("paper_file", str(exc))
                messages.error(
                    request,
                    _msg(
                        "Не удалось отправить бумажное подтверждение.",
                        "Failed to submit the paper confirmation.",
                    ),
                )
            else:
                messages.success(
                    request,
                    _msg(
                        "Бумажное согласие загружено и отправлено на проверяемое подтверждение.",
                        "Paper consent uploaded and submitted for verified confirmation.",
                    ),
                )
                redirect_url = reverse("pages:verified_paper_consent")
                query = {
                    "purpose_code": purpose_code,
                    "document_code": document_code,
                }
                if form_code:
                    query["form_code"] = form_code
                response = redirect(f"{redirect_url}?{urlencode(query)}")
                if anonymous_token:
                    persist_anonymous_token(response, anonymous_token=anonymous_token)
                return response
    else:
        request_user = cast(Any, request.user)
        form = VerifiedPaperConsentUploadForm(
            initial={
                "full_name": str(request_user.get_full_name() or ""),
                "email": str(getattr(request_user, "email", "") or ""),
            }
        )

    return render(
        request,
        "pages/verified_paper_consent.html",
        {
            "form": form,
            "consent_document_url": consent_document_url,
            "consent_document_pdf_url": consent_document_pdf_url,
            "consent_status_label": _status_label(
                str(status.get("status") or "missing")
            ),
            "consent_requires": bool(status.get("requires_consent")),
            "purpose_code": purpose_code,
            "document_code": document_code,
            "form_code": form_code,
            "return_to_certificate_url": (
                reverse("pages:certificate_request")
                if form_code == "demo.certificate_request"
                else ""
            ),
            "verified_transition": _build_verified_transition_ui(
                request=request,
                status_info=status,
                purpose_code=purpose_code,
                document_code=document_code,
                verification_context=verification_context,
            ),
        },
    )


def _strip_consent_fields(form: Any) -> None:
    form.fields.pop("confirm", None)
    form.fields.pop("consent_decision", None)
    form.fields.pop("consent_confirm", None)


def _log_demo_operation(
    *,
    request: HttpRequest,
    operation_code: str,
    source: str,
    status: str,
    purpose_code: str,
    summary: str,
    payload: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
) -> None:
    actor = request.user if getattr(request.user, "is_authenticated", False) else None
    log_module_operation(
        operation_code=operation_code,
        actor_user=actor,
        source=source,
        status=status,
        target_model="ConsentPurpose",
        target_id=purpose_code,
        summary=summary,
        payload=dict(payload or {}),
        result=dict(result or {}),
    )
