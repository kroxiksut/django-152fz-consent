from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from django_cookies_152fz import retention
from django_cookies_152fz.integration_contract import ConsentError
from django_cookies_152fz.models import (
    CookieCategory,
    CookieConsentEvent,
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


def _create_record(
    *,
    revision: CookiePolicyRevision,
    token: str,
    status: str,
    created_at,
) -> CookieConsentRecord:
    record = CookieConsentRecord.objects.create(
        policy_revision=revision,
        anonymous_token=token,
        selected_categories=["necessary"],
        status=status,
        source="tests.retention",
    )
    CookieConsentRecord.objects.filter(pk=record.pk).update(
        created_at=created_at,
        updated_at=created_at,
    )
    record.refresh_from_db()
    return record


@override_settings(
    DJANGO_COOKIES_152FZ={
        "enable_cookies": True,
        "cookie_retention": {
            "records_older_than_days": 0,
            "records_max_count": 2,
            "events_older_than_days": 0,
            "events_max_count": 0,
            "banner_states_older_than_days": 0,
            "banner_states_max_count": 0,
            "batch_size": 100,
            "protect_current_records": True,
        },
    }
)
def test_retention_max_count_uses_deletable_pool_without_over_deletion() -> None:
    revision = _create_policy_revision()
    now = timezone.now()
    base = now - timedelta(days=20)
    for index in range(10):
        _create_record(
            revision=revision,
            token=f"anon-current-{index}",
            status=CookieConsentRecord.Status.CURRENT,
            created_at=base + timedelta(minutes=index),
        )
    for index in range(5):
        _create_record(
            revision=revision,
            token=f"anon-outdated-{index}",
            status=CookieConsentRecord.Status.OUTDATED,
            created_at=base + timedelta(hours=1, minutes=index),
        )

    summary = retention.cleanup_cookie_audit(now=now)
    records_report = next(
        report for report in summary["models"] if report["model_code"] == "records"
    )

    assert records_report["max_count_candidates"] == 3
    assert records_report["deleted_max_count"] == 3
    assert (
        CookieConsentRecord.objects.filter(
            status=CookieConsentRecord.Status.CURRENT
        ).count()
        == 10
    )
    assert (
        CookieConsentRecord.objects.filter(
            status=CookieConsentRecord.Status.OUTDATED
        ).count()
        == 2
    )


@override_settings(
    DJANGO_COOKIES_152FZ={
        "enable_cookies": True,
        "cookie_retention": {
            "records_older_than_days": 1,
            "records_max_count": 0,
            "events_older_than_days": 0,
            "events_max_count": 0,
            "banner_states_older_than_days": 0,
            "banner_states_max_count": 0,
            "batch_size": 2,
            "protect_current_records": False,
        },
    }
)
def test_retention_does_not_stall_when_delete_step_makes_no_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _create_policy_revision()
    now = timezone.now()
    base = now - timedelta(days=20)
    for index in range(5):
        _create_record(
            revision=revision,
            token=f"anon-protected-{index}",
            status=CookieConsentRecord.Status.OUTDATED,
            created_at=base + timedelta(minutes=index),
        )

    calls = {"count": 0}

    def _always_zero_delete(*, model, ids, using):
        del model, ids, using
        calls["count"] += 1
        return 0

    monkeypatch.setattr(retention, "_delete_ids_resilient", _always_zero_delete)
    summary = retention.cleanup_cookie_audit(now=now)
    records_report = next(
        report for report in summary["models"] if report["model_code"] == "records"
    )

    assert calls["count"] == 3
    assert records_report["deleted_total"] == 0
    assert CookieConsentRecord.objects.count() == 5


@override_settings(
    DJANGO_COOKIES_152FZ={
        "enable_cookies": True,
        "cookie_retention": {
            "records_older_than_days": 0,
            "records_max_count": 0,
            "events_older_than_days": 1,
            "events_max_count": 0,
            "banner_states_older_than_days": 0,
            "banner_states_max_count": 0,
            "batch_size": 100,
            "protect_current_records": False,
        },
    }
)
def test_retention_refuses_event_purge_without_archive_acknowledgement() -> None:
    revision = _create_policy_revision()
    now = timezone.now()
    old_ts = now - timedelta(days=30)
    record = _create_record(
        revision=revision,
        token="anon-event",
        status=CookieConsentRecord.Status.OUTDATED,
        created_at=old_ts,
    )
    event = CookieConsentEvent.objects.create(
        cookie_consent_record=record,
        event_type=CookieConsentEvent.EventType.UPDATED,
        source="tests.retention",
        payload={},
        extra_meta={},
        occurred_at=old_ts,
    )

    with pytest.raises(ConsentError, match="archive sink acknowledgement"):
        retention.cleanup_cookie_audit(now=now)
    assert CookieConsentEvent.objects.filter(pk=event.pk).exists()


@override_settings(
    DJANGO_COOKIES_152FZ={
        "enable_cookies": True,
        "cookie_retention": {
            "records_older_than_days": 0,
            "records_max_count": 3,
            "events_older_than_days": 0,
            "events_max_count": 0,
            "banner_states_older_than_days": 0,
            "banner_states_max_count": 0,
            "batch_size": 100,
            "protect_current_records": True,
        },
    }
)
def test_retention_dry_run_matches_real_max_count_selection() -> None:
    revision = _create_policy_revision()
    now = timezone.now()
    base = now - timedelta(days=5)
    for index in range(7):
        _create_record(
            revision=revision,
            token=f"anon-dry-{index}",
            status=CookieConsentRecord.Status.OUTDATED,
            created_at=base + timedelta(minutes=index),
        )

    dry_summary = retention.cleanup_cookie_audit(now=now, dry_run=True)
    real_summary = retention.cleanup_cookie_audit(now=now)
    dry_records = next(
        report for report in dry_summary["models"] if report["model_code"] == "records"
    )
    real_records = next(
        report for report in real_summary["models"] if report["model_code"] == "records"
    )

    assert dry_records["max_count_candidates"] == real_records["deleted_max_count"]
    assert CookieConsentRecord.objects.count() == 3


@override_settings(
    DJANGO_COOKIES_152FZ={
        "enable_cookies": True,
        "cookie_retention": {
            "records_older_than_days": "oops",
            "records_max_count": 0,
            "events_older_than_days": 0,
            "events_max_count": 0,
            "banner_states_older_than_days": 0,
            "banner_states_max_count": 0,
            "batch_size": 100,
            "protect_current_records": True,
        },
    }
)
def test_retention_validates_settings_before_mutations() -> None:
    revision = _create_policy_revision()
    now = timezone.now()
    _create_record(
        revision=revision,
        token="anon-keep",
        status=CookieConsentRecord.Status.OUTDATED,
        created_at=now - timedelta(days=20),
    )

    with pytest.raises(ValueError, match="records_older_than_days"):
        retention.cleanup_cookie_audit(now=now)
    assert CookieConsentRecord.objects.count() == 1


@override_settings(
    DJANGO_COOKIES_152FZ={
        "enable_cookies": True,
        "cookie_retention": {
            "records_older_than_days": 0,
            "records_max_count": 0,
            "events_older_than_days": 0,
            "events_max_count": 0,
            "banner_states_older_than_days": 0,
            "banner_states_max_count": 0,
            "batch_size": 100,
            "protect_current_records": False,
            "private_signal_paths": [
                "cookie_runtime.is_private_mode",
                "retention_private.is_private_mode",
            ],
            "private_records_older_than_days": 7,
            "private_events_older_than_days": 0,
        },
    }
)
def test_retention_private_signal_uses_only_trusted_namespace() -> None:
    revision = _create_policy_revision()
    now = timezone.now()
    old_ts = now - timedelta(days=20)
    trusted_record = _create_record(
        revision=revision,
        token="anon-private-trusted",
        status=CookieConsentRecord.Status.OUTDATED,
        created_at=old_ts,
    )
    untrusted_record = _create_record(
        revision=revision,
        token="anon-private-untrusted",
        status=CookieConsentRecord.Status.OUTDATED,
        created_at=old_ts,
    )
    CookieConsentRecord.objects.filter(pk=trusted_record.pk).update(
        extra_meta={"retention_private": {"is_private_mode": True}}
    )
    CookieConsentRecord.objects.filter(pk=untrusted_record.pk).update(
        extra_meta={"cookie_runtime": {"is_private_mode": True}}
    )

    summary = retention.cleanup_cookie_audit(now=now)
    records_report = next(
        report for report in summary["models"] if report["model_code"] == "records"
    )

    assert records_report["deleted_total"] == 1
    assert CookieConsentRecord.objects.filter(pk=trusted_record.pk).exists() is False
    assert CookieConsentRecord.objects.filter(pk=untrusted_record.pk).exists() is True
