"""Consent-layer settings validation.

These tests exercise the consent config contract in
``django_consent_152fz.settings`` — normalization, the ``ConsentConfigurationError``
validation that the standalone cookies package deliberately does not perform, and
the ``E0xx`` system checks. They cover the cookie sub-sections only as they are
nested inside ``DJANGO_CONSENT_152FZ`` and re-exposed by the consent layer; the
standalone cookie contract lives in ``test_cookie_banner_settings.py``.

The module skips cleanly when the consent settings accessors are unavailable
(e.g. an incomplete ``settings.py``), instead of aborting collection for the
whole suite.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("django_consent_152fz")

try:
    import django_consent_152fz.checks as consent_checks
    import django_consent_152fz.settings as consent_settings
    from django_consent_152fz import constants
    from django_consent_152fz.exceptions import ConsentConfigurationError
    from django_consent_152fz.settings import (
        get_admin_navigation_settings,
        get_cookie_banner_settings,
        get_cookie_inventory_settings,
        get_cookie_retention_settings,
        get_cookie_runtime_settings,
        get_document_templates_settings,
        get_subject_consents_settings,
    )
except ImportError as exc:  # pragma: no cover - environment guard
    pytest.skip(
        f"consent settings accessors unavailable: {exc}",
        allow_module_level=True,
    )


def _geo_signal_hook(*, request) -> str:
    return "ru"


def _html_to_pdf_hook(*, body_html: str, revision) -> bytes:
    del revision
    return body_html.encode("utf-8")


def _patch_config(monkeypatch: pytest.MonkeyPatch, config) -> None:
    fake_settings = SimpleNamespace()
    if config is not None:
        setattr(fake_settings, constants.SETTING_CONFIG, config)
    monkeypatch.setattr(consent_settings, "django_settings", fake_settings)


def test_get_cookie_banner_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    banner_settings = get_cookie_banner_settings()

    assert banner_settings == {
        "reask_after_days": 0,
        "reask_after_months": 0,
        "banner_variant": "card",
        "consent_ui_variant": "panel",
        "reconsent_notice_variant": "inline",
        "text_preset": "ru_balanced",
        "bootstrap_initial_revision": True,
        "show_launcher": True,
        "show_preferences_link": True,
        "preferences_page_template": "",
    }


def test_get_cookie_banner_settings_accepts_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_banner": {
                "reask_after_days": 45,
            }
        },
    )

    banner_settings = get_cookie_banner_settings()

    assert banner_settings["reask_after_days"] == 45
    assert banner_settings["reask_after_months"] == 0
    assert banner_settings["banner_variant"] == "card"
    assert banner_settings["consent_ui_variant"] == "panel"


def test_get_cookie_banner_settings_rejects_conflicting_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_banner": {
                "reask_after_days": 30,
                "reask_after_months": 1,
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="configure only one"):
        get_cookie_banner_settings()


def test_cookie_banner_settings_check_surfaces_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_banner": {
                "reask_after_days": 30,
                "reask_after_months": 1,
            }
        },
    )

    errors = consent_checks.check_cookie_banner_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E017"]


def test_get_cookie_banner_settings_accepts_variant_and_text_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_banner": {
                "banner_variant": "modal",
                "consent_ui_variant": "inline",
                "reconsent_notice_variant": "alert",
                "text_preset": "ru_formal",
                "bootstrap_initial_revision": False,
                "show_launcher": False,
                "show_preferences_link": True,
                "preferences_page_template": "project/cookie_preferences.html",
            }
        },
    )

    banner_settings = get_cookie_banner_settings()

    assert banner_settings["banner_variant"] == "modal"
    assert banner_settings["consent_ui_variant"] == "inline"
    assert banner_settings["reconsent_notice_variant"] == "alert"
    assert banner_settings["text_preset"] == "ru_formal"
    assert banner_settings["bootstrap_initial_revision"] is False
    assert banner_settings["show_launcher"] is False
    assert banner_settings["show_preferences_link"] is True
    assert (
        banner_settings["preferences_page_template"]
        == "project/cookie_preferences.html"
    )


def test_get_cookie_banner_settings_rejects_non_string_preferences_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_banner": {
                "preferences_page_template": 42,
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="preferences_page_template"):
        get_cookie_banner_settings()


def test_get_cookie_banner_settings_rejects_unknown_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_banner": {
                "banner_variant": "sheet",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="banner_variant"):
        get_cookie_banner_settings()


def test_get_cookie_runtime_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

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
    assert runtime_settings["geo_signal_hook"] == ""


def test_get_cookie_runtime_settings_accepts_project_asset_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
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
                "geo_signal_hook": _geo_signal_hook,
            }
        },
    )

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
    assert runtime_settings["cookie_domain"] == "example.test"
    assert runtime_settings["geo_signal_hook"] is _geo_signal_hook


def test_get_cookie_runtime_settings_rejects_empty_preview_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_runtime": {
                "preview_param": "",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="non-empty string"):
        get_cookie_runtime_settings()


def test_get_cookie_runtime_settings_rejects_invalid_user_agent_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_runtime": {
                "user_agent_mode": "sampled",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="must be one of"):
        get_cookie_runtime_settings()


def test_get_cookie_runtime_settings_requires_cookie_domain_for_shared_subdomain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_runtime": {
                "shared_subdomain": True,
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="requires non-empty"):
        get_cookie_runtime_settings()


def test_cookie_runtime_settings_check_surfaces_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_runtime": {
                "force_banner": "yes",
            }
        },
    )

    errors = consent_checks.check_cookie_runtime_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E018"]


def test_cookie_runtime_settings_check_validates_geo_signal_hook_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_runtime": {
                "geo_signal_hook": "tests.missing.module.geo_hook",
            }
        },
    )

    errors = consent_checks.check_cookie_runtime_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E018"]


def test_get_cookie_inventory_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    inventory_settings = get_cookie_inventory_settings()

    assert inventory_settings == {
        "enable_registry_hints": False,
        "enable_external_scanners": False,
        "enable_db_auto_discovery": False,
    }


def test_get_cookie_inventory_settings_rejects_external_scanner_enable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_inventory": {
                "enable_external_scanners": True,
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="not supported in alpha core"):
        get_cookie_inventory_settings()


def test_cookie_inventory_settings_check_surfaces_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_inventory": {
                "enable_db_auto_discovery": True,
            }
        },
    )

    errors = consent_checks.check_cookie_inventory_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E024"]


def test_get_document_templates_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    templates_settings = get_document_templates_settings()

    assert templates_settings == {
        "default_text_format": "markdown",
        "admin_editor_mode": "textarea",
        "admin_wysiwyg_widget": "",
        "admin_wysiwyg_widget_attrs": {},
        "html_to_pdf_hook": "",
    }


def test_get_document_templates_settings_accepts_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "document_templates": {
                "default_text_format": "html",
                "admin_editor_mode": "wysiwyg",
                "admin_wysiwyg_widget": "django.forms.Textarea",
                "admin_wysiwyg_widget_attrs": {
                    "data-editor": "rich",
                    "class": "editor editor--legal",
                },
                "html_to_pdf_hook": _html_to_pdf_hook,
            }
        },
    )

    templates_settings = get_document_templates_settings()

    assert templates_settings["default_text_format"] == "html"
    assert templates_settings["admin_editor_mode"] == "wysiwyg"
    assert templates_settings["admin_wysiwyg_widget"] == "django.forms.Textarea"
    assert templates_settings["admin_wysiwyg_widget_attrs"] == {
        "data-editor": "rich",
        "class": "editor editor--legal",
    }
    assert templates_settings["html_to_pdf_hook"] is _html_to_pdf_hook


def test_get_document_templates_settings_rejects_invalid_default_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "document_templates": {
                "default_text_format": "rst",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="default_text_format"):
        get_document_templates_settings()


def test_get_document_templates_settings_rejects_invalid_widget_attrs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "document_templates": {
                "admin_wysiwyg_widget_attrs": ["class=editor"],
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="admin_wysiwyg_widget_attrs"):
        get_document_templates_settings()


def test_document_templates_settings_check_surfaces_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "document_templates": {
                "admin_editor_mode": "visual",
            }
        },
    )

    errors = consent_checks.check_document_templates_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E026"]


def test_cookie_banner_entry_points_check_detects_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_banner": {
                "show_launcher": False,
                "show_preferences_link": False,
            }
        },
    )

    errors = consent_checks.check_cookie_banner_entry_points(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E020"]


def test_cookie_only_configuration_check_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "enable_core": False,
            "enable_cookies": True,
            "cookie_banner": {
                "show_launcher": False,
                "show_preferences_link": False,
            },
        },
    )

    errors = consent_checks.check_cookie_only_configuration(None)

    assert errors == []


def test_get_cookie_retention_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    retention_settings = get_cookie_retention_settings()

    assert retention_settings["records_older_than_days"] == 365
    assert retention_settings["events_older_than_days"] == 365
    assert retention_settings["banner_states_older_than_days"] == 365
    assert retention_settings["batch_size"] == 1000
    assert retention_settings["protect_current_records"] is True
    assert retention_settings["private_records_older_than_days"] == 30
    assert retention_settings["private_events_older_than_days"] == 30


def test_get_cookie_retention_settings_accepts_custom_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
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
        },
    )

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


def test_get_cookie_retention_settings_rejects_zero_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_retention": {
                "batch_size": 0,
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="batch_size"):
        get_cookie_retention_settings()


def test_cookie_retention_settings_check_surfaces_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "cookie_retention": {
                "batch_size": 0,
            }
        },
    )

    errors = consent_checks.check_cookie_retention_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E022"]


def test_get_admin_navigation_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    navigation_settings = get_admin_navigation_settings()

    assert navigation_settings["enabled"] is False
    assert navigation_settings["app_order"] == []
    assert navigation_settings["collapsed_apps"] == []
    assert navigation_settings["consent_apps"] == [
        "django_consent_152fz",
        "django_consent_152fz_cookies",
        "verified_consents",
    ]
    assert navigation_settings["section_title"] == "Согласия 152-ФЗ"


def test_get_admin_navigation_settings_accepts_custom_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "admin_navigation": {
                "enabled": True,
                "app_order": [
                    "auth",
                    "django_consent_152fz",
                ],
                "collapsed_apps": [
                    "django_consent_152fz",
                ],
                "consent_apps": [
                    "django_consent_152fz",
                    "verified_consents",
                ],
                "section_title": "Блок согласий",
            }
        },
    )

    navigation_settings = get_admin_navigation_settings()

    assert navigation_settings["enabled"] is True
    assert navigation_settings["app_order"] == ["auth", "django_consent_152fz"]
    assert navigation_settings["collapsed_apps"] == ["django_consent_152fz"]
    assert navigation_settings["consent_apps"] == [
        "django_consent_152fz",
        "verified_consents",
    ]
    assert navigation_settings["section_title"] == "Блок согласий"


def test_get_admin_navigation_settings_rejects_invalid_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "admin_navigation": {
                "app_order": "django_consent_152fz",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="app_order"):
        get_admin_navigation_settings()


def test_admin_navigation_settings_check_surfaces_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "admin_navigation": {
                "enabled": "yes",
            }
        },
    )

    errors = consent_checks.check_admin_navigation_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E023"]


def test_get_subject_consents_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    subject_consents_settings = get_subject_consents_settings()

    assert subject_consents_settings["open_mode"] == "page"
    assert subject_consents_settings["allow_anonymous_withdraw"] is True
    assert subject_consents_settings["consent_input_mode"] == "checkbox"
    assert subject_consents_settings["checkbox_required"] is True
    assert subject_consents_settings["decline_action"] == "block_submit"
    assert subject_consents_settings["decline_warning_enabled"] is True
    assert "не сможем" in subject_consents_settings["decline_warning_text"]


def test_get_subject_consents_settings_accepts_modal_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "subject_consents": {
                "open_mode": "modal",
            }
        },
    )

    subject_consents_settings = get_subject_consents_settings()

    assert subject_consents_settings["open_mode"] == "modal"


def test_get_subject_consents_settings_accepts_anonymous_withdraw_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "subject_consents": {
                "open_mode": "page",
                "allow_anonymous_withdraw": False,
            },
        },
    )

    subject_consents_settings = get_subject_consents_settings()

    assert subject_consents_settings["allow_anonymous_withdraw"] is False


def test_get_subject_consents_settings_rejects_unknown_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "subject_consents": {
                "open_mode": "popup",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="open_mode"):
        get_subject_consents_settings()


def test_subject_consents_settings_check_surfaces_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "subject_consents": {
                "open_mode": 42,
            }
        },
    )

    errors = consent_checks.check_subject_consents_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E025"]


def test_get_subject_consents_settings_rejects_unknown_input_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "subject_consents": {
                "consent_input_mode": "toggle",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="consent_input_mode"):
        get_subject_consents_settings()
