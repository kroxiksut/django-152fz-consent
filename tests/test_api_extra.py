from __future__ import annotations

import importlib
import importlib.util
from types import SimpleNamespace

import pytest
from django.test import Client, override_settings

import django_consent_152fz.api.checks as api_checks
import django_consent_152fz.api.dependencies as api_dependencies
import django_consent_152fz.checks as consent_checks
import django_consent_152fz.settings as consent_settings
from django_consent_152fz import constants
from django_consent_152fz.exceptions import ConsentConfigurationError
from django_consent_152fz.settings import get_public_api_settings, use_api


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **values: object) -> None:
    fake_settings = SimpleNamespace(**values)
    monkeypatch.setattr(consent_settings, "django_settings", fake_settings)
    monkeypatch.setattr(api_checks, "django_settings", fake_settings)


@pytest.mark.api
def test_drf_is_available_when_api_extra_installed() -> None:
    assert importlib.util.find_spec("rest_framework") is not None


def test_use_api_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)
    assert use_api() is False


def test_use_api_rejects_non_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, USE_API_152FZ="yes")

    with pytest.raises(ConsentConfigurationError, match=constants.SETTING_USE_API):
        use_api()


def test_api_settings_check_rejects_non_bool_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, USE_API_152FZ="yes")

    errors = consent_checks.check_api_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E016"]


def test_api_settings_check_requires_api_app_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(
        monkeypatch,
        USE_API_152FZ=True,
        INSTALLED_APPS=["django_consent_152fz"],
    )
    monkeypatch.setattr(api_dependencies, "is_drf_available", lambda: True)

    errors = consent_checks.check_api_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E001"]


def test_api_settings_check_requires_drf_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(
        monkeypatch,
        USE_API_152FZ=True,
        INSTALLED_APPS=["django_consent_152fz", constants.API_APP],
    )
    monkeypatch.setattr(api_dependencies, "is_drf_available", lambda: False)

    errors = consent_checks.check_api_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E002"]
    assert "django-consent-152fz[api]" in errors[0].msg


def test_api_base_app_check_requires_root_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, INSTALLED_APPS=[constants.API_APP])

    errors = api_checks.check_api_base_app(None)

    assert [error.id for error in errors] == ["django_consent_152fz_api.E001"]


def test_require_drf_raises_friendly_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_dependencies, "find_spec", lambda name: None)

    with pytest.raises(
        ConsentConfigurationError,
        match="django-consent-152fz\\[api\\]",
    ):
        api_dependencies.require_drf()


def test_root_urls_skip_api_include_when_drf_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import django_consent_152fz.urls as consent_urls

    monkeypatch.setattr(api_dependencies, "is_drf_available", lambda: False)
    reloaded = importlib.reload(consent_urls)

    assert all(
        "django_consent_152fz.api.urls" not in str(getattr(pattern, "urlconf_name", ""))
        for pattern in reloaded.urlpatterns
    )


def test_public_api_settings_reject_invalid_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, PUBLIC_API_152FZ_THROTTLE_IP_RATE="fast")

    with pytest.raises(
        ConsentConfigurationError,
        match=constants.SETTING_PUBLIC_API_THROTTLE_IP_RATE,
    ):
        get_public_api_settings()


def test_public_api_settings_check_returns_e027_for_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, PUBLIC_API_152FZ_SHOW_ROOT="no")

    errors = consent_checks.check_public_api_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E027"]


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF="tests.urls",
    USE_API_152FZ=False,
    API_152FZ_SAFE_ROOT_STUBS_ENABLED=True,
)
def test_safe_api_root_stubs_are_available_without_api_app() -> None:
    client = Client()

    api_root = client.get("/api/")
    consents_root = client.get("/api/consents/")
    v1_root = client.get("/api/consents/v1/")
    unknown = client.get("/api/unknown/path/")

    assert api_root.status_code == 200
    assert consents_root.status_code == 200
    assert v1_root.status_code in (200, 404)
    assert unknown.status_code == 404
    assert "allowed" in unknown.json()


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF="tests.urls_api_conflict",
    USE_API_152FZ=False,
    API_152FZ_SAFE_ROOT_STUBS_ENABLED=True,
)
def test_safe_api_stubs_do_not_override_project_level_api_routes() -> None:
    client = Client()
    response = client.get("/api/")
    assert response.status_code == 200
    assert response.json()["source"] == "project_custom_api"
