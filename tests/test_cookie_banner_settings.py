"""Standalone cookie settings contract.

These tests exercise the cookie configuration accessors that ship with the
standalone ``django_cookies_152fz`` package via its own ``DJANGO_COOKIES_152FZ``
settings key. They must not import the consent layer: the cookies package reads
and normalizes its own config and, unlike the consent layer, returns coerced
defaults rather than raising ``ConsentConfigurationError``.

Consent-side validation of the nested cookie config (and the ``E0xx`` system
checks) lives in ``test_consent_settings_validation.py``.
"""

from __future__ import annotations

from django.test import override_settings

from django_cookies_152fz.integration_contract import (
    get_cookie_banner_settings,
    get_cookie_retention_settings,
    get_cookie_runtime_settings,
    get_default_cookie_category_codes,
    is_cookies_enabled,
)

# --- cookie_banner ---------------------------------------------------------


@override_settings(DJANGO_COOKIES_152FZ={})
def test_get_cookie_banner_settings_returns_defaults() -> None:
    assert get_cookie_banner_settings() == {
        "bootstrap_initial_revision": True,
        "preferences_page_template": "django_cookies_152fz/cookie_preferences.html",
        "banner_variant": "card",
        "consent_ui_variant": "panel",
        "reconsent_notice_variant": "inline",
        "text_preset": "ru_balanced",
        "show_empty_category_block": False,
        "show_customize_action_without_optional": False,
        "empty_category_block_text": "",
    }


@override_settings(
    DJANGO_COOKIES_152FZ={
        "cookie_banner": {
            "banner_variant": "modal",
            "consent_ui_variant": "inline",
            "reconsent_notice_variant": "alert",
            "text_preset": "ru_formal",
            "bootstrap_initial_revision": False,
            "preferences_page_template": "project/cookie_preferences.html",
            "show_empty_category_block": True,
            "show_customize_action_without_optional": True,
            "empty_category_block_text": "Нет дополнительных категорий.",
        }
    }
)
def test_get_cookie_banner_settings_accepts_overrides() -> None:
    banner_settings = get_cookie_banner_settings()

    assert banner_settings["banner_variant"] == "modal"
    assert banner_settings["consent_ui_variant"] == "inline"
    assert banner_settings["reconsent_notice_variant"] == "alert"
    assert banner_settings["text_preset"] == "ru_formal"
    assert banner_settings["bootstrap_initial_revision"] is False
    assert banner_settings["preferences_page_template"] == (
        "project/cookie_preferences.html"
    )
    assert banner_settings["show_empty_category_block"] is True
    assert banner_settings["show_customize_action_without_optional"] is True
    assert banner_settings["empty_category_block_text"] == (
        "Нет дополнительных категорий."
    )


@override_settings(
    DJANGO_COOKIES_152FZ={
        "cookie_banner": {
            "bootstrap_initial_revision": "",
            "empty_category_block_text": None,
        }
    }
)
def test_get_cookie_banner_settings_coerces_instead_of_raising() -> None:
    # The standalone contract coerces rather than validating: falsy values
    # become their typed defaults instead of raising ConsentConfigurationError.
    banner_settings = get_cookie_banner_settings()

    assert banner_settings["bootstrap_initial_revision"] is False
    assert banner_settings["empty_category_block_text"] == ""


# --- cookie_runtime --------------------------------------------------------


@override_settings(DJANGO_COOKIES_152FZ={})
def test_get_cookie_runtime_settings_returns_defaults() -> None:
    runtime_settings = get_cookie_runtime_settings()

    assert runtime_settings["force_banner"] is False
    assert runtime_settings["preview_param"] == "cookie_banner_preview"
    assert runtime_settings["custom_css_url"] == ""
    assert runtime_settings["custom_js_url"] == ""
    assert runtime_settings["hide_for_bots"] is True
    assert runtime_settings["bot_patterns"][-1] == "bot"
    assert runtime_settings["user_agent_mode"] == "all"
    assert runtime_settings["shared_subdomain"] is False
    assert runtime_settings["site_domain"] == ""
    assert runtime_settings["cookie_domain"] == ""
    assert runtime_settings["trusted_proxy_hops"] == 0
    assert runtime_settings["trusted_proxy_ips"] == []
    assert runtime_settings["geo_signal_hook"] == ""


