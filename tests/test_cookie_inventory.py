from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from django_cookies_152fz.inventory import (
    build_best_effort_inventory_hints,
    build_inventory_hints_for_registry_items,
    build_registry_mapping_review_queue_from_report,
)
from django_cookies_152fz.models import CookieCategory, CookieRegistryItem


@pytest.fixture
def advisory_found_integrations_fixture() -> list[dict[str, object]]:
    return [
        {
            "code": "ga_loader",
            "provider": "Google Analytics",
            "purpose": "site analytics",
            "src_url": "https://www.google-analytics.com/analytics.js",
            "cookie_names": ["_ga"],
            "current_category_code": "",
        },
        {
            "code": "fb_pixel",
            "provider": "Meta",
            "purpose": "ads remarketing",
            "src_url": "https://connect.facebook.net/en_US/fbevents.js",
            "cookie_names": ["_fbp"],
            "current_category_code": "",
        },
    ]


def test_build_best_effort_inventory_hints_marks_manual_verification(
    advisory_found_integrations_fixture: list[dict[str, object]],
) -> None:
    report = build_best_effort_inventory_hints(
        found_integrations=advisory_found_integrations_fixture
    )
    assert report["mode"] == "best_effort_advisory"
    assert report["requires_manual_verification"] is True
    assert report["total_integrations"] == 2
    suggestions = {
        item["integration_code"]: item["suggested_category"] for item in report["hints"]
    }
    assert suggestions["ga_loader"] == "analytics"
    assert suggestions["fb_pixel"] == "marketing"
    assert all(item["requires_manual_verification"] for item in report["hints"])


@pytest.mark.django_db
def test_build_inventory_hints_for_registry_items() -> None:
    analytics, _ = CookieCategory.objects.update_or_create(
        code="analytics",
        defaults={
            "title": "Analytics",
            "description": "Analytics",
            "is_required": False,
            "is_active": True,
        },
    )
    CookieRegistryItem.objects.create(
        code="metrika",
        category=analytics,
        provider="Yandex Metrika",
        purpose="analytics",
        cookie_names=["_ym_uid"],
        src_url="https://mc.yandex.ru/metrika/tag.js",
        is_active=True,
    )

    report = build_inventory_hints_for_registry_items()

    assert report["source"] == "cookie_registry_items"
    assert report["total_integrations"] == 1
    assert report["hints"][0]["integration_code"] == "metrika"
    assert report["hints"][0]["suggested_category"] == "analytics"
    assert report["registry_mapping_review_queue"][0]["mapping_status"] == "aligned"


@pytest.mark.django_db
def test_build_registry_mapping_review_queue_marks_manual_review() -> None:
    functional, _ = CookieCategory.objects.update_or_create(
        code="functional",
        defaults={
            "title": "Functional",
            "description": "Functional",
            "is_required": False,
            "is_active": True,
        },
    )
    CookieCategory.objects.update_or_create(
        code="analytics",
        defaults={
            "title": "Analytics",
            "description": "Analytics",
            "is_required": False,
            "is_active": True,
        },
    )
    report = build_best_effort_inventory_hints(
        found_integrations=[
            {
                "code": "ga_loader",
                "provider": "Google Analytics",
                "purpose": "site analytics",
                "src_url": "https://www.google-analytics.com/analytics.js",
                "cookie_names": ["_ga"],
                "current_category_code": functional.code,
            }
        ]
    )

    queue = build_registry_mapping_review_queue_from_report(report=report)

    assert queue[0]["mapping_status"] == "requires_manual_review"
    assert queue[0]["requires_manual_verification"] is True
    assert queue[0]["auto_apply_allowed"] is False
    assert queue[0]["suggested_category"] == "analytics"


@pytest.mark.django_db
def test_build_registry_mapping_review_queue_marks_missing_category() -> None:
    CookieCategory.objects.filter(code="marketing").update(is_active=False)
    report = build_best_effort_inventory_hints(
        found_integrations=[
            {
                "code": "ad_pixel",
                "provider": "Ads Vendor",
                "purpose": "marketing",
                "src_url": "https://example.test/pixel.js",
                "cookie_names": ["pixel_cookie"],
                "current_category_code": "",
            }
        ]
    )

    queue = build_registry_mapping_review_queue_from_report(report=report)

    assert queue[0]["mapping_status"] == "requires_manual_review"
    assert queue[0]["suggested_category"] == "marketing"
    assert queue[0]["suggested_category_exists"] is False
    assert queue[0]["suggested_category_id"] is None


@override_settings(
    DJANGO_COOKIES_152FZ={"cookie_inventory": {"enable_registry_hints": False}}
)
def test_inventory_command_respects_disabled_by_default() -> None:
    out = StringIO()
    call_command("inventory_152fz_cookie_integrations", stdout=out)
    assert "disabled by configuration" in out.getvalue()


@pytest.mark.django_db
@override_settings(
    DJANGO_COOKIES_152FZ={"cookie_inventory": {"enable_registry_hints": False}}
)
def test_inventory_command_force_runs_even_when_disabled() -> None:
    analytics, _ = CookieCategory.objects.update_or_create(
        code="analytics",
        defaults={
            "title": "Analytics",
            "description": "Analytics",
            "is_required": False,
            "is_active": True,
        },
    )
    CookieRegistryItem.objects.create(
        code="ga_loader",
        category=analytics,
        provider="Google Analytics",
        purpose="analytics",
        cookie_names=["_ga"],
        src_url="https://www.google-analytics.com/analytics.js",
        is_active=True,
    )

    out = StringIO()
    call_command("inventory_152fz_cookie_integrations", "--force", stdout=out)
    assert "Cookie integration inventory:" in out.getvalue()
