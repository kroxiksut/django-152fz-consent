from __future__ import annotations

import pytest
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from django_consent_152fz import admin as core_admin_module
from django_consent_152fz.admin import (
    StarterTemplateOriginFilter,
)
from django_consent_152fz.admin_helpers import PERSONAL_DATA_MANAGER_GROUP_NAME
from django_consent_152fz.box_templates.documents import bootstrap_sample_documents
from django_consent_152fz.core.models import (
    ConsentAccessPolicy,
    ConsentAudienceRule,
    ConsentEvent,
    ConsentModuleOperationAuditLog,
    ConsentPurpose,
    ConsentRecord,
    DocumentRevision,
    LegalDocument,
    ModuleOperationAuditLog,
    PersonalDataManagerAssignment,
)
from django_consent_152fz.verified_consents import admin as verified_admin_module
from django_consent_152fz.verified_consents.models import (
    VerifiedConsentPolicy,
)
from django_consent_152fz.verified_consents.services import submit_verified_consent
from django_cookies_152fz import admin as cookie_admin_module
from django_cookies_152fz.models import (
    CookieAdminSettings,
    CookieCategory,
    CookieConsentEvent,
    CookieConsentRecord,
    CookiePolicyRevision,
)
from django_cookies_152fz.services import (
    ensure_default_cookie_banner_text_presets,
)


def _create_superuser():
    User = get_user_model()
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="pass",
    )


def _create_staff_user(*, username: str, **assignment_flags):
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password="pass",
        is_staff=True,
    )
    assignment = PersonalDataManagerAssignment.objects.create(
        user=user,
        **assignment_flags,
    )
    return user, assignment


def _create_revision(
    *,
    purpose_code: str = "signup",
    document_code: str = "signup_doc",
):
    purpose = ConsentPurpose.objects.create(
        code=purpose_code,
        title="Signup",
        fields_config=["email"],
    )
    document = LegalDocument.objects.create(code=document_code, title="Signup doc")
    revision = DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="v1",
        fields_snapshot=["email"],
        is_active=True,
    )
    return purpose, document, revision


def _create_verified_pending_record(*, operator_user):
    purpose, document, _revision = _create_revision(
        purpose_code="verified_signup",
        document_code="verified_signup_doc",
    )
    policy = VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
    )
    record = submit_verified_consent(
        purpose_code=purpose.code,
        document_code=document.code,
        anonymous_token="anon-admin-verified",
        paper_file=SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.4 admin verified action",
            content_type="application/pdf",
        ),
        performed_by=operator_user,
    )
    return record, policy


def test_admin_register_contract_is_idempotent() -> None:
    initial_registry = set(admin.site._registry)

    core_admin_module.register_admin(admin.site)
    cookie_admin_module.register_admin(admin.site)
    verified_admin_module.register_admin(admin.site)

    assert set(admin.site._registry) == initial_registry


@pytest.mark.django_db
def test_consent_event_admin_is_read_only() -> None:
    superuser = _create_superuser()
    rf = RequestFactory()
    request = rf.get("/admin/")
    request.user = superuser

    event_admin = admin.site._registry[ConsentEvent]

    assert event_admin.has_view_permission(request) is True
    assert event_admin.has_add_permission(request) is False
    assert event_admin.has_change_permission(request) is False
    assert event_admin.has_delete_permission(request) is False


@pytest.mark.django_db
def test_personal_data_manager_assignment_admin_sets_staff_and_group_membership() -> (
    None
):
    superuser = _create_superuser()
    User = get_user_model()
    user = User.objects.create_user(
        username="operator",
        password="pass",
        is_staff=False,
    )
    assignment = PersonalDataManagerAssignment(
        user=user,
        can_manage_purposes=True,
        is_active=True,
    )
    rf = RequestFactory()
    request = rf.post("/admin/")
    request.user = superuser

    assignment_admin = admin.site._registry[PersonalDataManagerAssignment]
    assignment_admin.save_model(request, assignment, form=None, change=False)

    user.refresh_from_db()
    assert user.is_staff is True
    assert user.groups.filter(name=PERSONAL_DATA_MANAGER_GROUP_NAME).exists()


