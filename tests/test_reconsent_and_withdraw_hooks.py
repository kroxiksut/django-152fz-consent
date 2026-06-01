from __future__ import annotations

import pytest

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentPurpose,
    ConsentRecord,
    DocumentRevision,
    LegalDocument,
)
from django_consent_152fz.core.services import (
    accept_consent,
    get_consent_status,
    get_reconsent_notice,
    mark_outdated_consents,
    publish_document_revision,
    withdraw_consent,
)
from django_consent_152fz.integrations import (
    reset_hooks,
    set_external_cleanup_hook,
    set_reconsent_email_reminder_hook,
    set_session_termination_hook,
)


@pytest.fixture(autouse=True)
def _reset_integration_hooks():
    reset_hooks()
    yield
    reset_hooks()


def _create_purpose(
    *,
    code: str,
    reconsent_mode: str,
    withdraw_strategy: str,
) -> ConsentPurpose:
    return ConsentPurpose.objects.create(
        code=code,
        title=code,
        fields_config=["email"],
        reconsent_mode=reconsent_mode,
        withdraw_strategy=withdraw_strategy,
    )


def _create_outdated_current_record(*, purpose: ConsentPurpose) -> ConsentRecord:
    document = LegalDocument.objects.create(code=f"{purpose.code}_doc", title="Doc")
    old_revision = DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="v1",
        fields_snapshot=["email"],
        is_active=False,
    )
    DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=2,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="v2",
        fields_snapshot=["email"],
        is_active=True,
    )
    return ConsentRecord.objects.create(
        anonymous_token=f"{purpose.code}-anon",
        purpose=purpose,
        document_revision=old_revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )


@pytest.mark.django_db
def test_mark_outdated_consents_and_email_hook() -> None:
    purpose = _create_purpose(
        code="soft_case",
        reconsent_mode=constants.RECONSENT_MODE_SOFT,
        withdraw_strategy=constants.WITHDRAW_STRATEGY_BLOCK,
    )
    record = _create_outdated_current_record(purpose=purpose)
    reminders: list[int] = []
    set_reconsent_email_reminder_hook(lambda r: reminders.append(r.pk))

    changed = mark_outdated_consents(
        purpose_code=purpose.code,
        trigger_email_reminder=True,
    )

    record.refresh_from_db()
    assert len(changed) == 1
    assert record.status == ConsentRecord.Status.OUTDATED
    assert reminders == [record.pk]


@pytest.mark.django_db
def test_mark_outdated_consents_checks_only_same_document_stream() -> None:
    purpose = _create_purpose(
        code="stream_case",
        reconsent_mode=constants.RECONSENT_MODE_SOFT,
        withdraw_strategy=constants.WITHDRAW_STRATEGY_BLOCK,
    )
    main_document = LegalDocument.objects.create(code="stream_main", title="Main")
    alt_document = LegalDocument.objects.create(code="stream_alt", title="Alt")
    old_main_revision = DocumentRevision.objects.create(
        document=main_document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="main v1",
        fields_snapshot=["email"],
        is_active=False,
    )
    DocumentRevision.objects.create(
        document=main_document,
        purpose_code=purpose.code,
        version=2,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="main v2",
        fields_snapshot=["email"],
        is_active=True,
    )
    alt_revision = DocumentRevision.objects.create(
        document=alt_document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="alt v1",
        fields_snapshot=["email"],
        is_active=True,
    )
    main_record = ConsentRecord.objects.create(
        anonymous_token="stream-main-anon",
        purpose=purpose,
        document_revision=old_main_revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )
    alt_record = ConsentRecord.objects.create(
        anonymous_token="stream-alt-anon",
        purpose=purpose,
        document_revision=alt_revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )

    changed = mark_outdated_consents(purpose_code=purpose.code)

    main_record.refresh_from_db()
    alt_record.refresh_from_db()
    assert {record.pk for record in changed} == {main_record.pk}
    assert main_record.status == ConsentRecord.Status.OUTDATED
    assert alt_record.status == ConsentRecord.Status.CURRENT


@pytest.mark.django_db
def test_soft_and_hard_reconsent_notice_and_access_flags() -> None:
    soft_purpose = _create_purpose(
        code="soft_mode",
        reconsent_mode=constants.RECONSENT_MODE_SOFT,
        withdraw_strategy=constants.WITHDRAW_STRATEGY_BLOCK,
    )
    hard_purpose = _create_purpose(
        code="hard_mode",
        reconsent_mode=constants.RECONSENT_MODE_HARD,
        withdraw_strategy=constants.WITHDRAW_STRATEGY_BLOCK,
    )
    _create_outdated_current_record(purpose=soft_purpose)
    _create_outdated_current_record(purpose=hard_purpose)

    mark_outdated_consents()

    soft_status = get_consent_status(
        purpose_code=soft_purpose.code,
        anonymous_token="soft_mode-anon",
    )
    hard_status = get_consent_status(
        purpose_code=hard_purpose.code,
        anonymous_token="hard_mode-anon",
    )
    soft_notice = get_reconsent_notice(
        purpose_code=soft_purpose.code,
        anonymous_token="soft_mode-anon",
    )
    hard_notice = get_reconsent_notice(
        purpose_code=hard_purpose.code,
        anonymous_token="hard_mode-anon",
    )

    assert soft_status["status"] == ConsentRecord.Status.OUTDATED
    assert soft_status["access_restricted"] is False
    assert soft_notice is not None
    assert soft_notice["blocking"] is False
    assert soft_notice["kind"] == "soft_reconsent"
    assert soft_notice["document_code"] == "soft_mode_doc"

    assert hard_status["status"] == ConsentRecord.Status.OUTDATED
    assert hard_status["access_restricted"] is True
    assert hard_notice is not None
    assert hard_notice["blocking"] is True
    assert hard_notice["kind"] == "hard_reconsent"
    assert hard_notice["document_code"] == "hard_mode_doc"


@pytest.mark.django_db
def test_withdraw_strategy_hooks_block_and_delete() -> None:
    events: list[str] = []
    set_session_termination_hook(lambda record: events.append(f"session:{record.pk}"))
    set_external_cleanup_hook(lambda record: events.append(f"cleanup:{record.pk}"))

    block_purpose = _create_purpose(
        code="block_case",
        reconsent_mode=constants.RECONSENT_MODE_SOFT,
        withdraw_strategy=constants.WITHDRAW_STRATEGY_BLOCK,
    )
    delete_purpose = _create_purpose(
        code="delete_case",
        reconsent_mode=constants.RECONSENT_MODE_SOFT,
        withdraw_strategy=constants.WITHDRAW_STRATEGY_DELETE,
    )

    publish_document_revision(
        document_code="block_doc",
        purpose_code=block_purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    publish_document_revision(
        document_code="delete_doc",
        purpose_code=delete_purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    block_record = accept_consent(
        purpose_code=block_purpose.code,
        anonymous_token="block-anon",
    )
    delete_record = accept_consent(
        purpose_code=delete_purpose.code,
        anonymous_token="delete-anon",
    )

    withdraw_consent(purpose_code=block_purpose.code, anonymous_token="block-anon")
    withdraw_consent(purpose_code=delete_purpose.code, anonymous_token="delete-anon")

    assert f"session:{block_record.pk}" in events
    assert f"cleanup:{delete_record.pk}" in events
