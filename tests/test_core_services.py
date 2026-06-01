from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError
from django.test import override_settings
from django.utils import timezone

from django_consent_152fz import constants
from django_consent_152fz.core import services as core_services
from django_consent_152fz.core.models import (
    ConsentAccessPolicy,
    ConsentAudienceRule,
    ConsentEvent,
    ConsentPurpose,
    ConsentRecord,
    DocumentRevision,
    LegalDocument,
)
from django_consent_152fz.core.services import (
    accept_consent,
    anonymize_subject_consents,
    attach_anonymous_consents_to_user,
    build_audit_context,
    clone_access_policy_as_draft,
    clone_audience_rule_as_draft,
    clone_legal_document_stream_as_draft,
    get_consent_status,
    get_current_requirements,
    mark_outdated_consents,
    publish_document_revision,
    render_document_revision_pdf_bytes,
    withdraw_consent,
)
from django_consent_152fz.exceptions import ConsentError


def _create_purpose(
    *,
    code: str = "account_basic",
    withdraw_strategy: str = constants.WITHDRAW_STRATEGY_BLOCK,
    consent_frequency_policy: str = constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED,
) -> ConsentPurpose:
    return ConsentPurpose.objects.create(
        code=code,
        title="Регистрация",
        fields_config=["email"],
        withdraw_strategy=withdraw_strategy,
        consent_frequency_policy=consent_frequency_policy,
    )


def _html_pdf_hook(*, body_html: str, revision) -> bytes:
    del revision
    return ("%PDF-hook\n" + body_html).encode("utf-8")


@pytest.mark.django_db
def test_publish_document_revision_marks_previous_consents_outdated() -> None:
    purpose = _create_purpose()
    first_revision = publish_document_revision(
        document_code="consent_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    record = accept_consent(purpose_code=purpose.code, anonymous_token="anon-1")

    second_revision = publish_document_revision(
        document_code="consent_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v2",
    )

    first_revision.refresh_from_db()
    record.refresh_from_db()

    assert first_revision.is_active is False
    assert second_revision.version == 2
    assert record.status == ConsentRecord.Status.OUTDATED
    assert ConsentEvent.objects.filter(
        consent_record=record,
        event_type=ConsentEvent.EventType.OUTDATED,
    ).exists()


@pytest.mark.django_db
def test_render_document_revision_pdf_bytes_plain_text_uses_builtin_renderer() -> None:
    purpose = _create_purpose(code="pdf_plain")
    revision = publish_document_revision(
        document_code="pdf_plain_doc",
        purpose_code=purpose.code,
        content_format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="Тестовая строка",
    )

    pdf_bytes = render_document_revision_pdf_bytes(revision=revision)

    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"/Type /Catalog" in pdf_bytes


@pytest.mark.django_db
def test_render_document_revision_pdf_bytes_returns_uploaded_pdf_file() -> None:
    purpose = _create_purpose(code="pdf_file")
    uploaded_pdf = SimpleUploadedFile(
        "consent.pdf",
        b"%PDF-1.4\n% demo file\n",
        content_type="application/pdf",
    )
    revision = publish_document_revision(
        document_code="pdf_file_doc",
        purpose_code=purpose.code,
        content_format=DocumentRevision.ContentFormat.PDF_FILE,
        content_file=uploaded_pdf,
    )

    pdf_bytes = render_document_revision_pdf_bytes(revision=revision)

    assert pdf_bytes == b"%PDF-1.4\n% demo file\n"


@pytest.mark.django_db
def test_render_document_revision_pdf_bytes_html_requires_hook() -> None:
    purpose = _create_purpose(code="pdf_html_missing_hook")
    revision = publish_document_revision(
        document_code="pdf_html_doc",
        purpose_code=purpose.code,
        content_format=DocumentRevision.ContentFormat.HTML,
        content_text="<h1>Consent</h1>",
    )

    with pytest.raises(ConsentError, match="html_to_pdf_hook"):
        render_document_revision_pdf_bytes(revision=revision)


@override_settings(
    DJANGO_152FZ_CONSENT={
        "document_templates": {"html_to_pdf_hook": _html_pdf_hook},
    }
)
@pytest.mark.django_db
def test_render_document_revision_pdf_bytes_html_uses_configured_hook() -> None:
    purpose = _create_purpose(code="pdf_html_hook")
    revision = publish_document_revision(
        document_code="pdf_html_hook_doc",
        purpose_code=purpose.code,
        content_format=DocumentRevision.ContentFormat.HTML,
        content_text="<p>Consent hook</p>",
    )

    pdf_bytes = render_document_revision_pdf_bytes(revision=revision)

    assert pdf_bytes.startswith(b"%PDF-hook")
    assert b"Consent hook" in pdf_bytes


@pytest.mark.django_db
def test_accept_consent_creates_current_record_and_given_event() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="consent_doc",
        purpose_code=purpose.code,
        content_format="markdown",
        content_text="**consent**",
    )

    record = accept_consent(
        purpose_code=purpose.code,
        anonymous_token="anon-1",
        confirmation_method=ConsentRecord.ConfirmationMethod.WEB_BUTTON,
        source="ui",
    )

    assert record.status == ConsentRecord.Status.CURRENT
    assert ConsentEvent.objects.filter(
        consent_record=record,
        event_type=ConsentEvent.EventType.GIVEN,
    ).exists()


