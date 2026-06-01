from __future__ import annotations

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from django_cookies_152fz.models import CookieCategory, CookiePolicyRevision
from django_cookies_152fz.services import publish_cookie_policy_revision

COOKIE_ONLY_SETTINGS = {
    "enable_core": False,
    "enable_cookies": True,
    "enable_verified_consents": False,
    "enable_access_policies": False,
    "purposes": {},
}


def _create_cookie_categories() -> None:
    CookieCategory.objects.get_or_create(
        code="necessary",
        defaults={
            "title": "Necessary",
            "description": "Required cookies",
            "is_required": True,
            "sort_order": 1,
        },
    )
    CookieCategory.objects.get_or_create(
        code="analytics",
        defaults={
            "title": "Analytics",
            "description": "Analytics cookies",
            "sort_order": 2,
        },
    )


@override_settings(
    ROOT_URLCONF="tests.urls_cookie_only",
    DJANGO_COOKIES_152FZ=COOKIE_ONLY_SETTINGS,
)
@pytest.mark.django_db
def test_cookie_only_router_include_exposes_preferences_and_banner_urls() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy for cookie-only router",
    )
    client = Client()

    preferences_url = reverse("django_cookies_152fz:cookie_preferences")
    banner_url = reverse("django_cookies_152fz:cookie_banner_action")

    assert preferences_url == "/consent/cookies/"
    assert banner_url == "/consent/cookies/banner/"

    response = client.get(preferences_url)
    assert response.status_code == 200
