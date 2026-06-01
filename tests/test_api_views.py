from __future__ import annotations

import importlib.util

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from django_consent_152fz.api.views import (
    PublicApiRootView,
    PublicFormConsentAcceptApiView,
    PublicFormConsentStatusApiView,
    PublicFormDocumentApiView,
)
from django_consent_152fz.core.models import (
    ConsentEvent,
    ConsentRecord,
    LegalDocument,
    PersonalDataManagerAssignment,
)
from django_consent_152fz.core.services import accept_consent, publish_document_revision
from django_consent_152fz.request import generate_anonymous_token
from django_consent_152fz.verified_consents.models import VerifiedConsentPolicy
from django_consent_152fz.verified_consents.services import submit_verified_consent

from .test_core_services import _create_purpose

pytestmark = pytest.mark.api

DRF_AVAILABLE = importlib.util.find_spec("rest_framework") is not None

if DRF_AVAILABLE:
    from rest_framework.test import APIClient, APIRequestFactory


API_PREFIX = "/api/consents/v1"
API_CORE_SETTINGS = {
    "enable_core": True,
    "enable_cookies": False,
    "enable_verified_consents": False,
    "enable_access_policies": False,
    "purposes": {},
}


def _create_pending_verified_record(*, purpose_code: str = "api_verified_ops"):
    purpose = _create_purpose(code=purpose_code)
    publish_document_revision(
        document_code=f"{purpose_code}_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Verified doc",
    )
    policy = VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=LegalDocument.objects.get(code=f"{purpose_code}_doc"),
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
        is_active=True,
    )
    user = get_user_model().objects.create_user(
        username=f"{purpose_code}_subject",
        password="x",
    )
    file_obj = SimpleUploadedFile(
        f"{purpose_code}.pdf",
        b"%PDF-1.4\n%stub\n",
        content_type="application/pdf",
    )
    return submit_verified_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        user=user,
        paper_file=file_obj,
        source="tests.api.verified",
    )


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_requirements_endpoint_returns_service_payload() -> None:
    purpose = _create_purpose(code="api_requirements")
    publish_document_revision(
        document_code="requirements_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Requirements doc",
    )
    user = get_user_model().objects.create_user(username="u1", password="x")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(f"{API_PREFIX}/requirements/")

    assert response.status_code == 200
    assert response.json()["provider_code"] == "ru_152fz"


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_status_endpoint_returns_current_status_for_authenticated_subject() -> None:
    purpose = _create_purpose(code="api_status")
    publish_document_revision(
        document_code="status_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Status doc",
    )
    user = get_user_model().objects.create_user(username="u2", password="x")
    accept_consent(
        purpose_code=purpose.code,
        document_code="status_doc",
        user=user,
        confirmation_method=ConsentRecord.ConfirmationMethod.API_ACCEPT,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        f"{API_PREFIX}/status/",
        {"purpose_code": purpose.code, "document_code": "status_doc"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "current"


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_authenticated_request_rejects_explicit_anonymous_token() -> None:
    purpose = _create_purpose(code="api_auth_no_anon_token")
    publish_document_revision(
        document_code="auth_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="doc",
    )
    user = get_user_model().objects.create_user(username="u_auth_anon", password="x")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        f"{API_PREFIX}/status/",
        {
            "purpose_code": purpose.code,
            "document_code": "auth_doc",
            "anonymous_token": generate_anonymous_token(),
        },
    )
    assert response.status_code == 400
    assert "anonymous_token" in str(response.data)


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_accept_and_withdraw_endpoints_work() -> None:
    purpose = _create_purpose(code="api_accept_withdraw")
    publish_document_revision(
        document_code="accept_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Accept doc",
    )
    user = get_user_model().objects.create_user(
        username="u_accept_withdraw", password="x"
    )
    client = APIClient(
        HTTP_USER_AGENT="ConsentApiClient/1.0", HTTP_X_REQUEST_ID="req-1"
    )
    client.force_authenticate(user=user)

    accepted = client.post(
        f"{API_PREFIX}/accept/",
        {
            "purpose_code": purpose.code,
            "document_code": "accept_doc",
        },
        format="json",
    )
    assert accepted.status_code == 200

    record = ConsentRecord.objects.get(pk=accepted.json()["id"])
    event = record.events.get(event_type=ConsentEvent.EventType.GIVEN)
    assert event.request_id == "req-1"

    withdrawn = client.post(
        f"{API_PREFIX}/withdraw/",
        {
            "purpose_code": purpose.code,
            "document_code": "accept_doc",
        },
        format="json",
    )
    assert withdrawn.status_code == 200


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_documents_endpoint_returns_active_revision() -> None:
    purpose = _create_purpose(code="api_documents")
    publish_document_revision(
        document_code="documents_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Document body",
    )
    user = get_user_model().objects.create_user(username="u3", password="x")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        f"{API_PREFIX}/documents/documents_doc/",
        {"purpose_code": purpose.code},
    )

    assert response.status_code == 200
    assert response.json()["document_code"] == "documents_doc"


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_private_get_endpoints_require_authentication() -> None:
    purpose = _create_purpose(code="api_private_auth")
    publish_document_revision(
        document_code="private_auth_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Private auth doc",
    )
    client = APIClient()

    assert client.get(f"{API_PREFIX}/requirements/").status_code in (401, 403)
    assert client.get(
        f"{API_PREFIX}/status/",
        {"purpose_code": purpose.code, "document_code": "private_auth_doc"},
    ).status_code in (401, 403)


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_cookie_endpoints_are_absent_in_consent_api() -> None:
    client = APIClient()
    response = client.get(f"{API_PREFIX}/cookies/")
    assert response.status_code == 404


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_verified_artifact_service_endpoints_forbid_regular_user() -> None:
    record = _create_pending_verified_record(purpose_code="api_verified_forbid")
    user = get_user_model().objects.create_user(username="u4", password="x")
    client = APIClient()
    client.force_authenticate(user=user)

    assert (
        client.get(f"{API_PREFIX}/verified/artifacts/{record.pk}/").status_code == 403
    )
    assert (
        client.post(
            f"{API_PREFIX}/verified/artifacts/{record.pk}/confirm/",
            {},
            format="json",
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{API_PREFIX}/verified/artifacts/{record.pk}/reject/",
            {"rejection_note": "x"},
            format="json",
        ).status_code
        == 403
    )


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_verified_artifact_service_endpoints_allow_staff_user() -> None:
    record = _create_pending_verified_record(purpose_code="api_verified_staff")
    staff_user = get_user_model().objects.create_user(
        username="u5",
        password="x",
        is_staff=True,
    )
    PersonalDataManagerAssignment.objects.create(
        user=staff_user,
        can_handle_verified_consents=True,
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=staff_user)

    detail_response = client.get(f"{API_PREFIX}/verified/artifacts/{record.pk}/")
    assert detail_response.status_code == 200
    assert (
        client.post(
            f"{API_PREFIX}/verified/artifacts/{record.pk}/confirm/",
            {"confirmation_note": "ok"},
            format="json",
        ).status_code
        == 200
    )


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_verified_artifact_object_access_is_limited_by_pdm_group_scope() -> None:
    purpose_code = "api_verified_scope_limit"
    record = _create_pending_verified_record(purpose_code=purpose_code)
    allowed_group = Group.objects.create(name="api_verified_allowed")
    denied_group = Group.objects.create(name="api_verified_denied")
    record.user.groups.add(denied_group)

    staff_user = get_user_model().objects.create_user(
        username="u_verified_scope",
        password="x",
        is_staff=True,
    )
    assignment = PersonalDataManagerAssignment.objects.create(
        user=staff_user,
        scope_mode=PersonalDataManagerAssignment.ScopeMode.DJANGO_GROUPS,
        can_handle_verified_consents=True,
        is_active=True,
    )
    assignment.groups.add(allowed_group)

    client = APIClient()
    client.force_authenticate(user=staff_user)

    response = client.get(f"{API_PREFIX}/verified/artifacts/{record.pk}/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Verified consent artifact not found."


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_verified_artifact_not_found_response_is_unified() -> None:
    purpose = _create_purpose(code="api_verified_not_found")
    publish_document_revision(
        document_code="api_verified_not_found_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="doc",
    )
    subject = get_user_model().objects.create_user(
        username="u_verified_not_found",
        password="x",
    )
    no_artifact_record = accept_consent(
        purpose_code=purpose.code,
        document_code="api_verified_not_found_doc",
        user=subject,
        confirmation_method=ConsentRecord.ConfirmationMethod.API_ACCEPT,
    )
    missing_record_id = no_artifact_record.pk + 1000

    staff_user = get_user_model().objects.create_user(
        username="u_verified_not_found_staff",
        password="x",
        is_staff=True,
    )
    PersonalDataManagerAssignment.objects.create(
        user=staff_user,
        can_handle_verified_consents=True,
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=staff_user)

    no_artifact_response = client.get(
        f"{API_PREFIX}/verified/artifacts/{no_artifact_record.pk}/"
    )
    missing_record_response = client.get(
        f"{API_PREFIX}/verified/artifacts/{missing_record_id}/"
    )

    assert no_artifact_response.status_code == 404
    assert missing_record_response.status_code == 404
    assert (
        no_artifact_response.json()["detail"]
        == missing_record_response.json()["detail"]
        == "Verified consent artifact not found."
    )


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_consent_api_root_hides_verified_routes_for_anonymous_requests() -> None:
    client = APIClient()
    response = client.get(f"{API_PREFIX}/")
    assert response.status_code == 200
    assert "verified_artifact_detail" not in response.json()
    assert "verified_artifact_confirm" not in response.json()
    assert "verified_artifact_reject" not in response.json()


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_consent_api_root_shows_verified_routes_for_pdm() -> None:
    staff_user = get_user_model().objects.create_user(
        username="u_root_verified_staff",
        password="x",
        is_staff=True,
    )
    PersonalDataManagerAssignment.objects.create(
        user=staff_user,
        can_handle_verified_consents=True,
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=staff_user)

    response = client.get(f"{API_PREFIX}/")
    assert response.status_code == 200
    payload = response.json()
    assert "verified_artifact_detail" in payload
    assert "verified_artifact_confirm" in payload
    assert "verified_artifact_reject" in payload


@override_settings(
    USE_API_152FZ=True,
    PUBLIC_API_152FZ_ENABLED=True,
    PUBLIC_API_152FZ_ALLOWED_PURPOSES=["api_public_throttle"],
    PUBLIC_API_152FZ_THROTTLE_ENABLED=True,
    PUBLIC_API_152FZ_THROTTLE_IP_RATE="1/minute",
    PUBLIC_API_152FZ_THROTTLE_ANON_RATE="1/minute",
    DJANGO_152FZ_CONSENT=API_CORE_SETTINGS,
)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_public_api_throttling_returns_429_for_second_request() -> None:
    cache.clear()
    purpose = _create_purpose(code="api_public_throttle")
    publish_document_revision(
        document_code="api_public_throttle_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Public throttle doc",
    )
    factory = APIRequestFactory()
    view = PublicFormDocumentApiView.as_view()

    request_1 = factory.get(
        "/api/consents/public/v1/forms/api_public_throttle/documents/api_public_throttle_doc/",
        {"anonymous_token": "anon-public-throttle"},
        REMOTE_ADDR="127.0.0.1",
    )
    response_1 = view(
        request_1,
        purpose_code="api_public_throttle",
        document_code="api_public_throttle_doc",
    )
    assert response_1.status_code == 200

    request_2 = factory.get(
        "/api/consents/public/v1/forms/api_public_throttle/documents/api_public_throttle_doc/",
        {"anonymous_token": "anon-public-throttle"},
        REMOTE_ADDR="127.0.0.1",
    )
    response_2 = view(
        request_2,
        purpose_code="api_public_throttle",
        document_code="api_public_throttle_doc",
    )
    assert response_2.status_code == 429


@override_settings(
    USE_API_152FZ=True,
    PUBLIC_API_152FZ_ENABLED=True,
    PUBLIC_API_152FZ_ALLOWED_PURPOSES=["api_public_floor_throttle"],
    PUBLIC_API_152FZ_THROTTLE_ENABLED=False,
    PUBLIC_API_152FZ_THROTTLE_IP_WRITE_FLOOR_RATE="1/minute",
    DJANGO_152FZ_CONSENT=API_CORE_SETTINGS,
)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_public_accept_enforces_ip_floor_throttle_without_anonymous_token() -> None:
    cache.clear()
    purpose = _create_purpose(code="api_public_floor_throttle")
    publish_document_revision(
        document_code="api_public_floor_throttle_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="Public floor throttle doc",
    )
    view = PublicFormConsentAcceptApiView.as_view()
    path = "/api/consents/public/v1/forms/api_public_floor_throttle/accept/"

    first_request = APIRequestFactory().post(
        path,
        {
            "purpose_code": purpose.code,
            "document_code": "api_public_floor_throttle_doc",
        },
        format="json",
        REMOTE_ADDR="127.0.0.1",
    )
    first_response = view(first_request, purpose_code=purpose.code)
    assert first_response.status_code == 200

    second_request = APIRequestFactory().post(
        path,
        {
            "purpose_code": purpose.code,
            "document_code": "api_public_floor_throttle_doc",
        },
        format="json",
        REMOTE_ADDR="127.0.0.1",
    )
    second_response = view(second_request, purpose_code=purpose.code)
    assert second_response.status_code == 429


@override_settings(
    USE_API_152FZ=True,
    PUBLIC_API_152FZ_ENABLED=True,
    PUBLIC_API_152FZ_SHOW_ROOT=False,
    DJANGO_152FZ_CONSENT=API_CORE_SETTINGS,
)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_public_api_root_can_be_hidden_by_setting() -> None:
    factory = APIRequestFactory()
    view = PublicApiRootView.as_view()
    request = factory.get("/api/consents/public/v1/", REMOTE_ADDR="127.0.0.1")

    response = view(request)
    assert response.status_code == 404


@override_settings(
    USE_API_152FZ=True,
    PUBLIC_API_152FZ_ALLOWED_PURPOSES=["api_token_expired"],
    DJANGO_152FZ_CONSENT=API_CORE_SETTINGS,
)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_anonymous_token_expired_is_rejected() -> None:
    purpose = _create_purpose(code="api_token_expired")
    publish_document_revision(
        document_code="api_token_expired_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="doc",
    )
    factory = APIRequestFactory()
    view = PublicFormConsentAcceptApiView.as_view()
    request = factory.post(
        "/api/consents/public/v1/forms/api_token_expired/accept/",
        {
            "purpose_code": purpose.code,
            "document_code": "api_token_expired_doc",
            "anonymous_token": "v1.1.expiredtoken",
        },
        format="json",
    )
    response = view(request, purpose_code=purpose.code)
    assert response.status_code == 400


@override_settings(
    USE_API_152FZ=True,
    PUBLIC_API_152FZ_ALLOWED_PURPOSES=["api_token_reuse"],
    DJANGO_152FZ_CONSENT=API_CORE_SETTINGS,
)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_anonymous_token_reuse_is_blocked_after_attach() -> None:
    purpose = _create_purpose(code="api_token_reuse")
    publish_document_revision(
        document_code="api_token_reuse_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="doc",
    )
    token = generate_anonymous_token()
    factory = APIRequestFactory()
    public_accept = PublicFormConsentAcceptApiView.as_view()
    first_request = factory.post(
        "/api/consents/public/v1/forms/api_token_reuse/accept/",
        {
            "purpose_code": purpose.code,
            "document_code": "api_token_reuse_doc",
            "anonymous_token": token,
        },
        format="json",
    )
    assert public_accept(first_request, purpose_code=purpose.code).status_code == 200

    user = get_user_model().objects.create_user(username="u6", password="x")
    auth_client = APIClient()
    auth_client.force_authenticate(user=user)
    auth_client.cookies["django_consent_152fz_anonymous"] = token
    auth_response = auth_client.post(
        f"{API_PREFIX}/attach-anonymous/",
        {"anonymous_token": token},
        format="json",
    )
    assert auth_response.status_code == 200

    cache.clear()
    second_request = factory.post(
        "/api/consents/public/v1/forms/api_token_reuse/accept/",
        {
            "purpose_code": purpose.code,
            "document_code": "api_token_reuse_doc",
            "anonymous_token": token,
        },
        format="json",
    )
    assert public_accept(second_request, purpose_code=purpose.code).status_code == 400


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_status_query_rejects_anonymous_token_in_query_string() -> None:
    purpose = _create_purpose(code="api_status_query_reject")
    publish_document_revision(
        document_code="api_status_query_reject_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="doc",
    )
    foreign_token = generate_anonymous_token()
    foreign_record = accept_consent(
        purpose_code=purpose.code,
        document_code="api_status_query_reject_doc",
        anonymous_token=foreign_token,
    )
    user = get_user_model().objects.create_user(username="u_status_query", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["django_consent_152fz_anonymous"] = generate_anonymous_token()

    response = client.get(
        f"{API_PREFIX}/status/",
        {
            "purpose_code": purpose.code,
            "document_code": "api_status_query_reject_doc",
            "anonymous_token": generate_anonymous_token(),
        },
    )
    assert response.status_code == 400
    assert "query string" in str(response.data).lower()
    assert (
        ConsentRecord.objects.filter(
            purpose=purpose,
            user=user,
            document_revision__document__code="api_status_query_reject_doc",
        ).count()
        == 0
    )
    foreign_record.refresh_from_db()
    assert foreign_record.user_id is None


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_status_get_does_not_attach_cookie_anonymous_records() -> None:
    purpose = _create_purpose(code="api_no_auto_attach")
    publish_document_revision(
        document_code="api_no_auto_attach_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="doc",
    )
    token = generate_anonymous_token()
    accept_consent(
        purpose_code=purpose.code,
        document_code="api_no_auto_attach_doc",
        anonymous_token=token,
    )
    user = get_user_model().objects.create_user(
        username="u_no_auto_attach", password="x"
    )
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["django_consent_152fz_anonymous"] = token

    status_response = client.get(
        f"{API_PREFIX}/status/",
        {"purpose_code": purpose.code, "document_code": "api_no_auto_attach_doc"},
    )
    assert status_response.status_code == 200

    attached_count = ConsentRecord.objects.filter(
        purpose__code=purpose.code,
        user=user,
    ).count()
    assert attached_count == 0


@override_settings(USE_API_152FZ=True, DJANGO_152FZ_CONSENT=API_CORE_SETTINGS)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_attach_anonymous_endpoint_requires_cookie_match() -> None:
    user = get_user_model().objects.create_user(username="u_attach_match", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["django_consent_152fz_anonymous"] = generate_anonymous_token()

    response = client.post(
        f"{API_PREFIX}/attach-anonymous/",
        {"anonymous_token": generate_anonymous_token()},
        format="json",
    )
    assert response.status_code == 400
    assert "must match current session cookie" in str(response.data)


@override_settings(
    USE_API_152FZ=True,
    PUBLIC_API_152FZ_ENABLED=True,
    PUBLIC_API_152FZ_ALLOWED_PURPOSES=["api_public_status_fail_limit"],
    PUBLIC_API_152FZ_THROTTLE_ENABLED=False,
    PUBLIC_API_152FZ_STATUS_FAIL_LIMIT=1,
    PUBLIC_API_152FZ_STATUS_FAIL_WINDOW_SECONDS=600,
    DJANGO_152FZ_CONSENT=API_CORE_SETTINGS,
)
@pytest.mark.django_db
@pytest.mark.skipif(not DRF_AVAILABLE, reason="requires Django REST framework")
def test_public_status_failed_checks_are_limited_per_anonymous_context() -> None:
    purpose = _create_purpose(code="api_public_status_fail_limit")
    publish_document_revision(
        document_code="api_public_status_fail_limit_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="doc",
    )
    token = "v1.1.publicfail"
    factory = APIRequestFactory()
    view = PublicFormConsentStatusApiView.as_view()
    first_request = factory.post(
        "/api/consents/public/v1/forms/api_public_status_fail_limit/status/",
        {
            "document_code": "api_public_status_fail_limit_doc",
            "anonymous_token": token,
        },
        format="json",
        REMOTE_ADDR="127.0.0.1",
    )
    first = view(first_request, purpose_code=purpose.code)
    assert first.status_code == 400

    second_request = factory.post(
        "/api/consents/public/v1/forms/api_public_status_fail_limit/status/",
        {
            "document_code": "api_public_status_fail_limit_doc",
            "anonymous_token": token,
        },
        format="json",
        REMOTE_ADDR="127.0.0.1",
    )
    second = view(second_request, purpose_code=purpose.code)
    assert second.status_code == 403