@pytest.mark.django_db
def test_authenticated_only_purpose_is_hidden_for_anonymous_requirements() -> None:
    purpose = ConsentPurpose.objects.create(
        code="auth_only_purpose",
        title="Только для аккаунтов",
        fields_config=["email"],
        subject_availability_policy=(
            ConsentPurpose.SubjectAvailabilityPolicy.AUTHENTICATED_ONLY
        ),
    )
    publish_document_revision(
        document_code="auth_only_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    requirements = get_current_requirements(anonymous_token="anon-auth-only")

    assert requirements["requirements"] == []


@pytest.mark.django_db
def test_accept_consent_rejects_anonymous_for_authenticated_only_purpose() -> None:
    purpose = ConsentPurpose.objects.create(
        code="auth_only_accept",
        title="Только auth",
        fields_config=["email"],
        subject_availability_policy=(
            ConsentPurpose.SubjectAvailabilityPolicy.AUTHENTICATED_ONLY
        ),
    )
    publish_document_revision(
        document_code="auth_only_accept_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    with pytest.raises(ConsentError, match="требуется авторизация"):
        accept_consent(
            purpose_code=purpose.code,
            document_code="auth_only_accept_doc",
            anonymous_token="anon-auth-only",
        )


@pytest.mark.django_db
def test_get_consent_status_once_until_outdated_does_not_require_repeat_for_current() -> (
    None
):
    User = get_user_model()
    user = User.objects.create_user(username="once-user", password="pwd")
    purpose = _create_purpose(
        code="once_until_outdated_status",
        consent_frequency_policy=constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED,
    )
    publish_document_revision(
        document_code="once_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="once_doc",
        user=user,
    )

    status = get_consent_status(
        purpose_code=purpose.code,
        document_code="once_doc",
        user=user,
    )

    assert status["status"] == ConsentRecord.Status.CURRENT
    assert status["requires_consent"] is False
    assert status["consent_required_reason"] == "not_required"


@pytest.mark.django_db
def test_get_consent_status_every_time_requires_repeat_for_current() -> None:
    User = get_user_model()
    user = User.objects.create_user(username="every-user", password="pwd")
    purpose = _create_purpose(
        code="every_time_status",
        consent_frequency_policy=constants.CONSENT_FREQUENCY_EVERY_TIME,
    )
    publish_document_revision(
        document_code="every_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="every_doc",
        user=user,
    )

    status = get_consent_status(
        purpose_code=purpose.code,
        document_code="every_doc",
        user=user,
    )

    assert status["status"] == ConsentRecord.Status.CURRENT
    assert status["is_current"] is True
    assert status["requires_consent"] is True
    assert status["consent_required_reason"] == "every_time"


@pytest.mark.django_db
def test_every_time_accept_creates_new_current_record_and_keeps_audit_history() -> None:
    User = get_user_model()
    user = User.objects.create_user(username="repeat-user", password="pwd")
    purpose = _create_purpose(
        code="every_time_audit",
        consent_frequency_policy=constants.CONSENT_FREQUENCY_EVERY_TIME,
    )
    publish_document_revision(
        document_code="repeat_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    first = accept_consent(
        purpose_code=purpose.code,
        document_code="repeat_doc",
        user=user,
    )
    second = accept_consent(
        purpose_code=purpose.code,
        document_code="repeat_doc",
        user=user,
    )

    first.refresh_from_db()
    second.refresh_from_db()

    assert first.status == ConsentRecord.Status.OUTDATED
    assert second.status == ConsentRecord.Status.CURRENT
    assert (
        ConsentRecord.objects.filter(
            purpose=purpose,
            user=user,
            document_revision__document__code="repeat_doc",
        ).count()
        == 2
    )
    assert first.events.filter(event_type=ConsentEvent.EventType.OUTDATED).exists()
    second_given = second.events.get(event_type=ConsentEvent.EventType.GIVEN)
    assert second_given.payload["consent_frequency_policy"] == "every_time"
    assert second_given.payload["repeated_confirmation"] is True


@pytest.mark.django_db(transaction=True)
def test_accept_consent_double_submit_race_keeps_single_current_record(
    monkeypatch,
) -> None:
    purpose = _create_purpose(code="race_accept")
    publish_document_revision(
        document_code="race_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    race_token = "anon-race-accept"
    barrier = threading.Barrier(2)
    original_subject_records_qs = core_services._subject_records_qs

    def _subject_records_qs_with_barrier(*args, **kwargs):
        if kwargs.get("anonymous_token") == race_token:
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
        return original_subject_records_qs(*args, **kwargs)

    monkeypatch.setattr(
        core_services,
        "_subject_records_qs",
        _subject_records_qs_with_barrier,
    )

    def _run_accept() -> ConsentRecord:
        for attempt in range(5):
            try:
                return accept_consent(
                    purpose_code=purpose.code,
                    document_code="race_doc",
                    anonymous_token=race_token,
                )
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == 4:
                    raise
                time.sleep(0.05)
        raise AssertionError("unreachable")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_run_accept) for _ in range(2)]
        records = [future.result() for future in futures]

    base_qs = ConsentRecord.objects.filter(
        purpose=purpose,
        document_revision__document__code="race_doc",
        anonymous_token=race_token,
    )
    assert base_qs.filter(status=ConsentRecord.Status.CURRENT).count() == 1
    assert base_qs.count() == 2
    assert set(base_qs.values_list("pk", flat=True)) == {
        record.pk for record in records
    }


@pytest.mark.django_db
def test_accept_consent_writes_audit_context_to_record_and_event() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="audit_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    record = accept_consent(
        purpose_code=purpose.code,
        anonymous_token="anon-audit",
        audit_context={
            "source": "ui",
            "ip_address": "127.0.0.1",
            "user_agent": "Mozilla/5.0",
            "locale": "ru-RU",
            "request_id": "req-1",
            "session_key_hash": "session-hash-1",
            "extra_meta": {
                "client.os_family": "Windows",
                "client.browser_name": "Chrome",
                "client.device_type": "desktop",
                "client.languages": ["ru-RU", "en-US"],
                "client.timezone": "Asia/Irkutsk",
                "request": {"referrer": "https://example.com/start"},
            },
        },
    )

    event = record.events.get(event_type=ConsentEvent.EventType.GIVEN)

    assert record.source == "ui"
    assert record.ip_address == "127.0.0.1"
    assert record.user_agent == "Mozilla/5.0"
    assert record.locale == "ru-RU"
    assert record.extra_meta["client"]["os_family"] == "Windows"
    assert record.extra_meta["client"]["browser_name"] == "Chrome"
    assert record.extra_meta["client"]["device_type"] == "desktop"
    assert record.extra_meta["client"]["languages"] == ["ru-RU", "en-US"]
    assert record.extra_meta["client"]["timezone"] == "Asia/Irkutsk"
    assert record.extra_meta["request"]["referrer"] == "https://example.com/start"

    assert event.actor_type == ConsentEvent.ActorType.SUBJECT
    assert event.actor_user is None
    assert event.source == "ui"
    assert event.ip_address == "127.0.0.1"
    assert event.user_agent == "Mozilla/5.0"
    assert event.locale == "ru-RU"
    assert event.request_id == "req-1"
    assert event.session_key_hash == "session-hash-1"
    assert event.extra_meta["client"]["os_family"] == "Windows"
    assert event.extra_meta["client"]["browser_name"] == "Chrome"
    assert event.extra_meta["client"]["device_type"] == "desktop"
    assert event.extra_meta["client"]["languages"] == ["ru-RU", "en-US"]
    assert event.extra_meta["client"]["timezone"] == "Asia/Irkutsk"
    assert event.extra_meta["request"]["referrer"] == "https://example.com/start"


