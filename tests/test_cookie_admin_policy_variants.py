from __future__ import annotations

from typing import Any, cast

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse

from django_cookies_152fz.models import (
    CookieBannerTextPreset,
    CookieCategory,
    CookiePolicyRevision,
    CookiePolicyTextPreset,
    normalize_categories_snapshot,
)
from django_cookies_152fz.services import (
    ensure_default_cookie_banner_text_presets,
    ensure_default_cookie_policy_text_presets,
)


def _create_superuser():
    user_model = cast(Any, get_user_model())
    return user_model.objects.create_superuser(
        username="cookie-policy-admin",
        email="cookie-policy-admin@example.com",
        password="pass",
    )


def _create_box_policy_revision() -> CookiePolicyRevision:
    category = CookieCategory.objects.create(
        code="necessary_policy_box",
        title="Necessary",
        description="Required",
        is_required=True,
        sort_order=1,
        is_active=True,
    )
    snapshot = normalize_categories_snapshot(
        [
            {
                "code": category.code,
                "title": category.title,
                "description": category.description,
                "is_required": True,
                "sort_order": 1,
            }
        ]
    )
    return CookiePolicyRevision.objects.create(
        version=2001,
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Box policy revision",
        categories_snapshot=snapshot,
        is_active=False,
        is_box_template=True,
    )


@pytest.mark.django_db
def test_cookie_policy_revision_admin_moves_box_variant_actions_to_tools() -> None:
    superuser = _create_superuser()
    request = RequestFactory().get("/admin/")
    request.user = superuser

    policy_admin = admin.site._registry[CookiePolicyRevision]
    actions = cast(dict[str, object], policy_admin.get_actions(request))

    assert "publish_selected_box_policy_variant" not in actions
    assert "create_custom_draft_from_box_policy_variant" not in actions
    assert "clone_selected_revisions_as_drafts" in actions


@pytest.mark.django_db
def test_cookie_policy_revision_admin_changelist_contains_variant_tools() -> None:
    superuser = _create_superuser()
    client = Client()
    assert client.login(username=superuser.username, password="pass")

    response = client.get(
        reverse("admin:django_cookies_152fz_cookiepolicyrevision_changelist")
    )
    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert "publish-box-variant/?variant=short" in content
    assert "publish-box-variant/?variant=full" in content
    assert "create-custom-draft-from-box-variant/?variant=short" in content
    assert "create-custom-draft-from-box-variant/?variant=full" in content


@pytest.mark.django_db
def test_cookie_policy_revision_admin_variant_tool_view_uses_explicit_variant() -> None:
    superuser = _create_superuser()
    _create_box_policy_revision()
    client = Client()
    assert client.login(username=superuser.username, password="pass")

    publish_url = reverse(
        "admin:django_cookies_152fz_cookiepolicyrevision_publish_box_variant"
    )
    response = client.get(f"{publish_url}?variant=short")

    assert response.status_code == 302
    assert CookiePolicyRevision.objects.filter(is_active=True).exists()


@pytest.mark.django_db
def test_cookie_policy_revision_admin_blocks_box_template_modification() -> None:
    superuser = _create_superuser()
    request = RequestFactory().get("/admin/")
    request.user = superuser
    box_revision = _create_box_policy_revision()

    policy_admin = admin.site._registry[CookiePolicyRevision]

    assert policy_admin.has_change_permission(request, obj=box_revision) is False
    assert policy_admin.has_delete_permission(request, obj=box_revision) is False


@pytest.mark.django_db
def test_cookie_policy_text_preset_admin_blocks_box_template_modification() -> None:
    superuser = _create_superuser()
    request = RequestFactory().get("/admin/")
    request.user = superuser
    ensure_default_cookie_policy_text_presets()
    box_preset = CookiePolicyTextPreset.objects.filter(is_box_template=True).first()
    assert box_preset is not None

    preset_admin = admin.site._registry[CookiePolicyTextPreset]

    assert preset_admin.has_change_permission(request, obj=box_preset) is False
    assert preset_admin.has_delete_permission(request, obj=box_preset) is False


@pytest.mark.django_db
def test_cookie_banner_text_preset_admin_blocks_box_template_modification() -> None:
    superuser = _create_superuser()
    request = RequestFactory().get("/admin/")
    request.user = superuser
    ensure_default_cookie_banner_text_presets()
    box_preset = CookieBannerTextPreset.objects.filter(is_box_template=True).first()
    assert box_preset is not None

    preset_admin = admin.site._registry[CookieBannerTextPreset]

    assert preset_admin.has_change_permission(request, obj=box_preset) is False
    assert preset_admin.has_delete_permission(request, obj=box_preset) is False
