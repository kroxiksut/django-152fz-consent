from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import RequestContext, Template
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentAccessPolicy,
    ConsentAudienceRule,
    ConsentEvent,
    ConsentPurpose,
    ConsentRecord,
    ConsentSelfServiceSettings,
    DocumentRevision,
    LegalDocument,
)
from django_consent_152fz.core.services import accept_consent, publish_document_revision
from django_consent_152fz.request import ANONYMOUS_TOKEN_COOKIE_NAME
from django_consent_152fz.verified_consents.models import (
    VerifiedConsentFormPolicy,
    VerifiedConsentPolicy,
    VerifiedConsentSubmission,
)
from django_consent_152fz.verified_consents.services import (
    save_verified_consent_submission_data,
    submit_verified_consent_for_submission,
)


def _create_purpose(
    *,
    code: str = "signup",
    reconsent_mode: str = constants.RECONSENT_MODE_SOFT,
    subject_availability_policy: str = (
        constants.SUBJECT_AVAILABILITY_AUTHENTICATED_AND_ANONYMOUS
    ),
) -> ConsentPurpose:
    return ConsentPurpose.objects.create(
        code=code,
        title="Регистрация",
        description="Согласие для регистрационной формы",
        fields_config=["email", "full_name"],
        reconsent_mode=reconsent_mode,
        subject_availability_policy=subject_availability_policy,
    )


def _publish_revision(
    *,
    purpose: ConsentPurpose,
    document_code: str = "signup_doc",
    content_text: str = "Текст согласия",
) -> DocumentRevision:
    return publish_document_revision(
        document_code=document_code,
        purpose_code=purpose.code,
        content_format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text=content_text,
    )


def _html_pdf_download_hook(*, body_html: str, revision) -> bytes:
    del revision
    return ("%PDF-html-download\n" + body_html).encode("utf-8")


@pytest.mark.django_db
def test_document_page_renders_document_and_consent_form() -> None:
    purpose = _create_purpose()
    _publish_revision(purpose=purpose)
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "signup_doc",
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Регистрация" in content
    assert "Текст согласия" in content
    assert "Подтвердить согласие" in content
    assert "Я даю согласие на обработку персональных данных" in content


@pytest.mark.django_db
def test_document_page_renders_pdf_download_link() -> None:
    purpose = _create_purpose(code="pdf_link_ui")
    _publish_revision(purpose=purpose, document_code="pdf_link_doc")
    client = Client()
    document_url = reverse(
        "django_consent_152fz:document",
        kwargs={
            "purpose_code": purpose.code,
            "document_code": "pdf_link_doc",
        },
    )
    pdf_url = reverse(
        "django_consent_152fz:document_pdf",
        kwargs={
            "purpose_code": purpose.code,
            "document_code": "pdf_link_doc",
        },
    )

    response = client.get(document_url)

    assert response.status_code == 200
    assert pdf_url in response.content.decode("utf-8")


@pytest.mark.django_db
def test_document_pdf_download_returns_pdf_attachment() -> None:
    purpose = _create_purpose(code="pdf_download_ui")
    _publish_revision(
        purpose=purpose,
        document_code="pdf_download_doc",
        content_text="PDF export text",
    )
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document_pdf",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "pdf_download_doc",
            },
        )
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    content_disposition = response["Content-Disposition"]
    assert content_disposition.startswith("attachment; filename=")
    assert "pdf_download_doc" in content_disposition
    assert response.content.startswith(b"%PDF-1.4")


@pytest.mark.django_db
def test_document_pdf_download_returns_400_for_html_without_hook() -> None:
    purpose = _create_purpose(code="pdf_download_html_missing_hook_ui")
    publish_document_revision(
        document_code="pdf_download_html_missing_hook_doc",
        purpose_code=purpose.code,
        content_format=DocumentRevision.ContentFormat.HTML,
        content_text="<p>HTML export</p>",
    )
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document_pdf",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "pdf_download_html_missing_hook_doc",
            },
        )
    )

    assert response.status_code == 400
    assert "html_to_pdf_hook" in response.content.decode("utf-8")


