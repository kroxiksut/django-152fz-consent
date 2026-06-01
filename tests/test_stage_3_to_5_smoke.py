from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.checks import Tags, run_checks
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import RequestContext, Template
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from django_consent_152fz.contact_hooks import submit_anonymous_contact_consent
from django_consent_152fz.core.models import (
    ConsentAccessPolicy,
    ConsentAudienceRule,
    ConsentEvent,
    ConsentPurpose,
    ConsentRecord,
    PersonalDataManagerAssignment,
)
from django_consent_152fz.core.services import (
    accept_consent,
    get_consent_status,
    publish_document_revision,
)
from django_consent_152fz.request import ANONYMOUS_TOKEN_COOKIE_NAME
from django_consent_152fz.verified_consents.models import VerifiedConsentPolicy
from django_consent_152fz.verified_consents.services import (
    confirm_verified_consent,
    submit_verified_consent,
)
from django_cookies_152fz.integration_contract import (
    ANONYMOUS_TOKEN_COOKIE_NAME as COOKIES_ANONYMOUS_TOKEN_COOKIE_NAME,
)
from django_cookies_152fz.models import (
    CookieCategory,
    CookieConsentEvent,
    CookieConsentRecord,
    CookiePolicyRevision,
)
from django_cookies_152fz.services import (
    get_cookie_status,
    publish_cookie_policy_revision,
)

COOKIES_ONLY_SETTINGS = {
    "enable_core": False,
    "enable_cookies": True,
    "enable_verified_consents": False,
    "enable_access_policies": False,
    "purposes": {},
}
FULL_SETTINGS = {
    "enable_core": True,
    "enable_cookies": True,
    "enable_verified_consents": False,
    "enable_access_policies": False,
    "purposes": {},
}
FULL_WITH_ACCESS_SETTINGS = {
    "enable_core": True,
    "enable_cookies": True,
    "enable_verified_consents": False,
    "enable_access_policies": True,
    "purposes": {},
}
FULL_WITH_VERIFIED_SETTINGS = {
    "enable_core": True,
    "enable_cookies": True,
    "enable_verified_consents": True,
    "enable_access_policies": False,
    "purposes": {},
}


def _assert_no_compatibility_errors() -> None:
    assert run_checks(tags=[Tags.compatibility]) == []


def _create_cookie_categories() -> None:
    CookieCategory.objects.get_or_create(
        code="necessary",
        defaults={
            "title": "Necessary",
            "description": "Required cookies",
            "is_required": True,
            "sort_order": 1,
        },
    )
    CookieCategory.objects.get_or_create(
        code="analytics",
        defaults={
            "title": "Analytics",
            "description": "Analytics cookies",
            "sort_order": 2,
        },
    )


def _create_superuser():
    User = get_user_model()
    return User.objects.create_superuser(
        username="stage-smoke-admin",
        email="stage-smoke-admin@example.com",
        password="pass",
    )


def _create_verified_operator(*, username: str):
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password="pass",
        is_staff=True,
    )
    PersonalDataManagerAssignment.objects.create(
        user=user,
        can_handle_verified_consents=True,
        is_active=True,
    )
    return user


def _create_anonymous_purpose(*, code: str, document_code: str) -> ConsentPurpose:
    purpose = ConsentPurpose.objects.create(
        code=code,
        title=code.replace("_", " ").title(),
        fields_config=["email", "phone"],
    )
    revision = publish_document_revision(
        document_code=document_code,
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text=f"{code} consent",
    )
    ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=revision.document,
        scope_mode=ConsentAudienceRule.ScopeMode.ANONYMOUS_SUBJECTS,
    )
    return purpose


def _render_access_result(
    *,
    resource_code: str,
    action: str,
    anonymous_token: str,
) -> str:
    template = Template(
        "{% load consent_tags %}"
        "{% consent_access resource_code action as access %}"
        "{{ access.resolution }}|{{ access.reason }}|{{ access.allowed }}|"
        "{{ access.redirect_to_consent }}"
    )
    request = RequestFactory().get("/resource/")
    request.user = AnonymousUser()
    request.COOKIES[ANONYMOUS_TOKEN_COOKIE_NAME] = anonymous_token
    return template.render(
        RequestContext(
            request,
            {
                "resource_code": resource_code,
                "action": action,
            },
        )
    )


def _admin_changelist_name(model) -> str:
    return f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"


