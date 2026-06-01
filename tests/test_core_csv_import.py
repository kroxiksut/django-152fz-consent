from __future__ import annotations

import csv
import json
import os
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from django_consent_152fz.core.importers import (
    CoreConsentImportMapping,
    import_core_consents_from_csv,
)
from django_consent_152fz.core.models import (
    ConsentEvent,
    ConsentPurpose,
    ConsentRecord,
    ModuleOperationAuditLog,
)
from django_consent_152fz.core.services import publish_document_revision


def _create_flow() -> ConsentPurpose:
    purpose = ConsentPurpose.objects.create(
        code="newsletter",
        title="Newsletter",
        fields_config=["email"],
    )
    publish_document_revision(
        document_code="newsletter_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    return purpose


def _write_csv(tmp_path, rows: list[dict[str, str]]) -> str:
    csv_path = tmp_path / "import.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "purpose",
                "document_code",
                "status",
                "user",
                "anonymous_token",
                "consented_at",
                "source",
                "ip_address",
                "user_agent",
                "locale",
                "request_id",
                "session_key_hash",
                "extra_meta_json",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return str(csv_path)


def _default_mapping() -> CoreConsentImportMapping:
    return CoreConsentImportMapping(
        purpose_code="purpose",
        document_code="document_code",
        status="status",
        user="user",
        anonymous_token="anonymous_token",
        consented_at="consented_at",
        source="source",
        ip_address="ip_address",
        user_agent="user_agent",
        locale="locale",
        request_id="request_id",
        session_key_hash="session_key_hash",
        extra_meta_json="extra_meta_json",
    )


@pytest.mark.django_db
def test_import_core_consents_from_csv_dry_run(tmp_path) -> None:
    _create_flow()
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "current",
                "user": "",
                "anonymous_token": "anon-a",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "127.0.0.1",
                "user_agent": "ua",
                "locale": "ru-RU",
                "request_id": "req-1",
                "session_key_hash": "s-1",
                "extra_meta_json": json.dumps({"migration_batch": "b1"}),
            }
        ],
    )

    summary = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=True,
    )

    assert summary["total_rows"] == 1
    assert summary["imported"] == 0
    assert summary["would_import"] == 1
    assert summary["errors"] == 0
    assert ConsentRecord.objects.count() == 0


@pytest.mark.django_db
def test_import_core_consents_from_csv_imports_and_reports(tmp_path) -> None:
    _create_flow()
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "withdrawn",
                "user": "",
                "anonymous_token": "anon-a",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "127.0.0.1",
                "user_agent": "ua",
                "locale": "ru-RU",
                "request_id": "req-1",
                "session_key_hash": "s-1",
                "extra_meta_json": json.dumps({"migration_batch": "b1"}),
            },
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "unsupported_status",
                "user": "",
                "anonymous_token": "anon-b",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "",
                "user_agent": "",
                "locale": "",
                "request_id": "",
                "session_key_hash": "",
                "extra_meta_json": "{}",
            },
        ],
    )

    summary = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )

    assert summary["total_rows"] == 2
    assert summary["imported"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 0
    assert ConsentRecord.objects.count() == 1
    record = ConsentRecord.objects.get()
    assert record.status == ConsentRecord.Status.WITHDRAWN
    assert ConsentEvent.objects.filter(
        consent_record=record,
        event_type=ConsentEvent.EventType.GIVEN,
    ).exists()
    assert ConsentEvent.objects.filter(
        consent_record=record,
        event_type=ConsentEvent.EventType.WITHDRAWN,
    ).exists()


@pytest.mark.django_db
def test_management_command_import_152fz_core_consents(tmp_path) -> None:
    _create_flow()
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "current",
                "user": "",
                "anonymous_token": "anon-c",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "127.0.0.1",
                "user_agent": "ua",
                "locale": "ru-RU",
                "request_id": "req-1",
                "session_key_hash": "s-1",
                "extra_meta_json": "{}",
            }
        ],
    )
    stdout = StringIO()

    call_command("import_152fz_core_consents", "--csv-path", csv_path, stdout=stdout)

    output = stdout.getvalue()
    assert "rows=1" in output
    assert "imported=1" in output
    assert ConsentRecord.objects.count() == 1


@pytest.mark.django_db
def test_core_import_is_idempotent_for_same_row(tmp_path) -> None:
    _create_flow()
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "current",
                "user": "",
                "anonymous_token": "anon-d",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "127.0.0.1",
                "user_agent": "ua",
                "locale": "ru-RU",
                "request_id": "req-dup",
                "session_key_hash": "s-dup",
                "extra_meta_json": "{}",
            }
        ],
    )
    first = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )
    second = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )
    assert first["imported"] == 1
    assert second["skipped"] == 1
    assert ConsentRecord.objects.count() == 1


