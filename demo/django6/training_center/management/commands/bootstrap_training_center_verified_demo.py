from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentAudienceRule,
    ConsentPurpose,
    DocumentRevision,
    LegalDocument,
)


class Command(BaseCommand):
    help = "Bootstrap verified-consent demo flow (paper_required) for Django 5 training_center."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Database alias where verified demo data should be bootstrapped.",
        )

    def handle(self, *args, **options):
        using = options["database"]

        if not self._is_verified_layer_available():
            self.stdout.write(
                self.style.WARNING(
                    "Skip verified demo bootstrap: "
                    "verified_consents app is not installed."
                )
            )
            return

        from django_consent_152fz.verified_consents.models import (
            VerifiedConsentFormPolicy,
            VerifiedConsentPolicy,
        )

        now = timezone.now()

        purpose, _ = ConsentPurpose.objects.using(using).update_or_create(
            code="verified_paper_demo",
            defaults={
                "title": "Проверяемое согласие (демо)",
                "description": (
                    "Демо-поток для сценария загрузки бумажного подтверждения согласия "
                    "через verified-consents."
                ),
                "fields_config": [
                    {"name": "full_name", "label": "ФИО", "required": True},
                    {"name": "email", "label": "Email", "required": True},
                ],
                "withdraw_strategy": constants.WITHDRAW_STRATEGY_BLOCK,
                "reconsent_mode": constants.RECONSENT_MODE_HARD,
                "is_active": True,
            },
        )

        document, _ = LegalDocument.objects.using(using).update_or_create(
            code="sample_verified_paper_consent",
            defaults={
                "title": "Согласие с бумажным подтверждением (демо)",
                "document_type": "consent",
                "description": (
                    "Демо-документ для проверяемого согласия. "
                    "Подтверждение выполняется через загрузку бумажного файла."
                ),
                "is_active": True,
            },
        )

        DocumentRevision.objects.using(using).update_or_create(
            purpose_code=purpose.code,
            document=document,
            version=1,
            defaults={
                "format": "plain_text",
                "content_text": (
                    "Я подтверждаю согласие на обработку персональных данных для "
                    "учебного демо-сценария с обязательным бумажным подтверждением."
                ),
                "fields_snapshot": list(purpose.fields_config or []),
                "is_active": True,
                "is_box_template": False,
                "published_at": now,
            },
        )

        for scope_mode in (
            constants.AUDIENCE_SCOPE_ALL_REGISTERED_USERS,
            constants.AUDIENCE_SCOPE_ANONYMOUS_SUBJECTS,
        ):
            ConsentAudienceRule.objects.using(using).update_or_create(
                purpose=purpose,
                document=document,
                scope_mode=scope_mode,
                defaults={
                    "is_required": True,
                    "is_active": True,
                },
            )

        policy, created = VerifiedConsentPolicy.objects.using(using).update_or_create(
            purpose=purpose,
            document=document,
            defaults={
                "verification_mode": VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
                "flow_scope": VerifiedConsentPolicy.FlowScope.BOTH,
                "legacy_web_consent_policy": (
                    VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED
                ),
                "allow_subject_self_upload": True,
                "is_active": True,
                "notes": "Демо-политика: загрузка PDF бумажного подтверждения.",
            },
        )

        certificate_purpose = (
            ConsentPurpose.objects.using(using).filter(code="certificate_issue").first()
        )
        certificate_document = (
            LegalDocument.objects.using(using)
            .filter(code="sample_certificate_issue_consent")
            .first()
        )
        certificate_policy = None
        certificate_policy_created = False
        if certificate_purpose is not None and certificate_document is not None:
            certificate_policy, certificate_policy_created = (
                VerifiedConsentPolicy.objects.using(using).update_or_create(
                    purpose=certificate_purpose,
                    document=certificate_document,
                    defaults={
                        "verification_mode": (
                            VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED
                        ),
                        "flow_scope": VerifiedConsentPolicy.FlowScope.FORMS_ONLY,
                        "legacy_web_consent_policy": (
                            VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED
                        ),
                        "allow_subject_self_upload": True,
                        "allow_draft_data_before_upload": False,
                        "pre_upload_access_mode": (
                            VerifiedConsentPolicy.PreUploadAccessMode.BLOCK
                        ),
                        "is_active": True,
                        "notes": (
                            "Демонстрационная политика доступа для формы получения "
                            "сертификата: требуется согласие, подтверждённое на бумаге."
                        ),
                    },
                )
            )

        created_form_policies = 0
        for purpose_code, document_code, form_code in (
            ("feedback_contact", "sample_feedback_contact_consent", "demo.contact"),
            (
                "course_enrollment",
                "sample_course_enrollment_consent",
                "demo.course_signup",
            ),
            (
                "certificate_issue",
                "sample_certificate_issue_consent",
                "demo.certificate_request",
            ),
        ):
            form_purpose = (
                ConsentPurpose.objects.using(using).filter(code=purpose_code).first()
            )
            form_document = (
                LegalDocument.objects.using(using).filter(code=document_code).first()
            )
            if form_purpose is None or form_document is None:
                continue

            _, form_created = VerifiedConsentFormPolicy.objects.using(
                using
            ).update_or_create(
                purpose=form_purpose,
                document=form_document,
                form_code=form_code,
                defaults={
                    "verification_mode_override": (
                        VerifiedConsentFormPolicy.VerificationModeOverride.INHERIT
                    ),
                    "is_active": True,
                    "notes": "Демо-политика формы (16.9): наследование эффективного режима.",
                },
            )
            created_form_policies += int(form_created)

        legacy_deleted, _ = (
            VerifiedConsentFormPolicy.objects.using(using)
            .filter(
                purpose__code="webform_request",
                document__code="sample_generic_webform_consent",
                form_code="demo.course_signup",
            )
            .delete()
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Verified demo bootstrap complete: "
                f"purpose={purpose.code}, document={document.code}, "
                f"verified_policy_id={policy.pk}, created={created}, "
                f"certificate_policy_id={getattr(certificate_policy, 'pk', None)}, "
                f"certificate_policy_created={certificate_policy_created}, "
                f"created_form_policies={created_form_policies}, "
                f"legacy_form_policies_deleted={legacy_deleted}."
            )
        )
        self.stdout.write(
            "Use demo file: demo/common/fixtures/verified/sample_verified_consent.pdf"
        )

    def _is_verified_layer_available(self) -> bool:
        from django.conf import settings

        return "django_consent_152fz.verified_consents" in getattr(
            settings, "INSTALLED_APPS", []
        )