@pytest.mark.django_db
def test_cookies_only_can_upgrade_to_full_core_without_losing_cookie_history() -> None:
    client = Client(HTTP_USER_AGENT="Mozilla/5.0")

    with override_settings(DJANGO_152FZ_CONSENT=COOKIES_ONLY_SETTINGS):
        _assert_no_compatibility_errors()
        _create_cookie_categories()
        publish_cookie_policy_revision(
            content_format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
            content_text="Cookie policy v1",
        )

        cookie_response = client.post(
            reverse("django_cookies_152fz:cookie_preferences"),
            data={
                "selected_categories": ["analytics"],
                "next": "/after-cookies/",
                "client_timezone": "Asia/Irkutsk",
                "client_languages": '["ru-RU"]',
            },
            HTTP_REFERER="https://example.test/cookies/",
            HTTP_X_REQUEST_ID="req-stage-cookies-1",
        )

        assert cookie_response.status_code == 302
        # РџР°РєРµС‚С‹ РЅРµР·Р°РІРёСЃРёРјС‹: РІ cookies-only СЂРµР¶РёРјРµ cookies-РїР°РєРµС‚ РІС‹СЃС‚Р°РІР»СЏРµС‚
        # СЃРѕР±СЃС‚РІРµРЅРЅС‹Р№ Р°РЅРѕРЅРёРјРЅС‹Р№ cookie, Р° РЅРµ consent-РѕРІС‹Р№. РўРѕРєРµРЅ РїРµСЂРµРЅРѕСЃРёС‚СЃСЏ РІ
        # consent-cookie РѕРїРµСЂР°С‚РѕСЂРѕРј/РёРЅС‚РµРіСЂР°С†РёРµР№ РїСЂРё Р°РїРіСЂРµР№РґРµ (РЅРёР¶Рµ РїРѕ СЃС†РµРЅР°СЂРёСЋ).
        anonymous_token = cookie_response.cookies[
            COOKIES_ANONYMOUS_TOKEN_COOKIE_NAME
        ].value
        cookie_record = CookieConsentRecord.objects.get()

        assert cookie_record.anonymous_token == anonymous_token
        assert cookie_record.status == CookieConsentRecord.Status.CURRENT
        assert (
            cookie_record.events.get().event_type
            == CookieConsentEvent.EventType.ACCEPTED
        )
        assert get_cookie_status(anonymous_token=anonymous_token)["is_current"] is True

    with override_settings(DJANGO_152FZ_CONSENT=FULL_SETTINGS):
        _assert_no_compatibility_errors()
        purpose = _create_anonymous_purpose(
            code="contact_capture",
            document_code="contact_doc",
        )
        client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = anonymous_token

        document_response = client.get(
            reverse(
                "django_consent_152fz:document",
                kwargs={
                    "purpose_code": purpose.code,
                    "document_code": "contact_doc",
                },
            )
        )

        assert document_response.status_code == 200
        assert "contact_capture consent" in document_response.content.decode("utf-8")

        request = RequestFactory().post(
            "/contact/",
            data={
                "contact_consent-scenario": "contact",
                "contact_consent-confirm": "on",
                "contact_consent-contact_name": "Alice",
                "contact_consent-contact_email": "lead@example.com",
                "contact_consent-contact_phone": "+79990001122",
            },
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_REFERER="https://example.test/contact/",
            HTTP_X_REQUEST_ID="req-stage-contact-1",
        )
        request.user = AnonymousUser()
        request.COOKIES[ANONYMOUS_TOKEN_COOKIE_NAME] = anonymous_token

        consent_record, form = submit_anonymous_contact_consent(
            request,
            purpose_code=purpose.code,
            document_code="contact_doc",
            prefix="contact_consent",
        )

        cookie_record.refresh_from_db()

        assert form.is_valid() is True
        assert consent_record.anonymous_token == anonymous_token
        assert consent_record.subject_ref == "lead@example.com"
        assert consent_record.events.get(event_type=ConsentEvent.EventType.GIVEN)
        assert CookieConsentRecord.objects.count() == 1
        assert cookie_record.status == CookieConsentRecord.Status.CURRENT
        assert get_cookie_status(anonymous_token=anonymous_token)["is_current"] is True

        superuser = _create_superuser()
        admin_client = Client()
        admin_client.force_login(superuser)

        for model in (
            ConsentRecord,
            ConsentEvent,
            CookieConsentRecord,
            CookieConsentEvent,
        ):
            response = admin_client.get(reverse(_admin_changelist_name(model)))
            assert response.status_code == 200


