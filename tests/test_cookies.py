from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.template import RequestContext, Template
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from django_consent_152fz.integrations import (
    reset_hooks,
)
from django_cookies_152fz.integration_contract import (
    ANONYMOUS_TOKEN_COOKIE_NAME as COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME,
)
from django_cookies_152fz.integration_contract import constants as cookie_constants
from django_cookies_152fz.models import (
    CookieAdminSettings,
    CookieBannerRevision,
    CookieBannerState,
    CookieCategory,
    CookieConsentEvent,
    CookieConsentRecord,
    CookiePolicyRevision,
    CookiePolicyRevisionRegistryItem,
    CookiePolicyTextPreset,
    CookieRegistryItem,
)
from django_cookies_152fz.services import (
    COOKIE_POLICY_REVISION_TEXT_RU_FULL,
    COOKIE_POLICY_REVISION_TEXT_RU_SHORT,
    DEFAULT_COOKIE_POLICY_REVISION_TEXT_RU,
    accept_cookie_preferences,
    bootstrap_default_cookie_policy_revision,
    create_custom_cookie_policy_draft_from_variant,
    ensure_default_cookie_policy_variants,
    get_cookie_banner_configuration,
    get_cookie_banner_state,
    get_cookie_banner_text_presets,
    get_cookie_policy_text_variants,
    get_cookie_requirements,
    get_cookie_status,
    publish_box_cookie_policy_variant,
    publish_cookie_banner_revision,
    publish_cookie_policy_revision,
    sync_cookie_policy_revision_registry_items,
)

pytestmark = pytest.mark.django_db

COOKIE_SETTINGS = {
    "enable_core": True,
    "enable_cookies": True,
    "enable_verified_consents": False,
    "enable_access_policies": False,
    "purposes": {},
}
COOKIE_ONLY_SETTINGS = {
    "enable_core": False,
    "enable_cookies": True,
    "enable_verified_consents": False,
    "enable_access_policies": False,
    "purposes": {},
}
COOKIE_REASK_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "reask_after_days": 30,
    },
}
COOKIE_RUNTIME_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_runtime": {
        "preview_param": "cookie_preview",
        "custom_css_url": "/static/project/cookies.css",
        "custom_js_url": "/static/project/cookies.js",
    },
}
COOKIE_RUNTIME_SHARED_SUBDOMAIN_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_runtime": {
        "shared_subdomain": True,
        "cookie_domain": ".example.test",
        "site_domain": "consent.example.test",
    },
}
COOKIE_RUNTIME_USER_AGENT_OFF_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_runtime": {
        "user_agent_mode": "off",
    },
}
COOKIE_RUNTIME_USER_AGENT_UNIQUE_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_runtime": {
        "user_agent_mode": "unique",
    },
}


def _geo_signal_hook(*, request) -> str:
    if request.headers.get("X-Test-Geo") == "RU":
        return "ru"
    return "unknown"


COOKIE_RUNTIME_GEO_SETTINGS = {
    **COOKIE_RUNTIME_SHARED_SUBDOMAIN_SETTINGS,
    "cookie_runtime": {
        **COOKIE_RUNTIME_SHARED_SUBDOMAIN_SETTINGS["cookie_runtime"],
        "geo_signal_hook": _geo_signal_hook,
    },
}
COOKIE_BANNER_VARIANT_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "banner_variant": "modal",
        "consent_ui_variant": "inline",
        "reconsent_notice_variant": "alert",
        "text_preset": "ru_formal",
        "bootstrap_initial_revision": False,
    },
}
COOKIE_BANNER_NO_FOOTER_LINK_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "show_launcher": False,
        "show_preferences_link": False,
    },
}
COOKIE_BANNER_EMBEDDED_PREFERENCES_TEMPLATE_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "preferences_page_template": "project/cookie_preferences_page.html",
    },
}
COOKIE_BANNER_MISSING_PREFERENCES_TEMPLATE_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "preferences_page_template": "project/missing_cookie_preferences_page.html",
    },
}
COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "show_empty_category_block": True,
    },
}
COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_WITH_ACTION_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "show_empty_category_block": True,
        "show_customize_action_without_optional": True,
    },
}
COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_WITH_TEXT_SETTINGS = {
    **COOKIE_SETTINGS,
    "cookie_banner": {
        "show_empty_category_block": True,
        "empty_category_block_text": "Дополнительные категории сейчас недоступны.",
    },
}


@pytest.fixture(autouse=True)
def _reset_integration_hooks():
    reset_hooks()
    yield
    reset_hooks()


def _create_cookie_categories() -> None:
    CookieCategory.objects.all().delete()
    CookieCategory.objects.create(
        code="necessary",
        title="Necessary",
        description="Required cookies",
        is_required=True,
        sort_order=1,
    )
    CookieCategory.objects.create(
        code="analytics",
        title="Analytics",
        description="Analytics cookies",
        sort_order=2,
    )
    CookieCategory.objects.create(
        code="marketing",
        title="Marketing",
        description="Marketing cookies",
        sort_order=3,
    )


def _create_required_only_cookie_category() -> None:
    CookieCategory.objects.all().delete()
    CookieCategory.objects.create(
        code="necessary",
        title="Necessary",
        description="Required cookies",
        is_required=True,
        sort_order=1,
    )


def _create_superuser():
    User = get_user_model()
    return User.objects.create_superuser(
        username="cookie-admin",
        email="cookie-admin@example.com",
        password="pass",
    )


def _create_cookie_registry_item(
    *,
    code: str,
    category_code: str,
    provider: str = "Vendor",
    purpose: str = "Runtime metadata",
    retention: str = "session",
    cookie_names: list[str] | None = None,
    src_url: str = "",
    clear_strategy: str = CookieRegistryItem.ClearStrategy.NONE,
    is_active: bool = True,
) -> CookieRegistryItem:
    category = CookieCategory.objects.get(code=category_code)
    return CookieRegistryItem.objects.create(
        code=code,
        category=category,
        provider=provider,
        purpose=purpose,
        retention=retention,
        cookie_names=cookie_names or [],
        src_url=src_url,
        clear_strategy=clear_strategy,
        is_active=is_active,
    )