@pytest.mark.django_db
def test_document_revision_admin_actions_create_audience_rules() -> None:
    superuser = _create_superuser()
    _purpose, _document, revision = _create_revision()
    group = Group.objects.create(name="VIP")
    rf = RequestFactory()

    revision_admin = admin.site._registry[DocumentRevision]
    revision_admin.message_user = lambda *args, **kwargs: None

    all_request = rf.post("/admin/")
    all_request.user = superuser
    revision_admin.apply_revision_to_all_registered_users(
        all_request,
        DocumentRevision.objects.filter(pk=revision.pk),
    )

    assert ConsentAudienceRule.objects.filter(
        purpose__code="signup",
        document__code="signup_doc",
        scope_mode=ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS,
        group__isnull=True,
    ).exists()

    groups_request = rf.post("/admin/", data={"audience_groups": [group.pk]})
    groups_request.user = superuser
    revision_admin.apply_revision_to_selected_groups(
        groups_request,
        DocumentRevision.objects.filter(pk=revision.pk),
    )

    assert ConsentAudienceRule.objects.filter(
        purpose__code="signup",
        document__code="signup_doc",
        scope_mode=ConsentAudienceRule.ScopeMode.DJANGO_GROUP,
        group=group,
    ).exists()


@pytest.mark.django_db
def test_document_revision_admin_filter_separates_starter_templates() -> None:
    bootstrap_sample_documents()
    _purpose, _document, custom_revision = _create_revision(
        purpose_code="admin_filter_signup",
        document_code="admin_filter_signup_doc",
    )
    rf = RequestFactory()
    revision_admin = admin.site._registry[DocumentRevision]

    starter_request = rf.get("/admin/", data={"revision_origin": "starter"})
    starter_filter = StarterTemplateOriginFilter(
        starter_request,
        starter_request.GET.copy(),
        DocumentRevision,
        revision_admin,
    )
    starter_qs = starter_filter.queryset(
        starter_request,
        DocumentRevision.objects.order_by("pk"),
    )

    custom_request = rf.get("/admin/", data={"revision_origin": "custom"})
    custom_filter = StarterTemplateOriginFilter(
        custom_request,
        custom_request.GET.copy(),
        DocumentRevision,
        revision_admin,
    )
    custom_qs = custom_filter.queryset(
        custom_request,
        DocumentRevision.objects.order_by("pk"),
    )

    assert starter_qs is not None
    assert custom_qs is not None
    assert starter_qs.filter(is_box_template=True).exists()
    assert not starter_qs.filter(pk=custom_revision.pk).exists()
    assert custom_qs.filter(pk=custom_revision.pk, is_box_template=False).exists()


@pytest.mark.django_db
def test_document_revision_admin_action_clones_starter_template_as_custom_draft() -> (
    None
):
    superuser = _create_superuser()
    bootstrap_sample_documents()
    template_revision = DocumentRevision.objects.get(
        document__code="sample_feedback_contact_consent"
    )
    rf = RequestFactory()
    request = rf.post("/admin/")
    request.user = superuser

    revision_admin = admin.site._registry[DocumentRevision]
    messages_log: list[tuple[str, int]] = []
    revision_admin.message_user = lambda req, msg, level=messages.INFO, **kwargs: (
        messages_log.append((str(msg), level))
    )

    revision_admin.clone_starter_templates_as_drafts(
        request,
        DocumentRevision.objects.filter(pk=template_revision.pk),
    )

    cloned_revision = DocumentRevision.objects.get(
        document=template_revision.document,
        purpose_code=template_revision.purpose_code,
        version=template_revision.version + 1,
    )
    assert cloned_revision.pk != template_revision.pk
    assert cloned_revision.is_box_template is False
    assert cloned_revision.is_active is False
    assert cloned_revision.published_at is None
    assert cloned_revision.content_text == template_revision.content_text
    assert cloned_revision.meta["starter_template"] is False
    assert cloned_revision.meta["derived_from_box_template"] is True
    assert (
        cloned_revision.meta["box_template_source_revision_id"] == template_revision.pk
    )
    assert any(level == messages.SUCCESS for _, level in messages_log)