def test_build_audit_context_normalizes_namespaces_and_scrubs_sensitive_data() -> None:
    context = build_audit_context(
        source="ui",
        request_id="req-builder",
        audit_context={
            "client": {
                "os_family": "Windows",
                "headers": {"x-forwarded-for": "127.0.0.1"},
            },
            "request": {"path": "/consent", "cookies": {"sid": "secret"}},
            "project_code": "demo",
            "extra_meta": {
                "client.browser_name": "Chrome",
                "client_hints.sec_ch_ua_platform": "Windows",
                "integration.provider": "crm",
                "custom.debug": True,
                "headers": {"authorization": "Bearer secret"},
            },
        },
        custom={"release": "2026.03"},
    )

    assert context["source"] == "ui"
    assert context["request_id"] == "req-builder"
    assert context["extra_meta"]["client"]["os_family"] == "Windows"
    assert context["extra_meta"]["client"]["browser_name"] == "Chrome"
    assert context["extra_meta"]["request"]["path"] == "/consent"
    assert context["extra_meta"]["client_hints"]["sec_ch_ua_platform"] == "Windows"
    assert context["extra_meta"]["integration"]["provider"] == "crm"
    assert context["extra_meta"]["custom"]["debug"] is True
    assert context["extra_meta"]["custom"]["release"] == "2026.03"
    assert context["extra_meta"]["custom"]["project_code"] == "demo"
    assert "headers" not in context["extra_meta"]["client"]
    assert "cookies" not in context["extra_meta"]["request"]
    assert "headers" not in context["extra_meta"]