@override_settings(
    DJANGO_152FZ_CONSENT={
        "document_templates": {"html_to_pdf_hook": _html_pdf_download_hook},
    }
)
@pytest.mark.django_db
def test_document_pdf_download_uses_html_to_pdf_hook_for_html_revisions() -> None:
    purpose = _create_purpose(code="pdf_download_html_ui")
    publish_document_revision(
        document_code="pdf_download_html_doc",
        purpose_code=purpose.code,
        content_format=DocumentRevision.ContentFormat.HTML,
        content_text="<p>HTML export</p>",
    )
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document_pdf",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "pdf_download_html_doc",
            },
        )
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-html-download")


@override_settings(
    DJANGO_152FZ_CONSENT={
        "subject_consents": {
            "consent_input_mode": "radio",
            "decline_action": "block_submit",
        }
    }
)
@pytest.mark.django_db
def test_document_page_renders_radio_consent_mode() -> None:
    purpose = _create_purpose(code="radio_mode_ui")
    _publish_revision(purpose=purpose, document_code="radio_mode_doc")
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "radio_mode_doc",
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "consent_decision" in content
    assert 'name="confirm"' not in content


@override_settings(
    DJANGO_152FZ_CONSENT={
        "subject_consents": {
            "consent_input_mode": "checkbox",
            "decline_action": "block_submit",
        }
    }
)
@pytest.mark.django_db
def test_document_page_applies_per_purpose_capture_override() -> None:
    purpose = _create_purpose(code="purpose_override_ui")
    purpose.consent_input_mode_override = "radio"
    purpose.decline_action_override = "allow_submit"
    purpose.save(
        update_fields=[
            "consent_input_mode_override",
            "decline_action_override",
        ]
    )
    _publish_revision(purpose=purpose, document_code="purpose_override_doc")
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "purpose_override_doc",
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "consent_decision" in content
    assert 'name="confirm"' not in content


@override_settings(
    DJANGO_152FZ_CONSENT={
        "subject_consents": {
            "consent_input_mode": "radio",
            "decline_action": "block_submit",
        }
    }
)
@pytest.mark.django_db
def test_accept_view_blocks_decline_in_radio_mode() -> None:
    purpose = _create_purpose(code="radio_decline_ui")
    _publish_revision(purpose=purpose, document_code="radio_decline_doc")
    client = Client()

    response = client.post(
        reverse(
            "django_consent_152fz:accept",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "radio_decline_doc",
            },
        ),
        data={
            "consent_decision": "decline",
            "next": "/after-consent/",
        },
    )

    assert response.status_code == 400
    assert ConsentRecord.objects.filter(purpose=purpose).count() == 0


@pytest.mark.django_db
def test_document_page_hides_accept_form_for_authenticated_only_purpose() -> None:
    purpose = _create_purpose(
        code="auth_only_ui",
        subject_availability_policy=constants.SUBJECT_AVAILABILITY_AUTHENTICATED_ONLY,
    )
    _publish_revision(purpose=purpose, document_code="auth_only_ui_doc")
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "auth_only_ui_doc",
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Для этого согласия требуется авторизация" in content
    assert "Подтвердить согласие" not in content


@pytest.mark.django_db
def test_accept_view_creates_record_sets_cookie_and_writes_request_audit_context() -> (
    None
):
    purpose = _create_purpose()
    _publish_revision(purpose=purpose)
    client = Client(HTTP_USER_AGENT="Mozilla/5.0")

    response = client.post(
        reverse(
            "django_consent_152fz:accept",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "signup_doc",
            },
        ),
        data={
            "confirm": "on",
            "next": "/after-consent/",
            "client_timezone": "Asia/Irkutsk",
            "client_languages": '["ru-RU", "en-US"]',
            "client_os_locale": "ru-RU",
            "client_screen_width": "1440",
            "client_screen_height": "900",
        },
        HTTP_REFERER="https://example.test/signup/",
        HTTP_X_REQUEST_ID="req-template-1",
        HTTP_SEC_CH_UA_PLATFORM='"Windows"',
        HTTP_SEC_CH_UA_MOBILE="?0",
    )

    assert response.status_code == 302
    assert response["Location"] == "/after-consent/"
    assert ANONYMOUS_TOKEN_COOKIE_NAME in response.cookies

    record = ConsentRecord.objects.get(purpose=purpose)
    event = record.events.get(event_type=ConsentEvent.EventType.GIVEN)

    assert record.status == ConsentRecord.Status.CURRENT
    assert record.source == "template_ui.accept"
    assert record.user_agent == "Mozilla/5.0"
    assert record.extra_meta["request"]["path"].endswith(
        "/consent/accept/signup/signup_doc/"
    )
    assert record.extra_meta["request"]["referrer"] == "https://example.test/signup/"
    assert record.extra_meta["client"]["timezone"] == "Asia/Irkutsk"
    assert record.extra_meta["client"]["languages"] == ["ru-RU", "en-US"]
    assert record.extra_meta["client"]["os_locale"] == "ru-RU"
    assert record.extra_meta["client"]["screen"]["width"] == 1440
    assert record.extra_meta["client"]["screen"]["height"] == 900
    assert event.request_id == "req-template-1"
    assert event.extra_meta["client_hints"]["sec_ch_ua_platform"] == '"Windows"'
    assert event.extra_meta["client_hints"]["sec_ch_ua_mobile"] == "?0"