@pytest.mark.django_db
def test_legal_document_admin_action_clones_selected_stream_as_draft() -> None:
    superuser = _create_superuser()
    _purpose, document, _revision = _create_revision(
        purpose_code="doc_clone_signup",
        document_code="doc_clone_signup_doc",
    )
    second_revision = DocumentRevision.objects.create(
        document=document,
        purpose_code="doc_clone_signup",
        version=2,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="v2",
        fields_snapshot=["email"],
        is_active=False,
    )
    document_admin = admin.site._registry[LegalDocument]
    document_admin.message_user = lambda *args, **kwargs: None
    request = RequestFactory().post("/admin/")
    request.user = superuser

    document_admin.clone_selected_document_streams_as_drafts(
        request,
        LegalDocument.objects.filter(pk=document.pk),
    )

    cloned_document = LegalDocument.objects.exclude(pk=document.pk).get()
    assert cloned_document.code.startswith(f"{document.code}_copy")
    assert cloned_document.is_active is False
    cloned_revisions = list(
        DocumentRevision.objects.filter(document=cloned_document).order_by("version")
    )
    assert [rev.version for rev in cloned_revisions] == [1, 2]
    assert all(rev.is_active is False for rev in cloned_revisions)
    assert all(rev.is_box_template is False for rev in cloned_revisions)
    assert cloned_revisions[0].meta["derived_from_document_clone"] is True
    assert cloned_revisions[1].meta["source_revision_id"] == second_revision.pk
    assert ModuleOperationAuditLog.objects.filter(
        operation_code="admin.legal_document.clone_document_streams"
    ).exists()


@pytest.mark.django_db
def test_audience_rule_admin_action_clones_selected_rules_as_drafts() -> None:
    superuser = _create_superuser()
    purpose, document, _revision = _create_revision(
        purpose_code="aud_clone_signup",
        document_code="aud_clone_signup_doc",
    )
    source_rule = ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS,
        is_required=True,
        is_active=True,
        notes="Source rule",
        created_by=superuser,
    )
    audience_admin = admin.site._registry[ConsentAudienceRule]
    audience_admin.message_user = lambda *args, **kwargs: None
    request = RequestFactory().post("/admin/")
    request.user = superuser

    audience_admin.clone_selected_rules_as_drafts(
        request,
        ConsentAudienceRule.objects.filter(pk=source_rule.pk),
    )

    clone = ConsentAudienceRule.objects.exclude(pk=source_rule.pk).get()
    assert clone.is_active is False
    assert clone.scope_mode == source_rule.scope_mode
    assert clone.purpose_id == source_rule.purpose_id
    assert clone.document_id == source_rule.document_id
    assert "Черновая копия." in clone.notes
    assert ModuleOperationAuditLog.objects.filter(
        operation_code="admin.audience_rule.clone_rules"
    ).exists()


@pytest.mark.django_db
def test_access_policy_admin_action_clones_selected_policies_as_drafts() -> None:
    superuser = _create_superuser()
    purpose, document, _revision = _create_revision(
        purpose_code="policy_clone_signup",
        document_code="policy_clone_signup_doc",
    )
    source_policy = ConsentAccessPolicy.objects.create(
        code="policy_clone_source",
        title="Policy source",
        description="Source policy",
        purpose=purpose,
        document=document,
        resource_code="profile_page",
        action="view",
        on_missing_consent=ConsentAccessPolicy.MissingConsentAction.DENY,
        on_outdated_consent=(
            ConsentAccessPolicy.OutdatedConsentAction.RESPECT_RECONSENT_MODE
        ),
        is_active=True,
        notes="Policy notes",
        extra_meta={"custom": "value"},
    )
    policy_admin = admin.site._registry[ConsentAccessPolicy]
    policy_admin.message_user = lambda *args, **kwargs: None
    request = RequestFactory().post("/admin/")
    request.user = superuser

    policy_admin.clone_selected_policies_as_drafts(
        request,
        ConsentAccessPolicy.objects.filter(pk=source_policy.pk),
    )

    clone = ConsentAccessPolicy.objects.exclude(pk=source_policy.pk).get()
    assert clone.code.startswith("policy_clone_source_copy")
    assert clone.resource_code.startswith("profile_page_copy")
    assert clone.action == source_policy.action
    assert clone.is_active is False
    assert clone.extra_meta["derived_from_policy_clone"] is True
    assert clone.extra_meta["source_policy_id"] == source_policy.pk
    assert ModuleOperationAuditLog.objects.filter(
        operation_code="admin.access_policy.clone_policies"
    ).exists()


