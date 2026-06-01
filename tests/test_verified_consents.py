from __future__ import annotations

import importlib
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentEvent,
    ConsentPurpose,
    ConsentRecord,
    ModuleOperationAuditLog,
    PersonalDataManagerAssignment,
)
from django_consent_152fz.core.services import (
    accept_consent,
    anonymize_subject_consents,
    get_consent_status,
    get_current_requirements,
    publish_document_revision,
)
from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.verified_consents.models import (
    VerifiedConsentArtifact,
    VerifiedConsentFormPolicy,
    VerifiedConsentPolicy,
    VerifiedConsentSubmission,
)
from django_consent_152fz.verified_consents.services import (
    apply_verified_legacy_transition,
    confirm_verified_consent,
    generate_verified_consent_blank_file,
    get_verified_consent_policy,
    get_verified_transition_state,
    preview_verified_legacy_transition,
    reject_verified_consent,
    resolve_verified_consent_mode,
    save_verified_consent_submission_data,
    submit_verified_consent,
    submit_verified_consent_for_submission,
)


def _create_verified_policy(
    *,
    code: str = "special_category",
    verification_mode: str = VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
) -> tuple[ConsentPurpose, VerifiedConsentPolicy]:
    purpose = ConsentPurpose.objects.create(
        code=code,
        title=f"Purpose {code}",
        fields_config=["email"],
    )
    revision = publish_document_revision(
        document_code=f"{code}_document",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    policy = VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        verification_mode=verification_mode,
    )
    return purpose, policy


def _create_verified_operator(*, username: str):
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password="x",
        is_staff=True,
    )
    PersonalDataManagerAssignment.objects.create(
        user=user,
        can_handle_verified_consents=True,
        is_active=True,
    )
    return user


def _build_subject_context(*, subject_kind: str, code: str) -> dict[str, object]:
    if subject_kind == "authenticated":
        User = get_user_model()
        user = User.objects.create_user(
            username=f"{code}_user",
            password="x",
            is_active=True,
        )
        return {
            "user": user,
            "anonymous_token": None,
        }
    return {
        "user": None,
        "anonymous_token": f"anon-{code}",
    }


@pytest.mark.django_db
def test_verified_consent_policy_requires_valid_time_window() -> None:
    purpose, policy = _create_verified_policy(code="policy_window")
    policy.starts_at = timezone.now()
    policy.ends_at = policy.starts_at - timedelta(minutes=5)

    with pytest.raises(ValidationError, match="ends_at"):
        policy.save()

    purpose.refresh_from_db()


@pytest.mark.django_db
def test_verified_consent_artifact_requires_matching_flow() -> None:
    purpose, policy = _create_verified_policy(code="artifact_flow")
    other_purpose = ConsentPurpose.objects.create(
        code="artifact_flow_other",
        title="Other",
        fields_config=["email"],
    )
    other_revision = publish_document_revision(
        document_code="artifact_flow_other_document",
        purpose_code=other_purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    record = ConsentRecord.objects.create(
        anonymous_token="anon-flow",
        purpose=other_purpose,
        document_revision=other_revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.PENDING_CONFIRMATION,
        confirmation_method=ConsentRecord.ConfirmationMethod.UPLOADED_PAPER,
    )

    artifact = VerifiedConsentArtifact(
        consent_record=record,
        policy=policy,
        artifact_type=VerifiedConsentArtifact.ArtifactType.PAPER_DOCUMENT,
        file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 artifact content",
            content_type="application/pdf",
        ),
    )

    with pytest.raises(ValidationError, match="policy"):
        artifact.full_clean()


def test_verified_consents_migration_history_is_squashed_to_single_initial() -> None:
    migration_module = importlib.import_module(
        "django_consent_152fz.verified_consents.migrations.0001_initial"
    )
    dependencies = set(migration_module.Migration.dependencies)
    assert ("django_consent_152fz", "0001_initial") in dependencies

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(
            "django_consent_152fz.verified_consents.migrations."
            "0002_backfill_legacy_paper_artifacts"
        )


