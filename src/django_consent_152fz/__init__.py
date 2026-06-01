"""Публичная точка входа пакета django-consent-152fz.

Здесь сознательно оставлена только самая базовая информация:
- версия установленного дистрибутива;
- отсутствие импортов тяжёлых Django-модулей на уровне пакета.

Такой минимализм важен ещё с этапа 3.1: импорт `django_consent_152fz`
не должен сам по себе требовать настроенного Django-приложения.
Это позволяет безопасно использовать модуль в тестах, packaging-check'ах
и любых внешних инструментах, которые читают только метаданные пакета.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    # We take the version from the metadata of the installed distribution,
    # to avoid duplicating the version number in several places.
    __version__ = version("django-consent-152fz")
except PackageNotFoundError:
    # This fallback is needed for local development and running tests from sources,
    # when the package is not yet installed as wheel/sdist.
    __version__ = "0.0.0"
