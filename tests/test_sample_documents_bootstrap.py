from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

import django_consent_152fz.settings as consent_settings
from django_consent_152fz import constants
from django_consent_152fz.box_templates.documents import (
    bootstrap_sample_documents,
    bootstrap_sample_documents_post_migrate,
    get_sample_access_policy_definitions,
    get_sample_audience_rule_definitions,
    get_sample_document_definitions,
)
from django_consent_152fz.checks import check_sample_documents_settings
from django_consent_152fz.core.models import (
    ConsentAccessPolicy,
    ConsentAudienceRule,
    ConsentPurpose,
    DocumentRevision,
    LegalDocument,
)
from django_consent_152fz.exceptions import ConsentConfigurationError
from django_consent_152fz.settings import get_sample_documents_settings


def _patch_config(monkeypatch: pytest.MonkeyPatch, config) -> None:
    fake_settings = SimpleNamespace(INSTALLED_APPS=["django_consent_152fz"])
    if config is not None:
        setattr(fake_settings, constants.SETTING_CONFIG, config)
    monkeypatch.setattr(consent_settings, "django_settings", fake_settings)


def test_get_sample_documents_settings_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)

    assert get_sample_documents_settings() == {
        constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: (
            constants.SAMPLE_DOCUMENTS_LOAD_MODE_COMMAND
        )
    }


def test_get_sample_documents_settings_rejects_invalid_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            constants.CONFIG_SAMPLE_DOCUMENTS: {
                constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: "unexpected",
            }
        },
    )

    with pytest.raises(ConsentConfigurationError, match="load_mode"):
        get_sample_documents_settings()


def test_sample_documents_check_returns_e019(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        {
            constants.CONFIG_SAMPLE_DOCUMENTS: {
                constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: "broken",
            }
        },
    )

    errors = check_sample_documents_settings(None)

    assert [error.id for error in errors] == ["django_consent_152fz.E019"]


@pytest.mark.django_db
def test_bootstrap_sample_documents_creates_curated_inactive_templates() -> None:
    summary = bootstrap_sample_documents()

    sample_count = len(get_sample_document_definitions())
    sample_policy_count = len(get_sample_access_policy_definitions())
    sample_audience_count = len(get_sample_audience_rule_definitions())
    sample_purpose_codes = {
        sample.purpose_code for sample in get_sample_document_definitions()
    }
    assert summary["created_documents"] == sample_count
    assert summary["created_revisions"] == sample_count
    assert summary["created_purposes"] + summary["existing_purposes"] == len(
        sample_purpose_codes
    )
    assert (
        summary["created_access_policies"] + summary["existing_access_policies"]
        == sample_policy_count
    )
    assert (
        summary["created_audience_rules"] + summary["existing_audience_rules"]
        == sample_audience_count
    )
    assert (
        LegalDocument.objects.filter(code__startswith="sample_").count() == sample_count
    )
    assert ConsentPurpose.objects.filter(code__in=sample_purpose_codes).count() == len(
        sample_purpose_codes
    )
    assert DocumentRevision.objects.filter(is_box_template=True).count() == sample_count
    assert DocumentRevision.objects.filter(is_active=True).count() == 0
    assert DocumentRevision.objects.filter(published_at__isnull=False).count() == (
        sample_count
    )
    assert (
        ConsentAccessPolicy.objects.filter(code__startswith="sample_policy_").count()
        == sample_policy_count
    )
    assert (
        ConsentAudienceRule.objects.filter(
            notes__contains="[bundled_sample_rule_key="
        ).count()
        == sample_audience_count
    )
    assert (
        ConsentAccessPolicy.objects.filter(
            code="sample_policy_profile_view",
            is_active=False,
            resource_code="profile_page",
            action="view",
        ).count()
        == 1
    )
    assert (
        ConsentAudienceRule.objects.filter(
            scope_mode=ConsentAudienceRule.ScopeMode.ANONYMOUS_SUBJECTS,
            is_required=False,
        ).count()
        == 1
    )

    privacy_revision = DocumentRevision.objects.get(
        document__code="sample_personal_data_processing_policy"
    )
    assert privacy_revision.format == DocumentRevision.ContentFormat.MARKDOWN
    assert privacy_revision.document.document_type == "privacy_policy"
    assert privacy_revision.fields_snapshot == ["policy_document"]
    assert privacy_revision.meta["starter_template"] is True
    assert privacy_revision.meta["legal_review_required"] is True
    assert "Политика обработки персональных данных" in privacy_revision.content_text
    assert "юридическая проверка" in privacy_revision.content_text

    notice_revision = DocumentRevision.objects.get(
        document__code="sample_personal_data_notice"
    )
    assert notice_revision.document.document_type == "notice"

    agreement_revision = DocumentRevision.objects.get(
        document__code="sample_service_terms_agreement"
    )
    assert agreement_revision.document.document_type == "agreement"

    enrollment_revision = DocumentRevision.objects.get(
        document__code="sample_course_enrollment_consent"
    )
    assert enrollment_revision.document.document_type == "consent"
    assert "записи на курс" in enrollment_revision.content_text

    certificate_revision = DocumentRevision.objects.get(
        document__code="sample_certificate_issue_consent"
    )
    assert certificate_revision.document.document_type == "consent"
    assert "оформления сертификата" in certificate_revision.content_text

    theme_revision = DocumentRevision.objects.get(
        document__code="sample_newsletter_topics_theme"
    )
    assert theme_revision.document.document_type == "theme"
    assert not LegalDocument.objects.filter(code="sample_cookie_policy").exists()


