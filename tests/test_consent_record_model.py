from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from django_consent_152fz.core.models import (
    ConsentPurpose,
    ConsentRecord,
    DocumentRevision,
    LegalDocument,
)


def _create_revision(
    *,
    purpose_code: str = "account_basic",
) -> tuple[ConsentPurpose, DocumentRevision]:
    purpose = ConsentPurpose.objects.create(
        code=purpose_code,
        title="Р РµРіРёСЃС‚СЂР°С†РёСЏ",
        fields_config=["email"],
    )
    document = LegalDocument.objects.create(
        code=f"{purpose_code}_doc",
        title="РЎРѕРіР»Р°СЃРёРµ",
    )
    revision = DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="РўРµРєСЃС‚ СЃРѕРіР»Р°СЃРёСЏ",
        fields_snapshot=["email"],
    )
    return purpose, revision


@pytest.mark.django_db
def test_consent_record_can_be_created_for_authenticated_user() -> None:
    User = get_user_model()
    user = User.objects.create_user(username="u1", password="x")
    purpose, revision = _create_revision()

    record = ConsentRecord.objects.create(
        user=user,
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    )

    assert record.user_id == user.id
    assert record.anonymous_token == ""
    assert record.status == ConsentRecord.Status.CURRENT


@pytest.mark.django_db
def test_consent_record_can_be_created_for_anonymous_subject() -> None:
    purpose, revision = _create_revision()

    record = ConsentRecord.objects.create(
        anonymous_token="anon-123",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
    )

    assert record.user_id is None
    assert record.anonymous_token == "anon-123"


@pytest.mark.django_db
def test_consent_record_requires_user_or_anonymous_token() -> None:
    purpose, revision = _create_revision()
    record = ConsentRecord(
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
    )

    with pytest.raises(ValidationError, match="Either user or anonymous_token"):
        record.full_clean()


@pytest.mark.django_db
def test_consent_record_save_rejects_empty_subject() -> None:
    purpose, revision = _create_revision()

    with pytest.raises(ValidationError, match="Either user or anonymous_token"):
        ConsentRecord.objects.create(
            anonymous_token="",
            purpose=purpose,
            document_revision=revision,
            fields_snapshot=["email"],
        )


@pytest.mark.django_db
def test_uploaded_paper_no_longer_requires_legacy_core_file() -> None:
    purpose, revision = _create_revision()
    record = ConsentRecord(
        anonymous_token="anon-1",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        confirmation_method=ConsentRecord.ConfirmationMethod.UPLOADED_PAPER,
    )

    record.full_clean()


@pytest.mark.django_db
def test_admin_confirmed_requires_confirmed_by() -> None:
    purpose, revision = _create_revision()
    record = ConsentRecord(
        anonymous_token="anon-1",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        confirmation_method=ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED,
    )

    with pytest.raises(ValidationError, match="confirmed_by"):
        record.full_clean()


@pytest.mark.django_db
def test_admin_confirmed_flow_supports_audit_fields() -> None:
    User = get_user_model()
    user = User.objects.create_user(username="admin", password="x")
    purpose, revision = _create_revision()

    record = ConsentRecord.objects.create(
        anonymous_token="anon-1",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        confirmation_method=ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED,
        confirmed_by=user,
        confirmed_at=timezone.now(),
        confirmation_note="РџРѕРґС‚РІРµСЂР¶РґРµРЅРѕ РІ РѕС„РёСЃРµ",
    )

    assert record.confirmed_by_id == user.id
    assert record.confirmed_at is not None


@pytest.mark.django_db
def test_consent_record_rejects_revision_from_other_purpose() -> None:
    _, revision = _create_revision(purpose_code="account_basic")
    other_purpose, _ = _create_revision(purpose_code="marketing")

    with pytest.raises(ValidationError, match="purpose_code must match"):
        ConsentRecord.objects.create(
            anonymous_token="anon-1",
            purpose=other_purpose,
            document_revision=revision,
            fields_snapshot=["email"],
        )


@pytest.mark.django_db
def test_consent_record_current_stream_is_unique_for_authenticated_subject() -> None:
    User = get_user_model()
    user = User.objects.create_user(username="uniq-auth", password="x")
    purpose, revision = _create_revision(purpose_code="unique_auth_subject")
    ConsentRecord.objects.create(
        user=user,
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )

    with pytest.raises(
        ValidationError, match="uq_consent_record_current_auth_subject_stream"
    ):
        ConsentRecord.objects.create(
            user=user,
            purpose=purpose,
            document_revision=revision,
            fields_snapshot=["email"],
            status=ConsentRecord.Status.CURRENT,
        )


@pytest.mark.django_db
def test_consent_record_current_stream_is_unique_for_anonymous_subject() -> None:
    purpose, revision = _create_revision(purpose_code="unique_anon_subject")
    ConsentRecord.objects.create(
        anonymous_token="anon-unique",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )

    with pytest.raises(
        ValidationError, match="uq_consent_record_current_anon_subject_stream"
    ):
        ConsentRecord.objects.create(
            anonymous_token="anon-unique",
            purpose=purpose,
            document_revision=revision,
            fields_snapshot=["email"],
            status=ConsentRecord.Status.CURRENT,
        )
