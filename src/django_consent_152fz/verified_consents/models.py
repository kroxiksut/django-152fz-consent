"""Модели optional app `verified_consents`.

Важно понимать границу этого модуля:
- он не хранит отдельный домен согласий;
- канонические статусы и события остаются в `core`;
- здесь лежат только policy и method-specific артефакты усиленного подтверждения.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Django dynamic ORM/admin attributes are not fully inferable by pyright.
import os
import uuid
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from django_consent_152fz.core.models import (
    ConsentPurpose,
    ConsentRecord,
    LegalDocument,
)

ALLOWED_PAPER_FILE_EXTENSIONS = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
)
MAX_PAPER_FILE_SIZE_BYTES = 10 * 1024 * 1024


def _verified_artifact_upload_to(instance, filename: str) -> str:
    """Create a stable path for storing paper artifacts without name collisions."""
    ext = os.path.splitext(str(filename or ""))[1].lower() or ".bin"
    safe_ext = ext if ext.startswith(".") else f".{ext}"
    now = datetime.now()
    short_hash = uuid.uuid4().hex[:10]
    return (
        f"django_consent_152fz/verified_artifacts/{now:%Y/%m/%d}/{short_hash}{safe_ext}"
    )


class VerifiedConsentPolicy(models.Model):
    """Политика усиленного подтверждения для потока `purpose + document`.

    Модель отвечает не на вопрос "есть ли согласие", а на вопрос
    "каким способом согласие должно считаться достаточным для этого потока".
    """

    class VerificationMode(models.TextChoices):
        """Supported Enhanced Confirmation Strategies."""

        WEB_ONLY = "web_only", _("Web only")
        PAPER_REQUIRED = "paper_required", _("Paper required")
        GOSKEY_REQUIRED = "goskey_required", _("Goskey required")
        PAPER_OR_GOSKEY = "paper_or_goskey", _("Paper or Goskey")

    class FlowScope(models.TextChoices):
        BOTH = "both", _("Both (self-service and forms)")
        SELF_SERVICE_ONLY = "self_service_only", _("Self-service only")
        FORMS_ONLY = "forms_only", _("Forms only")

    class LegacyWebConsentPolicy(models.TextChoices):
        KEEP_WEB_CURRENT = (
            "keep_web_current",
            _("Keep existing web consent as current"),
        )
        MARK_WEB_OUTDATED = (
            "mark_web_outdated",
            _("Mark existing web consent as outdated"),
        )
        WITHDRAW_WEB_NOW = (
            "withdraw_web_now",
            _("Withdraw existing web consent immediately"),
        )
        WITHDRAW_AFTER_PAPER_CONFIRMED = (
            "withdraw_after_paper_confirmed",
            _("Withdraw existing web consent after paper is confirmed"),
        )

    class PreUploadAccessMode(models.TextChoices):
        BLOCK = "block", _("Block")
        ALLOW_LIMITED = "allow_limited", _("Allow limited access")

    class NotificationMode(models.TextChoices):
        AUDIT_ONLY = "audit_only", _("Audit log only")
        ASSIGNMENT_USERS = "assignment_users", _("Notify responsible users")

    purpose = models.ForeignKey(
        ConsentPurpose,
        on_delete=models.PROTECT,
        related_name="verified_policies",
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.PROTECT,
        related_name="verified_policies",
    )
    verification_mode = models.CharField(
        max_length=32,
        choices=VerificationMode.choices,
        default=VerificationMode.PAPER_REQUIRED,
    )
    flow_scope = models.CharField(
        max_length=32,
        choices=FlowScope.choices,
        default=FlowScope.BOTH,
    )
    legacy_web_consent_policy = models.CharField(
        max_length=32,
        choices=LegacyWebConsentPolicy.choices,
        default=LegacyWebConsentPolicy.MARK_WEB_OUTDATED,
    )
    allow_subject_self_upload = models.BooleanField(default=True)
    allow_draft_data_before_upload = models.BooleanField(default=True)
    pre_upload_access_mode = models.CharField(
        max_length=32,
        choices=PreUploadAccessMode.choices,
        default=PreUploadAccessMode.BLOCK,
    )
    notification_mode = models.CharField(
        max_length=32,
        choices=NotificationMode.choices,
        default=NotificationMode.AUDIT_ONLY,
    )
    notification_templates = models.JSONField(default=dict, blank=True)
    notify_on_data_saved = models.BooleanField(default=False)
    notify_on_paper_uploaded = models.BooleanField(default=True)
    notify_on_verified = models.BooleanField(default=True)
    notify_on_rejected = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Verified Consent Policy")
        verbose_name_plural = _("Verified Consent Policies")
        ordering = ["purpose__code", "document__code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("purpose", "document"),
                name="uq_verified_policy_purpose_document",
            )
        ]

    def clean(self) -> None:
        """Check basic timing consistency policy."""
        super().clean()
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValidationError(
                {"ends_at": "ends_at must be greater than or equal to starts_at."}
            )

    def save(self, *args, **kwargs):
        """Always run full_clean before writing policy to the database."""
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        purpose_label = str(getattr(self.purpose, "title", "") or self.purpose.code)
        document_label = str(getattr(self.document, "title", "") or self.document.code)
        mode_label = str(self.get_verification_mode_display() or self.verification_mode)
        return f"{purpose_label} · {document_label} · {mode_label}"


class VerifiedConsentFormPolicy(models.Model):
    """Per-form of override verified mode on top of the base policy flow."""

    class VerificationModeOverride(models.TextChoices):
        INHERIT = "inherit", _("Inherit from purpose/document policy")
        WEB_ONLY = VerifiedConsentPolicy.VerificationMode.WEB_ONLY, _("Web only")
        PAPER_REQUIRED = (
            VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
            _("Paper required"),
        )
        GOSKEY_REQUIRED = (
            VerifiedConsentPolicy.VerificationMode.GOSKEY_REQUIRED,
            _("Goskey required"),
        )
        PAPER_OR_GOSKEY = (
            VerifiedConsentPolicy.VerificationMode.PAPER_OR_GOSKEY,
            _("Paper or Goskey"),
        )

    class DraftDataPolicyOverride(models.TextChoices):
        INHERIT = "inherit", _("Inherit from purpose/document policy")
        ALLOW = "allow", _("Allow draft data before upload")
        FORBID = "forbid", _("Forbid draft data before upload")

    class PreUploadAccessModeOverride(models.TextChoices):
        INHERIT = "inherit", _("Inherit from purpose/document policy")
        BLOCK = VerifiedConsentPolicy.PreUploadAccessMode.BLOCK, _("Block")
        ALLOW_LIMITED = (
            VerifiedConsentPolicy.PreUploadAccessMode.ALLOW_LIMITED,
            _("Allow limited access"),
        )

    class NotificationModeOverride(models.TextChoices):
        INHERIT = "inherit", _("Inherit from purpose/document policy")
        AUDIT_ONLY = (
            VerifiedConsentPolicy.NotificationMode.AUDIT_ONLY,
            _("Audit log only"),
        )
        ASSIGNMENT_USERS = (
            VerifiedConsentPolicy.NotificationMode.ASSIGNMENT_USERS,
            _("Notify responsible users"),
        )

    purpose = models.ForeignKey(
        ConsentPurpose,
        on_delete=models.PROTECT,
        related_name="verified_form_policies",
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.PROTECT,
        related_name="verified_form_policies",
    )
    form_code = models.CharField(max_length=128)
    verification_mode_override = models.CharField(
        max_length=32,
        choices=VerificationModeOverride.choices,
        default=VerificationModeOverride.INHERIT,
    )
    draft_data_policy_override = models.CharField(
        max_length=32,
        choices=DraftDataPolicyOverride.choices,
        default=DraftDataPolicyOverride.INHERIT,
    )
    pre_upload_access_mode_override = models.CharField(
        max_length=32,
        choices=PreUploadAccessModeOverride.choices,
        default=PreUploadAccessModeOverride.INHERIT,
    )
    notification_mode_override = models.CharField(
        max_length=32,
        choices=NotificationModeOverride.choices,
        default=NotificationModeOverride.INHERIT,
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Verified Consent Form Policy")
        verbose_name_plural = _("Verified Consent Form Policies")
        ordering = ["form_code", "purpose__code", "document__code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("purpose", "document", "form_code"),
                name="uq_verified_form_policy_purpose_document_form",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if not (self.form_code or "").strip():
            raise ValidationError({"form_code": "form_code must not be empty."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        mode = str(
            self.get_verification_mode_override_display()
            or self.verification_mode_override
        )
        return f"{self.form_code} · {self.purpose.code} · {self.document.code} · {mode}"


class VerifiedConsentSubmission(models.Model):
    """Two-step intake for paper-based verified consent flows."""

    class WorkflowStatus(models.TextChoices):
        DRAFT_DATA = "draft_data", _("Draft data")
        AWAITING_PAPER_UPLOAD = "awaiting_paper_upload", _("Awaiting paper upload")
        PAPER_UPLOADED = "paper_uploaded", _("Paper uploaded")
        VERIFIED = "verified", _("Verified")
        REJECTED = "rejected", _("Rejected")

    purpose = models.ForeignKey(
        ConsentPurpose,
        on_delete=models.PROTECT,
        related_name="verified_submissions",
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.PROTECT,
        related_name="verified_submissions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_consent_submissions",
    )
    anonymous_token = models.CharField(max_length=128, blank=True)
    subject_ref = models.CharField(max_length=255, blank=True)
    form_code = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=32,
        choices=WorkflowStatus.choices,
        default=WorkflowStatus.DRAFT_DATA,
    )
    subject_data = models.JSONField(default=dict, blank=True)
    generated_blank_file = models.FileField(
        upload_to="django_consent_152fz/verified_blanks/",
        blank=True,
    )
    blank_generated_at = models.DateTimeField(null=True, blank=True)
    consent_record = models.OneToOneField(
        ConsentRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_submission",
    )
    latest_artifact = models.ForeignKey(
        "VerifiedConsentArtifact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    notes = models.TextField(blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Verified Consent Submission")
        verbose_name_plural = _("Verified Consent Submissions")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["purpose", "document", "status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["anonymous_token", "status"]),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            not self.user_id
            and not (self.anonymous_token or "").strip()
            and not (self.subject_ref or "").strip()
        ):
            raise ValidationError("user, anonymous_token or subject_ref must be set.")
        if self.consent_record_id and (
            self.consent_record.purpose_id != self.purpose_id
            or self.consent_record.document_revision.document_id != self.document_id
        ):
            raise ValidationError(
                {
                    "consent_record": (
                        "consent_record flow must match submission purpose/document."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        subject = (
            f"user:{self.user_id}"
            if self.user_id
            else (self.anonymous_token or self.subject_ref or "anonymous")
        )
        return f"{self.purpose.code}:{self.document.code}:{subject}:{self.status}"


class VerifiedConsentArtifact(models.Model):
    """Дополнительное доказательство verified-сценария.

    Артефакт всегда привязан к уже существующему `ConsentRecord` из `core`
    и хранит только method-specific данные: файл бумаги, внешний reference,
    дату фактической подписи субъекта и т.п.
    """

    class ArtifactType(models.TextChoices):
        """Evidence types supported by optional app."""

        PAPER_DOCUMENT = "paper_document", _("Paper document")
        EXTERNAL_SIGNATURE = "external_signature", _("External signature")

    consent_record = models.OneToOneField(
        ConsentRecord,
        on_delete=models.PROTECT,
        related_name="verified_artifact",
    )
    policy = models.ForeignKey(
        VerifiedConsentPolicy,
        on_delete=models.PROTECT,
        related_name="artifacts",
    )
    artifact_type = models.CharField(
        max_length=32,
        choices=ArtifactType.choices,
        default=ArtifactType.PAPER_DOCUMENT,
    )
    file = models.FileField(
        upload_to=_verified_artifact_upload_to,
        blank=True,
    )
    subject_signed_at = models.DateTimeField(null=True, blank=True)
    external_provider = models.CharField(max_length=64, blank=True)
    external_ref = models.CharField(max_length=128, blank=True)
    note = models.TextField(blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Verified Consent Artifact")
        verbose_name_plural = _("Verified Consent Artifacts")
        ordering = ["-created_at", "-id"]

    def clean(self) -> None:
        """Проверить, что артефакт согласован и с policy, и с core-record.

        Здесь намеренно проверяются сразу два уровня:
        1. Артефакт относится к тому же потоку `purpose + document`, что и record.
        2. Поля соответствуют выбранному `artifact_type`.
        """
        super().clean()

        errors: dict[str, str] = {}
        if (
            self.consent_record_id
            and self.policy_id
            and self.consent_record.purpose_id != self.policy.purpose_id
        ):
            errors["policy"] = "policy purpose must match consent_record purpose."
        if (
            self.consent_record_id
            and self.policy_id
            and self.consent_record.document_revision.document_id
            != self.policy.document_id
        ):
            errors["policy"] = "policy document must match consent_record document."

        if self.artifact_type == self.ArtifactType.PAPER_DOCUMENT:
            if not self.file:
                errors["file"] = "file is required for paper_document artifact."
            else:
                filename = str(self.file.name or "")
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ALLOWED_PAPER_FILE_EXTENSIONS:
                    errors["file"] = (
                        f"file extension must be one of: "
                        f"{', '.join(sorted(ALLOWED_PAPER_FILE_EXTENSIONS))}."
                    )
                file_size = int(getattr(self.file, "size", 0) or 0)
                if file_size <= 0:
                    errors["file"] = "file must not be empty."
                elif file_size > MAX_PAPER_FILE_SIZE_BYTES:
                    errors["file"] = (
                        f"file size must not exceed {MAX_PAPER_FILE_SIZE_BYTES} bytes."
                    )
            if self.external_provider:
                errors["external_provider"] = (
                    "external_provider must be empty for paper_document artifact."
                )
            if self.external_ref:
                errors["external_ref"] = (
                    "external_ref must be empty for paper_document artifact."
                )
        elif self.file:
            errors["file"] = "file must be empty for external_signature artifact."

        if self.artifact_type == self.ArtifactType.EXTERNAL_SIGNATURE:
            if not self.external_provider:
                errors["external_provider"] = (
                    "external_provider is required for external_signature artifact."
                )
            if not self.external_ref:
                errors["external_ref"] = (
                    "external_ref is required for external_signature artifact."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Do not allow saving an invalid verified artifact."""
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.consent_record_id}:{self.artifact_type}"
