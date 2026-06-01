from __future__ import annotations

import gettext as gettext_lib
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib import admin
from django.test import override_settings

from django_consent_152fz.admin_navigation import register_optional_admin
from django_consent_152fz.core.models import (
    ConsentModuleOperationAuditLog,
    ModuleOperationAuditLog,
)
from django_cookies_152fz.models import CookieCategory


@pytest.mark.django_db
def test_cookie_app_is_russian_labeled_and_self_described() -> None:
    cfg = apps.get_app_config("django_cookies_152fz")
    assert cfg.name == "django_cookies_152fz"
    assert cfg.label == "django_cookies_152fz"
    assert "cookie" in str(cfg.verbose_name).lower()
    assert CookieCategory._meta.app_label == "django_cookies_152fz"


@pytest.mark.django_db
def test_consent_optional_admin_does_not_require_cookie_admin_when_cookie_app_missing() -> (
    None
):
    class DummyAdminSite(admin.AdminSite):
        pass

    site = DummyAdminSite(name="dummy")
    with override_settings(
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.admin",
            "django.contrib.sessions",
            "django_consent_152fz",
        ]
    ):
        register_optional_admin(site)
    assert ConsentModuleOperationAuditLog in site._registry
    assert ModuleOperationAuditLog not in site._registry


def test_locale_catalogs_exist_for_both_packages_and_are_parseable() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    paths = [
        repo_root
        / "src"
        / "django_consent_152fz"
        / "locale"
        / "ru"
        / "LC_MESSAGES"
        / "django.po",
        repo_root
        / "src"
        / "django_consent_152fz"
        / "locale"
        / "ru"
        / "LC_MESSAGES"
        / "django.mo",
        repo_root
        / "src"
        / "django_cookies_152fz"
        / "locale"
        / "ru"
        / "LC_MESSAGES"
        / "django.po",
        repo_root
        / "src"
        / "django_cookies_152fz"
        / "locale"
        / "ru"
        / "LC_MESSAGES"
        / "django.mo",
    ]
    for p in paths:
        assert p.exists(), f"missing locale file: {p}"
        assert p.stat().st_size > 0, f"empty locale file: {p}"

    with paths[0].open("r", encoding="utf-8") as fh:
        po_text = fh.read()
    assert "msgid" in po_text
    with paths[1].open("rb") as fh:
        mo = gettext_lib.GNUTranslations(fh)
    assert mo.gettext("Cookie Category")


@pytest.mark.django_db
def test_audit_sections_stay_in_their_packages() -> None:
    assert ConsentModuleOperationAuditLog._meta.app_label == "django_consent_152fz"
    assert ModuleOperationAuditLog._meta.app_label == "django_consent_152fz"
    assert str(ConsentModuleOperationAuditLog._meta.verbose_name)
