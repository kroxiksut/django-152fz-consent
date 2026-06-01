from __future__ import annotations

import csv
import logging
from typing import Any, cast

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from django_cookies_152fz.integration_contract import log_module_operation
from django_cookies_152fz.models import (
    CookieAdminSettings,
    CookieBannerState,
    CookieCategory,
    CookieConsentEvent,
    CookieConsentRecord,
    CookiePolicyRevision,
)


def _create_superuser():
    User = cast(Any, get_user_model())
    return User.objects.create_superuser(
        username="cookie-admin",
        email="cookie-admin@example.com",
        password="pass",
    )


@pytest.mark.django_db
def test_cookie_consent_event_admin_is_read_only() -> None:
    superuser = _create_superuser()
    request = RequestFactory().get("/admin/")
    request.user = superuser

    event_admin = admin.site._registry[CookieConsentEvent]

    assert event_admin.has_view_permission(request) is True
    assert event_admin.has_add_permission(request) is False
    assert event_admin.has_change_permission(request) is False
    assert event_admin.has_delete_permission(request) is False


@pytest.mark.django_db
def test_cookie_record_and_banner_state_admins_are_immutable_for_superuser() -> None:
    superuser = _create_superuser()
    request = RequestFactory().get("/admin/")
    request.user = superuser

    record_admin = admin.site._registry[CookieConsentRecord]

    assert record_admin.has_view_permission(request) is True
    assert record_admin.has_add_permission(request) is False
    assert record_admin.has_change_permission(request) is False
    assert record_admin.has_delete_permission(request) is False

    banner_state_admin = admin.site._registry[CookieBannerState]
    assert banner_state_admin.has_view_permission(request) is True
    assert banner_state_admin.has_add_permission(request) is False
    assert banner_state_admin.has_change_permission(request) is False
    assert banner_state_admin.has_delete_permission(request) is False


@pytest.mark.django_db
def test_log_module_operation_writes_structured_cookie_audit_log(caplog) -> None:
    superuser = _create_superuser()
    with caplog.at_level(logging.INFO, logger="django_cookies_152fz.operations"):
        log_module_operation(
            operation_code="admin.cookies.publish_banner_revision",
            source="tests.cookie.admin",
            summary="Published banner revision.",
            actor_user=superuser,
            payload={"revision": 5},
            result={"status": "ok"},
        )

    assert "admin.cookies.publish_banner_revision" in caplog.text
    assert "tests.cookie.admin" in caplog.text


@pytest.mark.django_db
def test_cookie_consent_event_admin_uses_selected_csv_delimiter() -> None:
    superuser = _create_superuser()
    category = CookieCategory.objects.create(
        code="necessary",
        title="Необходимые",
        is_required=True,
        sort_order=1,
        is_active=True,
    )
    policy = CookiePolicyRevision.objects.create(
        version=1,
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Policy",
        categories_snapshot=[
            {
                "code": category.code,
                "title": category.title,
                "description": "",
                "is_required": True,
                "sort_order": 1,
            }
        ],
        is_active=True,
    )
    record = CookieConsentRecord.objects.create(
        anonymous_token="anon-cookie-export",
        policy_revision=policy,
        selected_categories=[category.code],
        status=CookieConsentRecord.Status.CURRENT,
        source="tests.admin",
    )
    event = CookieConsentEvent.objects.create(
        cookie_consent_record=record,
        event_type=CookieConsentEvent.EventType.ACCEPTED,
        source="tests.admin",
        payload={"ok": True},
    )
    CookieAdminSettings.objects.create(
        csv_export_delimiter=CookieAdminSettings.CsvDelimiter.SEMICOLON
    )

    request = RequestFactory().post("/admin/")
    request.user = superuser
    event_admin = admin.site._registry[CookieConsentEvent]

    response = cast(Any, event_admin).export_selected_records(
        request,
        CookieConsentEvent.objects.filter(pk=event.pk),
    )

    content = response.content.decode("utf-8")
    header = content.splitlines()[0]
    row = content.splitlines()[1]

    assert response.status_code == 200
    assert ";" in header
    assert ";" in row
    assert "cookie_consent_record_id" in header
    assert str(record.pk) in row


@pytest.mark.django_db
def test_cookie_consent_event_admin_sanitizes_formula_cells_in_csv_export() -> None:
    superuser = _create_superuser()
    category = CookieCategory.objects.create(
        code="necessary_formula",
        title="Necessary",
        is_required=True,
        sort_order=1,
        is_active=True,
    )
    policy = CookiePolicyRevision.objects.create(
        version=77,
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Policy",
        categories_snapshot=[
            {
                "code": category.code,
                "title": category.title,
                "description": "",
                "is_required": True,
                "sort_order": 1,
            }
        ],
        is_active=True,
    )
    record = CookieConsentRecord.objects.create(
        anonymous_token="anon-cookie-export-formula",
        policy_revision=policy,
        selected_categories=[category.code],
        status=CookieConsentRecord.Status.CURRENT,
        source="tests.admin",
    )
    event = CookieConsentEvent.objects.create(
        cookie_consent_record=record,
        event_type=CookieConsentEvent.EventType.ACCEPTED,
        source='=HYPERLINK("https://evil.example")',
        user_agent="+curl/8.0",
        payload={"formula": "-1+2"},
        extra_meta={"formula": "-2+3"},
    )

    request = RequestFactory().post("/admin/")
    request.user = superuser
    event_admin = admin.site._registry[CookieConsentEvent]
    response = cast(Any, event_admin).export_selected_records(
        request,
        CookieConsentEvent.objects.filter(pk=event.pk),
    )

    content = response.content.decode("utf-8")
    parsed = list(csv.reader(content.splitlines()))
    data_row = parsed[1]
    # source and user_agent columns are 3 and 5
    assert data_row[3].startswith("'=")
    assert data_row[5].startswith("'+")
