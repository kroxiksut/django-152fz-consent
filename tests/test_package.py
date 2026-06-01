"""Базовые smoke-тесты упаковочного слоя."""

from django_consent_152fz import __version__
from django_consent_152fz.apps import Django152FzConsentConfig


def test_package_has_version_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_main_app_config_points_to_package() -> None:
    assert Django152FzConsentConfig.name == "django_consent_152fz"
