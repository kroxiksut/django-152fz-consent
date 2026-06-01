from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from django_consent_152fz.core.models import (
    ConsentAudienceRule,
    ConsentPurpose,
    ConsentRecord,
    LegalDocument,
    PersonalDataManagerAssignment,
)
from django_consent_152fz.core.services import (
    accept_consent,
    get_consent_status,
    get_current_requirements,
    publish_document_revision,
)


def _create_purpose(*, code: str = "account_basic") -> ConsentPurpose:
    return ConsentPurpose.objects.create(
        code=code,
        title="Регистрация",
        fields_config=["email"],
    )


def _get_document(*, code: str) -> LegalDocument:
    return LegalDocument.objects.get(code=code)


@pytest.mark.django_db
def test_consent_audience_rule_requires_group_for_django_group_scope() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="audience_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = _get_document(code="audience_doc")
    rule = ConsentAudienceRule(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.DJANGO_GROUP,
    )

    with pytest.raises(ValidationError, match="group"):
        rule.full_clean()


@pytest.mark.django_db
def test_consent_audience_rule_rejects_group_for_non_group_scope() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="audience_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = _get_document(code="audience_doc")
    group = Group.objects.create(name="A")
    rule = ConsentAudienceRule(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS,
        group=group,
    )

    with pytest.raises(ValidationError, match="group"):
        rule.full_clean()


@pytest.mark.django_db
def test_personal_data_manager_assignment_requires_staff_user() -> None:
    User = get_user_model()
    user = User.objects.create_user(username="manager", password="x", is_staff=False)
    assignment = PersonalDataManagerAssignment(user=user)

    with pytest.raises(ValidationError):
        assignment.full_clean()


@pytest.mark.django_db
def test_all_registered_audience_rule_filters_requirements_and_status() -> None:
    purpose = _create_purpose()
    publish_document_revision(
        document_code="account_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = _get_document(code="account_doc")
    ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS,
    )
    User = get_user_model()
    user = User.objects.create_user(username="member", password="x")

    user_requirements = get_current_requirements(user=user)
    anon_requirements = get_current_requirements(anonymous_token="anon-1")
    anon_status = get_consent_status(
        purpose_code=purpose.code,
        document_code="account_doc",
        anonymous_token="anon-1",
    )

    assert len(user_requirements["requirements"]) == 1
    assert anon_requirements["requirements"] == []
    assert anon_status["requires_consent"] is False
    assert anon_status["is_applicable"] is False


@pytest.mark.django_db
def test_anonymous_audience_rule_filters_out_registered_users() -> None:
    purpose = _create_purpose(code="contact_capture")
    publish_document_revision(
        document_code="contact_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = _get_document(code="contact_doc")
    ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.ANONYMOUS_SUBJECTS,
    )
    User = get_user_model()
    user = User.objects.create_user(username="registered", password="x")

    anon_requirements = get_current_requirements()
    user_requirements = get_current_requirements(user=user)

    assert len(anon_requirements["requirements"]) == 1
    assert user_requirements["requirements"] == []


@pytest.mark.django_db
def test_inactive_audience_rules_do_not_fallback_to_legacy_global_requirement() -> None:
    purpose = _create_purpose(code="expiring_rule")
    publish_document_revision(
        document_code="expiring_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = _get_document(code="expiring_doc")
    ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS,
        is_active=False,
    )
    User = get_user_model()
    user = User.objects.create_user(username="inactive_member", password="x")

    requirements = get_current_requirements(user=user)
    status = get_consent_status(
        purpose_code=purpose.code,
        document_code="expiring_doc",
        user=user,
    )

    assert requirements["requirements"] == []
    assert status["requires_consent"] is False
    assert status["is_applicable"] is False


@pytest.mark.django_db
def test_group_audience_rules_limit_outdated_marking_to_matching_group_members() -> (
    None
):
    purpose = _create_purpose(code="group_scoped")
    publish_document_revision(
        document_code="group_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    document = _get_document(code="group_doc")
    group = Group.objects.create(name="A")
    ConsentAudienceRule.objects.create(
        purpose=purpose,
        document=document,
        scope_mode=ConsentAudienceRule.ScopeMode.DJANGO_GROUP,
        group=group,
    )
    User = get_user_model()
    member = User.objects.create_user(username="member_a", password="x")
    outsider = User.objects.create_user(username="outsider_b", password="x")
    member.groups.add(group)

    member_record = accept_consent(
        purpose_code=purpose.code,
        document_code="group_doc",
        user=member,
    )
    outsider_record = accept_consent(
        purpose_code=purpose.code,
        document_code="group_doc",
        user=outsider,
    )

    publish_document_revision(
        document_code="group_doc",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v2",
    )

    member_record.refresh_from_db()
    outsider_record.refresh_from_db()

    assert member_record.status == ConsentRecord.Status.OUTDATED
    assert outsider_record.status == ConsentRecord.Status.CURRENT