@pytest.mark.django_db
def test_get_verified_consent_policy_returns_policy_when_configured() -> None:
    purpose, policy = _create_verified_policy(code="feature_configured")

    resolved = get_verified_consent_policy(
        purpose_code=purpose.code,
        document_code=policy.document.code,
    )

    assert resolved is not None
    assert resolved.id == policy.id


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_submit_verified_consent_creates_pending_core_record_and_artifact() -> None:
    purpose, policy = _create_verified_policy(code="submit_verified")
    operator = _create_verified_operator(username="verified_operator_submit")

    record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-verified",
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 verified content",
            content_type="application/pdf",
        ),
        subject_signed_at=timezone.now(),
        audit_context={
            "source": "admin",
            "request": {"path": "/admin/verified/upload"},
            "client_hints": {"sec_ch_ua_platform": "Windows"},
            "upload_batch": "batch-1",
            "extra_meta": {"cookies": {"sessionid": "secret"}},
        },
        artifact_note="Uploaded paper",
        performed_by=operator,
    )

    artifact = record.verified_artifact
    event = record.events.get(event_type=ConsentEvent.EventType.PAPER_UPLOADED)

    assert record.status == ConsentRecord.Status.PENDING_CONFIRMATION
    assert artifact.policy_id == policy.id
    assert artifact.artifact_type == VerifiedConsentArtifact.ArtifactType.PAPER_DOCUMENT
    assert bool(artifact.file) is True
    assert event.source == "admin"
    assert event.actor_user_id == operator.id
    assert event.actor_type == ConsentEvent.ActorType.EMPLOYEE
    assert (
        event.payload["paper_document_hash"]
        == artifact.extra_meta["paper_document_hash"]
    )
    assert event.payload["paper_document_meta"]["name"] == "paper.pdf"
    assert event.extra_meta["request"]["path"] == "/admin/verified/upload"
    assert event.extra_meta["client_hints"]["sec_ch_ua_platform"] == "Windows"
    assert event.extra_meta["custom"]["upload_batch"] == "batch-1"
    assert "cookies" not in event.extra_meta["request"]


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_confirm_verified_consent_updates_core_record_and_event_payload() -> None:
    purpose, policy = _create_verified_policy(code="confirm_verified")
    subject_signed_at = timezone.now() - timedelta(days=1)
    operator = _create_verified_operator(username="verified_operator_confirm_submit")
    record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-confirm",
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 verified confirm",
            content_type="application/pdf",
        ),
        subject_signed_at=subject_signed_at,
        performed_by=operator,
    )
    employee = _create_verified_operator(username="verified_employee")

    confirmed = confirm_verified_consent(
        consent_record=record,
        confirmed_by=employee,
        confirmation_note="Confirmed from office",
        audit_context={
            "integration": {"provider": "backoffice", "provider_ref": "TICKET-7"},
            "approval_ticket": "A-1",
            "extra_meta": {"csrf_token": "secret"},
        },
    )

    event = confirmed.events.get(event_type=ConsentEvent.EventType.EMPLOYEE_CONFIRMED)
    assert confirmed.status == ConsentRecord.Status.CURRENT
    assert confirmed.confirmed_by_id == employee.id
    assert event.actor_user_id == employee.id
    assert event.payload["artifact_id"] == confirmed.verified_artifact.id
    assert event.payload["subject_signed_at"] == subject_signed_at.isoformat()
    assert (
        event.payload["paper_document_hash"]
        == confirmed.verified_artifact.extra_meta["paper_document_hash"]
    )
    assert event.payload["confirmation_note"] == "Confirmed from office"
    assert event.extra_meta["integration"]["provider"] == "backoffice"
    assert event.extra_meta["integration"]["provider_ref"] == "TICKET-7"
    assert event.extra_meta["custom"]["approval_ticket"] == "A-1"
    assert "csrf_token" not in event.extra_meta
    transition = get_verified_transition_state(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-confirm",
        verification_context={"channel": "self_service"},
    )
    assert transition["status_code"] == constants.VERIFIED_TRANSITION_STATUS_VERIFIED
    assert transition["reason_code"] == constants.VERIFIED_TRANSITION_STATUS_VERIFIED


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_confirm_verified_consent_can_withdraw_legacy_web_after_paper_confirmation() -> (
    None
):
    purpose, policy = _create_verified_policy(code="confirm_verified_withdraw_after")
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.WEB_ONLY
    policy.save(update_fields=["verification_mode"])

    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-confirm-withdraw-after",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED
    policy.legacy_web_consent_policy = (
        VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_AFTER_PAPER_CONFIRMED
    )
    policy.save(update_fields=["verification_mode", "legacy_web_consent_policy"])
    legacy_record = ConsentRecord.objects.get(
        purpose=purpose,
        anonymous_token="anon-confirm-withdraw-after",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )

    operator = _create_verified_operator(
        username="verified_operator_confirm_withdraw_after"
    )
    pending_record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-confirm-withdraw-after",
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 verified confirm withdraw-after",
            content_type="application/pdf",
        ),
        performed_by=operator,
    )
    employee = _create_verified_operator(username="verified_employee_withdraw_after")

    confirmed = confirm_verified_consent(
        consent_record=pending_record,
        confirmed_by=employee,
        confirmation_note="Confirmed from office",
    )

    legacy_record.refresh_from_db()
    assert confirmed.status == ConsentRecord.Status.CURRENT
    assert legacy_record.status == ConsentRecord.Status.WITHDRAWN
    withdrawn_event = legacy_record.events.get(
        event_type=ConsentEvent.EventType.WITHDRAWN
    )
    assert withdrawn_event.payload["reason"] == "verified_policy_withdraw_web_now"
    assert withdrawn_event.payload["transition_mode"] == "withdraw_web_now"


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_reject_verified_consent_updates_core_record_and_event_payload() -> None:
    purpose, policy = _create_verified_policy(code="reject_verified")
    subject_signed_at = timezone.now() - timedelta(hours=3)
    operator = _create_verified_operator(username="verified_operator_reject_submit")
    record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-reject",
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 verified reject",
            content_type="application/pdf",
        ),
        subject_signed_at=subject_signed_at,
        performed_by=operator,
    )
    User = get_user_model()
    admin = User.objects.create_user(
        username="verified_admin",
        password="x",
        is_staff=True,
        is_superuser=True,
    )

    rejected = reject_verified_consent(
        consent_record=record,
        rejected_by=admin,
        actor_type=ConsentEvent.ActorType.ADMIN,
        rejection_note="Rejected due to invalid scan",
    )

    event = rejected.events.get(event_type=ConsentEvent.EventType.REJECTED)
    assert rejected.status == ConsentRecord.Status.REJECTED
    assert rejected.confirmed_by_id == admin.id
    assert event.actor_user_id == admin.id
    assert event.actor_type == ConsentEvent.ActorType.ADMIN
    assert event.payload["artifact_id"] == rejected.verified_artifact.id
    assert event.payload["subject_signed_at"] == subject_signed_at.isoformat()
    assert event.payload["confirmation_note"] == "Rejected due to invalid scan"
    assert (
        event.payload["paper_document_hash"]
        == rejected.verified_artifact.extra_meta["paper_document_hash"]
    )
    transition = get_verified_transition_state(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-reject",
        verification_context={"channel": "self_service"},
    )
    assert transition["status_code"] == constants.VERIFIED_TRANSITION_STATUS_REJECTED
    assert transition["reason_code"] == constants.VERIFIED_TRANSITION_STATUS_REJECTED


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_anonymize_subject_consents_scrubs_verified_artifact_if_present() -> None:
    purpose, policy = _create_verified_policy(code="anonymize_verified")
    operator = _create_verified_operator(username="verified_operator_anonymize")
    record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-verified-anonymize",
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 verified anonymize",
            content_type="application/pdf",
        ),
        subject_signed_at=timezone.now(),
        performed_by=operator,
    )
    artifact_id = record.verified_artifact.pk

    anonymize_subject_consents(
        anonymous_token="anon-verified-anonymize",
        audit_context={"source": "verified_cleanup"},
    )

    record.refresh_from_db()

    assert record.status == ConsentRecord.Status.DELETED
    assert record.events.filter(event_type=ConsentEvent.EventType.ANONYMIZED).exists()
    assert not VerifiedConsentArtifact.objects.filter(pk=artifact_id).exists()


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_submit_verified_consent_rejects_unsupported_file_extension() -> None:
    purpose, policy = _create_verified_policy(code="submit_invalid_extension")
    operator = _create_verified_operator(username="verified_operator_bad_ext")

    with pytest.raises(ConsentError, match="Unsupported paper_file extension"):
        submit_verified_consent(
            purpose_code=purpose.code,
            document_code=policy.document.code,
            anonymous_token="anon-invalid-extension",
            paper_file=SimpleUploadedFile(
                "paper.txt",
                b"not a paper scan",
                content_type="text/plain",
            ),
            performed_by=operator,
        )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_reject_verified_consent_requires_rejection_note() -> None:
    purpose, policy = _create_verified_policy(code="reject_requires_note")
    operator = _create_verified_operator(username="verified_operator_reject_note")
    record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-reject-note",
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 verified reject note",
            content_type="application/pdf",
        ),
        performed_by=operator,
    )

    with pytest.raises(ConsentError, match="rejection_note is required"):
        reject_verified_consent(
            consent_record=record,
            rejected_by=operator,
            rejection_note="",
        )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_accept_consent_rejects_plain_web_flow_when_verified_policy_is_active() -> None:
    purpose, policy = _create_verified_policy(code="plain_web_rejected")

    with pytest.raises(ConsentError, match="requires verified confirmation"):
        accept_consent(
            purpose_code=purpose.code,
            document_code=policy.document.code,
            anonymous_token="anon-plain-web",
            confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
        )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_get_current_requirements_includes_verified_consent_block() -> None:
    purpose, policy = _create_verified_policy(code="requirements_verified")

    requirements = get_current_requirements(anonymous_token="anon-requirements")

    entry = next(
        item
        for item in requirements["requirements"]
        if item["purpose_code"] == purpose.code
        and item["document_code"] == policy.document.code
    )
    assert entry["verified_consent"] == {
        "required": True,
        "verification_mode": VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
    }


