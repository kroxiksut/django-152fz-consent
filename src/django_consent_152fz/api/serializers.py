"""Serializers for the consent API layer."""

from __future__ import annotations

from django.urls import reverse

from django_consent_152fz import constants
from django_consent_152fz.core.models import ConsentRecord, DocumentRevision
from django_consent_152fz.core.services import build_audit_context
from django_consent_152fz.exceptions import ConsentError

from .dependencies import require_drf

require_drf()

from rest_framework import serializers  # noqa: E402


def _build_code_field(*, required: bool = True) -> serializers.CharField:
    """Build a standard code field used across API serializers."""
    return serializers.CharField(
        max_length=64,
        required=required,
        allow_blank=False,
        trim_whitespace=True,
    )


class AuditContextSerializer(serializers.Serializer):
    """Validate and normalize audit context payloads."""

    source = serializers.CharField(required=False, allow_blank=True, max_length=64)  # pyright: ignore[reportAssignmentType]
    ip_address = serializers.IPAddressField(required=False, allow_null=True)
    user_agent = serializers.CharField(required=False, allow_blank=True)
    locale = serializers.CharField(required=False, allow_blank=True, max_length=32)
    request_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    session_key_hash = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
    )
    occurred_at = serializers.DateTimeField(required=False)
    extra_meta = serializers.JSONField(required=False)
    client = serializers.JSONField(required=False)
    request = serializers.JSONField(required=False)
    client_hints = serializers.JSONField(required=False)
    integration = serializers.JSONField(required=False)
    custom = serializers.JSONField(required=False)

    def validate(self, attrs):
        try:
            return build_audit_context(audit_context=attrs)
        except ConsentError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AnonymousSubjectSerializer(serializers.Serializer):
    """Base serializer for request payloads that may carry an anonymous token."""

    anonymous_token = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=128,
        trim_whitespace=True,
    )


class RequirementsQuerySerializer(AnonymousSubjectSerializer):
    """Query parameters for the requirements endpoint."""

    pass


class ConsentStatusQuerySerializer(AnonymousSubjectSerializer):
    """Query parameters for the consent status endpoint."""

    purpose_code = _build_code_field()
    document_code = _build_code_field(required=False)


class ConsentStatusRequestSerializer(AnonymousSubjectSerializer):
    """Request body for the consent status endpoint."""

    purpose_code = _build_code_field()
    document_code = _build_code_field(required=False)


class PublicConsentStatusRequestSerializer(AnonymousSubjectSerializer):
    """Request body for the public consent status endpoint."""

    document_code = _build_code_field(required=False)


class AttachAnonymousConsentsRequestSerializer(AnonymousSubjectSerializer):
    """Request body for attaching anonymous consent records."""

    pass


class DocumentLookupSerializer(serializers.Serializer):
    """Query payload for resolving a document revision."""

    purpose_code = _build_code_field(required=False)


class ConsentActionRequestSerializer(AnonymousSubjectSerializer):
    """Common request body for consent actions."""

    purpose_code = _build_code_field()
    document_code = _build_code_field(required=False)
    audit_context = AuditContextSerializer(required=False)


class AcceptConsentRequestSerializer(ConsentActionRequestSerializer):
    """Request body for accepting consent."""

    subject_ref = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
        trim_whitespace=True,
    )
    fields_snapshot = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
    )


class WithdrawConsentRequestSerializer(ConsentActionRequestSerializer):
    """Request body for withdrawing consent."""

    pass


class VerifiedArtifactConfirmRequestSerializer(serializers.Serializer):
    """Request body for confirming a verified artifact."""

    confirmation_method = serializers.ChoiceField(
        choices=(
            ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
            ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED,
        ),
        required=False,
        default=ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
    )
    confirmation_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )
    audit_context = AuditContextSerializer(required=False)


class VerifiedArtifactRejectRequestSerializer(serializers.Serializer):
    """Request body for rejecting a verified artifact."""

    rejection_note = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=2000,
    )
    audit_context = AuditContextSerializer(required=False)


class VerifiedConsentSerializer(serializers.Serializer):
    """Summary of whether a verified consent policy applies."""

    required = serializers.BooleanField()  # pyright: ignore[reportAssignmentType]
    verification_mode = serializers.CharField(allow_null=True, read_only=True)


class VerifiedTransitionSerializer(serializers.Serializer):
    """Representation of the verified-transition decision."""

    enabled = serializers.BooleanField()
    status_code = serializers.ChoiceField(
        choices=constants.VERIFIED_TRANSITION_STATUSES,
        allow_null=True,
    )
    reason_code = serializers.ChoiceField(
        choices=constants.VERIFIED_TRANSITION_STATUSES,
        allow_null=True,
    )
    verification_mode = serializers.CharField()
    resolution_source = serializers.CharField()
    channel = serializers.CharField()
    form_code = serializers.CharField(allow_blank=True)
    submission_id = serializers.IntegerField(allow_null=True)
    consent_record_id = serializers.IntegerField(allow_null=True)