@pytest.mark.django_db
def test_document_revision_admin_change_form_shows_origin_and_save_as_new() -> None:
    superuser = _create_superuser()
    bootstrap_sample_documents()
    template_revision = DocumentRevision.objects.get(
        document__code="sample_feedback_contact_consent"
    )
    client = Client()
    client.force_login(superuser)

    response = client.get(
        reverse(
            "admin:django_consent_152fz_documentrevision_change",
            args=[template_revision.pk],
        )
    )

    content = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "_saveasnew" in content
    assert "sample_feedback_contact_consent" in content


@pytest.mark.django_db
def test_consent_record_admin_exports_csv() -> None:
    superuser = _create_superuser()
    purpose, _document, revision = _create_revision()
    record = ConsentRecord.objects.create(
        anonymous_token="anon-export",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )
    rf = RequestFactory()
    request = rf.post("/admin/")
    request.user = superuser

    record_admin = admin.site._registry[ConsentRecord]
    response = record_admin.export_selected_records(
        request,
        ConsentRecord.objects.filter(pk=record.pk),
    )

    content = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "purpose_code" in content
    assert "anon-export" in content
    assert "signup_doc" in content


@pytest.mark.django_db
def test_consent_record_admin_csv_export_sanitizes_formula_like_cells() -> None:
    superuser = _create_superuser()
    purpose, _document, revision = _create_revision()
    record = ConsentRecord.objects.create(
        anonymous_token="anon-export-safe",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
        subject_ref="=2+5",
        source="+untrusted",
    )
    request = RequestFactory().post("/admin/")
    request.user = superuser

    record_admin = admin.site._registry[ConsentRecord]
    response = record_admin.export_selected_records(
        request,
        ConsentRecord.objects.filter(pk=record.pk),
    )

    content = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "'=2+5" in content
    assert "'+untrusted" in content


@pytest.mark.django_db
def test_module_operation_audit_csv_export_sanitizes_formula_like_cells() -> None:
    superuser = _create_superuser()
    row = ModuleOperationAuditLog.objects.create(
        operation_code="admin.document_revision.publish",
        source="\tunsafe-source",
        status=ModuleOperationAuditLog.Status.SUCCESS,
        summary="@unsafe-summary",
        payload={"k": "v"},
        result={"ok": True},
    )
    request = RequestFactory().post("/admin/")
    request.user = superuser

    log_admin = admin.site._registry[ConsentModuleOperationAuditLog]
    response = log_admin.export_selected_records(
        request,
        ConsentModuleOperationAuditLog.objects.filter(pk=row.pk),
    )

    content = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "'\tunsafe-source" in content
    assert "'@unsafe-summary" in content


