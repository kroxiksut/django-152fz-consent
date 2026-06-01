from __future__ import annotations

from types import SimpleNamespace

import pytest

import django_consent_152fz.settings as consent_settings
from django_consent_152fz import constants
from django_consent_152fz.exceptions import ConsentConfigurationError
from django_consent_152fz.settings import get_fields_config


def _patch_config(monkeypatch: pytest.MonkeyPatch, config):
    fake_settings = SimpleNamespace()
    if config is not None:
        setattr(fake_settings, constants.SETTING_CONFIG, config)
    monkeypatch.setattr(consent_settings, "django_settings", fake_settings)


def test_get_fields_config_uses_standard_fields_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    fields = get_fields_config()

    assert fields["full_name"]["label"] == "ФИО"
    assert fields["email"]["label"] == "Электронная почта"
    assert fields["address"]["label"] == "Адрес"


def test_get_fields_config_extends_standard_fields_with_custom_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "fields": {
                "telegram": {"label": "Telegram"},
            }
        },
    )

    fields = get_fields_config()

    assert "full_name" in fields
    assert fields["telegram"]["label"] == "Telegram"


def test_get_fields_config_allows_override_of_standard_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "fields": {
                "email": {"label": "Рабочий email"},
            }
        },
    )

    fields = get_fields_config()

    assert fields["email"]["label"] == "Рабочий email"


def test_get_fields_config_supports_replace_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "fields_mode": "replace",
            "fields": {
                "contract_number": {"label": "Номер договора"},
            },
        },
    )

    fields = get_fields_config()

    assert set(fields) == {"contract_number"}
    assert fields["contract_number"]["label"] == "Номер договора"


def test_get_fields_config_rejects_invalid_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "fields_mode": "merge",
            "fields": {},
        },
    )

    with pytest.raises(ConsentConfigurationError, match="fields_mode"):
        get_fields_config()


def test_get_fields_config_rejects_non_mapping_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            "fields": ["email"],
        },
    )

    with pytest.raises(ConsentConfigurationError, match='\\["fields"\\]'):
        get_fields_config()


@pytest.mark.parametrize(
    "field_code,field_config",
    [
        ("Email", {"label": "Email"}),
        ("", {"label": "Email"}),
        ("email", {}),
        ("email", {"label": ""}),
        ("email", "email"),
    ],
)
def test_get_fields_config_rejects_invalid_field_definition(
    monkeypatch: pytest.MonkeyPatch, field_code: str, field_config
) -> None:
    _patch_config(
        monkeypatch,
        {
            "fields": {
                field_code: field_config,
            },
        },
    )

    with pytest.raises(ConsentConfigurationError):
        get_fields_config()
