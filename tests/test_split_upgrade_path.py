from __future__ import annotations

import importlib

import pytest
from django.apps import apps

from django_cookies_152fz.models import CookieCategory


def test_cookie_app_label_uses_standalone_name() -> None:
    cfg = apps.get_app_config("django_cookies_152fz")
    assert cfg.name == "django_cookies_152fz"
    assert cfg.label == "django_cookies_152fz"
    assert CookieCategory._meta.app_label == "django_cookies_152fz"


def test_cookie_migration_keeps_cross_package_dependency_contract() -> None:
    migration_0001 = importlib.import_module(
        "django_cookies_152fz.migrations.0001_initial"
    )
    deps = set(migration_0001.Migration.dependencies)
    assert ("django_consent_152fz", "0001_initial") not in deps


@pytest.mark.django_db
def test_cookie_table_name_stays_stable_for_upgrade_installations() -> None:
    obj = CookieCategory.objects.create(code="required", title="Required")
    assert obj._meta.db_table.startswith("django_cookies_152fz_")
