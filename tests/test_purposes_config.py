from __future__ import annotations

from types import SimpleNamespace

import pytest

import django_consent_152fz.settings as consent_settings
from django_consent_152fz import constants
from django_consent_152fz.exceptions import ConsentConfigurationError
from django_consent_152fz.settings import get_purposes_config


def _patch_config(monkeypatch: pytest.MonkeyPatch, config) -> None:
    fake_settings = SimpleNamespace()
    if config is not None:
        setattr(fake_settings, constants.SETTING_CONFIG, config)
    monkeypatch.setattr(consent_settings, "django_settings", fake_settings)


def test_get_purposes_config_returns_empty_mapping_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    purposes = get_purposes_config()

    assert purposes == {}


def test_get_purposes_config_normalizes_valid_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": ["nickname", "email"],
                    "withdraw_strategy": "block",
                    "reconsent_mode": "soft_reconsent",
                    "is_experimental": False,
                    "is_active": True,
                }
            }
        },
    )

    purposes = get_purposes_config()

    purpose = purposes["account_basic"]
    assert purpose["title"] == "Регистрация"
    assert purpose["fields"] == ["nickname", "email"]
    assert purpose["withdraw_strategy"] == "block"
    assert purpose["reconsent_mode"] == "soft_reconsent"
    assert (
        purpose["consent_frequency_policy"]
        == constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED
    )
    assert (
        purpose["subject_availability_policy"]
        == constants.SUBJECT_AVAILABILITY_AUTHENTICATED_AND_ANONYMOUS
    )


def test_get_purposes_config_applies_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(
        monkeypatch,
        {
            "purposes": {
                "marketing_newsletter": {
                    "label": "Маркетинговые рассылки",
                    "fields": ["email"],
                }
            }
        },
    )

    purpose = get_purposes_config()["marketing_newsletter"]

    assert purpose["description"] == ""
    assert purpose["withdraw_strategy"] == constants.WITHDRAW_STRATEGY_BLOCK
    assert purpose["reconsent_mode"] == constants.RECONSENT_MODE_SOFT
    assert (
        purpose["consent_frequency_policy"]
        == constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED
    )
    assert (
        purpose["subject_availability_policy"]
        == constants.SUBJECT_AVAILABILITY_AUTHENTICATED_AND_ANONYMOUS
    )
    assert purpose["is_experimental"] is False
    assert purpose["is_active"] is True


def test_get_purposes_config_rejects_non_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "purposes": [],
        },
    )

    with pytest.raises(ConsentConfigurationError, match='\\["purposes"\\]'):
        get_purposes_config()


def test_get_purposes_config_rejects_unknown_field_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": ["unknown_field"],
                }
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="unknown field"):
        get_purposes_config()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "purposes": {
                "account_basic": {
                    "fields": ["email"],
                }
            }
        },
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": "email",
                }
            }
        },
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": ["email"],
                    "withdraw_strategy": "archive",
                }
            }
        },
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": ["email"],
                    "reconsent_mode": "force",
                }
            }
        },
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": ["email"],
                    "is_experimental": "no",
                }
            }
        },
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": ["email"],
                    "consent_frequency_policy": "sometimes",
                }
            }
        },
        {
            "purposes": {
                "account_basic": {
                    "label": "Регистрация",
                    "fields": ["email"],
                    "subject_availability_policy": "authenticated_or_guest",
                }
            }
        },
    ],
)
def test_get_purposes_config_rejects_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    _patch_config(monkeypatch, payload)

    with pytest.raises(ConsentConfigurationError):
        get_purposes_config()