@pytest.mark.django_db
def test_accept_consent_moves_unknown_extra_meta_to_custom_namespace() -> None:
    purpose = _create_purpose(code="custom_meta")
    publish_document_revision(
        document_code="custom_meta_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    record = accept_consent(
        purpose_code=purpose.code,
        anonymous_token="anon-custom-meta",
        audit_context={
            "client": {"browser_name": "Firefox"},
            "request": {"path": "/signup", "referrer": "https://example.com/landing"},
            "preorder_id": "PO-42",
            "extra_meta": {
                "campaign": "spring",
                "request.headers": {"accept": "text/html"},
                "custom.segment": "vip",
            },
        },
    )

    event = record.events.get(event_type=ConsentEvent.EventType.GIVEN)

    assert record.extra_meta["client"]["browser_name"] == "Firefox"
    assert record.extra_meta["request"]["path"] == "/signup"
    assert record.extra_meta["request"]["referrer"] == "https://example.com/landing"
    assert record.extra_meta["custom"]["preorder_id"] == "PO-42"
    assert record.extra_meta["custom"]["campaign"] == "spring"
    assert record.extra_meta["custom"]["segment"] == "vip"
    assert "headers" not in record.extra_meta["request"]
    assert event.extra_meta == record.extra_meta


@pytest.mark.parametrize(
    ("confirmation_method", "expected_actor_type", "expected_event_type"),
    [
        (
            ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED,
            ConsentEvent.ActorType.ADMIN,
            ConsentEvent.EventType.ADMIN_CONFIRMED,
        ),
        (
            ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
            ConsentEvent.ActorType.EMPLOYEE,
            ConsentEvent.EventType.EMPLOYEE_CONFIRMED,
        ),
    ],
)
@pytest.mark.django_db
def test_accept_consent_manual_confirmation_uses_actor_and_confirmed_at(
    confirmation_method: str,
    expected_actor_type: str,
    expected_event_type: str,
) -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="manual_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    User = get_user_model()
    staff_user = User.objects.create_user(
        username=f"{confirmation_method}_user",
        password="x",
        is_staff=True,
    )
    confirmed_at = timezone.now()

    record = accept_consent(
        purpose_code=purpose.code,
        anonymous_token=f"anon-{confirmation_method}",
        confirmation_method=confirmation_method,
        confirmed_by=staff_user,
        confirmed_at=confirmed_at,
        audit_context={"source": "admin"},
    )

    event = record.events.get(event_type=expected_event_type)

    assert record.status == ConsentRecord.Status.CURRENT
    assert event.actor_user_id == staff_user.pk
    assert event.actor_type == expected_actor_type
    assert event.source == "admin"
    assert event.occurred_at == confirmed_at


