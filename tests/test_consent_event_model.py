from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from django_consent_152fz.core.models import (
    ConsentEvent,
    ConsentPurpose,
    ConsentRecord,
    DocumentRevision,
    LegalDocument,
)


def _create_consent_record() -> ConsentRecord:
    purpose = ConsentPurpose.objects.create(
        code="account_basic",
        title="Регистрация",
        fields_config=["email"],
    )
    document = LegalDocument.objects.create(
        code="account_basic_doc",
        title="Согласие",
    )
    revision = DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="Текст согласия",
        fields_snapshot=["email"],
    )
    return ConsentRecord.objects.create(
        anonymous_token="anon-1",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
    )


@pytest.mark.parametrize(
    "event_type",
    [
        ConsentEvent.EventType.GIVEN,
        ConsentEvent.EventType.WITHDRAWN,
        ConsentEvent.EventType.OUTDATED,
        ConsentEvent.EventType.PAPER_UPLOADED,
        ConsentEvent.EventType.REJECTED,
    ],
)
@pytest.mark.django_db
def test_consent_event_can_be_created_with_basic_event_types(event_type: str) -> None:
    record = _create_consent_record()

    event = ConsentEvent.objects.create(
        consent_record=record,
        event_type=event_type,
        payload={"reason": "test"},
    )

    assert event.pk is not None
    assert event.event_type == event_type


@pytest.mark.django_db
def test_consent_event_stores_extended_audit_context() -> None:
    record = _create_consent_record()
    User = get_user_model()
    actor = User.objects.create_user(username="auditor", password="x", is_staff=True)

    event = ConsentEvent.objects.create(
        consent_record=record,
        event_type=ConsentEvent.EventType.GIVEN,
        actor_user=actor,
        actor_type=ConsentEvent.ActorType.SUBJECT,
        source="ui",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0",
        locale="ru-RU",
        request_id="req-1",
        session_key_hash="hash-1",
        payload={"reason": "test"},
        extra_meta={"client": {"os_family": "Windows"}},
    )

    assert event.actor_user_id == actor.pk
    assert event.actor_type == ConsentEvent.ActorType.SUBJECT
    assert event.source == "ui"
    assert event.request_id == "req-1"
    assert event.session_key_hash == "hash-1"
    assert event.extra_meta["client"]["os_family"] == "Windows"
    assert event.occurred_at is not None


@pytest.mark.django_db
def test_consent_event_requires_actor_user_for_employee_and_admin_events() -> None:
    record = _create_consent_record()

    with pytest.raises(ValidationError, match="actor_user"):
        ConsentEvent.objects.create(
            consent_record=record,
            event_type=ConsentEvent.EventType.ADMIN_CONFIRMED,
            actor_type=ConsentEvent.ActorType.ADMIN,
        )


@pytest.mark.django_db
def test_consent_event_system_actor_must_not_have_actor_user() -> None:
    record = _create_consent_record()
    User = get_user_model()
    actor = User.objects.create_user(
        username="system_like",
        password="x",
        is_staff=True,
    )

    with pytest.raises(ValidationError, match="actor_user"):
        ConsentEvent.objects.create(
            consent_record=record,
            event_type=ConsentEvent.EventType.OUTDATED,
            actor_user=actor,
            actor_type=ConsentEvent.ActorType.SYSTEM,
        )


@pytest.mark.django_db
def test_consent_event_rejects_unknown_event_type() -> None:
    record = _create_consent_record()

    with pytest.raises(ValidationError, match="event_type"):
        ConsentEvent.objects.create(
            consent_record=record,
            event_type="unknown_type",
            payload={},
        )


@pytest.mark.django_db
def test_consent_event_instance_update_is_forbidden() -> None:
    record = _create_consent_record()
    event = ConsentEvent.objects.create(
        consent_record=record,
        event_type=ConsentEvent.EventType.GIVEN,
        payload={"v": 1},
    )

    event.payload = {"v": 2}
    with pytest.raises(ValidationError, match="immutable"):
        event.save()


@pytest.mark.django_db
def test_consent_event_instance_delete_is_forbidden() -> None:
    record = _create_consent_record()
    event = ConsentEvent.objects.create(
        consent_record=record,
        event_type=ConsentEvent.EventType.GIVEN,
    )

    with pytest.raises(ValidationError, match="immutable"):
        event.delete()


@pytest.mark.django_db
def test_consent_event_queryset_update_and_delete_are_forbidden() -> None:
    record = _create_consent_record()
    ConsentEvent.objects.create(
        consent_record=record,
        event_type=ConsentEvent.EventType.GIVEN,
    )

    with pytest.raises(ValidationError, match="immutable"):
        ConsentEvent.objects.filter(consent_record=record).update(payload={"v": 2})

    with pytest.raises(ValidationError, match="immutable"):
        ConsentEvent.objects.filter(consent_record=record).delete()