@pytest.mark.django_db
def test_accept_view_honors_form_specific_verified_override() -> None:
    purpose = _create_purpose(code="signup_form_verified")
    revision = _publish_revision(
        purpose=purpose,
        document_code="signup_form_verified_doc",
    )
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.WEB_ONLY,
    )
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        form_code="demo.signup_form",
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED
        ),
    )
    client = Client(HTTP_USER_AGENT="Mozilla/5.0")

    response = client.post(
        reverse(
            "django_consent_152fz:accept",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": revision.document.code,
            },
        ),
        data={
            "confirm": "on",
            "next": "/after-consent/",
            "verification_channel": "form",
            "verification_form_code": "demo.signup_form",
        },
    )

    assert response.status_code == 400
    assert "requires verified confirmation" in response.content.decode("utf-8")
    assert ConsentRecord.objects.filter(purpose=purpose).count() == 0


@pytest.mark.django_db
def test_document_page_shows_verified_transition_message_and_hides_web_submit() -> None:
    purpose = _create_purpose(code="signup_verified_ui")
    revision = _publish_revision(
        purpose=purpose,
        document_code="signup_verified_ui_doc",
    )
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
    )
    client = Client()

    response = client.get(
        reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": revision.document.code,
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Подписание через web-форму недоступно" in content
    assert "Подтвердить согласие" not in content


@pytest.mark.parametrize(
    ("status_code", "expected_message"),
    [
        (
            constants.VERIFIED_TRANSITION_STATUS_AWAITING_UPLOAD,
            "ещё не загружен подписанный бумажный документ",
        ),
        (
            constants.VERIFIED_TRANSITION_STATUS_PENDING_VERIFICATION,
            "ожидает проверки оператором ПДн",
        ),
        (
            constants.VERIFIED_TRANSITION_STATUS_REJECTED,
            "проверяемое подтверждение отклонено",
        ),
    ],
)
@pytest.mark.django_db
def test_document_page_shows_transition_messages_for_non_verified_states(
    *,
    status_code: str,
    expected_message: str,
) -> None:
    purpose = _create_purpose(code=f"signup_verified_ui_{status_code}")
    revision = _publish_revision(
        purpose=purpose,
        document_code=f"signup_verified_ui_{status_code}_doc",
    )
    policy = VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=revision.document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
    )
    anonymous_token = f"anon-ui-{status_code}"

    if status_code == constants.VERIFIED_TRANSITION_STATUS_AWAITING_UPLOAD:
        save_verified_consent_submission_data(
            purpose_code=purpose.code,
            document_code=policy.document.code,
            anonymous_token=anonymous_token,
            subject_data={"full_name": "Иван Иванов"},
            verification_context={"channel": "self_service"},
        )
    else:
        submission = save_verified_consent_submission_data(
            purpose_code=purpose.code,
            document_code=policy.document.code,
            anonymous_token=anonymous_token,
            subject_data={"full_name": "Иван Иванов"},
            verification_context={"channel": "self_service"},
        )
        record = submit_verified_consent_for_submission(
            submission=submission,
            paper_file=SimpleUploadedFile(
                "paper.pdf",
                b"%PDF-1.4 ui transition",
                content_type="application/pdf",
            ),
        )
        if status_code == constants.VERIFIED_TRANSITION_STATUS_REJECTED:
            record.status = ConsentRecord.Status.REJECTED
            record.save(update_fields=["status"])
            submission.status = VerifiedConsentSubmission.WorkflowStatus.REJECTED
            submission.save(update_fields=["status"])

    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = anonymous_token
    response = client.get(
        reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": revision.document.code,
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert expected_message in content
    assert "Подтвердить согласие" not in content


@override_settings(
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
@pytest.mark.django_db
def test_accept_view_with_csrf_checks_enabled_works_from_document_page() -> None:
    purpose = _create_purpose()
    _publish_revision(purpose=purpose)
    client = Client(enforce_csrf_checks=True)
    document_url = reverse(
        "django_consent_152fz:document",
        kwargs={
            "purpose_code": purpose.code,
            "document_code": "signup_doc",
        },
    )
    accept_url = reverse(
        "django_consent_152fz:accept",
        kwargs={
            "purpose_code": purpose.code,
            "document_code": "signup_doc",
        },
    )

    get_response = client.get(document_url)
    assert get_response.status_code == 200
    csrf_token = str(get_response.context["csrf_token"])

    post_response = client.post(
        accept_url,
        data={
            "csrfmiddlewaretoken": csrf_token,
            "confirm": "on",
            "next": "/after-consent/",
        },
    )
    assert post_response.status_code == 302
    assert post_response["Location"] == "/after-consent/"


@override_settings(
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
@pytest.mark.django_db
def test_every_time_flow_keeps_accept_step_and_csrf_after_first_confirmation() -> None:
    purpose = ConsentPurpose.objects.create(
        code="every_time_ui",
        title="Повторное подтверждение",
        description="Тест every_time",
        fields_config=["email"],
        consent_frequency_policy=constants.CONSENT_FREQUENCY_EVERY_TIME,
    )
    _publish_revision(purpose=purpose, document_code="every_time_ui_doc")
    client = Client(enforce_csrf_checks=True)
    document_url = reverse(
        "django_consent_152fz:document",
        kwargs={
            "purpose_code": purpose.code,
            "document_code": "every_time_ui_doc",
        },
    )
    accept_url = reverse(
        "django_consent_152fz:accept",
        kwargs={
            "purpose_code": purpose.code,
            "document_code": "every_time_ui_doc",
        },
    )

    first_get = client.get(document_url)
    first_token = str(first_get.context["csrf_token"])
    first_post = client.post(
        accept_url,
        data={
            "csrfmiddlewaretoken": first_token,
            "confirm": "on",
            "next": "/after-consent/",
        },
    )
    assert first_post.status_code == 302

    second_get = client.get(document_url)
    content = second_get.content.decode("utf-8")
    assert "Для этого действия нужно повторное подтверждение согласия." in content
    assert "Подтвердить согласие" in content
    second_token = str(second_get.context["csrf_token"])
    second_post = client.post(
        accept_url,
        data={
            "csrfmiddlewaretoken": second_token,
            "confirm": "on",
            "next": "/after-consent/",
        },
    )
    assert second_post.status_code == 302


@pytest.mark.django_db
def test_withdraw_page_with_cookie_withdraws_and_preserves_request_context() -> None:
    purpose = _create_purpose()
    _publish_revision(purpose=purpose)
    record = accept_consent(
        purpose_code=purpose.code,
        document_code="signup_doc",
        anonymous_token="anon-template-ui",
    )
    client = Client(HTTP_USER_AGENT="Mozilla/5.0")
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-template-ui"

    get_response = client.get(
        reverse(
            "django_consent_152fz:withdraw",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "signup_doc",
            },
        )
    )
    assert get_response.status_code == 200
    assert "Отзыв согласия" in get_response.content.decode("utf-8")

    post_response = client.post(
        reverse(
            "django_consent_152fz:withdraw",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "signup_doc",
            },
        ),
        data={"confirm": "on", "next": "/withdrawn/"},
        HTTP_REFERER="https://example.test/account/",
        HTTP_X_REQUEST_ID="req-withdraw-1",
    )

    assert post_response.status_code == 302
    assert post_response["Location"] == "/withdrawn/"

    record.refresh_from_db()
    assert record.status == ConsentRecord.Status.WITHDRAWN
    withdraw_event = record.events.get(event_type=ConsentEvent.EventType.WITHDRAWN)
    assert withdraw_event.source == "template_ui.withdraw"
    assert withdraw_event.request_id == "req-withdraw-1"
    assert (
        withdraw_event.extra_meta["request"]["referrer"]
        == "https://example.test/account/"
    )


@pytest.mark.django_db
def test_document_page_shows_reconsent_notice_for_outdated_record() -> None:
    purpose = _create_purpose(
        code="hard_signup",
        reconsent_mode=constants.RECONSENT_MODE_HARD,
    )
    _publish_revision(
        purpose=purpose,
        document_code="hard_doc",
        content_text="Редакция 1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="hard_doc",
        anonymous_token="anon-hard-ui",
    )
    _publish_revision(
        purpose=purpose,
        document_code="hard_doc",
        content_text="Редакция 2",
    )
    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-hard-ui"

    response = client.get(
        reverse(
            "django_consent_152fz:document",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "hard_doc",
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Требуется новое согласие" in content
    assert "Редакция 2" in content


@pytest.mark.django_db
def test_subject_consents_page_shows_latest_records_with_signed_actions() -> None:
    purpose = _create_purpose(code="profile")
    _publish_revision(
        purpose=purpose,
        document_code="profile_doc",
        content_text="Редакция 1",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="profile_doc",
        anonymous_token="anon-self-service",
    )
    _publish_revision(
        purpose=purpose,
        document_code="profile_doc",
        content_text="Редакция 2",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="profile_doc",
        anonymous_token="anon-self-service",
    )
    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-self-service"

    response = client.get(reverse("django_consent_152fz:subject_consents"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Мои согласия" in content
    assert "Регистрация" in content
    assert "(<code>profile_doc</code>)" not in content
    assert ">current<" not in content
    assert "Открыть и подписать" not in content
    assert "Отозвать" in content


@pytest.mark.django_db
def test_subject_consents_uses_russian_title_for_sample_service_document() -> None:
    purpose = _create_purpose(code="service_account_ui")
    revision = _publish_revision(
        purpose=purpose,
        document_code="sample_service_terms_agreement",
        content_text="Sample agreement",
    )
    revision.document.title = "sample_service_terms_agreement"
    revision.document.save(update_fields=["title"])
    accept_consent(
        purpose_code=purpose.code,
        document_code="sample_service_terms_agreement",
        anonymous_token="anon-service-account",
    )
    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-service-account"

    response = client.get(reverse("django_consent_152fz:subject_consents"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Соглашение об условиях обслуживания аккаунта" in content
    assert "(<code>sample_service_terms_agreement</code>)" not in content


@override_settings(
    DJANGO_152FZ_CONSENT={
        "subject_consents": {
            "open_mode": "new_window",
        }
    }
)
@pytest.mark.django_db
def test_subject_consents_page_supports_new_window_open_mode() -> None:
    purpose = _create_purpose(code="profile_new_window")
    _publish_revision(
        purpose=purpose,
        document_code="profile_new_window_doc",
        content_text="Редакция",
    )
    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-open-new-window"

    response = client.get(reverse("django_consent_152fz:subject_consents"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Открыть и подписать" in content
    assert 'target="_blank"' in content
    assert 'data-action="open-document-modal"' not in content


@override_settings(
    DJANGO_152FZ_CONSENT={
        "subject_consents": {
            "open_mode": "modal",
        }
    }
)
@pytest.mark.django_db
def test_subject_consents_page_supports_modal_open_mode() -> None:
    purpose = _create_purpose(code="profile_modal")
    _publish_revision(
        purpose=purpose,
        document_code="profile_modal_doc",
        content_text="Редакция",
    )
    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-open-modal"

    response = client.get(reverse("django_consent_152fz:subject_consents"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Открыть и подписать" in content
    assert 'data-action="open-document-modal"' in content
    assert 'id="subject-consents-modal"' in content


@override_settings(
    DJANGO_152FZ_CONSENT={
        "subject_consents": {
            "open_mode": "page",
        }
    }
)
@pytest.mark.django_db
def test_subject_consents_page_prefers_explicit_settings_over_admin_override() -> None:
    ConsentSelfServiceSettings.objects.create(
        subject_consents_open_mode=(
            ConsentSelfServiceSettings.SubjectConsentsOpenMode.NEW_WINDOW
        )
    )
    purpose = _create_purpose(code="profile_admin_override")
    revision = _publish_revision(
        purpose=purpose,
        document_code="profile_admin_override_doc",
        content_text="Редакция",
    )
    ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=revision.document,
        scope_mode=ConsentAudienceRule.ScopeMode.ANONYMOUS_SUBJECTS,
        is_required=True,
        is_active=True,
    )
    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-open-admin-override"

    response = client.get(reverse("django_consent_152fz:subject_consents"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert 'target="_blank"' not in content
    assert 'data-action="open-document-modal"' not in content


@pytest.mark.django_db
def test_subject_consents_page_supports_signed_only_list_mode() -> None:
    ConsentSelfServiceSettings.objects.create(
        subject_consents_list_mode=(
            ConsentSelfServiceSettings.SubjectConsentsListMode.SIGNED_ONLY
        )
    )
    purpose = _create_purpose(code="profile_signed_only")
    _publish_revision(
        purpose=purpose,
        document_code="profile_signed_only_doc",
        content_text="Редакция",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code="profile_signed_only_doc",
        anonymous_token="anon-signed-only",
    )
    client = Client()
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-signed-only"

    response = client.get(reverse("django_consent_152fz:subject_consents"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Открыть и подписать" not in content
    assert "Отозвать" in content


@pytest.mark.django_db
def test_subject_consents_self_service_withdraw_uses_service_layer_and_audit_source() -> (
    None
):
    purpose = _create_purpose(code="self_withdraw")
    _publish_revision(
        purpose=purpose,
        document_code="self_withdraw_doc",
        content_text="Редакция",
    )
    record = accept_consent(
        purpose_code=purpose.code,
        document_code="self_withdraw_doc",
        anonymous_token="anon-self-withdraw",
    )
    client = Client(HTTP_USER_AGENT="Mozilla/5.0")
    client.cookies[ANONYMOUS_TOKEN_COOKIE_NAME] = "anon-self-withdraw"

    response = client.post(
        reverse(
            "django_consent_152fz:subject_consents_withdraw",
            kwargs={
                "purpose_code": purpose.code,
                "document_code": "self_withdraw_doc",
            },
        ),
        HTTP_X_REQUEST_ID="req-self-withdraw-1",
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("django_consent_152fz:subject_consents")
    record.refresh_from_db()
    assert record.status == ConsentRecord.Status.WITHDRAWN
    withdraw_event = record.events.get(event_type=ConsentEvent.EventType.WITHDRAWN)
    assert withdraw_event.source == "self_service.withdraw"
    assert withdraw_event.request_id == "req-self-withdraw-1"


@override_settings(
    DJANGO_152FZ_CONSENT={
        "enable_core": True,
        "enable_access_policies": True,
        "purposes": {},
    }
)
@pytest.mark.django_db
def test_template_tags_return_access_result_and_notice() -> None:
    purpose = _create_purpose(code="billing")
    document = LegalDocument.objects.create(code="billing_doc", title="Billing")
    DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="Billing consent",
        fields_snapshot=["email"],
        is_active=True,
    )
    ConsentAccessPolicy.objects.create(
        code="billing-view",
        title="Billing view",
        purpose=purpose,
        document=document,
        resource_code="billing_portal",
        action="view",
        on_missing_consent=ConsentAccessPolicy.MissingConsentAction.REDIRECT_TO_CONSENT,
    )
    factory = RequestFactory()
    request = factory.get("/billing/")
    template = Template(
        "{% load consent_tags %}"
        "{% consent_access 'billing_portal' 'view' as access %}"
        "{% consent_reconsent_notice 'billing' 'billing_doc' as notice %}"
        "{{ access.resolution }}|{{ notice|default:'no-notice' }}"
    )

    rendered = template.render(RequestContext(request, {}))

    assert "redirect_to_consent" in rendered
    assert "no-notice" in rendered
