from __future__ import annotations

import pytest

from django_consent_152fz.core.models import ConsentPurpose, LegalDocument
from django_consent_152fz.verified_consents.checks import (
    check_verified_form_policies_have_base_policy,
    check_verified_form_policies_match_forms_scope,
)
from django_consent_152fz.verified_consents.models import (
    VerifiedConsentFormPolicy,
    VerifiedConsentPolicy,
)


def _create_flow(*, suffix: str) -> tuple[ConsentPurpose, LegalDocument]:
    purpose = ConsentPurpose.objects.create(
        code=f"verified_checks_purpose_{suffix}",
        title=f"Verified checks purpose {suffix}",
    )
    document = LegalDocument.objects.create(
        code=f"verified_checks_document_{suffix}",
        title=f"Verified checks document {suffix}",
    )
    return purpose, document


@pytest.mark.django_db
def test_form_policy_requires_active_base_policy_check() -> None:
    purpose, document = _create_flow(suffix="missing_base")
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=document,
        form_code="course_signup",
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED
        ),
    )

    errors = check_verified_form_policies_have_base_policy(None)

    assert [error.id for error in errors] == [
        "django_consent_152fz_verified_consents.E002"
    ]


@pytest.mark.django_db
def test_form_policy_scope_check_rejects_self_service_only_base_policy() -> None:
    purpose, document = _create_flow(suffix="scope")
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
        flow_scope=VerifiedConsentPolicy.FlowScope.SELF_SERVICE_ONLY,
    )
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=document,
        form_code="course_signup",
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED
        ),
    )

    errors = check_verified_form_policies_match_forms_scope(None)

    assert [error.id for error in errors] == [
        "django_consent_152fz_verified_consents.E003"
    ]


@pytest.mark.django_db
def test_form_policy_checks_keep_back_compat_without_verified_policy() -> None:
    purpose, document = _create_flow(suffix="back_compat")
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=document,
        form_code="course_signup",
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.INHERIT
        ),
    )

    missing_policy_errors = check_verified_form_policies_have_base_policy(None)
    scope_errors = check_verified_form_policies_match_forms_scope(None)

    assert missing_policy_errors == []
    assert scope_errors == []


@pytest.mark.django_db
def test_form_policy_checks_pass_for_valid_forms_flow() -> None:
    purpose, document = _create_flow(suffix="ok")
    VerifiedConsentPolicy.objects.create(
        purpose=purpose,
        document=document,
        verification_mode=VerifiedConsentPolicy.VerificationMode.PAPER_REQUIRED,
        flow_scope=VerifiedConsentPolicy.FlowScope.BOTH,
    )
    VerifiedConsentFormPolicy.objects.create(
        purpose=purpose,
        document=document,
        form_code="course_signup",
        verification_mode_override=(
            VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED
        ),
    )

    missing_policy_errors = check_verified_form_policies_have_base_policy(None)
    scope_errors = check_verified_form_policies_match_forms_scope(None)

    assert missing_policy_errors == []
    assert scope_errors == []
