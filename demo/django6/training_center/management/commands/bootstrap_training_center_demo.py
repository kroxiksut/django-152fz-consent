from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentAudienceRule,
    ConsentPurpose,
    ConsentSelfServiceSettings,
    DocumentRevision,
    LegalDocument,
)
from training_center.models import Course


class Command(BaseCommand):
    help = (
        "Bootstrap demo courses and activate required consent revisions for demo forms."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Database alias where demo data should be bootstrapped.",
        )

    def handle(self, *args, **options):
        using = options["database"]
        now = timezone.now()

        courses = (
            {
                "slug": "python-backend-start",
                "title": "Python Backend Start",
                "short_description": "Основы backend-разработки на Python.",
                "description": "Практический курс по Django, API и базам данных.",
            },
            {
                "slug": "data-analytics-fast-track",
                "title": "Data Analytics Fast Track",
                "short_description": "Быстрый старт в аналитике данных.",
                "description": "SQL, визуализация и прикладная аналитика на реальных кейсах.",
            },
        )

        created_courses = 0
        for item in courses:
            _, created = Course.objects.using(using).update_or_create(
                slug=item["slug"],
                defaults={
                    "title": item["title"],
                    "short_description": item["short_description"],
                    "description": item["description"],
                    "is_active": True,
                },
            )
            if created:
                created_courses += 1

        required_pairs = (
            ("feedback_contact", "sample_feedback_contact_consent"),
            ("course_enrollment", "sample_course_enrollment_consent"),
            ("certificate_issue", "sample_certificate_issue_consent"),
        )
        purpose_text_overrides = {
            "course_enrollment": {
                "title": "Запись на курсы",
                "description": (
                    "Согласие на обработку персональных данных для обработки "
                    "заявок на запись на курсы."
                ),
            },
            "certificate_issue": {
                "title": "Получение сертификата",
                "description": (
                    "Согласие на обработку персональных данных для подготовки "
                    "и выдачи сертификата."
                ),
            },
        }
        document_text_overrides = {
            "sample_course_enrollment_consent": {
                "title": (
                    "Согласие на обработку персональных данных для записи на курсы"
                ),
                "description": (
                    "Документ согласия, применяемый при отправке формы записи на курс."
                ),
            },
            "sample_certificate_issue_consent": {
                "title": (
                    "Согласие на обработку персональных данных "
                    "для получения сертификата"
                ),
                "description": (
                    "Документ согласия, применяемый при отправке формы "
                    "получения сертификата."
                ),
            },
        }
        purpose_capture_overrides = {
            "feedback_contact": {
                "consent_input_mode_override": "radio",
                "checkbox_required_override": None,
                "decline_action_override": "block_submit",
                "decline_warning_enabled_override": True,
                "decline_warning_text_override": (
                    "Если вы не согласны на обработку персональных данных, "
                    "мы не сможем ответить на ваше обращение."
                ),
            },
            "course_enrollment": {
                "consent_input_mode_override": "checkbox",
                "checkbox_required_override": True,
                "decline_action_override": "inherit",
                "decline_warning_enabled_override": None,
                "decline_warning_text_override": "",
            },
            "certificate_issue": {
                "consent_input_mode_override": "checkbox",
                "checkbox_required_override": True,
                "decline_action_override": "inherit",
                "decline_warning_enabled_override": None,
                "decline_warning_text_override": "",
            },
        }

        activated_revisions = 0
        configured_purposes = 0
        for purpose_code, document_code in required_pairs:
            updated_purpose = (
                ConsentPurpose.objects.using(using)
                .filter(code=purpose_code)
                .update(
                    is_active=True,
                    **purpose_text_overrides.get(purpose_code, {}),
                    **purpose_capture_overrides.get(purpose_code, {}),
                )
            )
            if updated_purpose:
                configured_purposes += updated_purpose

            LegalDocument.objects.using(using).filter(code=document_code).update(
                is_active=True,
                **document_text_overrides.get(document_code, {}),
            )

            revision_qs = DocumentRevision.objects.using(using).filter(
                purpose_code=purpose_code,
                document__code=document_code,
            )
            updated = revision_qs.update(
                is_active=True,
                is_box_template=False,
                published_at=now,
            )
            if updated:
                activated_revisions += updated

        disabled_legacy_purposes = (
            ConsentPurpose.objects.using(using)
            .filter(code="webform_request")
            .update(is_active=False)
        )
        disabled_legacy_revisions = (
            DocumentRevision.objects.using(using)
            .filter(
                purpose_code="webform_request",
                document__code="sample_generic_webform_consent",
            )
            .update(is_active=False)
        )

        course_purpose = (
            ConsentPurpose.objects.using(using).filter(code="course_enrollment").first()
        )
        course_document = (
            LegalDocument.objects.using(using)
            .filter(code="sample_course_enrollment_consent")
            .first()
        )
        audience_rules_configured = 0
        if course_purpose is not None and course_document is not None:
            for scope_mode in (
                constants.AUDIENCE_SCOPE_ALL_REGISTERED_USERS,
                constants.AUDIENCE_SCOPE_ANONYMOUS_SUBJECTS,
            ):
                ConsentAudienceRule.objects.using(using).update_or_create(
                    purpose=course_purpose,
                    document=course_document,
                    scope_mode=scope_mode,
                    defaults={
                        "is_required": True,
                        "is_active": True,
                    },
                )
                audience_rules_configured += 1

        self_service_settings, _ = ConsentSelfServiceSettings.objects.using(
            using
        ).get_or_create(
            defaults={
                "subject_consents_open_mode": "page",
                "subject_consents_list_mode": "signed_only",
                "consent_input_mode": "checkbox",
                "checkbox_required": True,
                "decline_action": "block_submit",
                "decline_warning_enabled": True,
                "decline_warning_text": (
                    "Если вы не согласны на обработку персональных данных, "
                    "мы не сможем связаться с вами по заявке."
                ),
            }
        )
        if self_service_settings.subject_consents_list_mode != "signed_only":
            self_service_settings.subject_consents_list_mode = "signed_only"
            self_service_settings.save(update_fields=["subject_consents_list_mode"])

        self.stdout.write(
            self.style.SUCCESS(
                "Demo bootstrap complete: "
                f"courses_created={created_courses}, "
                f"purposes_configured={configured_purposes}, "
                f"consent_revisions_activated={activated_revisions}, "
                f"legacy_purposes_disabled={disabled_legacy_purposes}, "
                f"legacy_revisions_disabled={disabled_legacy_revisions}, "
                f"webform_audience_rules_configured={audience_rules_configured}, "
                "self_service_list_mode=signed_only."
            )
        )
