from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from django_cookies_152fz.models import (
    CookieCategory,
    CookieConsentEvent,
    CookieConsentRecord,
    CookiePolicyRevision,
    normalize_categories_snapshot,
)
from django_cookies_152fz.services import accept_cookie_preferences

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
    return CookiePolicyRevision.objects.create(
        version=(latest.version if latest else 0) + 1,
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="cookie policy",
        categories_snapshot=snapshot,
        is_active=True,
        is_box_template=False,
    )


def test_current_record_unique_for_anonymous_subject() -> None:
    revision = _create_policy_revision()
    CookieConsentRecord.objects.create(
        policy_revision=revision,
        anonymous_token="anon-unique-subject",
        selected_categories=["necessary"],
        status=CookieConsentRecord.Status.CURRENT,
        source="tests",
    )

    with pytest.raises(ValidationError, match="cookie_rec_current_token_unique"):
        CookieConsentRecord.objects.create(
            policy_revision=revision,
            anonymous_token="anon-unique-subject",
            selected_categories=["necessary", "analytics"],
            status=CookieConsentRecord.Status.CURRENT,
            source="tests",
        )

    CookieConsentRecord.objects.create(
        policy_revision=revision,
        anonymous_token="anon-unique-subject",
        selected_categories=["necessary"],
        status=CookieConsentRecord.Status.OUTDATED,
        source="tests",
    )


def test_current_record_unique_for_authenticated_subject() -> None:
    revision = _create_policy_revision()
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="cookie-current-user",
        email="cookie-current-user@example.com",
        password="pass",
    )
    CookieConsentRecord.objects.create(
        user=user,
        policy_revision=revision,
        anonymous_token="",
        selected_categories=["necessary"],
        status=CookieConsentRecord.Status.CURRENT,
        source="tests",
    )

    with pytest.raises(ValidationError, match="cookie_rec_current_user_unique"):
        CookieConsentRecord.objects.create(
            user=user,
            policy_revision=revision,
            anonymous_token="",
            selected_categories=["necessary", "analytics"],
            status=CookieConsentRecord.Status.CURRENT,
            source="tests",
        )


def test_accept_preferences_keeps_single_current_record_per_subject() -> None:
    _create_policy_revision()
    accept_cookie_preferences(
        anonymous_token="anon-accept-uniqueness",
        selected_categories=["necessary"],
        source="tests.first",
    )
    accept_cookie_preferences(
        anonymous_token="anon-accept-uniqueness",
        selected_categories=["analytics"],
        source="tests.second",
    )

    subject_records = CookieConsentRecord.objects.filter(
        anonymous_token="anon-accept-uniqueness"
    )
    assert (
        subject_records.filter(status=CookieConsentRecord.Status.CURRENT).count() == 1
    )
    assert (
        subject_records.filter(status=CookieConsentRecord.Status.OUTDATED).count() == 1
    )


def test_cookie_consent_record_validates_extra_meta_contract() -> None:
    revision = _create_policy_revision()

    with pytest.raises(ValidationError) as not_object_error:
        CookieConsentRecord.objects.create(
            policy_revision=revision,
            anonymous_token="anon-meta-not-object",
            selected_categories=["necessary"],
            status=CookieConsentRecord.Status.CURRENT,
            source="tests",
            extra_meta=["not-object"],
        )
    assert "extra_meta" in not_object_error.value.message_dict

    with pytest.raises(ValidationError) as reserved_error:
        CookieConsentRecord.objects.create(
            policy_revision=revision,
            anonymous_token="anon-meta-reserved",
            selected_categories=["necessary"],
            status=CookieConsentRecord.Status.CURRENT,
            source="tests",
            extra_meta={"import_meta": {"row_fingerprint": "spoofed"}},
        )
    assert "extra_meta" in reserved_error.value.message_dict

    with pytest.raises(ValidationError) as oversized_error:
        CookieConsentRecord.objects.create(
            policy_revision=revision,
            anonymous_token="anon-meta-oversized",
            selected_categories=["necessary"],
            status=CookieConsentRecord.Status.CURRENT,
            source="tests",
            extra_meta={"blob": "x" * (70 * 1024)},
        )
    assert "extra_meta" in oversized_error.value.message_dict


def test_cookie_consent_event_validates_payload_and_extra_meta_contract() -> None:
    revision = _create_policy_revision()
    record = CookieConsentRecord.objects.create(
        policy_revision=revision,
        anonymous_token="anon-event-validation",
        selected_categories=["necessary"],
        status=CookieConsentRecord.Status.CURRENT,
        source="tests",
    )

    with pytest.raises(ValidationError) as payload_type_error:
        record.events.create(
            event_type=CookieConsentEvent.EventType.ACCEPTED,
            source="tests",
            payload="not-object",
        )
    assert "payload" in payload_type_error.value.message_dict

    with pytest.raises(ValidationError) as payload_reserved_error:
        record.events.create(
            event_type=CookieConsentEvent.EventType.ACCEPTED,
            source="tests",
            payload={"retention_private": {"is_private_mode": True}},
        )
    assert "payload" in payload_reserved_error.value.message_dict

    with pytest.raises(ValidationError) as extra_meta_reserved_error:
        record.events.create(
            event_type=CookieConsentEvent.EventType.ACCEPTED,
            source="tests",
            payload={},
            extra_meta={"import_meta": {"row_fingerprint": "spoofed"}},
        )
    assert "extra_meta" in extra_meta_reserved_error.value.message_dict