@pytest.mark.django_db
def test_core_import_logs_actor_user(tmp_path) -> None:
    _create_flow()
    User = get_user_model()
    operator = User.objects.create_user(username="operator_1", password="x")
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "current",
                "user": "",
                "anonymous_token": "anon-op",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "",
                "user_agent": "",
                "locale": "",
                "request_id": "",
                "session_key_hash": "",
                "extra_meta_json": "{}",
            }
        ],
    )
    import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
        actor_user=operator,
    )
    assert ModuleOperationAuditLog.objects.filter(
        operation_code="service.core.import_consents_csv",
        actor_user=operator,
    ).exists()


@pytest.mark.django_db
def test_core_import_rolls_back_row_when_followup_status_update_fails(
    tmp_path, monkeypatch
) -> None:
    _create_flow()
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "withdrawn",
                "user": "",
                "anonymous_token": "anon-rollback",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "",
                "user_agent": "",
                "locale": "",
                "request_id": "",
                "session_key_hash": "",
                "extra_meta_json": "{}",
            }
        ],
    )

    def _broken_withdraw(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "django_consent_152fz.core.importers.withdraw_consent", _broken_withdraw
    )
    summary = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )

    assert summary["errors"] == 1
    assert ConsentRecord.objects.count() == 0


@pytest.mark.django_db
def test_core_import_is_idempotent_when_consented_at_is_missing(tmp_path) -> None:
    _create_flow()
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "current",
                "user": "",
                "anonymous_token": "anon-no-time",
                "consented_at": "",
                "source": "legacy",
                "ip_address": "127.0.0.1",
                "user_agent": "ua",
                "locale": "ru-RU",
                "request_id": "req-no-time",
                "session_key_hash": "s-no-time",
                "extra_meta_json": "{}",
            }
        ],
    )
    first = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )
    second = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )

    assert first["imported"] == 1
    assert second["skipped"] == 1
    assert ConsentRecord.objects.count() == 1


@pytest.mark.django_db
def test_core_import_is_idempotent_for_stream_larger_than_200_rows(tmp_path) -> None:
    _create_flow()
    rows = [
        {
            "purpose": "newsletter",
            "document_code": "newsletter_doc",
            "status": "current",
            "user": "",
            "anonymous_token": f"anon-large-{index}",
            "consented_at": "2026-03-10T10:00:00+03:00",
            "source": "legacy",
            "ip_address": "127.0.0.1",
            "user_agent": "ua",
            "locale": "ru-RU",
            "request_id": f"req-large-{index}",
            "session_key_hash": f"s-large-{index}",
            "extra_meta_json": "{}",
        }
        for index in range(220)
    ]
    csv_path = _write_csv(tmp_path, rows)

    first = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )
    second = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )

    assert first["imported"] == 220
    assert second["skipped"] == 220
    assert ConsentRecord.objects.count() == 220


@pytest.mark.django_db
def test_core_import_rejects_too_large_extra_meta_json(tmp_path) -> None:
    _create_flow()
    huge_meta = '{"k":"' + ("x" * 70000) + '"}'
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "current",
                "user": "",
                "anonymous_token": "anon-huge-meta",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "",
                "user_agent": "",
                "locale": "",
                "request_id": "",
                "session_key_hash": "",
                "extra_meta_json": huge_meta,
            }
        ],
    )
    summary = import_core_consents_from_csv(
        csv_path=csv_path,
        mapping=_default_mapping(),
        dry_run=False,
    )

    assert summary["errors"] == 1
    assert "too large" in summary["rows"][0]["detail"].lower()
    assert ConsentRecord.objects.count() == 0


@pytest.mark.django_db
def test_management_command_removes_temp_csv_for_adapter_source(
    tmp_path, monkeypatch
) -> None:
    _create_flow()
    temp_csv_path = tmp_path / "core-consent-import-temp.csv"

    def _fake_mkstemp(*args, **kwargs):
        fd = os.open(temp_csv_path, os.O_RDWR | os.O_CREAT)
        return fd, str(temp_csv_path)

    monkeypatch.setattr(
        "django_consent_152fz.management.commands.import_152fz_core_consents.tempfile.mkstemp",
        _fake_mkstemp,
    )
    monkeypatch.setattr(
        "django_consent_152fz.management.commands.import_152fz_core_consents.run_import_adapter",
        lambda code, payload: [
            {
                "purpose": "newsletter",
                "document_code": "newsletter_doc",
                "status": "current",
                "user": "",
                "anonymous_token": "anon-adapter-temp",
                "consented_at": "2026-03-10T10:00:00+03:00",
                "source": "legacy",
                "ip_address": "",
                "user_agent": "",
                "locale": "",
                "request_id": "",
                "session_key_hash": "",
                "extra_meta_json": "{}",
            }
        ],
    )

    stdout = StringIO()
    call_command(
        "import_152fz_core_consents",
        "--adapter-code",
        "demo_adapter",
        "--adapter-payload-json",
        "{}",
        stdout=stdout,
    )

    assert not temp_csv_path.exists()