@pytest.mark.django_db
def test_accept_consent_requires_document_code_for_multiple_active_documents() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="doc_a",
        purpose_code=purpose.code,
        content_format="markdown",
        content_text="doc a",
    )
    publish_document_revision(
        document_code="doc_b",
        purpose_code=purpose.code,
        content_format="markdown",
        content_text="doc b",
    )

    with pytest.raises(ConsentError, match="Multiple active documents"):
        accept_consent(
            purpose_code=purpose.code,
            anonymous_token="anon-multi",
        )


@pytest.mark.django_db
def test_accept_consent_uploaded_paper_requires_verified_services() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="paper_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    with pytest.raises(
        ConsentError,
        match="uploaded_paper flow is available only through "
        "verified_consents.submit_verified_consent",
    ):
        accept_consent(
            purpose_code=purpose.code,
            anonymous_token="anon-2",
            confirmation_method=ConsentRecord.ConfirmationMethod.UPLOADED_PAPER,
        )


@pytest.mark.django_db
def test_publish_document_revision_outdates_only_same_document_stream() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="privacy_main",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="main v1",
    )
    publish_document_revision(
        document_code="privacy_alt",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="alt v1",
    )
    main_record = accept_consent(
        purpose_code=purpose.code,
        document_code="privacy_main",
        anonymous_token="main-user",
    )
    alt_record = accept_consent(
        purpose_code=purpose.code,
        document_code="privacy_alt",
        anonymous_token="alt-user",
    )

    publish_document_revision(
        document_code="privacy_alt",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="alt v2",
    )

    main_record.refresh_from_db()
    alt_record.refresh_from_db()
    assert main_record.status == ConsentRecord.Status.CURRENT
    assert alt_record.status == ConsentRecord.Status.OUTDATED