@pytest.mark.django_db
def test_cookie_consent_event_admin_uses_selected_csv_delimiter() -> None:
    superuser = _create_superuser()
    category = CookieCategory.objects.create(
        code="necessary",
        title="Необходимые",
        is_required=True,
        sort_order=1,
        is_active=True,
    )
    policy = CookiePolicyRevision.objects.create(
        version=1,
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text="Policy",
        categories_snapshot=[
            {
                "code": category.code,
                "title": category.title,
                "description": "",
                "is_required": True,
                "sort_order": 1,
            }
        ],
        is_active=True,
    )
    record = CookieConsentRecord.objects.create(
        anonymous_token="anon-cookie-export",
        policy_revision=policy,
        selected_categories=[category.code],
        status=CookieConsentRecord.Status.CURRENT,
        source="tests.admin",
    )
    event = CookieConsentEvent.objects.create(
        cookie_consent_record=record,
        event_type=CookieConsentEvent.EventType.ACCEPTED,
        source="tests.admin",
        payload={"ok": True},
    )
    CookieAdminSettings.objects.create(
        csv_export_delimiter=CookieAdminSettings.CsvDelimiter.SEMICOLON
    )

    request = RequestFactory().post("/admin/")
    request.user = superuser
    event_admin = admin.site._registry[CookieConsentEvent]

    response = event_admin.export_selected_records(
        request,
        CookieConsentEvent.objects.filter(pk=event.pk),
    )

    content = response.content.decode("utf-8")
    header = content.splitlines()[0]
    row = content.splitlines()[1]

    assert response.status_code == 200
    assert ";" in header
    assert ";" in row
    assert "cookie_consent_record_id" in header
    assert str(record.pk) in row


@pytest.mark.django_db
def test_personal_data_manager_permissions_affect_admin_endpoints() -> None:
    _purpose, _document, _revision = _create_revision()
    purpose_manager, _assignment = _create_staff_user(
        username="pdm-purpose",
        can_manage_purposes=True,
        can_manage_documents=False,
        can_publish_revisions=False,
        can_manage_audience_rules=False,
        can_manage_access_policies=False,
        can_handle_verified_consents=False,
        is_active=True,
    )
    client = Client()
    client.force_login(purpose_manager)

    purpose_response = client.get(
        reverse("admin:django_consent_152fz_consentpurpose_changelist")
    )
    policy_response = client.get(
        reverse("admin:django_consent_152fz_consentaccesspolicy_changelist")
    )

    assert purpose_response.status_code == 200
    assert policy_response.status_code == 403


@pytest.mark.django_db
def test_optional_admin_route_is_available_without_breaking_default_admin() -> None:
    superuser = _create_superuser()
    client = Client()
    client.force_login(superuser)

    default_response = client.get(reverse("admin:index"))
    optional_response = client.get(reverse("dz152fz_admin:index"))

    assert default_response.status_code == 200
    assert optional_response.status_code == 200
    assert reverse("admin:index") == "/admin/"
    assert reverse("dz152fz_admin:index") == "/admin-152fz/"


@pytest.mark.django_db
def test_default_admin_merges_verified_consents_into_core_section() -> None:
    superuser = _create_superuser()
    request = RequestFactory().get("/admin/")
    request.user = superuser

    app_list = admin.site.get_app_list(request)
    app_labels = {str(item.get("app_label") or "") for item in app_list}
    assert "verified_consents" not in app_labels

    consent_app = next(
        item
        for item in app_list
        if str(item.get("app_label") or "") == "django_consent_152fz"
    )
    model_object_names = {
        str(model.get("object_name") or "")
        for model in list(consent_app.get("models") or [])
    }
    assert "VerifiedConsentPolicy" in model_object_names
    assert "VerifiedConsentArtifact" in model_object_names