@pytest.mark.django_db
def test_get_consent_status_marks_legacy_current_record_as_outdated_when_policy_enabled() -> (
    None
):
    purpose = ConsentPurpose.objects.create(
        code="legacy_verified",
        title="Purpose legacy_verified",
        fields_config=["email"],
    )
    revision = publish_document_revision(
        document_code="legacy_verified_document",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code=revision.document.code,
        anonymous_token="anon-legacy",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
    )
    status = get_consent_status(
        purpose_code=purpose.code,
        document_code=revision.document.code,
        anonymous_token="anon-legacy",
    )
    legacy_record = ConsentRecord.objects.get(
        purpose=purpose,
        anonymous_token="anon-legacy",
    )

    assert status["status"] == ConsentRecord.Status.OUTDATED
    assert status["requires_consent"] is True
    assert legacy_record.status == ConsentRecord.Status.OUTDATED
    outdated_event = legacy_record.events.get(
        event_type=ConsentEvent.EventType.OUTDATED
    )
    assert outdated_event.payload["reason"] == "verified_policy_mark_web_outdated"
    assert outdated_event.payload["transition_mode"] == "mark_web_outdated"

    repeated_status = get_consent_status(
        purpose_code=purpose.code,
        document_code=revision.document.code,
        anonymous_token="anon-legacy",
    )
    assert repeated_status["status"] == ConsentRecord.Status.OUTDATED
    assert (
        legacy_record.events.filter(event_type=ConsentEvent.EventType.OUTDATED).count()
        == 1
    )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_resolve_verified_mode_uses_form_override_for_form_channel() -> None:
    purpose, policy = _create_verified_policy(code="form_override_case")
    from django_consent_152fz.verified_consents.models import VerifiedConsentFormPolicy

    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=policy.document,
        form_code="demo.contact",
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.WEB_ONLY
        ),
    )

    resolved = resolve_verified_consent_mode(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        channel="form",
        form_code="demo.contact",
    )

    assert resolved["required"] is False
    assert resolved["verification_mode"] == "web_only"
    assert resolved["resolution_source"] == "form_override"


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_resolve_verified_mode_skips_forms_only_policy_for_self_service() -> None:
    purpose, policy = _create_verified_policy(code="forms_only_scope")
    policy.flow_scope = VerifiedConsentPolicy.FlowScope.FORMS_ONLY
    policy.save(update_fields=["flow_scope"])

    resolved = resolve_verified_consent_mode(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        channel="self_service",
    )

    assert resolved["required"] is False
    assert resolved["verification_mode"] == "web_only"
    assert resolved["resolution_source"] == "policy_scope_skipped"