@override_settings(
    DJANGO_COOKIES_152FZ={
        "cookie_runtime": {
            "force_banner": True,
            "preview_param": "cookie_preview",
            "custom_css_url": "/static/project/cookies.css",
            "custom_js_url": "/static/project/cookies.js",
            "hide_for_bots": False,
            "bot_patterns": ["qa-bot", "crawler"],
            "user_agent_mode": "unique",
            "shared_subdomain": True,
            "site_domain": "consent.example.test",
            "cookie_domain": ".example.test",
            "trusted_proxy_hops": 2,
            "trusted_proxy_ips": ["10.0.0.1"],
            "geo_signal_hook": "tests.support.geo_hook",
        }
    }
)
def test_get_cookie_runtime_settings_accepts_overrides() -> None:
    runtime_settings = get_cookie_runtime_settings()

    assert runtime_settings["force_banner"] is True
    assert runtime_settings["preview_param"] == "cookie_preview"
    assert runtime_settings["custom_css_url"] == "/static/project/cookies.css"
    assert runtime_settings["custom_js_url"] == "/static/project/cookies.js"
    assert runtime_settings["hide_for_bots"] is False
    assert runtime_settings["bot_patterns"] == ["qa-bot", "crawler"]
    assert runtime_settings["user_agent_mode"] == "unique"
    assert runtime_settings["shared_subdomain"] is True
    assert runtime_settings["site_domain"] == "consent.example.test"
    # The standalone contract does not strip the leading dot; that
    # normalization happens only when the cookie is actually written.
    assert runtime_settings["cookie_domain"] == ".example.test"
    assert runtime_settings["trusted_proxy_hops"] == 2
    assert runtime_settings["trusted_proxy_ips"] == ["10.0.0.1"]
    # geo_signal_hook is kept as a dotted import path string, resolved lazily.
    assert runtime_settings["geo_signal_hook"] == "tests.support.geo_hook"


@override_settings(DJANGO_COOKIES_152FZ={"cookie_runtime": {"bot_patterns": []}})
def test_get_cookie_runtime_settings_falls_back_on_empty_bot_patterns() -> None:
    runtime_settings = get_cookie_runtime_settings()

    assert runtime_settings["bot_patterns"][-1] == "bot"
    assert "googlebot" in runtime_settings["bot_patterns"]


# --- cookie_retention ------------------------------------------------------


@override_settings(DJANGO_COOKIES_152FZ={})
def test_get_cookie_retention_settings_returns_defaults() -> None:
    retention_settings = get_cookie_retention_settings()

    assert retention_settings["batch_size"] == 500
    assert retention_settings["events_older_than_days"] is None
    assert retention_settings["events_max_count"] is None
    assert retention_settings["records_older_than_days"] is None
    assert retention_settings["records_max_count"] is None
    assert retention_settings["banner_states_older_than_days"] is None
    assert retention_settings["banner_states_max_count"] is None
    assert retention_settings["private_events_older_than_days"] is None
    assert retention_settings["private_records_older_than_days"] is None
    assert retention_settings["private_signal_paths"] == []
    assert retention_settings["protect_current_records"] is True


@override_settings(
    DJANGO_COOKIES_152FZ={
        "cookie_retention": {
            "records_older_than_days": 180,
            "events_older_than_days": 120,
            "banner_states_older_than_days": 90,
            "records_max_count": 1000,
            "events_max_count": 5000,
            "banner_states_max_count": 2000,
            "batch_size": 250,
            "protect_current_records": False,
            "private_signal_paths": ["cookie_runtime.private_mode"],
            "private_records_older_than_days": 14,
            "private_events_older_than_days": 14,
        }
    }
)
def test_get_cookie_retention_settings_accepts_overrides() -> None:
    retention_settings = get_cookie_retention_settings()

    assert retention_settings["records_older_than_days"] == 180
    assert retention_settings["events_older_than_days"] == 120
    assert retention_settings["banner_states_older_than_days"] == 90
    assert retention_settings["records_max_count"] == 1000
    assert retention_settings["events_max_count"] == 5000
    assert retention_settings["banner_states_max_count"] == 2000
    assert retention_settings["batch_size"] == 250
    assert retention_settings["protect_current_records"] is False
    assert retention_settings["private_signal_paths"] == ["cookie_runtime.private_mode"]
    assert retention_settings["private_records_older_than_days"] == 14
    assert retention_settings["private_events_older_than_days"] == 14


# --- enable flag + default categories --------------------------------------


@override_settings(DJANGO_COOKIES_152FZ={})
def test_is_cookies_enabled_defaults_true() -> None:
    assert is_cookies_enabled() is True


@override_settings(DJANGO_COOKIES_152FZ={"enable_cookies": False})
def test_is_cookies_enabled_respects_flag() -> None:
    assert is_cookies_enabled() is False


@override_settings(DJANGO_COOKIES_152FZ={})
def test_get_default_cookie_category_codes_defaults_to_necessary() -> None:
    assert get_default_cookie_category_codes() == ["necessary"]


@override_settings(
    DJANGO_COOKIES_152FZ={"default_cookie_category_codes": ["necessary", "analytics"]}
)
def test_get_default_cookie_category_codes_accepts_override() -> None:
    assert get_default_cookie_category_codes() == ["necessary", "analytics"]