@pytest.mark.django_db
def test_access_policies_can_be_enabled_later_for_existing_template_flow() -> None:
    anonymous_token = "anon-late-access"
    purpose = _create_anonymous_purpose(
        code="portal_access",
        document_code="portal_doc",
    )
    ConsentAccessPolicy.objects.create(
        code="portal-access-create",
        title="Portal access",
        purpose=purpose,
        document_id=purpose.audience_rules.get().document_id,
        resource_code="portal.profile",
        action="update",
        on_missing_consent=ConsentAccessPolicy.MissingConsentAction.REDIRECT_TO_CONSENT,
    )

    with override_settings(DJANGO_152FZ_CONSENT=FULL_SETTINGS):
        _assert_no_compatibility_errors()
        assert (
            _render_access_result(
                resource_code="portal.profile",
                action="update",
                anonymous_token=anonymous_token,
            )
            == "allow|feature_disabled|True|False"
        )

    with override_settings(DJANGO_152FZ_CONSENT=FULL_WITH_ACCESS_SETTINGS):
        _assert_no_compatibility_errors()
        assert (
            _render_access_result(
                resource_code="portal.profile",
                action="update",
                anonymous_token=anonymous_token,
            )
            == "redirect_to_consent|missing_consent|False|True"
        )

        client = Client(HTTP_USER_AGENT="Mozilla/5.0")
        client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = anonymous_token
        accept_response = client.post(
            reverse(
                "django_consent_152fz:accept",
                kwargs={
                    "purpose_code": purpose.code,
                    "document_code": "portal_doc",
                },
            ),
            data={
                "confirm": "on",
                "next": "/after-access-consent/",
            },
            HTTP_X_REQUEST_ID="req-stage-access-1",
        )

        assert accept_response.status_code == 302
        assert (
            _render_access_result(
                resource_code="portal.profile",
                action="update",
                anonymous_token=anonymous_token,
            )
            == "allow|current_consent|True|False"
        )


@pytest.mark.django_db
def test_verified_consents_can_be_enabled_later_for_existing_core_record() -> None:
    anonymous_token = "anon-late-verified"
    purpose = _create_anonymous_purpose(
        code="verified_late_enable",
        document_code="verified_late_enable_doc",
    )
    operator = _create_verified_operator(username="pdm-late-verified")

    with override_settings(DJANGO_152FZ_CONSENT=FULL_SETTINGS):
        _assert_no_compatibility_errors()
        legacy_record = accept_consent(
            purpose_code=purpose.code,
            document_code="verified_late_enable_doc",
            anonymous_token=anonymous_token,
            confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
            source="web",
        )
        legacy_status = get_consent_status(
            purpose_code=purpose.code,
            document_code="verified_late_enable_doc",
            anonymous_token=anonymous_token,
        )

        assert legacy_record.status == ConsentRecord.Status.CURRENT
        assert legacy_status["status"] == ConsentRecord.Status.CURRENT
        assert legacy_status["requires_consent"] is False

    with override_settings(DJANGO_152FZ_CONSENT=FULL_WITH_VERIFIED_SETTINGS):
        _assert_no_compatibility_errors()
        VerifiedConsentPolicy.objects.create(
            purpose=purpose,
            document_id=purpose.audience_rules.get().document_id,
            verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
        )
        transition_status = get_consent_status(
            purpose_code=purpose.code,
            document_code="verified_late_enable_doc",
            anonymous_token=anonymous_token,
        )
        assert transition_status["status"] == ConsentRecord.Status.OUTDATED
        assert transition_status["requires_consent"] is True

        pending_record = submit_verified_consent(
            purpose_code=purpose.code,
            document_code="verified_late_enable_doc",
            anonymous_token=anonymous_token,
            paper_file=SimpleUploadedFile(
                "late-enable.pdf",
                b"%PDF-1.4 late enable verified",
                content_type="application/pdf",
            ),
            artifact_note="Late enable verification upload",
            performed_by=operator,
        )
        confirmed_record = confirm_verified_consent(
            consent_record=pending_record,
            confirmed_by=operator,
            confirmation_method=ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
            confirmation_note="Late-enable verified confirmation",
            audit_context={"source": "admin"},
        )
        final_status = get_consent_status(
            purpose_code=purpose.code,
            document_code="verified_late_enable_doc",
            anonymous_token=anonymous_token,
        )
        legacy_record.refresh_from_db()

        assert confirmed_record.status == ConsentRecord.Status.CURRENT
        assert final_status["status"] == ConsentRecord.Status.CURRENT
        assert final_status["requires_consent"] is False
        assert legacy_record.status == ConsentRecord.Status.OUTDATED
        assert (
            legacy_record.events.get(
                event_type=ConsentEvent.EventType.OUTDATED
            ).payload["reason"]
            == "verified_policy_mark_web_outdated"
        )

        event_types = list(
            confirmed_record.events.order_by("occurred_at", "id").values_list(
                "event_type",
                flat=True,
            )
        )
        assert event_types == [
            ConsentEvent.EventType.PAPER_UPLOADED,
            ConsentEvent.EventType.EMPLOYEE_CONFIRMED,
        ]
