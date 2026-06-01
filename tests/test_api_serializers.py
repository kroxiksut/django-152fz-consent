from __future__ import annotations

import importlib.util

import pytest
from django.test import RequestFactory

pytestmark = pytest.mark.api

DRF_AVAILABLE = importlib.util.find_spec("rest_framework") is not None

if DRF_AVAILABLE:
    from django_consent_152fz.api.serializers import (
        AcceptConsentRequestSerializer,
        AcceptConsentResponseSerializer,
        AuditContextSerializer,
        DocumentRevisionSerializer,
        RequirementsResponseSerializer,
    )


@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_audit_context_serializer_normalizes_extra_meta() -> None:
    serializer = AuditContextSerializer(
        data={
            "source": "api.accept",
            "client": {"timezone": "Asia/Irkutsk"},
            "extra_meta": {
                "request.referrer": "https://example.test/form/",
                "cookie": "must_be_removed",
            },
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["source"] == "api.accept"
    assert serializer.validated_data["extra_meta"]["client"]["timezone"] == (
        "Asia/Irkutsk"
    )
    assert serializer.validated_data["extra_meta"]["request"]["referrer"] == (
        "https://example.test/form/"
    )
    assert "cookie" not in serializer.validated_data["extra_meta"]


@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_accept_request_serializer_accepts_headless_payload() -> None:
    serializer = AcceptConsentRequestSerializer(
        data={
            "purpose_code": "account_signup",
            "document_code": "signup_doc",
            "anonymous_token": "anon-serializer",
            "subject_ref": "lead-42",
            "fields_snapshot": ["email", "phone"],
            "audit_context": {
                "source": "api.accept",
                "client": {"languages": ["ru-RU"]},
            },
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["subject_ref"] == "lead-42"
    assert serializer.validated_data["audit_context"]["extra_meta"]["client"] == {
        "languages": ["ru-RU"]
    }


@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_requirements_response_serializer_matches_service_shape() -> None:
    serializer = RequirementsResponseSerializer(
        data={
            "provider_code": "ru_152fz",
            "requirements": [
                {
                    "purpose_code": "account_signup",
                    "title": "Регистрация",
                    "description": "",
                    "fields": ["nickname", "email"],
                    "withdraw_strategy": "block",
                    "reconsent_mode": "soft_reconsent",
                    "document_code": "signup_doc",
                    "document_title": "Signup",
                    "document_type": "consent",
                    "verified_consent": {
                        "required": False,
                        "verification_mode": None,
                    },
                    "latest_revision": {
                        "id": 1,
                        "document_code": "signup_doc",
                        "document_title": "Signup",
                        "document_type": "consent",
                        "version": 1,
                        "format": "plain_text",
                        "published_at": "2026-03-27T00:00:00Z",
                        "is_box_template": False,
                    },
                    "consent_status": "current",
                    "requires_consent": False,
                    "consent_required_reason": "not_required",
                    "is_applicable": True,
                }
            ],
        }
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_document_revision_serializer_exposes_document_fields() -> None:
    from django_consent_152fz.core.services import publish_document_revision

    from .test_core_services import _create_purpose

    purpose = _create_purpose(code="api_docs")
    revision = publish_document_revision(
        document_code="api_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="API content",
    )

    data = DocumentRevisionSerializer(instance=revision).data

    assert data["purpose_code"] == purpose.code
    assert data["document_code"] == "api_doc"
    assert data["document_title"] == "api_doc"
    assert data["content_text"] == "API content"
    assert data["content_url"] is None


@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_document_revision_serializer_exposes_pdf_url_with_request_context() -> None:
    from django_consent_152fz.core.services import publish_document_revision

    from .test_core_services import _create_purpose

    purpose = _create_purpose(code="api_docs_pdf")
    revision = publish_document_revision(
        document_code="api_doc_pdf",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="API content",
    )
    request = RequestFactory().get("/api/consents/v1/documents/")

    data = DocumentRevisionSerializer(
        instance=revision,
        context={"request": request},
    ).data

    assert data["pdf_url"].endswith(
        f"/consent/documents/{purpose.code}/api_doc_pdf/pdf/"
    )


@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_accept_response_serializer_serializes_record_model() -> None:
    from django_consent_152fz.core.services import (
        accept_consent,
        publish_document_revision,
    )

    from .test_core_services import _create_purpose

    purpose = _create_purpose(code="api_accept")
    publish_document_revision(
        document_code="accept_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )

    record = accept_consent(
        purpose_code=purpose.code,
        document_code="accept_doc",
        anonymous_token="anon-api-accept",
        confirmation_method="api_accept",
    )

    data = AcceptConsentResponseSerializer(instance=record).data

    assert data["purpose_code"] == purpose.code
    assert data["document_code"] == "accept_doc"
    assert data["status"] == "current"
    assert data["confirmation_method"] == "api_accept"