@pytest.mark.django_db
@override_settings(
    DJANGO_152FZ_CONSENT={
        "admin_navigation": {
            "enabled": True,
            "app_order": [
                "django_consent_152fz",
                "django_consent_152fz_cookies",
                "verified_consents",
            ],
            "collapsed_apps": [
                "django_consent_152fz",
            ],
            "consent_apps": [
                "django_consent_152fz",
                "django_consent_152fz_cookies",
                "verified_consents",
            ],
            "section_title": "РЎРѕРіР»Р°СЃРёСЏ 152-Р¤Р—",
        }
    }
)
def test_admin_forms_expose_help_texts_for_editable_fields() -> None:
    form_classes = (
        core_admin_module.ConsentPurposeAdminForm,
        core_admin_module.LegalDocumentAdminForm,
        core_admin_module.DocumentRevisionAdminForm,
        core_admin_module.ConsentAudienceRuleAdminForm,
        core_admin_module.ConsentAccessPolicyAdminForm,
        core_admin_module.PersonalDataManagerAssignmentAdminForm,
        core_admin_module.ConsentSelfServiceSettingsAdminForm,
        cookie_admin_module.CookieCategoryAdminForm,
        cookie_admin_module.CookiePolicyRevisionAdminForm,
        cookie_admin_module.CookieRegistryItemAdminForm,
        cookie_admin_module.CookieBannerRevisionAdminForm,
        cookie_admin_module.CookiePolicyTextPresetAdminForm,
        cookie_admin_module.CookieBannerTextPresetAdminForm,
        cookie_admin_module.CookieAdminSettingsAdminForm,
        verified_admin_module.VerifiedConsentPolicyAdminForm,
        verified_admin_module.VerifiedConsentArtifactAdminForm,
        verified_admin_module.VerifiedConsentFormPolicyAdminForm,
        verified_admin_module.VerifiedConsentSubmissionAdminForm,
    )

    for form_class in form_classes:
        form = form_class()
        assert form.fields, f"{form_class.__name__} has no editable fields."
        for field_name, field in form.fields.items():
            help_text = str(field.help_text or "").strip()
            assert help_text, (
                f"{form_class.__name__}.{field_name} must define non-empty help_text."
            )


@pytest.mark.django_db
def test_consent_record_admin_exposes_subject_and_policy_filters() -> None:
    model_admin = admin.site._registry[ConsentRecord]
    list_filter = model_admin.list_filter

    assert core_admin_module.ConsentRecordSubjectTypeFilter in list_filter
    assert "purpose__consent_frequency_policy" in list_filter
    assert "purpose__subject_availability_policy" in list_filter


@pytest.mark.django_db
def test_consent_record_subject_type_filter_splits_registered_and_anonymous() -> None:
    purpose = ConsentPurpose.objects.create(
        code="admin_subject_filter",
        title="Фильтр субъектов",
        fields_config=["email"],
    )
    document = LegalDocument.objects.create(
        code="admin_subject_filter_doc",
        title="Документ фильтра",
        document_type="consent",
    )
    revision = DocumentRevision.objects.create(
        document=document,
        purpose_code=purpose.code,
        version=1,
        format=DocumentRevision.ContentFormat.PLAIN_TEXT,
        content_text="v1",
        fields_snapshot=["email"],
        is_active=True,
    )
    User = get_user_model()
    user = User.objects.create_user(username="filter-user", password="pwd")
    ConsentRecord.objects.create(
        user=user,
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )
    ConsentRecord.objects.create(
        anonymous_token="anon-filter",
        purpose=purpose,
        document_revision=revision,
        fields_snapshot=["email"],
        status=ConsentRecord.Status.CURRENT,
    )

    model_admin = admin.site._registry[ConsentRecord]
    request = RequestFactory().get("/admin/")
    qs = ConsentRecord.objects.all()

    registered_filter = core_admin_module.ConsentRecordSubjectTypeFilter(
        request=request,
        params=QueryDict("subject_type=registered").copy(),
        model=ConsentRecord,
        model_admin=model_admin,
    )
    anonymous_filter = core_admin_module.ConsentRecordSubjectTypeFilter(
        request=request,
        params=QueryDict("subject_type=anonymous").copy(),
        model=ConsentRecord,
        model_admin=model_admin,
    )

    assert registered_filter.queryset(request, qs).count() == 1
    assert anonymous_filter.queryset(request, qs).count() == 1


@pytest.mark.django_db
def test_cookie_banner_revision_form_rejects_manual_unknown_preset_code() -> None:
    ensure_default_cookie_banner_text_presets()

    form = cookie_admin_module.CookieBannerRevisionAdminForm(
        data={
            "version": 1,
            "text_preset_code": "manual_unknown_code",
            "mobile_text_preset_code": "",
        }
    )
    form.is_valid()
    assert "text_preset_code" in form.errors