@pytest.mark.django_db
def test_publish_cookie_policy_revision_marks_previous_record_outdated() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy v1",
    )
    record = accept_cookie_preferences(
        anonymous_token="anon-cookie",
        selected_categories=["analytics"],
        audit_context={"source": "test.cookies"},
    )

    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy v2",
    )

    record.refresh_from_db()
    status = get_cookie_status(anonymous_token="anon-cookie")

    assert record.status == CookieConsentRecord.Status.OUTDATED
    assert status["status"] == CookieConsentRecord.Status.OUTDATED
    assert record.events.filter(
        event_type=CookieConsentEvent.EventType.OUTDATED
    ).exists()


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_ONLY_SETTINGS)
@pytest.mark.django_db
def test_accept_cookie_preferences_works_in_cookies_only_mode() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy standalone",
    )

    record = accept_cookie_preferences(
        anonymous_token="anon-only",
        selected_categories=["marketing"],
        audit_context={"source": "test.cookies_only"},
    )

    assert record.user_id is None
    assert record.status == CookieConsentRecord.Status.CURRENT
    assert set(record.selected_categories) == {"necessary", "marketing"}
    assert record.events.filter(
        event_type=CookieConsentEvent.EventType.ACCEPTED
    ).exists()


@pytest.mark.django_db
def test_publish_cookie_policy_revision_snapshots_registry_items() -> None:
    _create_cookie_categories()
    item = _create_cookie_registry_item(
        code="ga4",
        category_code="analytics",
        provider="Google",
        purpose="Analytics runtime",
        retention="13 months",
        cookie_names=["_ga", "_gid"],
        src_url="https://www.googletagmanager.com/gtag/js?id=G-TEST",
        clear_strategy=CookieRegistryItem.ClearStrategy.BEST_EFFORT_DELETE,
    )

    revision = publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy with registry",
    )

    snapshots = list(
        CookiePolicyRevisionRegistryItem.objects.filter(policy_revision=revision)
    )
    assert len(snapshots) == 1
    assert snapshots[0].registry_item_id == item.pk
    assert snapshots[0].registry_code == "ga4"
    assert snapshots[0].provider == "Google"

    item.provider = "Changed provider"
    item.purpose = "Changed purpose"
    item.save()

    requirements = get_cookie_requirements(anonymous_token="anon-registry")
    assert requirements["registry_items"] == [
        {
            "code": "ga4",
            "category_code": "analytics",
            "category_title": "Analytics",
            "category_is_required": False,
            "provider": "Google",
            "purpose": "Analytics runtime",
            "retention": "13 months",
            "cookie_names": ["_ga", "_gid"],
            "src_url": "https://www.googletagmanager.com/gtag/js?id=G-TEST",
            "clear_strategy": "best_effort_delete",
        }
    ]


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_requirements_fallback_to_live_registry_for_legacy_revision() -> None:
    _create_cookie_categories()
    _create_cookie_registry_item(
        code="yandex_metrica",
        category_code="analytics",
        provider="Yandex",
        purpose="Audience analytics",
        retention="400 days",
        cookie_names=["_ym_uid"],
        src_url="https://mc.yandex.ru/metrika/tag.js",
        clear_strategy=CookieRegistryItem.ClearStrategy.BEST_EFFORT_DELETE,
    )
    CookiePolicyRevision.objects.create(
        version=1,
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Legacy cookie policy",
        categories_snapshot=[
            {
                "code": "necessary",
                "title": "Necessary",
                "description": "Required cookies",
                "is_required": True,
                "sort_order": 1,
            },
            {
                "code": "analytics",
                "title": "Analytics",
                "description": "Analytics cookies",
                "is_required": False,
                "sort_order": 2,
            },
        ],
        is_active=True,
    )

    requirements = get_cookie_requirements(anonymous_token="anon-legacy-registry")

    assert requirements["registry_items"] == [
        {
            "code": "yandex_metrica",
            "category_code": "analytics",
            "category_title": "Analytics",
            "category_is_required": False,
            "provider": "Yandex",
            "purpose": "Audience analytics",
            "retention": "400 days",
            "cookie_names": ["_ym_uid"],
            "src_url": "https://mc.yandex.ru/metrika/tag.js",
            "clear_strategy": "best_effort_delete",
        }
    ]


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_sync_cookie_policy_revision_registry_items_rebuilds_snapshot() -> None:
    _create_cookie_categories()
    revision = publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy sync registry",
    )
    assert revision.registry_items.count() == 0

    _create_cookie_registry_item(
        code="retargeting_pixel",
        category_code="marketing",
        provider="AdVendor",
        purpose="Remarketing pixel",
        retention="90 days",
        cookie_names=["_adv"],
        src_url="https://cdn.example.test/pixel.js",
        clear_strategy=CookieRegistryItem.ClearStrategy.ADAPTER_HOOK,
    )

    sync_cookie_policy_revision_registry_items(policy_revision=revision)

    assert revision.registry_items.count() == 1
    snapshot = revision.registry_items.get()
    assert snapshot.registry_code == "retargeting_pixel"
    assert snapshot.category_code == "marketing"
    assert snapshot.clear_strategy == "adapter_hook"


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
def test_cookie_registry_item_rejects_executable_src_snippet() -> None:
    _create_cookie_categories()

    with pytest.raises(ValidationError):
        _create_cookie_registry_item(
            code="bad_runtime",
            category_code="analytics",
            src_url="javascript:alert('xss')",
        )


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.parametrize(
    "unsafe_src_url",
    [
        "data:text/javascript,alert(1)",
        "vbscript:msgbox('xss')",
        "blob:https://example.test/123",
        "//cdn.example.test/script.js",
        "static/script.js",
    ],
)
def test_cookie_registry_item_rejects_non_allowlisted_src_url(
    unsafe_src_url: str,
) -> None:
    _create_cookie_categories()

    with pytest.raises(ValidationError):
        _create_cookie_registry_item(
            code="bad_runtime_allowlist",
            category_code="analytics",
            src_url=unsafe_src_url,
        )


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_requirements_runtime_allows_current_categories_only() -> None:
    _create_cookie_categories()
    _create_cookie_registry_item(
        code="ga4_runtime_current",
        category_code="analytics",
        provider="Google",
        purpose="Analytics runtime",
        retention="13 months",
        cookie_names=["_ga"],
        src_url="https://www.googletagmanager.com/gtag/js?id=G-RUNTIME",
        clear_strategy=CookieRegistryItem.ClearStrategy.BEST_EFFORT_DELETE,
    )
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy runtime current",
    )
    accept_cookie_preferences(
        anonymous_token="anon-runtime-current",
        selected_categories=["analytics"],
        audit_context={"source": "test.cookies.runtime"},
    )

    requirements = get_cookie_requirements(anonymous_token="anon-runtime-current")
    runtime = requirements["runtime"]

    assert runtime["enabled"] is True
    assert runtime["status"] == CookieConsentRecord.Status.CURRENT
    assert runtime["strict_default_deny"] is True
    assert runtime["consent_allows_runtime"] is True
    assert set(runtime["allowed_categories"]) == {"necessary", "analytics"}
    assert runtime["event_contract"]["version"] == "1.0"
    assert runtime["event_contract"]["namespace"] == "dz152fz"
    assert (
        runtime["event_contract"]["events"]["banner_action_submitted"]
        == "dz152fz:cookie-banner:action-submitted"
    )
    assert [item["code"] for item in runtime["script_items"]] == ["ga4_runtime_current"]
    assert [item["code"] for item in runtime["cleanup_items"]] == [
        "ga4_runtime_current"
    ]


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_requirements_runtime_blocks_outdated_optional_scripts() -> None:
    _create_cookie_categories()
    _create_cookie_registry_item(
        code="ga4_runtime_outdated",
        category_code="analytics",
        provider="Google",
        purpose="Analytics runtime",
        retention="13 months",
        cookie_names=["_ga"],
        src_url="https://www.googletagmanager.com/gtag/js?id=G-OUTDATED",
        clear_strategy=CookieRegistryItem.ClearStrategy.BEST_EFFORT_DELETE,
    )
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy runtime v1",
    )
    accept_cookie_preferences(
        anonymous_token="anon-runtime-outdated",
        selected_categories=["analytics"],
        audit_context={"source": "test.cookies.runtime"},
    )
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy runtime v2",
    )

    requirements = get_cookie_requirements(anonymous_token="anon-runtime-outdated")
    runtime = requirements["runtime"]

    assert runtime["status"] == CookieConsentRecord.Status.OUTDATED
    assert runtime["consent_allows_runtime"] is False
    assert runtime["allowed_categories"] == []
    assert set(runtime["selected_categories"]) == {"necessary", "analytics"}
    assert [item["code"] for item in runtime["script_items"]] == [
        "ga4_runtime_outdated"
    ]


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
def test_cookie_preferences_page_renders_choice_state_controls_for_accessibility() -> (
    None
):
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy page choice state",
    )
    client = Client()

    response = client.get(reverse("django_cookies_152fz:cookie_preferences"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "data-cookie-choice-root" in content
    assert 'data-cookie-choice-mode="preferences"' in content
    assert 'data-cookie-choice-action="accept_all"' in content
    assert 'data-cookie-choice-action="reject_all"' in content
    assert 'data-cookie-choice-action="required_only"' in content
    assert 'data-cookie-choice-action="custom"' in content
    assert "data-cookie-choice-reject-label=" in content
    assert "data-cookie-choice-indicator" in content
    assert "data-cookie-choice-status" in content
    assert 'aria-live="polite"' in content
    assert 'aria-pressed="false"' in content


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_hides_customize_block_when_optional_categories_absent_by_default() -> (
    None
):
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert 'id="dz152fz-cookie-banner-custom"' not in rendered
    assert "data-cookie-banner-open-custom" not in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_can_show_empty_customize_block_without_optional_categories() -> (
    None
):
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert 'id="dz152fz-cookie-banner-custom"' in rendered
    assert "data-cookie-banner-open-custom" not in rendered


@override_settings(
    DJANGO_COOKIES_152FZ=COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_WITH_ACTION_SETTINGS
)
@pytest.mark.django_db
def test_cookie_banner_can_show_customize_action_without_optional_categories() -> None:
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert 'id="dz152fz-cookie-banner-custom"' in rendered
    assert "data-cookie-banner-open-custom" in rendered


@override_settings(
    DJANGO_COOKIES_152FZ=COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_WITH_TEXT_SETTINGS
)
@pytest.mark.django_db
def test_cookie_banner_uses_configured_empty_category_block_text() -> None:
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "Дополнительные категории сейчас недоступны." in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_admin_override_can_show_customize_action_without_optional() -> (
    None
):
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    CookieAdminSettings.objects.create(
        show_customize_action_without_optional_override=True
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "data-cookie-banner-open-custom" in rendered


@override_settings(
    DJANGO_COOKIES_152FZ=COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_WITH_TEXT_SETTINGS
)
@pytest.mark.django_db
def test_cookie_banner_admin_override_text_has_priority_over_settings() -> None:
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    CookieAdminSettings.objects.create(
        empty_category_block_text_override="Текст из админки."
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "Текст из админки." in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_preferences_page_hides_customize_controls_without_optional_categories() -> (
    None
):
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    client = Client()

    response = client.get(reverse("django_cookies_152fz:cookie_preferences"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert 'data-cookie-choice-action="custom"' not in content
    assert 'name="banner_action" value="save_custom"' not in content


@override_settings(
    DJANGO_COOKIES_152FZ=COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK_WITH_TEXT_SETTINGS
)
@pytest.mark.django_db
def test_cookie_preferences_page_can_show_empty_optional_block_text() -> None:
    _create_required_only_cookie_category()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy required only",
    )
    client = Client()

    response = client.get(reverse("django_cookies_152fz:cookie_preferences"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Дополнительные категории сейчас недоступны." in content

@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_preferences_page_no_js_flow_can_save_without_client_side_fields() -> (
    None
):
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy no js page",
    )
    client = Client()

    response = client.post(
        reverse("django_cookies_152fz:cookie_preferences"),
        data={
            "selected_categories": ["analytics"],
            "next": "/no-js/",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == "/no-js/"
    record = CookieConsentRecord.objects.get()
    assert set(record.selected_categories) == {"necessary", "analytics"}
    assert record.status == CookieConsentRecord.Status.CURRENT


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
def test_cookie_banner_configuration_uses_active_revision_and_deactivates_previous() -> (
    None
):
    _create_cookie_categories()
    first_revision = publish_cookie_banner_revision(
        launcher_label="Р РЋРЎвЂљР В°РЎР‚РЎвЂ№Р Вµ Р Р…Р В°РЎРѓРЎвЂљРЎР‚Р С•Р в„–Р С”Р С‘ cookie",
        theme_variant=CookieBannerRevision.ThemeVariant.LIGHT,
    )
    second_revision = publish_cookie_banner_revision(
        launcher_label="Р Р€Р С—РЎР‚Р В°Р Р†Р В»Р ВµР Р…Р С‘Р Вµ cookie",
        title_text="Р РЋР С•Р С–Р В»Р В°РЎРѓРЎС“Р в„–РЎвЂљР Вµ Р С”Р В°РЎвЂљР ВµР С–Р С•РЎР‚Р С‘Р С‘ cookie Р Т‘Р В»РЎРЏ РЎРѓР В°Р в„–РЎвЂљР В°.",
        layout_variant=CookieBannerRevision.LayoutVariant.WIDE,
        theme_variant=CookieBannerRevision.ThemeVariant.CONTRAST,
        desktop_position=CookieBannerRevision.DesktopPosition.BOTTOM_LEFT,
        mobile_position=CookieBannerRevision.MobilePosition.TOP,
    )

    first_revision.refresh_from_db()
    configuration = get_cookie_banner_configuration()

    assert first_revision.is_active is False
    assert configuration["revision_id"] == second_revision.pk
    assert configuration["revision_version"] == second_revision.version
    assert configuration["launcher_label"] == "Р Р€Р С—РЎР‚Р В°Р Р†Р В»Р ВµР Р…Р С‘Р Вµ cookie"
    assert configuration["layout_variant"] == "wide"
    assert configuration["theme_variant"] == "contrast"
    assert configuration["desktop_position"] == "bottom_left"
    assert configuration["mobile_position"] == "top"
    assert configuration["show_close_control"] is True
    assert configuration["show_reject_action"] is False
    assert configuration["mobile_show_reject_action"] is None
    assert configuration["mobile_overrides"]["show_reject_action"] is False
    assert configuration["mobile_overrides"]["banner_variant"] == "modal"
    assert configuration["blocking_mode_until_choice"] is False
    assert configuration["hide_launcher_after_decision"] is False
    assert configuration["keep_visible_after_accept_all"] is False
    assert configuration["keep_visible_after_required_only"] is False
    assert configuration["keep_visible_after_save_custom"] is False


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_publish_cookie_banner_revision_does_not_outdate_cookie_consents() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy stable",
    )
    record = accept_cookie_preferences(
        anonymous_token="anon-banner-config",
        selected_categories=["analytics"],
        audit_context={"source": "test.cookies.banner_revision"},
    )

    publish_cookie_banner_revision(
        launcher_label="Р СџР В°РЎР‚Р В°Р СР ВµРЎвЂљРЎР‚РЎвЂ№ cookie",
        description_text="Р СњР В°РЎРѓРЎвЂљРЎР‚Р С•Р в„–РЎвЂљР Вµ Р С”Р В°РЎвЂљР ВµР С–Р С•РЎР‚Р С‘Р С‘ cookie Р В±Р ВµР В· Р С‘Р В·Р СР ВµР Р…Р ВµР Р…Р С‘РЎРЏ РЎР‚Р ВµР Т‘Р В°Р С”РЎвЂ Р С‘Р С‘ Р С—Р С•Р В»Р С‘РЎвЂљР С‘Р С”Р С‘.",
    )

    record.refresh_from_db()
    status = get_cookie_status(anonymous_token="anon-banner-config")

    assert record.status == CookieConsentRecord.Status.CURRENT
    assert status["status"] == CookieConsentRecord.Status.CURRENT
    assert not record.events.filter(
        event_type=CookieConsentEvent.EventType.OUTDATED
    ).exists()


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
def test_cookie_banner_tag_renders_reject_action_choice_contract_when_enabled() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy banner reject contract",
    )
    publish_cookie_banner_revision(show_reject_action=True)
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert 'data-cookie-choice-reject-label="' in rendered
    assert 'data-cookie-choice-initial-state="accept_all"' in rendered
    assert 'data-cookie-choice-action="reject_all"' in rendered
    assert 'value="reject_all"' in rendered


@override_settings(
    DJANGO_COOKIES_152FZ={
        **COOKIE_SETTINGS,
        "cookie_banner": {"show_preferences_link": True},
    }
)
@pytest.mark.django_db
def test_cookie_banner_tag_renders_published_texts_and_presentation_attrs() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy banner presentation",
    )
    publish_cookie_banner_revision(
        launcher_label="Управление cookie",
        title_text="Разрешите только нужные категории cookie.",
        description_text="Ненужные скрипты останутся отключёнными до вашего выбора.",
        accept_all_label="Разрешить всё",
        required_only_label="Оставить обязательные",
        customize_label="Настроить вручную",
        custom_section_summary="Точный выбор категорий",
        save_custom_label="Сохранить настройки",
        preferences_link_label="Открыть полные настройки",
        dismiss_label="Закрыть баннер",
        close_tooltip_text="Закрыть окно cookie-баннера",
        close_aria_label="Закрыть окно cookie-баннера",
        close_control_placement=CookieBannerRevision.CloseControlPlacement.RIGHT,
        noscript_text="Без JavaScript откройте",
        noscript_link_label="настройки cookie",
        layout_variant=CookieBannerRevision.LayoutVariant.WIDE,
        theme_variant=CookieBannerRevision.ThemeVariant.CONTRAST,
        desktop_position=CookieBannerRevision.DesktopPosition.CENTER,
        mobile_position=CookieBannerRevision.MobilePosition.BOTTOM_FULLWIDTH,
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "Управление cookie" in rendered
    assert "Разрешить всё" in rendered
    assert "Настроить вручную" in rendered
    assert "Открыть полные настройки" in rendered
    assert "Закрыть окно cookie-баннера" not in rendered
    assert 'data-cookie-banner-layout="wide"' in rendered
    assert 'data-cookie-banner-theme="contrast"' in rendered
    assert 'data-cookie-banner-desktop-position="center"' in rendered
    assert 'data-cookie-banner-mobile-position="bottom_fullwidth"' in rendered
    assert 'data-cookie-banner-close-placement="right"' in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_BANNER_VARIANT_SETTINGS)
def test_publish_cookie_banner_revision_keeps_text_preset_independent_from_variant() -> (
    None
):
    publish_cookie_banner_revision(
        text_preset_code=cookie_constants.COOKIE_BANNER_TEXT_PRESET_RU_COMPACT,
        banner_variant=CookieBannerRevision.BannerVariant.BAR,
        consent_ui_variant=CookieBannerRevision.ConsentUiVariant.PANEL,
        reconsent_notice_variant=(CookieBannerRevision.ReconsentNoticeVariant.ALERT),
    )

    configuration = get_cookie_banner_configuration()
    preset = get_cookie_banner_text_presets()[
        cookie_constants.COOKIE_BANNER_TEXT_PRESET_RU_COMPACT
    ]

    assert configuration["text_preset_code"] == "ru_compact"
    assert configuration["banner_variant"] == "bar"
    assert configuration["consent_ui_variant"] == "panel"
    assert configuration["reconsent_notice_variant"] == "alert"
    assert configuration["custom_section_summary"] == preset["custom_section_summary"]


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_mobile_overrides_fallback_to_desktop_when_not_set() -> None:
    publish_cookie_banner_revision(
        text_preset_code=cookie_constants.COOKIE_BANNER_TEXT_PRESET_RU_COMPACT,
        banner_variant=CookieBannerRevision.BannerVariant.BAR,
        consent_ui_variant=CookieBannerRevision.ConsentUiVariant.PANEL,
        reconsent_notice_variant=CookieBannerRevision.ReconsentNoticeVariant.ALERT,
        show_reject_action=True,
    )

    configuration = get_cookie_banner_configuration()

    assert configuration["mobile_text_preset_code"] == ""
    assert configuration["mobile_overrides"]["banner_variant"] == "bar"
    assert configuration["mobile_overrides"]["consent_ui_variant"] == "panel"
    assert configuration["mobile_overrides"]["reconsent_notice_variant"] == "alert"
    assert configuration["mobile_overrides"]["show_reject_action"] is True
    assert (
        configuration["mobile_overrides"]["text_values"]["customize_label"]
        == (
            get_cookie_banner_text_presets()[
                cookie_constants.COOKIE_BANNER_TEXT_PRESET_RU_COMPACT
            ]["customize_label"]
        )
    )


def test_cookie_banner_render_supports_media_slot_image() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy media slot",
    )
    publish_cookie_banner_revision(
        show_media_slot=True,
        media_slot_type="image",
        media_image_url="/static/img/cookie.svg",
        media_image_alt="Cookie visual",
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")
    rendered = template.render(RequestContext(request, {}))

    assert 'class="dz152fz-cookie-banner__media"' in rendered
    assert 'src="/static/img/cookie.svg"' in rendered
    assert 'alt="Cookie visual"' in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.parametrize(
    "unsafe_media_image_url",
    [
        "javascript:alert(1)",
        "data:image/svg+xml;base64,AAA",
        "blob:https://example.test/abc",
        "//cdn.example.test/cookie.svg",
        "images/cookie.svg",
    ],
)
def test_cookie_banner_revision_rejects_non_allowlisted_media_image_url(
    unsafe_media_image_url: str,
) -> None:
    with pytest.raises(ValidationError):
        publish_cookie_banner_revision(
            show_media_slot=True,
            media_slot_type="image",
            media_image_url=unsafe_media_image_url,
            media_image_alt="Cookie visual",
        )


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
def test_db_policy_text_preset_overrides_box_variant_content() -> None:
    _create_cookie_categories()
    CookiePolicyTextPreset.objects.create(
        code="short",
        title="Short override",
        content_text="Р СџР С•Р В»РЎРЉР В·Р С•Р Р†Р В°РЎвЂљР ВµР В»РЎРЉРЎРѓР С”Р С‘Р в„– Р С”Р С•РЎР‚Р С•РЎвЂљР С”Р С‘Р в„– РЎвЂљР ВµР С”РЎРѓРЎвЂљ Р С—Р С•Р В»Р С‘РЎвЂљР С‘Р С”Р С‘ cookie.",
        is_box_template=False,
        is_active=True,
    )
    revision = publish_box_cookie_policy_variant(variant_code="short")
    assert (
        revision.content_text
        == "Р СџР С•Р В»РЎРЉР В·Р С•Р Р†Р В°РЎвЂљР ВµР В»РЎРЉРЎРѓР С”Р С‘Р в„– Р С”Р С•РЎР‚Р С•РЎвЂљР С”Р С‘Р в„– РЎвЂљР ВµР С”РЎРѓРЎвЂљ Р С—Р С•Р В»Р С‘РЎвЂљР С‘Р С”Р С‘ cookie."
    )


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_BANNER_VARIANT_SETTINGS)
def test_cookie_banner_variant_css_contract_contains_required_presets() -> None:
    css_path = finders.find("django_cookies_152fz/cookie_banner.css")
    assert css_path is not None
    css_text = Path(css_path).read_text(encoding="utf-8")

    assert '[data-cookie-banner-variant="bar"]' in css_text
    assert '[data-cookie-banner-variant="modal"]' in css_text
    assert '[data-cookie-banner-desktop-position="center"]' in css_text
    assert '[data-cookie-banner-desktop-position="bottom_fullwidth"]' in css_text
    assert '[data-cookie-banner-mobile-position="center"]' in css_text
    assert '[data-cookie-banner-mobile-position="bottom_fullwidth"]' in css_text
    assert '[data-cookie-banner-consent-ui="panel"]' in css_text
    assert '[data-cookie-banner-consent-ui="inline"]' in css_text
    assert ".dz152fz-cookie-banner__notice--alert" in css_text
    assert ".dz152fz-cookie-choice-action--active" in css_text
    assert ".dz152fz-cookie-banner__selection" in css_text
    assert ".dz152fz-cookie-banner__sr-status" in css_text


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_js_contract_covers_choice_state_machine_and_a11y_hooks() -> None:
    js_path = finders.find("django_cookies_152fz/cookie_banner.js")
    assert js_path is not None
    js_text = Path(js_path).read_text(encoding="utf-8")

    assert "setupCookieChoiceState" in js_text
    assert "data-cookie-choice-root" in js_text
    assert "data-cookie-choice-action" in js_text
    assert "data-cookie-choice-indicator" in js_text
    assert "data-cookie-choice-status" in js_text
    assert "data-cookie-choice-initial-state" in js_text
    assert "reject_all" in js_text
    assert "data-cookie-choice-reject-label" in js_text
    assert "aria-pressed" in js_text


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_mobile_tablet_layout_acceptance_contract() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy mobile tablet layout",
    )
    publish_cookie_banner_revision(
        launcher_label="Р СњР В°РЎРѓРЎвЂљРЎР‚Р С•Р в„–Р С”Р С‘ cookie",
        mobile_position=CookieBannerRevision.MobilePosition.BOTTOM,
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert 'data-cookie-banner-mobile-position="bottom"' in rendered

    css_path = finders.find("django_cookies_152fz/cookie_banner.css")
    assert css_path is not None
    css_text = Path(css_path).read_text(encoding="utf-8")

    media_css = css_text.split("@media (max-width: 900px)", maxsplit=1)[1]
    default_panel_block = media_css.split(
        ".dz152fz-cookie-banner__panel {", maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    top_position_selector = (
        '.dz152fz-cookie-banner[data-cookie-banner-mobile-position="top"] '
        ".dz152fz-cookie-banner__panel {"
    )
    top_panel_block = media_css.split(
        top_position_selector,
        maxsplit=1,
    )[1].split("}", maxsplit=1)[0]

    assert "bottom: 0;" in default_panel_block
    assert "top: 0;" in top_panel_block
    assert "bottom: auto;" in top_panel_block


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_center_mode_functional_render_contract() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy center mode",
    )
    publish_cookie_banner_revision(
        desktop_position=CookieBannerRevision.DesktopPosition.CENTER
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert 'data-cookie-banner-desktop-position="center"' in rendered
    assert 'data-cookie-banner-open="true"' in rendered
    assert 'id="dz152fz-cookie-banner-panel"' in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_bottom_fullwidth_mode_functional_render_contract() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy bottom fullwidth mode",
    )
    publish_cookie_banner_revision(
        desktop_position=CookieBannerRevision.DesktopPosition.BOTTOM_FULLWIDTH,
        mobile_position=CookieBannerRevision.MobilePosition.BOTTOM_FULLWIDTH,
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert 'data-cookie-banner-desktop-position="bottom_fullwidth"' in rendered
    assert 'data-cookie-banner-mobile-position="bottom_fullwidth"' in rendered
    assert 'data-cookie-banner-open="true"' in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_publish_cookie_banner_revision_normalizes_invalid_position_modes() -> None:
    publish_cookie_banner_revision(
        desktop_position="invalid_desktop_position",
        mobile_position="invalid_mobile_position",
    )

    configuration = get_cookie_banner_configuration()

    assert configuration["desktop_position"] == "bottom_right"
    assert configuration["mobile_position"] == "bottom"


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_RUNTIME_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_tag_renders_runtime_payload_and_custom_assets() -> None:
    _create_cookie_categories()
    _create_cookie_registry_item(
        code="ga4_template_runtime",
        category_code="analytics",
        provider="Google",
        purpose="Analytics runtime",
        retention="13 months",
        cookie_names=["_ga"],
        src_url="https://www.googletagmanager.com/gtag/js?id=G-TEMPLATE",
        clear_strategy=CookieRegistryItem.ClearStrategy.BEST_EFFORT_DELETE,
    )
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy template runtime",
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "/static/project/cookies.css" in rendered
    assert "/static/project/cookies.js" in rendered
    assert "dz152fz-cookie-banner-runtime-data" in rendered
    assert '"strict_default_deny": true' in rendered
    assert '"event_contract"' in rendered
    assert '"dz152fz:cookie-runtime:applied"' in rendered
    assert '"script_items"' in rendered
    assert '"cleanup_items"' in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_is_hidden_for_bot_user_agent_by_default() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy bot hidden",
    )
    request = RequestFactory().get(
        "/landing/",
        HTTP_USER_AGENT="Googlebot/2.1",
    )
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "Р СњР В°РЎРѓРЎвЂљРЎР‚Р С•Р в„–Р С”Р С‘ cookie" not in rendered
    assert 'role="dialog"' not in rendered


def test_cookie_banner_custom_selection_saves_optional_choices() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy banner custom",
    )
    client = Client()

    response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "save_custom",
            "selected_categories": ["analytics"],
            "next": "/landing/",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == "/landing/"

    record = CookieConsentRecord.objects.get()
    assert set(record.selected_categories) == {"necessary", "analytics"}


@pytest.mark.parametrize(
    ("banner_action", "revision_fields"),
    [
        ("accept_all", {"keep_visible_after_accept_all": True}),
        ("required_only", {"keep_visible_after_required_only": True}),
        ("save_custom", {"keep_visible_after_save_custom": True}),
    ],
)
@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_state_can_keep_panel_visible_per_decision_action(
    banner_action: str,
    revision_fields: dict[str, object],
) -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy action visibility",
    )
    publish_cookie_banner_revision(**revision_fields)
    client = Client()
    post_data = {
        "banner_action": banner_action,
        "next": "/landing/",
    }
    if banner_action == "save_custom":
        post_data["selected_categories"] = ["analytics"]

    response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data=post_data,
    )

    assert response.status_code == 302
    token = response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value
    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["state"] == "shown"
    assert lifecycle["should_show"] is True
    assert lifecycle["keep_visible_after_decision"] is True
    assert lifecycle["decision_action"] == banner_action


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_render_hides_close_control_when_disabled_in_revision() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy no close control",
    )
    publish_cookie_banner_revision(show_close_control=False)
    accept_cookie_preferences(
        anonymous_token="anon-no-close",
        selected_categories=["analytics"],
    )
    request = RequestFactory().get("/landing/")
    request.COOKIES[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-no-close"
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "data-cookie-banner-dismiss" in rendered
    assert "dz152fz-cookie-banner__launcher-close" in rendered
    assert "hidden" in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_render_shows_launcher_close_after_decision() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy launcher dismiss",
    )
    accept_cookie_preferences(
        anonymous_token="anon-launcher-close",
        selected_categories=["analytics"],
    )
    request = RequestFactory().get("/landing/")
    request.COOKIES[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-launcher-close"
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "data-cookie-banner-dismiss" in rendered
    assert "dz152fz-cookie-banner__launcher-close" in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_blocking_mode_state_and_render_contract() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy blocking mode",
    )
    publish_cookie_banner_revision(blocking_mode_until_choice=True)

    lifecycle = get_cookie_banner_state(anonymous_token="anon-blocking-mode")
    assert lifecycle["blocking_mode_enabled"] is True
    assert lifecycle["blocking_mode_active"] is True
    assert lifecycle["initial_visit"] is True
    assert lifecycle["reopen_after_saved_choice"] is False
    assert lifecycle["default_choice_action"] == "accept_all"
    assert lifecycle["should_show"] is True

    request = RequestFactory().get("/landing/")
    request.COOKIES[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-blocking-mode"
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")
    rendered = template.render(RequestContext(request, {}))

    assert "dz152fz-cookie-banner--blocking-active" in rendered
    assert 'data-cookie-banner-blocking-mode="true"' in rendered
    assert 'data-cookie-banner-blocking-active="true"' in rendered
    assert 'aria-modal="true"' in rendered
    assert "data-cookie-banner-launcher" not in rendered
    assert "data-cookie-banner-dismiss" not in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_blocking_mode_mobile_layout_contract() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy blocking mobile mode",
    )
    publish_cookie_banner_revision(
        blocking_mode_until_choice=True,
        mobile_position=CookieBannerRevision.MobilePosition.BOTTOM_FULLWIDTH,
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "dz152fz-cookie-banner--blocking-active" in rendered
    assert 'data-cookie-banner-mobile-position="bottom_fullwidth"' in rendered
    assert 'data-cookie-banner-blocking-active="true"' in rendered
    assert 'aria-modal="true"' in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_reject_all_saves_required_only_categories() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy reject all",
    )
    publish_cookie_banner_revision(show_reject_action=True)
    client = Client()

    response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "reject_all",
            "next": "/landing/",
        },
    )

    assert response.status_code == 302
    record = CookieConsentRecord.objects.get()
    assert set(record.selected_categories) == {"necessary"}
    token = response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value
    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["decision_action"] == "reject_all"


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_preferences_reject_all_uses_explicit_refusal_action() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy preferences reject all",
    )
    client = Client()

    response = client.post(
        reverse("django_cookies_152fz:cookie_preferences"),
        data={
            "banner_action": "reject_all",
            "selected_categories": ["analytics", "marketing"],
            "next": "/prefs/",
        },
    )

    assert response.status_code == 302
    token = response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value
    status_info = get_cookie_status(anonymous_token=token)
    assert set(status_info["selected_categories"]) == {"necessary"}
    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["decision_action"] == "reject_all"
    follow_up = client.get(reverse("django_cookies_152fz:cookie_preferences"))
    assert follow_up.status_code == 200
    assert 'data-cookie-choice-initial-state="reject_all"' in follow_up.content.decode(
        "utf-8"
    )


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_dismiss_persists_server_side_state_without_consent() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy dismiss",
    )
    client = Client()

    response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "dismiss",
            "next": "/landing/",
        },
    )

    assert response.status_code == 302
    token = response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value
    assert CookieConsentRecord.objects.count() == 0

    banner_state = CookieBannerState.objects.get(anonymous_token=token)
    assert banner_state.dismissed_at is not None
    assert banner_state.decided_at is None
    assert banner_state.decision_action == ""

    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["state"] == "dismissed"
    assert lifecycle["should_show"] is False


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
def test_cookie_banner_dismiss_is_allowed_after_choice_in_blocking_mode() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy blocking after choice",
    )
    publish_cookie_banner_revision(blocking_mode_until_choice=True)
    client = Client()

    accept_response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "accept_all",
            "next": "/landing/",
        },
    )
    token = accept_response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value

    dismiss_response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "dismiss",
            "next": "/landing/",
        },
    )

    assert dismiss_response.status_code == 302
    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["blocking_mode_enabled"] is True
    assert lifecycle["blocking_mode_active"] is False
    assert lifecycle["initial_visit"] is False
    assert lifecycle["reopen_after_saved_choice"] is False
    assert lifecycle["default_choice_action"] == "accept_all"
    assert lifecycle["state"] == "dismissed"


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_reopen_after_saved_choice_is_not_blocking() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy reopen after saved choice",
    )
    publish_cookie_banner_revision(
        blocking_mode_until_choice=True,
        keep_visible_after_accept_all=True,
    )
    client = Client()
    response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={"banner_action": "accept_all", "next": "/landing/"},
    )
    token = response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value

    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["should_show"] is True
    assert lifecycle["reopen_after_saved_choice"] is True
    assert lifecycle["blocking_mode_active"] is False
    assert lifecycle["default_choice_action"] == "accept_all"


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_blocking_mode_no_js_submit_allows_explicit_choice() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy blocking no-js submit",
    )
    publish_cookie_banner_revision(blocking_mode_until_choice=True)
    client = Client()

    response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "required_only",
            "next": "/landing/",
        },
    )

    assert response.status_code == 302
    record = CookieConsentRecord.objects.get()
    assert set(record.selected_categories) == {"necessary"}
    token = response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value
    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["blocking_mode_enabled"] is True
    assert lifecycle["blocking_mode_active"] is False
    assert lifecycle["state"] == "decided"


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_dismiss_hides_launcher_row_on_next_render() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy dismiss launcher hide",
    )
    client = Client()

    response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "dismiss",
            "next": "/landing/",
        },
    )

    token = response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value
    request = RequestFactory().get("/landing/")
    request.COOKIES[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = token
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "data-cookie-banner-launcher" not in rendered
    assert "dz152fz-cookie-banner__launcher-row" not in rendered
    assert "data-cookie-banner-dismiss" not in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_dismiss_after_decision_hides_launcher_row() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy dismiss after decision",
    )
    client = Client()
    accept_response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "accept_all",
            "next": "/landing/",
        },
    )
    token = accept_response.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME].value

    dismiss_response = client.post(
        reverse("django_cookies_152fz:cookie_banner_action"),
        data={
            "banner_action": "dismiss",
            "next": "/landing/",
        },
    )

    assert dismiss_response.status_code == 302
    lifecycle = get_cookie_banner_state(anonymous_token=token)
    assert lifecycle["state"] == "dismissed"
    assert lifecycle["should_show"] is False

    request = RequestFactory().get("/landing/")
    request.COOKIES[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = token
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")
    rendered = template.render(RequestContext(request, {}))

    assert "data-cookie-banner-launcher" not in rendered
    assert "dz152fz-cookie-banner__launcher-row" not in rendered
    assert "data-cookie-banner-dismiss" not in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_hides_launcher_after_decision_when_enabled_in_revision() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy hide launcher after decision",
    )
    publish_cookie_banner_revision(hide_launcher_after_decision=True)
    accept_cookie_preferences(
        anonymous_token="anon-hide-launcher-after-decision",
        selected_categories=["analytics"],
        decision_action="accept_all",
    )
    request = RequestFactory().get("/landing/")
    request.COOKIES[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-hide-launcher-after-decision"
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "data-cookie-banner-launcher" not in rendered
    assert "dz152fz-cookie-banner__launcher-row" not in rendered
    assert "data-cookie-banner-dismiss" not in rendered


def test_bootstrap_default_cookie_policy_revision_is_idempotent() -> None:
    _create_cookie_categories()
    _create_cookie_registry_item(
        code="bootstrap_policy_registry",
        category_code="analytics",
        provider="Bootstrap Vendor",
        purpose="Bootstrap runtime",
        src_url="https://cdn.example.test/bootstrap.js",
        clear_strategy=CookieRegistryItem.ClearStrategy.BEST_EFFORT_DELETE,
    )

    first = bootstrap_default_cookie_policy_revision()
    second = bootstrap_default_cookie_policy_revision()

    assert first["created"] is True
    assert second["created"] is False
    assert second["reason"] == "box_variants_already_exist"
    assert CookiePolicyRevision.objects.filter(is_active=True).count() == 1
    active_revision = CookiePolicyRevision.objects.get(is_active=True)
    assert active_revision.is_box_template is True
    assert active_revision.content_text == COOKIE_POLICY_REVISION_TEXT_RU_SHORT
    assert active_revision.content_text == DEFAULT_COOKIE_POLICY_REVISION_TEXT_RU
    assert (
        CookiePolicyRevision.objects.filter(
            is_box_template=True,
            content_text=COOKIE_POLICY_REVISION_TEXT_RU_SHORT,
        ).count()
        == 1
    )
    assert (
        CookiePolicyRevision.objects.filter(
            is_box_template=True,
            content_text=COOKIE_POLICY_REVISION_TEXT_RU_FULL,
        ).count()
        == 1
    )
    assert active_revision.registry_items.filter(
        registry_code="bootstrap_policy_registry"
    ).exists()


def test_default_cookie_policy_texts_are_curated_legal_starters() -> None:
    assert COOKIE_POLICY_REVISION_TEXT_RU_SHORT != COOKIE_POLICY_REVISION_TEXT_RU_FULL
    assert "cookie" in COOKIE_POLICY_REVISION_TEXT_RU_SHORT.lower()
    assert "cookie" in COOKIE_POLICY_REVISION_TEXT_RU_FULL.lower()
    assert "[email" in COOKIE_POLICY_REVISION_TEXT_RU_SHORT
    assert "[email" in COOKIE_POLICY_REVISION_TEXT_RU_FULL


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_default_presets_include_english_variants() -> None:
    presets = get_cookie_banner_text_presets()
    assert "en_balanced" in presets
    assert "en_formal" in presets
    assert "en_compact" in presets
    assert presets["en_balanced"]["accept_all_label"] == "Accept all"


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_cookie_policy_default_presets_include_english_variants() -> None:
    variants = get_cookie_policy_text_variants()
    assert "short_en" in variants
    assert "full_en" in variants
    assert "cookie" in variants["short_en"]["content_text"].lower()


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_ensure_default_cookie_policy_variants_creates_both_without_duplicates() -> (
    None
):
    _create_cookie_categories()

    first = ensure_default_cookie_policy_variants()
    second = ensure_default_cookie_policy_variants()

    assert first["created"] is True
    assert set(first["created_variants"]) == {"short", "full"}
    assert second["created"] is False
    assert second["created_variants"] == []
    assert second["active_box_variant"] == "short"
    assert (
        CookiePolicyRevision.objects.filter(
            is_box_template=True,
            content_text=COOKIE_POLICY_REVISION_TEXT_RU_SHORT,
        ).count()
        == 1
    )
    assert (
        CookiePolicyRevision.objects.filter(
            is_box_template=True,
            content_text=COOKIE_POLICY_REVISION_TEXT_RU_FULL,
        ).count()
        == 1
    )


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_publish_box_cookie_policy_variant_switches_active_revision() -> None:
    _create_cookie_categories()
    ensure_default_cookie_policy_variants()

    revision = publish_box_cookie_policy_variant(variant_code="full")

    assert revision.is_active is True
    assert revision.is_box_template is True
    assert revision.content_text == COOKIE_POLICY_REVISION_TEXT_RU_FULL
    assert CookiePolicyRevision.objects.filter(is_active=True).count() == 1


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_create_custom_cookie_policy_draft_from_variant_creates_editable_draft() -> (
    None
):
    _create_cookie_categories()
    ensure_default_cookie_policy_variants()

    draft = create_custom_cookie_policy_draft_from_variant(variant_code="short")

    assert draft.is_active is False
    assert draft.is_box_template is False
    assert draft.content_text == COOKIE_POLICY_REVISION_TEXT_RU_SHORT


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_bootstrap_cookie_defaults_command_is_idempotent() -> None:
    call_command("bootstrap_152fz_cookie_defaults")
    call_command("bootstrap_152fz_cookie_defaults")

    assert CookiePolicyRevision.objects.filter(is_active=True).count() == 1
    assert CookieBannerRevision.objects.filter(is_active=True).count() == 1


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_BANNER_NO_FOOTER_LINK_SETTINGS)
@pytest.mark.django_db
def test_cookie_banner_hides_footer_link_but_keeps_noscript_link() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy no footer link",
    )
    request = RequestFactory().get("/landing/")
    template = Template("{% load cookies_tags %}{% render_cookie_banner %}")

    rendered = template.render(RequestContext(request, {}))

    assert "data-cookie-banner-launcher" not in rendered
    assert 'class="dz152fz-cookie-banner__link"' not in rendered
    assert f'href="{reverse("django_cookies_152fz:cookie_preferences")}"' in rendered


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_authenticated_cookie_preferences_get_does_not_attach_cookie_state() -> None:
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy attach",
    )
    accept_cookie_preferences(
        anonymous_token="anon-cookie-attach-ui",
        selected_categories=["analytics"],
        audit_context={"source": "test.cookies"},
    )
    user = get_user_model().objects.create_user(
        username="cookie-linked-user",
        password="x",
    )
    client = Client()
    client.force_login(user)
    client.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-cookie-attach-ui"

    response = client.get(reverse("django_cookies_152fz:cookie_preferences"))

    assert response.status_code == 200

    record = CookieConsentRecord.objects.get()
    record.refresh_from_db()
    assert record.user_id is None
    assert record.anonymous_token == "anon-cookie-attach-ui"
    assert not CookieBannerState.objects.filter(user=user).exists()
    assert CookieBannerState.objects.filter(
        anonymous_token="anon-cookie-attach-ui"
    ).exists()


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_authenticated_cookie_preferences_post_attaches_only_matching_cookie_token() -> (
    None
):
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy attach on post",
    )
    accept_cookie_preferences(
        anonymous_token="anon-cookie-attach-post",
        selected_categories=["analytics"],
        audit_context={"source": "test.cookies"},
    )
    user = get_user_model().objects.create_user(
        username="cookie-linked-user-post",
        password="x",
    )
    client = Client()
    client.force_login(user)
    client.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-cookie-attach-post"

    response = client.post(
        reverse("django_cookies_152fz:cookie_preferences"),
        data={
            "anonymous_token": "anon-cookie-attach-post",
            "selected_categories": ["analytics"],
            "next": "/cookie-ok/",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == "/cookie-ok/"
    record = CookieConsentRecord.objects.get()
    record.refresh_from_db()
    assert record.user_id == user.pk
    assert record.anonymous_token == ""
    banner_state = CookieBannerState.objects.get(user=user)
    assert banner_state.anonymous_token is None
    assert not CookieBannerState.objects.filter(
        anonymous_token="anon-cookie-attach-post"
    ).exists()


@override_settings(DJANGO_COOKIES_152FZ=COOKIE_SETTINGS)
@pytest.mark.django_db
def test_authenticated_cookie_preferences_post_with_mismatch_token_does_not_attach() -> (
    None
):
    _create_cookie_categories()
    publish_cookie_policy_revision(
        content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Cookie policy mismatch",
    )
    accept_cookie_preferences(
        anonymous_token="anon-cookie-mismatch",
        selected_categories=["analytics"],
        audit_context={"source": "test.cookies"},
    )
    user = get_user_model().objects.create_user(
        username="cookie-linked-user-mismatch",
        password="x",
    )
    client = Client()
    client.force_login(user)
    client.cookies[COOKIE_ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-cookie-mismatch"

    response = client.post(
        reverse("django_cookies_152fz:cookie_preferences"),
        data={
            "anonymous_token": "foreign-token",
            "selected_categories": ["marketing"],
            "next": "/cookie-mismatch/",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == "/cookie-mismatch/"
    anonymous_record = CookieConsentRecord.objects.get(
        anonymous_token="anon-cookie-mismatch"
    )
    assert anonymous_record.user_id is None
    assert CookieConsentRecord.objects.filter(user=user).exists()
    assert CookieBannerState.objects.filter(user=user).exists()
    assert CookieBannerState.objects.filter(
        anonymous_token="anon-cookie-mismatch"
    ).exists()