@pytest.mark.django_db
def test_get_consent_status_can_keep_legacy_web_current_when_policy_requests_it() -> (
    None
):
    purpose = ConsentPurpose.objects.create(
        code="legacy_keep_current",
        title="Purpose legacy_keep_current",
        fields_config=["email"],
    )
    revision = publish_document_revision(
        document_code="legacy_keep_current_document",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code=revision.document.code,
        anonymous_token="anon-legacy-keep-current",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
        legacy_web_consent_policy=(
            VerifiedConsentPolicy.LegacyWebConsentPolicy.KEEP_WEB_CURRENT
        ),
    )
    status = get_consent_status(
        purpose_code=purpose.code,
        document_code=revision.document.code,
        anonymous_token="anon-legacy-keep-current",
        verification_context={"channel": "self_service"},
    )

    assert status["status"] == ConsentRecord.Status.CURRENT
    assert status["requires_consent"] is False


@pytest.mark.django_db
def test_get_consent_status_withdraws_legacy_web_record_immediately_when_policy_requests() -> (
    None
):
    purpose = ConsentPurpose.objects.create(
        code="legacy_withdraw_now",
        title="Purpose legacy_withdraw_now",
        fields_config=["email"],
    )
    revision = publish_document_revision(
        document_code="legacy_withdraw_now_document",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code=revision.document.code,
        anonymous_token="anon-legacy-withdraw",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
        legacy_web_consent_policy=(
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_WEB_NOW
        ),
    )

    status = get_consent_status(
        purpose_code=purpose.code,
        document_code=revision.document.code,
        anonymous_token="anon-legacy-withdraw",
    )
    legacy_record = ConsentRecord.objects.get(
        purpose=purpose,
        anonymous_token="anon-legacy-withdraw",
    )

    assert status["status"] == ConsentRecord.Status.WITHDRAWN
    assert status["requires_consent"] is True
    assert legacy_record.status == ConsentRecord.Status.WITHDRAWN
    withdrawn_event = legacy_record.events.get(
        event_type=ConsentEvent.EventType.WITHDRAWN
    )
    assert withdrawn_event.payload["reason"] == "verified_policy_withdraw_web_now"
    assert withdrawn_event.payload["transition_mode"] == "withdraw_web_now"


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_submit_verified_consent_allows_subject_self_service_without_staff_actor() -> (
    None
):
    purpose, policy = _create_verified_policy(code="subject_self_submit")
    User = get_user_model()
    subject = User.objects.create_user(
        username="subject-self-submit",
        password="x",
        is_active=True,
    )

    record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        user=subject,
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 subject self upload",
            content_type="application/pdf",
        ),
        verification_context={"channel": "self_service"},
    )

    event = record.events.get(event_type=ConsentEvent.EventType.PAPER_UPLOADED)
    assert event.actor_type == ConsentEvent.ActorType.SUBJECT
    assert event.actor_user_id == subject.id


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_submit_verified_consent_rejects_subject_self_service_when_disabled() -> None:
    purpose, policy = _create_verified_policy(code="subject_self_submit_off")
    policy.allow_subject_self_upload = False
    policy.save(update_fields=["allow_subject_self_upload"])
    User = get_user_model()
    subject = User.objects.create_user(
        username="subject-self-submit-off",
        password="x",
        is_active=True,
    )

    with pytest.raises(
        ConsentError,
        match="requires active staff user",
    ):
        submit_verified_consent(
            purpose_code=purpose.code,
            document_code=policy.document.code,
            user=subject,
            paper_file=SimpleUploadedFile(
                "paper.pdf",
                b"%PDF-1.4 subject self upload denied",
                content_type="application/pdf",
            ),
            verification_context={"channel": "self_service"},
        )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_save_verified_submission_data_creates_awaiting_upload_submission() -> None:
    purpose, policy = _create_verified_policy(code="submission_stage1")

    submission = save_verified_consent_submission_data(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-stage1",
        subject_data={"full_name": "Иван Иванов", "email": "ivan@example.com"},
        verification_context={"channel": "self_service"},
    )

    assert (
        submission.status
        == VerifiedConsentSubmission.WorkflowStatus.AWAITING_PAPER_UPLOAD
    )
    assert submission.generated_blank_file
    assert submission.blank_generated_at is not None

    transition = get_verified_transition_state(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-stage1",
        verification_context={"channel": "self_service"},
    )
    assert transition["enabled"] is True
    assert (
        transition["status_code"]
        == constants.VERIFIED_TRANSITION_STATUS_AWAITING_UPLOAD
    )
    assert (
        transition["reason_code"]
        == constants.VERIFIED_TRANSITION_STATUS_AWAITING_UPLOAD
    )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_save_verified_submission_data_respects_policy_forbid_draft() -> None:
    purpose, policy = _create_verified_policy(code="submission_stage1_forbid")
    policy.allow_draft_data_before_upload = False
    policy.save(update_fields=["allow_draft_data_before_upload"])

    with pytest.raises(
        ConsentError, match="Draft data save before paper upload is disabled"
    ):
        save_verified_consent_submission_data(
            purpose_code=purpose.code,
            document_code=policy.document.code,
            anonymous_token="anon-stage1-forbid",
            subject_data={"full_name": "Иван Иванов"},
            verification_context={"channel": "self_service"},
        )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_submit_verified_consent_for_submission_creates_record_and_updates_status() -> (
    None
):
    purpose, policy = _create_verified_policy(code="submission_stage2")
    submission = save_verified_consent_submission_data(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-stage2",
        subject_data={"full_name": "Иван Иванов", "email": "ivan@example.com"},
        verification_context={"channel": "self_service"},
    )

    record = submit_verified_consent_for_submission(
        submission=submission,
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 stage2 upload",
            content_type="application/pdf",
        ),
    )

    submission.refresh_from_db()
    assert submission.status == VerifiedConsentSubmission.WorkflowStatus.PAPER_UPLOADED
    assert submission.consent_record_id == record.id
    assert submission.latest_artifact_id == record.verified_artifact.id

    transition = get_verified_transition_state(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-stage2",
        verification_context={"channel": "self_service"},
    )
    assert transition["status_code"] == (
        constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION
    )
    assert transition["reason_code"] == (
        constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION
    )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_verified_transition_state_returns_paper_required_when_no_submission_exists() -> (
    None
):
    purpose, policy = _create_verified_policy(code="transition_initial_state")

    transition = get_verified_transition_state(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-transition-initial",
        verification_context={"channel": "form", "form_code": "demo.form"},
    )

    assert transition["enabled"] is True
    assert (
        transition["status_code"] == constants.VERIFIED_TRANSITION_STATUS_PAPER_REQUIRED
    )
    assert (
        transition["reason_code"] == constants.VERIFIED_TRANSITION_STATUS_PAPER_REQUIRED
    )

    status = get_consent_status(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-transition-initial",
        verification_context={"channel": "form", "form_code": "demo.form"},
    )
    assert status["verified_transition"]["status_code"] == (
        constants.VERIFIED_TRANSITION_STATUS_PAPER_REQUIRED
    )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_generate_verified_blank_file_regenerates_pdf_file() -> None:
    purpose, policy = _create_verified_policy(code="submission_blank_pdf")
    submission = save_verified_consent_submission_data(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-blank",
        subject_data={"full_name": "Иван Иванов", "email": "ivan@example.com"},
        verification_context={"channel": "self_service"},
    )
    first_name = str(submission.generated_blank_file.name)

    regenerated_name = generate_verified_consent_blank_file(
        submission=submission,
        regenerate=True,
    )
    submission.refresh_from_db()

    assert regenerated_name
    assert str(submission.generated_blank_file.name)
    assert str(submission.generated_blank_file.name).endswith(".pdf")
    assert first_name != str(submission.generated_blank_file.name)


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_verified_submission_notifications_log_for_assignment_users() -> None:
    purpose, policy = _create_verified_policy(code="submission_notify")
    policy.notification_mode = VerifiedConsentPolicy.NotificationMode.ASSIGNMENT_USERS
    policy.notification_templates = {
        "verified": "Submission {submission_id} verified for {purpose_code}/{document_code}",
    }
    policy.notify_on_data_saved = True
    policy.notify_on_paper_uploaded = True
    policy.notify_on_verified = True
    policy.save(
        update_fields=[
            "notification_mode",
            "notification_templates",
            "notify_on_data_saved",
            "notify_on_paper_uploaded",
            "notify_on_verified",
        ]
    )
    operator = _create_verified_operator(username="verified_notify_operator")

    submission = save_verified_consent_submission_data(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-notify",
        subject_data={"full_name": "Иван Иванов"},
        verification_context={"channel": "self_service"},
    )
    submit_verified_consent_for_submission(
        submission=submission,
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 notify upload",
            content_type="application/pdf",
        ),
    )
    confirm_verified_consent(
        consent_record=submission.consent_record,
        confirmed_by=operator,
        confirmation_method=ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
    )

    audit_rows = ModuleOperationAuditLog.objects.filter(
        operation_code__startswith="service.verified.notification."
    )
    assert audit_rows.count() >= 3
    last_payload = dict(audit_rows.order_by("-id").first().payload)
    assert operator.id in list(last_payload.get("recipients_user_ids") or [])
    assert "verified for" in str(last_payload.get("message") or "")


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_preview_verified_legacy_transition_counts_candidates() -> None:
    purpose, policy = _create_verified_policy(code="transition_preview")
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.WEB_ONLY
    policy.save(update_fields=["verification_mode"])

    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-transition-preview-1",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-transition-preview-2",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED
    policy.legacy_web_consent_policy = (
        VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED
    )
    policy.save(update_fields=["verification_mode", "legacy_web_consent_policy"])

    summary = preview_verified_legacy_transition(
        purpose_code=purpose.code,
        document_code=policy.document.code,
    )

    assert summary["transition_mode"] == "mark_web_outdated"
    assert summary["affected_candidates"] == 2
    assert summary["would_change_immediately"] == 2
    assert summary["would_defer_until_confirmation"] == 0
    assert len(summary["candidate_ids"]) == 2


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_apply_verified_legacy_transition_supports_dry_run_and_batch_apply() -> None:
    purpose, policy = _create_verified_policy(code="transition_apply")
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.WEB_ONLY
    policy.save(update_fields=["verification_mode"])

    record_1 = accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-transition-apply-1",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    record_2 = accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-transition-apply-2",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED
    policy.legacy_web_consent_policy = (
        VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED
    )
    policy.save(update_fields=["verification_mode", "legacy_web_consent_policy"])

    dry_summary = apply_verified_legacy_transition(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        dry_run=True,
        batch_size=1,
        source="tests.transition.apply",
    )
    record_1.refresh_from_db()
    record_2.refresh_from_db()
    assert dry_summary["dry_run"] is True
    assert dry_summary["would_change_immediately"] == 2
    assert dry_summary["changed_records"] == 0
    assert record_1.status == ConsentRecord.Status.CURRENT
    assert record_2.status == ConsentRecord.Status.CURRENT
    assert ModuleOperationAuditLog.objects.filter(
        operation_code="service.verified.apply_legacy_transition",
        source="tests.transition.apply",
        status=ModuleOperationAuditLog.Status.DRY_RUN,
    ).exists()

    stdout = StringIO()
    call_command(
        "transition_152fz_verified_legacy_web",
        f"--purpose-code={purpose.code}",
        f"--document-code={policy.document.code}",
        "--channel=runtime",
        "--batch-size=1",
        "--apply",
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert "Apply completed" in output

    record_1.refresh_from_db()
    record_2.refresh_from_db()
    assert record_1.status == ConsentRecord.Status.OUTDATED
    assert record_2.status == ConsentRecord.Status.OUTDATED
    assert record_1.events.filter(
        event_type=ConsentEvent.EventType.OUTDATED,
        payload__reason="verified_policy_mark_web_outdated",
    ).exists()
    assert record_2.events.filter(
        event_type=ConsentEvent.EventType.OUTDATED,
        payload__reason="verified_policy_mark_web_outdated",
    ).exists()
    assert (
        ModuleOperationAuditLog.objects.filter(
            operation_code="service.verified.apply_legacy_transition.batch",
            source="management.transition_152fz_verified_legacy_web",
        ).count()
        >= 2
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("subject_kind", "transition_mode", "expected_status", "expected_requires_consent"),
    [
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.KEEP_WEB_CURRENT,
            ConsentRecord.Status.CURRENT,
            False,
        ),
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED,
            ConsentRecord.Status.OUTDATED,
            True,
        ),
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_WEB_NOW,
            ConsentRecord.Status.WITHDRAWN,
            True,
        ),
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_AFTER_PAPER_CONFIRMED,
            ConsentRecord.Status.CURRENT,
            False,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.KEEP_WEB_CURRENT,
            ConsentRecord.Status.CURRENT,
            False,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED,
            ConsentRecord.Status.OUTDATED,
            True,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_WEB_NOW,
            ConsentRecord.Status.WITHDRAWN,
            True,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_AFTER_PAPER_CONFIRMED,
            ConsentRecord.Status.CURRENT,
            False,
        ),
    ],
)
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_transition_matrix_self_service_all_modes_for_both_subject_types(
    *,
    subject_kind: str,
    transition_mode: str,
    expected_status: str,
    expected_requires_consent: bool,
) -> None:
    code = f"matrix_self_{subject_kind}_{transition_mode}"
    purpose, policy = _create_verified_policy(code=code)
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.WEB_ONLY
    policy.save(update_fields=["verification_mode"])

    subject = _build_subject_context(subject_kind=subject_kind, code=code)
    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        user=subject["user"],
        anonymous_token=subject["anonymous_token"],
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
        verification_context={"channel": "self_service"},
    )
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED
    policy.legacy_web_consent_policy = transition_mode
    policy.save(update_fields=["verification_mode", "legacy_web_consent_policy"])

    status = get_consent_status(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        user=subject["user"],
        anonymous_token=subject["anonymous_token"],
        verification_context={"channel": "self_service"},
    )

    assert status["status"] == expected_status
    assert status["requires_consent"] is expected_requires_consent


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("subject_kind", "transition_mode", "expected_status", "expected_requires_consent"),
    [
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.KEEP_WEB_CURRENT,
            ConsentRecord.Status.CURRENT,
            False,
        ),
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED,
            ConsentRecord.Status.OUTDATED,
            True,
        ),
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_WEB_NOW,
            ConsentRecord.Status.WITHDRAWN,
            True,
        ),
        (
            "anonymous",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_AFTER_PAPER_CONFIRMED,
            ConsentRecord.Status.CURRENT,
            False,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.KEEP_WEB_CURRENT,
            ConsentRecord.Status.CURRENT,
            False,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED,
            ConsentRecord.Status.OUTDATED,
            True,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_WEB_NOW,
            ConsentRecord.Status.WITHDRAWN,
            True,
        ),
        (
            "authenticated",
            VerifiedConsentPolicy.LegacyWebConsentPolicy.WITHDRAW_AFTER_PAPER_CONFIRMED,
            ConsentRecord.Status.CURRENT,
            False,
        ),
    ],
)
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_transition_matrix_form_bound_all_modes_for_both_subject_types(
    *,
    subject_kind: str,
    transition_mode: str,
    expected_status: str,
    expected_requires_consent: bool,
) -> None:
    code = f"matrix_form_{subject_kind}_{transition_mode}"
    purpose, policy = _create_verified_policy(code=code)
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.WEB_ONLY
    policy.legacy_web_consent_policy = transition_mode
    policy.save(update_fields=["verification_mode", "legacy_web_consent_policy"])
    form_code = "demo.enroll"
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=policy.document,
        form_code=form_code,
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.WEB_ONLY
        ),
    )

    subject = _build_subject_context(subject_kind=subject_kind, code=code)
    form_context = {"channel": "form", "form_code": form_code}
    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        user=subject["user"],
        anonymous_token=subject["anonymous_token"],
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
        verification_context=form_context,
    )
    form_policy = VerifiedConsentFormPolicy.objects.get(
        purpose=purpose,
        document=policy.document,
        form_code=form_code,
    )
    form_policy.verification_mode_override = (
        VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED
    )
    form_policy.save(update_fields=["verification_mode_override"])

    status = get_consent_status(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        user=subject["user"],
        anonymous_token=subject["anonymous_token"],
        verification_context=form_context,
    )

    assert status["status"] == expected_status
    assert status["requires_consent"] is expected_requires_consent


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={"enable_verified_consents": True})
def test_form_bound_transition_does_not_regress_other_web_only_forms() -> None:
    code = "matrix_form_web_only_regression"
    purpose, policy = _create_verified_policy(code=code)
    policy.verification_mode = VerifiedConsentPolicy.VerificationMode.WEB_ONLY
    policy.legacy_web_consent_policy = (
        VerifiedConsentPolicy.LegacyWebConsentPolicy.MARK_WEB_OUTDATED
    )
    policy.save(update_fields=["verification_mode", "legacy_web_consent_policy"])
    target_form_code = "demo.target"
    untouched_form_code = "demo.untouched"
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=policy.document,
        form_code=target_form_code,
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.WEB_ONLY
        ),
    )
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=policy.document,
        form_code=untouched_form_code,
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.WEB_ONLY
        ),
    )

    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-matrix-form-untouched",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
        verification_context={"channel": "form", "form_code": untouched_form_code},
    )

    target_policy = VerifiedConsentFormPolicy.objects.get(
        purpose=purpose,
        document=policy.document,
        form_code=target_form_code,
    )
    target_policy.verification_mode_override = (
        VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED
    )
    target_policy.save(update_fields=["verification_mode_override"])

    untouched_status = get_consent_status(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-matrix-form-untouched",
        verification_context={"channel": "form", "form_code": untouched_form_code},
    )

    assert untouched_status["status"] == ConsentRecord.Status.CURRENT
    assert untouched_status["requires_consent"] is False
    assert untouched_status["verified_transition"]["enabled"] is False