@pytest.mark.django_db
def test_cookie_banner_forms_widen_text_widgets_for_admin_readability() -> None:
    revision_form = cookie_admin_module.CookieBannerRevisionAdminForm()
    preset_form = cookie_admin_module.CookieBannerTextPresetAdminForm()

    assert "max-width: 1200px" in str(
        revision_form.fields["description_text"].widget.attrs.get("style", "")
    )
    assert "max-width: 1200px" in str(
        preset_form.fields["description_text"].widget.attrs.get("style", "")
    )


@pytest.mark.django_db
def test_cookie_banner_form_uses_native_color_picker_widgets() -> None:
    form = cookie_admin_module.CookieBannerRevisionAdminForm()
    for field_name in (
        "custom_bg_color",
        "custom_text_color",
        "custom_primary_color",
        "custom_primary_text_color",
        "custom_border_color",
        "custom_surface_color",
        "custom_overlay_color",
    ):
        widget = form.fields[field_name].widget
        assert widget.input_type == "color"


@pytest.mark.django_db
def test_cookie_banner_mobile_override_clean_preserves_none_fallback() -> None:
    form = cookie_admin_module.CookieBannerRevisionAdminForm()
    form.cleaned_data = {
        "mobile_show_close_control": True,
        "mobile_show_close_control__inherit": True,
        "mobile_show_reject_action": True,
        "mobile_show_reject_action__inherit": False,
        "mobile_blocking_mode_until_choice": False,
        "mobile_blocking_mode_until_choice__inherit": False,
        "mobile_hide_launcher_after_decision": False,
        "mobile_hide_launcher_after_decision__inherit": True,
        "mobile_keep_visible_after_accept_all": False,
        "mobile_keep_visible_after_accept_all__inherit": True,
        "mobile_keep_visible_after_required_only": True,
        "mobile_keep_visible_after_required_only__inherit": False,
        "mobile_keep_visible_after_save_custom": False,
        "mobile_keep_visible_after_save_custom__inherit": True,
    }
    cleaned = form.clean()
    assert cleaned["mobile_show_close_control"] is None
    assert cleaned["mobile_show_reject_action"] is True
    assert cleaned["mobile_blocking_mode_until_choice"] is False
    assert cleaned["mobile_hide_launcher_after_decision"] is None
    assert cleaned["mobile_keep_visible_after_accept_all"] is None
    assert cleaned["mobile_keep_visible_after_required_only"] is True
    assert cleaned["mobile_keep_visible_after_save_custom"] is None


@pytest.mark.django_db
def test_audit_logs_are_split_between_consent_and_cookie_admin_sections() -> None:
    superuser = _create_superuser()
    ModuleOperationAuditLog.objects.create(
        operation_code="admin.cookies.publish_banner_revision",
        source="admin.cookies.banner_revision",
        status=ModuleOperationAuditLog.Status.SUCCESS,
    )
    ModuleOperationAuditLog.objects.create(
        operation_code="admin.document_revision.publish",
        source="admin.document_revision",
        status=ModuleOperationAuditLog.Status.SUCCESS,
    )

    rf = RequestFactory()
    request = rf.get("/admin/")
    request.user = superuser

    consent_admin = admin.site._registry[ConsentModuleOperationAuditLog]

    consent_codes = set(
        consent_admin.get_queryset(request).values_list("operation_code", flat=True)
    )
    all_codes = set(
        ModuleOperationAuditLog.objects.values_list("operation_code", flat=True)
    )

    assert "admin.document_revision.publish" in consent_codes
    assert "admin.cookies.publish_banner_revision" not in consent_codes
    assert "admin.cookies.publish_banner_revision" in all_codes


def test_access_policy_admin_uses_autocomplete_for_purpose_and_document() -> None:
    policy_admin = admin.site._registry[ConsentAccessPolicy]
    assert policy_admin.autocomplete_fields == ("purpose", "document")


def test_access_policy_extra_meta_help_text_describes_module_scope_contract() -> None:
    policy_form = core_admin_module.ConsentAccessPolicyAdminForm()
    extra_help = str(policy_form.fields["extra_meta"].help_text)

    assert "module_scope" in extra_help
    assert "billing" in extra_help
    assert "subsystem" in extra_help
    assert "invoices" in extra_help
