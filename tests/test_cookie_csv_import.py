from __future__ import annotations

import csv
import json

import pytest

from django_cookies_152fz.importers import (
    COOKIE_IMPORT_CONTRACT_VERSION,
    CookieImportMapping,
    import_cookie_data_from_csv,
)
from django_cookies_152fz.models import (
    CookieCategory,
    CookieConsentRecord,
    CookiePolicyRevision,
    normalize_categories_snapshot,
)

pytestmark = pytest.mark.django_db


def _create_policy_revision() -> CookiePolicyRevision:
    CookieCategory.objects.update_or_create(
        code="necessary",
        defaults={
            "title": "Necessary",
            "description": "Required",
            "is_required": True,
            "sort_order": 1,
            "is_active": True,
        },
    )
    CookieCategory.objects.update_or_create(
        code="analytics",
        defaults={
            "title": "Analytics",
            "description": "Optional",
            "is_required": False,
            "sort_order": 2,
            "is_active": True,
        },
    )
    snapshot = normalize_categories_snapshot(
        [
            {
                "code": "necessary",
                "title": "Necessary",
                "description": "Required",
                "is_required": True,
                "sort_order": 1,
            },
            {
                "code": "analytics",
                "title": "Analytics",
                "description": "Optional",
                "is_required": False,
                "sort_order": 2,
            },
        ]
    )
    CookiePolicyRevision.objects.update(is_active=False)
    latest = CookiePolicyRevision.objects.order_by("-version").first()
    next_version = (latest.version if latest else 0) + 1
    return CookiePolicyRevision.objects.create(
        version=next_version,
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="cookie policy",
        categories_snapshot=snapshot,
        is_active=True,
        is_box_template=False,
    )


def _mapping() -> CookieImportMapping:
    return CookieImportMapping(
        kind="kind",
        contract_version="contract_version",
        policy_revision_version="policy_revision_version",
        policy_categories_snapshot_json="policy_categories_snapshot_json",
        selected_categories_json="selected_categories_json",
        user="user",
        anonymous_token="anonymous_token",
        source="source",
        ip_address="ip_address",
        user_agent="user_agent",
        locale="locale",
        request_id="request_id",
        session_key_hash="session_key_hash",
        extra_meta_json="extra_meta_json",
        consented_at="consented_at",
        decision_action="decision_action",
        decided_at="decided_at",
        dismissed_at="dismissed_at",
    )


def _consent_row(
    *, revision: CookiePolicyRevision, token: str, extra_meta_json: str = "{}"
) -> dict[str, str]:
    return {
        "kind": "consent",
        "contract_version": COOKIE_IMPORT_CONTRACT_VERSION,
        "policy_revision_version": str(revision.version),
        "policy_categories_snapshot_json": json.dumps(revision.categories_snapshot),
        "selected_categories_json": json.dumps(["necessary"]),
        "user": "",
        "anonymous_token": token,
        "source": "legacy",
        "ip_address": "",
        "user_agent": "",
        "locale": "",
        "request_id": "",
        "session_key_hash": "",
        "extra_meta_json": extra_meta_json,
        "consented_at": "2026-01-01T00:00:00+03:00",
        "decision_action": "",
        "decided_at": "",
        "dismissed_at": "",
    }


def _write_csv(tmp_path, rows: list[dict[str, str]]) -> str:
    path = tmp_path / "cookie_import.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def test_cookie_import_dry_run(tmp_path) -> None:
    revision = _create_policy_revision()
    csv_path = _write_csv(
        tmp_path,
        [_consent_row(revision=revision, token="anon-1")],
    )

    summary = import_cookie_data_from_csv(
        csv_path=csv_path,
        mapping=_mapping(),
        dry_run=True,
    )

    assert summary["would_import"] == 1
    assert CookieConsentRecord.objects.count() == 0


def test_cookie_import_uses_revision_from_csv_even_if_newer_active(tmp_path) -> None:
    old_revision = _create_policy_revision()
    newer_revision = _create_policy_revision()
    assert newer_revision.version > old_revision.version

    csv_path = _write_csv(
        tmp_path,
        [_consent_row(revision=old_revision, token="anon-old-revision")],
    )

    summary = import_cookie_data_from_csv(
        csv_path=csv_path,
        mapping=_mapping(),
        dry_run=False,
    )

    assert summary["imported"] == 1
    record = CookieConsentRecord.objects.get(anonymous_token="anon-old-revision")
    assert record.policy_revision_id == old_revision.pk
    assert record.policy_revision_id != newer_revision.pk


def test_cookie_import_is_idempotent_by_row_fingerprint(tmp_path) -> None:
    revision = _create_policy_revision()
    csv_path = _write_csv(
        tmp_path,
        [_consent_row(revision=revision, token="anon-dedupe")],
    )

    first = import_cookie_data_from_csv(
        csv_path=csv_path,
        mapping=_mapping(),
        dry_run=False,
    )
    second = import_cookie_data_from_csv(
        csv_path=csv_path,
        mapping=_mapping(),
        dry_run=False,
    )

    assert first["imported"] == 1
    assert second["skipped"] == 1
    assert (
        CookieConsentRecord.objects.filter(anonymous_token="anon-dedupe").count() == 1
    )


def test_cookie_import_rejects_oversized_extra_meta_json(tmp_path) -> None:
    revision = _create_policy_revision()
    oversized = "{" + '"x":"' + ("a" * (70 * 1024)) + '"}'
    csv_path = _write_csv(
        tmp_path,
        [
            _consent_row(
                revision=revision, token="anon-oversized", extra_meta_json=oversized
            )
        ],
    )

    summary = import_cookie_data_from_csv(
        csv_path=csv_path,
        mapping=_mapping(),
        dry_run=False,
    )

    assert summary["errors"] == 1
    assert "max JSON size" in summary["rows"][0]["detail"]
    assert (
        CookieConsentRecord.objects.filter(anonymous_token="anon-oversized").count()
        == 0
    )


def test_cookie_import_reserves_import_meta_namespace(tmp_path) -> None:
    revision = _create_policy_revision()
    spoofed_extra_meta = json.dumps(
        {
            "import_meta": {"row_fingerprint": "spoofed"},
            "legacy": {"source": "external"},
        }
    )
    csv_path = _write_csv(
        tmp_path,
        [
            _consent_row(
                revision=revision,
                token="anon-import-meta",
                extra_meta_json=spoofed_extra_meta,
            )
        ],
    )

    summary = import_cookie_data_from_csv(
        csv_path=csv_path,
        mapping=_mapping(),
        dry_run=False,
    )

    assert summary["imported"] == 1
    record = CookieConsentRecord.objects.get(anonymous_token="anon-import-meta")
    import_meta = dict(record.extra_meta or {}).get("import_meta") or {}
    assert import_meta.get("row_fingerprint") != "spoofed"
    assert isinstance(import_meta.get("row_fingerprint"), str)
    assert len(str(import_meta.get("row_fingerprint"))) == 64