@pytest.mark.django_db
def test_withdraw_consent_emits_withdrawn_and_strategy_event() -> None:
    purpose = _create_purpose(withdraw_strategy=constants.WITHDRAW_STRATEGY_DELETE)
    publish_document_revision(
        document_code="withdraw_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    record = accept_consent(purpose_code=purpose.code, anonymous_token="anon-1")

    withdrawn = withdraw_consent(purpose_code=purpose.code, anonymous_token="anon-1")

    assert withdrawn.pk == record.pk
    assert withdrawn.status == ConsentRecord.Status.WITHDRAWN
    assert ConsentEvent.objects.filter(
        consent_record=withdrawn,
        event_type=ConsentEvent.EventType.WITHDRAWN,
    ).exists()
    assert ConsentEvent.objects.filter(
        consent_record=withdrawn,
        event_type=ConsentEvent.EventType.DELETE_REQUESTED,
    ).exists()


@pytest.mark.django_db
def test_withdraw_consent_writes_audit_context_to_withdraw_and_strategy_events() -> (
    None
):
    purpose = _create_purpose(withdraw_strategy=constants.WITHDRAW_STRATEGY_BLOCK)
    publish_document_revision(
        document_code="withdraw_audit_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    accept_consent(purpose_code=purpose.code, anonymous_token="anon-withdraw-audit")

    withdrawn = withdraw_consent(
        purpose_code=purpose.code,
        anonymous_token="anon-withdraw-audit",
        audit_context={
            "source": "api",
            "ip_address": "10.0.0.2",
            "user_agent": "curl/8.0",
            "locale": "ru",
            "request_id": "req-withdraw",
            "session_key_hash": "session-withdraw",
            "extra_meta": {"request.referrer": "https://example.com/profile"},
        },
    )

    withdrawn_event = withdrawn.events.get(event_type=ConsentEvent.EventType.WITHDRAWN)
    blocked_event = withdrawn.events.get(event_type=ConsentEvent.EventType.BLOCKED)

    assert withdrawn_event.actor_type == ConsentEvent.ActorType.SUBJECT
    assert withdrawn_event.source == "api"
    assert withdrawn_event.request_id == "req-withdraw"
    assert withdrawn_event.extra_meta["request"]["referrer"] == (
        "https://example.com/profile"
    )
    assert blocked_event.actor_type == ConsentEvent.ActorType.SYSTEM
    assert blocked_event.request_id == "req-withdraw"
    assert blocked_event.extra_meta["request"]["referrer"] == (
        "https://example.com/profile"
    )


@pytest.mark.django_db
def test_withdraw_consent_rejects_anonymous_when_disabled_by_settings() -> None:
    purpose = _create_purpose(code="anon_withdraw_off")
    publish_document_revision(
        document_code="anon_withdraw_off_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="anon_withdraw_off_doc",
        anonymous_token="anon-withdraw-off",
    )

    with override_settings(
        DJANGO_152FZ_CONSENT={
            "subject_consents": {
                "open_mode": "page",
                "allow_anonymous_withdraw": False,
            }
        }
    ):
        with pytest.raises(ConsentError, match="Отзыв согласия для анонимного"):
            withdraw_consent(
                purpose_code=purpose.code,
                document_code="anon_withdraw_off_doc",
                anonymous_token="anon-withdraw-off",
            )


@pytest.mark.django_db
def test_anonymize_subject_consents_scrubs_record_and_writes_event() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="anonymize_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    User = get_user_model()
    user = User.objects.create_user(username="anon-service-user", password="x")
    record = accept_consent(
        purpose_code=purpose.code,
        user=user,
        source="ui",
        audit_context={
            "ip_address": "127.0.0.10",
            "user_agent": "Mozilla/5.0 anonymize",
            "locale": "ru-RU",
            "request": {"path": "/profile/delete"},
        },
    )

    anonymized_records = anonymize_subject_consents(
        user=user,
        reason="user_requested_cleanup",
        audit_context={
            "source": "account_cleanup",
            "request_id": "req-anonymize-1",
            "request": {"path": "/profile/delete"},
        },
    )

    record.refresh_from_db()
    event = record.events.get(event_type=ConsentEvent.EventType.ANONYMIZED)

    assert [item.pk for item in anonymized_records] == [record.pk]
    assert record.status == ConsentRecord.Status.DELETED
    assert record.user_id is None
    assert record.anonymous_token == f"anonymized:{record.pk}"
    assert record.subject_ref == ""
    assert record.ip_address is None
    assert record.user_agent == ""
    assert record.locale == ""
    assert record.extra_meta == {"custom": {"anonymized": True}}
    assert event.actor_type == ConsentEvent.ActorType.SUBJECT
    assert event.source == "account_cleanup"
    assert event.request_id == "req-anonymize-1"
    assert event.payload["reason"] == "user_requested_cleanup"
    assert event.payload["previous_status"] == ConsentRecord.Status.CURRENT
    assert event.payload["new_status"] == ConsentRecord.Status.DELETED
    assert event.payload["document_code"] == "anonymize_doc"
    assert "ip_address" in event.payload["anonymized_fields"]


@pytest.mark.django_db
def test_anonymize_subject_consents_is_idempotent_for_same_record() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="anonymize_idempotent_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    record = accept_consent(
        purpose_code=purpose.code,
        anonymous_token="anon-idempotent",
    )

    first = anonymize_subject_consents(
        anonymous_token="anon-idempotent",
        audit_context={"source": "cleanup-job"},
    )
    second = anonymize_subject_consents(
        anonymous_token=f"anonymized:{record.pk}",
        audit_context={"source": "cleanup-job"},
    )

    assert [item.pk for item in first] == [record.pk]
    assert second == []
    assert (
        record.events.filter(event_type=ConsentEvent.EventType.ANONYMIZED).count() == 1
    )


@pytest.mark.django_db
def test_mark_outdated_consents_writes_audit_context_to_outdated_event() -> None:
    purpose = _create_purpose()
    first_revision = publish_document_revision(
        document_code="outdated_audit_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    publish_document_revision(
        document_code="outdated_audit_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v2",
    )
    record = ConsentRecord.objects.create(
        anonymous_token="anon-outdated-audit",
        purpose=purpose,
        document_revision=first_revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )
    changed_records = mark_outdated_consents(
        purpose_code=purpose.code,
        anonymous_token="anon-outdated-audit",
        audit_context={
            "source": "system_job",
            "request_id": "req-outdated",
            "extra_meta": {"client_hints.sec_ch_ua_platform": "Windows"},
        },
    )

    record.refresh_from_db()
    event = record.events.filter(event_type=ConsentEvent.EventType.OUTDATED).latest(
        "id"
    )

    assert {item.pk for item in changed_records} == {record.pk}
    assert event.actor_type == ConsentEvent.ActorType.SYSTEM
    assert event.source == "system_job"
    assert event.request_id == "req-outdated"
    assert event.extra_meta["client_hints"]["sec_ch_ua_platform"] == "Windows"


@pytest.mark.django_db
def test_get_consent_status_and_requirements() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="status_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    initial = get_consent_status(purpose_code=purpose.code, anonymous_token="anon-3")
    assert initial["status"] is None
    assert initial["requires_consent"] is True
    assert initial["consent_required_reason"] == "missing_or_other"

    accept_consent(purpose_code=purpose.code, anonymous_token="anon-3")
    status = get_consent_status(purpose_code=purpose.code, anonymous_token="anon-3")
    assert status["status"] == ConsentRecord.Status.CURRENT
    assert status["is_current"] is True
    assert status["document_code"] == "status_doc"
    assert status["consent_required_reason"] == "not_required"

    requirements = get_current_requirements(anonymous_token="anon-3")
    assert requirements["provider_code"] == constants.PROVIDER_CODE
    assert requirements["requirements"][0]["purpose_code"] == purpose.code
    assert requirements["requirements"][0]["document_code"] == "status_doc"
    assert requirements["requirements"][0]["consent_status"] == (
        ConsentRecord.Status.CURRENT
    )
    assert requirements["requirements"][0]["consent_required_reason"] == "not_required"


@pytest.mark.django_db
def test_get_current_requirements_returns_entry_per_active_document() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="module_a_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="a v1",
    )
    publish_document_revision(
        document_code="module_b_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="b v1",
    )

    requirements = get_current_requirements(anonymous_token="anon-5")

    entries = [
        item
        for item in requirements["requirements"]
        if item["purpose_code"] == purpose.code
    ]
    assert len(entries) == 2
    assert {item["document_code"] for item in entries} == {
        "module_a_doc",
        "module_b_doc",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("subject_kind", "frequency_policy", "make_outdated", "expected_reason"),
    [
        (
            "auth",
            constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED,
            False,
            "not_required",
        ),
        ("auth", constants.CONSENT_FREQUENCY_EVERY_TIME, False, "every_time"),
        ("auth", constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED, True, "outdated"),
        ("auth", constants.CONSENT_FREQUENCY_EVERY_TIME, True, "outdated"),
        (
            "anon",
            constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED,
            False,
            "not_required",
        ),
        ("anon", constants.CONSENT_FREQUENCY_EVERY_TIME, False, "every_time"),
        ("anon", constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED, True, "outdated"),
        ("anon", constants.CONSENT_FREQUENCY_EVERY_TIME, True, "outdated"),
    ],
)
def test_status_matrix_auth_anon_frequency_and_outdated(
    subject_kind: str,
    frequency_policy: str,
    make_outdated: bool,
    expected_reason: str,
) -> None:
    purpose = _create_purpose(
        code=f"matrix_{subject_kind}_{frequency_policy}_{int(make_outdated)}",
        consent_frequency_policy=frequency_policy,
    )
    publish_document_revision(
        document_code="matrix_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    user = None
    anonymous_token = None
    if subject_kind == "auth":
        User = get_user_model()
        user = User.objects.create_user(
            username=f"matrix-{frequency_policy}-{int(make_outdated)}",
            password="pwd",
        )
    else:
        anonymous_token = f"anon-matrix-{frequency_policy}-{int(make_outdated)}"

    accept_consent(
        purpose_code=purpose.code,
        document_code="matrix_doc",
        user=user,
        anonymous_token=anonymous_token,
    )
    if make_outdated:
        publish_document_revision(
            document_code="matrix_doc",
            purpose_code=purpose.code,
            content_format="plain_text",
            content_text="v2",
        )

    status = get_consent_status(
        purpose_code=purpose.code,
        document_code="matrix_doc",
        user=user,
        anonymous_token=anonymous_token,
    )
    requirements = get_current_requirements(
        user=user,
        anonymous_token=anonymous_token,
    )["requirements"]
    requirement = next(
        item
        for item in requirements
        if item["purpose_code"] == purpose.code
        and item["document_code"] == "matrix_doc"
    )

    assert status["consent_required_reason"] == expected_reason
    assert requirement["consent_required_reason"] == expected_reason


@pytest.mark.django_db
def test_get_consent_status_scopes_to_document_stream() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="module_a_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="a v1",
    )
    publish_document_revision(
        document_code="module_b_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="b v1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="module_a_doc",
        anonymous_token="anon-6",
    )

    scoped_status = get_consent_status(
        purpose_code=purpose.code,
        document_code="module_a_doc",
        anonymous_token="anon-6",
    )
    other_status = get_consent_status(
        purpose_code=purpose.code,
        document_code="module_b_doc",
        anonymous_token="anon-6",
    )

    assert scoped_status["status"] == ConsentRecord.Status.CURRENT
    assert other_status["status"] is None

    with pytest.raises(ConsentError, match="Multiple active documents"):
        get_consent_status(
            purpose_code=purpose.code,
            anonymous_token="anon-6",
        )


