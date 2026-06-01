from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from django_consent_152fz.core.models import DocumentRevision, LegalDocument


@pytest.mark.django_db
def test_plain_text_box_template_revision_can_be_created() -> None:
    document = LegalDocument.objects.create(
        code="privacy_policy",
        title="Политика конфиденциальности",
        document_type="privacy_policy",
    )
    revision = DocumentRevision(
        document=document,
        purpose_code="account_basic",
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="Текст согласия",
        fields_snapshot=["full_name", "email"],
        is_box_template=True,
    )

    revision.full_clean()
    revision.save()

    saved = DocumentRevision.objects.get(pk=revision.pk)
    assert saved.is_box_template is True
    assert saved.content_text == "Текст согласия"


@pytest.mark.django_db
def test_pdf_custom_revision_can_be_created() -> None:
    document = LegalDocument.objects.create(
        code="consent_doc",
        title="Согласие на обработку ПДн",
    )
    revision = DocumentRevision(
        document=document,
        purpose_code="account_basic",
        version=2,
        format=DocumentRevision.ContentFormat.PDF_FILE,
        content_file=SimpleUploadedFile(
            "consent.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        ),
        fields_snapshot=["email"],
        is_box_template=False,
    )

    revision.full_clean()
    revision.save()

    saved = DocumentRevision.objects.get(pk=revision.pk)
    assert bool(saved.content_file) is True
    assert saved.is_box_template is False


@pytest.mark.django_db
def test_text_formats_require_content_text() -> None:
    document = LegalDocument.objects.create(code="terms_doc", title="Пользовательское")
    revision = DocumentRevision(
        document=document,
        purpose_code="account_basic",
        version=1,
        format=DocumentRevision.ContentFormat.MARKDOWN,
        content_text="",
    )

    with pytest.raises(ValidationError, match="content_text"):
        revision.full_clean()


@pytest.mark.django_db
def test_pdf_format_requires_file_and_rejects_text() -> None:
    document = LegalDocument.objects.create(code="pdf_doc", title="PDF")
    revision = DocumentRevision(
        document=document,
        purpose_code="account_basic",
        version=1,
        format=DocumentRevision.ContentFormat.PDF_FILE,
        content_text="not allowed",
    )

    with pytest.raises(ValidationError):
        revision.full_clean()


@pytest.mark.django_db
def test_document_revision_save_runs_validation() -> None:
    document = LegalDocument.objects.create(code="invalid_pdf_doc", title="Invalid PDF")

    with pytest.raises(ValidationError, match="content_file"):
        DocumentRevision.objects.create(
            document=document,
            purpose_code="account_basic",
            version=1,
            format=DocumentRevision.ContentFormat.PDF_FILE,
            fields_snapshot=["email"],
        )


@pytest.mark.django_db
def test_document_revision_unique_per_document_purpose_and_version() -> None:
    document = LegalDocument.objects.create(code="main_doc", title="Main")
    DocumentRevision.objects.create(
        document=document,
        purpose_code="account_basic",
        version=1,
        format=DocumentRevision.ContentFormat.HTML,
        content_text="<p>v1</p>",
        fields_snapshot=["email"],
    )

    with pytest.raises(ValidationError):
        DocumentRevision.objects.create(
            document=document,
            purpose_code="account_basic",
            version=1,
            format=DocumentRevision.ContentFormat.HTML,
            content_text="<p>duplicate</p>",
            fields_snapshot=["email"],
        )