@pytest.mark.django_db
def test_bootstrap_sample_documents_is_idempotent() -> None:
    first = bootstrap_sample_documents()
    second = bootstrap_sample_documents()

    sample_count = len(get_sample_document_definitions())
    sample_policy_count = len(get_sample_access_policy_definitions())
    sample_audience_count = len(get_sample_audience_rule_definitions())
    assert first["created_revisions"] == sample_count
    assert second["created_revisions"] == 0
    assert second["existing_samples"] == sample_count
    assert (
        first["created_access_policies"] + first["existing_access_policies"]
        == sample_policy_count
    )
    assert second["existing_access_policies"] == sample_policy_count
    assert (
        first["created_audience_rules"] + first["existing_audience_rules"]
        == sample_audience_count
    )
    assert second["existing_audience_rules"] == sample_audience_count
    assert DocumentRevision.objects.filter(is_box_template=True).count() == sample_count


@pytest.mark.django_db
def test_management_command_bootstraps_samples() -> None:
    stdout = StringIO()
    sample_count = len(get_sample_document_definitions())

    call_command("bootstrap_152fz_sample_documents", stdout=stdout)

    output = stdout.getvalue()
    assert f"created_documents={sample_count}" in output
    assert "Текущий режим bootstrap: command" in output
    assert (
        LegalDocument.objects.filter(code__startswith="sample_").count() == sample_count
    )


@pytest.mark.django_db
def test_management_command_respects_disabled_mode() -> None:
    with override_settings(
        DJANGO_152FZ_CONSENT={
            constants.CONFIG_SAMPLE_DOCUMENTS: {
                constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: (
                    constants.SAMPLE_DOCUMENTS_LOAD_MODE_DISABLED
                )
            }
        }
    ):
        with pytest.raises(CommandError, match="sample_documents.load_mode='disabled'"):
            call_command("bootstrap_152fz_sample_documents")


@pytest.mark.django_db
def test_management_command_force_overrides_disabled_mode() -> None:
    sample_count = len(get_sample_document_definitions())
    with override_settings(
        DJANGO_152FZ_CONSENT={
            constants.CONFIG_SAMPLE_DOCUMENTS: {
                constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: (
                    constants.SAMPLE_DOCUMENTS_LOAD_MODE_DISABLED
                )
            }
        }
    ):
        call_command("bootstrap_152fz_sample_documents", "--force")

    assert (
        LegalDocument.objects.filter(code__startswith="sample_").count() == sample_count
    )


@pytest.mark.django_db
def test_post_migrate_bootstrap_runs_only_for_auto_mode() -> None:
    sample_count = len(get_sample_document_definitions())
    with override_settings(
        DJANGO_152FZ_CONSENT={
            constants.CONFIG_SAMPLE_DOCUMENTS: {
                constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: (
                    constants.SAMPLE_DOCUMENTS_LOAD_MODE_COMMAND
                )
            }
        }
    ):
        result = bootstrap_sample_documents_post_migrate(sender=None, using="default")
        assert result is None
        assert LegalDocument.objects.filter(code__startswith="sample_").count() == 0

    with override_settings(
        DJANGO_152FZ_CONSENT={
            constants.CONFIG_SAMPLE_DOCUMENTS: {
                constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: (
                    constants.SAMPLE_DOCUMENTS_LOAD_MODE_AUTO
                )
            }
        }
    ):
        result = bootstrap_sample_documents_post_migrate(sender=None, using="default")
        assert result is not None
        assert result["created_revisions"] == sample_count
        assert (
            LegalDocument.objects.filter(code__startswith="sample_").count()
            == sample_count
        )