@pytest.mark.django_db
def test_attach_anonymous_consents_to_user() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="attach_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    record = accept_consent(purpose_code=purpose.code, anonymous_token="anon-attach")
    User = get_user_model()
    user = User.objects.create_user(username="linked_user", password="x")

    attached = attach_anonymous_consents_to_user(
        user=user,
        anonymous_token="anon-attach",
    )

    record.refresh_from_db()
    assert len(attached) == 1
    assert record.user_id == user.id
    assert record.subject_ref == str(user.pk)
    attach_event = record.events.get(event_type=ConsentEvent.EventType.RECONFIRMED)
    assert attach_event.payload["reason"] == "subject_attached"
    assert attach_event.payload["attached_user_id"] == user.id


@pytest.mark.django_db
def test_clone_legal_document_stream_as_draft_creates_inactive_copy() -> None:
    purpose = _create_purpose(code="clone_stream")
    publish_document_revision(
        document_code="clone_doc_stream",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    publish_document_revision(
        document_code="clone_doc_stream",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v2",
    )
    source_document = LegalDocument.objects.get(code="clone_doc_stream")

    cloned_document, cloned_revisions_count = clone_legal_document_stream_as_draft(
        source_document=source_document
    )

    assert cloned_document.code.startswith("clone_doc_stream_copy")
    assert cloned_document.is_active is False
    assert cloned_revisions_count == 2
    cloned_revisions = list(
        DocumentRevision.objects.filter(document=cloned_document).order_by("version")
    )
    assert len(cloned_revisions) == 2
    assert all(revision.is_active is False for revision in cloned_revisions)
    assert all(revision.is_box_template is False for revision in cloned_revisions)
    assert cloned_revisions[0].meta["derived_from_document_clone"] is True
    assert cloned_revisions[1].meta["source_document_code"] == source_document.code


@pytest.mark.django_db
def test_clone_access_policy_as_draft_generates_unique_code_and_resource() -> None:
    purpose = _create_purpose(code="clone_policy")
    publish_document_revision(
        document_code="clone_policy_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = LegalDocument.objects.get(code="clone_policy_doc")
    source_policy = ConsentAccessPolicy.objects.create(
        code="clone_policy_source",
        title="Source policy",
        description="Source description",
        purpose=purpose,
        document=document,
        resource_code="profile_page",
        action="view",
        on_missing_consent=ConsentAccessPolicy.MissingConsentAction.DENY,
        on_outdated_consent=(
            ConsentAccessPolicy.OutdatedConsentAction.RESPECT_RECONSENT_MODE
        ),
        is_active=True,
        notes="Source notes",
        extra_meta={"origin": "test"},
    )

    clone = clone_access_policy_as_draft(source_policy=source_policy)

    assert clone.pk != source_policy.pk
    assert clone.code.startswith("clone_policy_source_copy")
    assert clone.resource_code.startswith("profile_page_copy")
    assert clone.action == source_policy.action
    assert clone.is_active is False
    assert clone.extra_meta["derived_from_policy_clone"] is True
    assert clone.extra_meta["source_policy_id"] == source_policy.pk


@pytest.mark.django_db
def test_clone_audience_rule_as_draft_creates_inactive_copy() -> None:
    purpose = _create_purpose(code="clone_audience")
    publish_document_revision(
        document_code="clone_audience_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = LegalDocument.objects.get(code="clone_audience_doc")
    source_rule = ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS,
        is_required=True,
        is_active=True,
        notes="Audience source",
    )

    clone = clone_audience_rule_as_draft(source_rule=source_rule)

    assert clone.pk != source_rule.pk
    assert clone.is_active is False
    assert clone.scope_mode == source_rule.scope_mode
    assert clone.purpose_id == source_rule.purpose_id
    assert clone.document_id == source_rule.document_id
    assert "Черновая копия." in clone.notes