class LatestRevisionSerializer(serializers.Serializer):
    """Metadata for the latest document revision."""

    id = serializers.IntegerField()
    document_code = serializers.CharField()
    document_title = serializers.CharField()
    document_type = serializers.CharField()
    version = serializers.IntegerField()
    format = serializers.ChoiceField(choices=DocumentRevision.ContentFormat.choices)
    published_at = serializers.DateTimeField(allow_null=True)
    is_box_template = serializers.BooleanField()


class RequirementSerializer(serializers.Serializer):
    """Single consent requirement entry."""

    purpose_code = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    fields = serializers.ListField(  # pyright: ignore[reportAssignmentType]
        child=serializers.CharField(max_length=64),
        allow_empty=True,
    )
    withdraw_strategy = serializers.ChoiceField(choices=constants.WITHDRAW_STRATEGIES)
    reconsent_mode = serializers.ChoiceField(choices=constants.RECONSENT_MODES)
    document_code = serializers.CharField()
    document_title = serializers.CharField()
    document_type = serializers.CharField()
    verified_consent = VerifiedConsentSerializer()
    latest_revision = LatestRevisionSerializer()
    consent_status = serializers.ChoiceField(
        choices=constants.CONSENT_STATUSES,
        allow_null=True,
    )
    requires_consent = serializers.BooleanField()
    consent_required_reason = serializers.ChoiceField(
        choices=constants.CONSENT_REQUIRED_REASONS
    )
    is_applicable = serializers.BooleanField()
    verified_transition = VerifiedTransitionSerializer(required=False)


class RequirementsResponseSerializer(serializers.Serializer):
    """Response payload for the requirements endpoint."""

    provider_code = serializers.CharField()
    requirements = RequirementSerializer(many=True)


class ConsentStatusResponseSerializer(serializers.Serializer):
    """Response payload for the consent status endpoint."""

    purpose_code = serializers.CharField()
    document_code = serializers.CharField()
    record_id = serializers.IntegerField(allow_null=True)
    status = serializers.ChoiceField(
        choices=constants.CONSENT_STATUSES,
        allow_null=True,
    )
    requires_consent = serializers.BooleanField()
    consent_required_reason = serializers.ChoiceField(
        choices=constants.CONSENT_REQUIRED_REASONS
    )
    is_current = serializers.BooleanField()
    is_outdated = serializers.BooleanField()
    latest_revision_id = serializers.IntegerField(allow_null=True)
    record_revision_id = serializers.IntegerField(allow_null=True)
    reconsent_mode = serializers.ChoiceField(choices=constants.RECONSENT_MODES)
    access_restricted = serializers.BooleanField()
    is_applicable = serializers.BooleanField()
    verified_transition = VerifiedTransitionSerializer(required=False)


class ConsentRecordSerializer(serializers.ModelSerializer):
    """Serialized consent record for API responses."""

    purpose_code = serializers.CharField(source="purpose.code", read_only=True)
    document_code = serializers.CharField(
        source="document_revision.document.code",
        read_only=True,
    )
    document_title = serializers.CharField(
        source="document_revision.document.title",
        read_only=True,
    )
    document_type = serializers.CharField(
        source="document_revision.document.document_type",
        read_only=True,
    )
    document_revision_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ConsentRecord
        fields = (
            "id",
            "purpose_code",
            "document_code",
            "document_title",
            "document_type",
            "document_revision_id",
            "status",
            "confirmation_method",
            "fields_snapshot",
            "source",
            "locale",
            "confirmed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AcceptConsentResponseSerializer(ConsentRecordSerializer):
    """Response body for accept-consent requests."""

    pass


class WithdrawConsentResponseSerializer(ConsentRecordSerializer):
    """Response body for withdraw-consent requests."""

    pass


class DocumentRevisionSerializer(serializers.ModelSerializer):
    """Serialized document revision for API responses."""

    document_code = serializers.CharField(source="document.code", read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    document_type = serializers.CharField(
        source="document.document_type",
        read_only=True,
    )
    document_description = serializers.CharField(
        source="document.description",
        read_only=True,
    )
    content_url = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentRevision
        fields = (
            "id",
            "purpose_code",
            "document_code",
            "document_title",
            "document_type",
            "document_description",
            "version",
            "format",
            "content_text",
            "content_url",
            "pdf_url",
            "fields_snapshot",
            "meta",
            "is_box_template",
            "published_at",
        )
        read_only_fields = fields

    def get_content_url(self, obj: DocumentRevision) -> str | None:
        content_file = getattr(obj, "content_file", None)
        if not content_file:
            return None
        url = getattr(content_file, "url", None)
        if not url:
            return None
        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    def get_pdf_url(self, obj: DocumentRevision) -> str | None:
        request = self.context.get("request")
        if request is None:
            return None
        path = reverse(
            "django_consent_152fz:document_pdf",
            kwargs={
                "purpose_code": obj.purpose_code,
                "document_code": obj.document.code,
            },
        )
        return request.build_absolute_uri(path)
