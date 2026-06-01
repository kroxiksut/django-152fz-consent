from __future__ import annotations

from types import SimpleNamespace

import pytest

import django_consent_152fz.settings as consent_settings
from django_consent_152fz import constants
from django_consent_152fz.checks import (
    check_feature_flags_settings,
    check_verified_consents_installation,
)
from django_consent_152fz.exceptions import ConsentConfigurationError
from django_consent_152fz.settings import get_feature_flags


def _patch_config(monkeypatch: pytest.MonkeyPatch, config) -> None:
    fake_settings = SimpleNamespace()
    if config is not None:
        setattr(fake_settings, constants.SETTING_CONFIG, config)
    monkeypatch.setattr(consent_settings, "django_settings", fake_settings)


def test_get_feature_flags_returns_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(monkeypatch, None)

    flags = get_feature_flags()

    assert flags == {
        constants.CONFIG_ENABLE_CORE: True,
        constants.CONFIG_ENABLE_VERIFIED_CONSENTS: False,
        constants.CONFIG_ENABLE_ACCESS_POLICIES: False,
    }


def test_get_feature_flags_rejects_non_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(
        monkeypatch,
        {
            constants.CONFIG_ENABLE_CORE: "yes",
        },
    )

    with pytest.raises(ConsentConfigurationError, match=constants.CONFIG_ENABLE_CORE):
        get_feature_flags()


def test_get_feature_flags_allows_legacy_verified_flag_without_core_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            constants.CONFIG_ENABLE_CORE: False,
            constants.CONFIG_ENABLE_VERIFIED_CONSENTS: True,
        },
    )

    flags = get_feature_flags()
    assert flags[constants.CONFIG_ENABLE_CORE] is False
    assert flags[constants.CONFIG_ENABLE_VERIFIED_CONSENTS] is True


def test_get_feature_flags_reads_access_policies_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            constants.CONFIG_ENABLE_ACCESS_POLICIES: True,
        },
    )

    flags = get_feature_flags()

    assert flags[constants.CONFIG_ENABLE_ACCESS_POLICIES] is True


def test_feature_flag_check_returns_e012(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(
        monkeypatch,
        {
            constants.CONFIG_ENABLE_CORE: "yes",
        },
    )

    errors = check_feature_flags_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E012"]


def test_verified_consents_installation_check_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            constants.CONFIG_ENABLE_VERIFIED_CONSENTS: True,
        },
    )
    monkeypatch.setattr(
        consent_settings,
        "django_settings",
        SimpleNamespace(
            DJANGO_152FZ_CONSENT={
                constants.CONFIG_ENABLE_VERIFIED_CONSENTS: True,
            },
            INSTALLED_APPS=["django_consent_152fz"],
        ),
    )

    errors = check_verified_consents_installation(None)

    assert errors == []
