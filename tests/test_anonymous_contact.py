from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.template import RequestContext, Template
from django.test import RequestFactory

from django_consent_152fz.contact_hooks import submit_anonymous_contact_consent
from django_consent_152fz.core.models import (
    ConsentAudienceRule,
    ConsentEvent,
    ConsentPurpose,
)
from django_consent_152fz.core.services import publish_document_revision
from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.verified_consents.models import (
    VerifiedConsentFormPolicy,
    VerifiedConsentPolicy,
)


def _create_anonymous_purpose(
    *,
    code: str,
    document_code: str,
) -> ConsentPurpose:
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


@pytest.mark.django_db
def test_render_contact_consent_hook_outputs_prefixed_fields_and_document_link() -> (
    None
):
    _create_anonymous_purpose(code="contact_capture", document_code="contact_doc")
    factory = RequestFactory()
    request = factory.get("/contact/")
    request.user = AnonymousUser()
    template = Template(
        "{% load consent_tags %}<form>"
        "{% render_contact_consent_hook 'contact_capture' 'contact_doc' %}"
        "{% render_preorder_consent_hook 'contact_capture' 'contact_doc' %}"
        "</form>"
    )

    rendered = template.render(RequestContext(request, {}))

    assert "/consent/documents/contact_capture/contact_doc/" in rendered
    assert 'name="contact_consent-subject_ref"' in rendered
    assert 'name="preorder_consent-preorder_id"' in rendered
    assert 'name="contact_consent-verification_channel"' in rendered
    assert 'name="contact_consent-verification_form_code"' in rendered
    assert "обратной связи" in rendered
    assert "предзаказа" in rendered


@pytest.mark.django_db
def test_submit_anonymous_contact_consent_uses_email_as_subject_ref() -> None:
    _create_anonymous_purpose(code="contact_capture", document_code="contact_doc")
    factory = RequestFactory()
    request = factory.post(
        "/contact/",
        data={
            "contact_consent-scenario": "contact",
            "contact_consent-confirm": "on",
            "contact_consent-contact_name": "Alice",
            "contact_consent-contact_email": "lead@example.com",
            "contact_consent-contact_phone": "+79990001122",
            "contact_consent-contact_message": "Call me back",
            "contact_consent-client_timezone": "Asia/Irkutsk",
            "contact_consent-client_languages": '["ru-RU"]',
        },
        HTTP_USER_AGENT="Mozilla/5.0",
        HTTP_REFERER="https://example.test/contact/",
        HTTP_X_REQUEST_ID="req-contact-1",
    )
    request.user = AnonymousUser()

    record, form = submit_anonymous_contact_consent(
        request,
        purpose_code="contact_capture",
        document_code="contact_doc",
        prefix="contact_consent",
    )

    event = record.events.get(event_type=ConsentEvent.EventType.GIVEN)

    assert form.is_valid() is True
    assert record.user_id is None
    assert record.anonymous_token
    assert record.subject_ref == "lead@example.com"
    assert record.extra_meta["custom"]["contact"]["scenario"] == "contact"
    assert record.extra_meta["custom"]["contact"]["name"] == "Alice"
    assert record.extra_meta["custom"]["contact"]["email"] == "lead@example.com"
    assert record.extra_meta["custom"]["contact"]["phone"] == "+79990001122"
    assert record.extra_meta["custom"]["contact"]["message"] == "Call me back"
    assert record.extra_meta["client"]["timezone"] == "Asia/Irkutsk"
    assert event.request_id == "req-contact-1"


@pytest.mark.django_db
def test_submit_anonymous_preorder_consent_uses_preorder_id_as_subject_ref() -> None:
    _create_anonymous_purpose(code="preorder_capture", document_code="preorder_doc")
    factory = RequestFactory()
    request = factory.post(
        "/preorder/",
        data={
            "preorder_consent-scenario": "preorder",
            "preorder_consent-confirm": "on",
            "preorder_consent-preorder_id": "PO-42",
            "preorder_consent-contact_phone": "+79991234567",
            "preorder_consent-contact_address": "Irkutsk",
        },
        HTTP_USER_AGENT="Mozilla/5.0",
    )
    request.user = AnonymousUser()

    record, _form = submit_anonymous_contact_consent(
        request,
        purpose_code="preorder_capture",
        document_code="preorder_doc",
        scenario="preorder",
        prefix="preorder_consent",
    )

    assert record.subject_ref == "PO-42"
    assert record.extra_meta["custom"]["preorder_id"] == "PO-42"
    assert record.extra_meta["custom"]["contact"]["scenario"] == "preorder"
    assert record.extra_meta["custom"]["contact"]["phone"] == "+79991234567"
    assert record.extra_meta["custom"]["contact"]["address"] == "Irkutsk"


@pytest.mark.django_db
def test_submit_anonymous_contact_consent_requires_identifier() -> None:
    _create_anonymous_purpose(code="contact_capture", document_code="contact_doc")
    factory = RequestFactory()
    request = factory.post(
        "/contact/",
        data={
            "contact_consent-scenario": "contact",
            "contact_consent-confirm": "on",
        },
    )
    request.user = AnonymousUser()

    with pytest.raises(ConsentError, match="subject_ref"):
        submit_anonymous_contact_consent(
            request,
            purpose_code="contact_capture",
            document_code="contact_doc",
            prefix="contact_consent",
        )


@pytest.mark.django_db
def test_submit_anonymous_contact_consent_honors_verified_form_policy_switch() -> None:
    purpose = _create_anonymous_purpose(
        code="contact_verified_switch",
        document_code="contact_verified_switch_doc",
    )
    document = purpose.audience_rules.get().document
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.WEB_ONLY,
    )
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=document,
        form_code="anonymous_hook:contact",
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED
        ),
    )

    factory = RequestFactory()
    request = factory.post(
        "/contact/",
        data={
            "contact_consent-scenario": "contact",
            "contact_consent-confirm": "on",
            "contact_consent-contact_name": "Alice",
            "contact_consent-contact_email": "lead@example.com",
        },
        HTTP_USER_AGENT="Mozilla/5.0",
    )
    request.user = AnonymousUser()

    with pytest.raises(ConsentError, match="requires verified confirmation"):
        submit_anonymous_contact_consent(
            request,
            purpose_code=purpose.code,
            document_code=document.code,
            prefix="contact_consent",
        )
