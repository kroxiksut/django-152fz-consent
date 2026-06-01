from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentAccessPolicy,
    ConsentPurpose,
    ConsentRecord,
)
from django_consent_152fz.core.services import (
    accept_consent,
    assert_consent_access,
    evaluate_consent_access,
    publish_document_revision,
)
from django_consent_152fz.exceptions import ConsentAccessDenied


def _create_purpose(
    *,
    code: str,
    reconsent_mode: str = constants.RECONSENT_MODE_SOFT,
) -> ConsentPurpose:
    return ConsentPurpose.objects.create(
        code=code,
        title=f"Purpose {code}",
        fields_config=["email"],
        reconsent_mode=reconsent_mode,
    )


def _create_policy(
    *,
    code: str,
    resource_code: str,
    action: str,
    reconsent_mode: str = constants.RECONSENT_MODE_SOFT,
    on_missing_consent: str = constants.ACCESS_POLICY_ACTION_DENY,
    on_outdated_consent: str = constants.ACCESS_POLICY_ACTION_RESPECT_RECONSENT_MODE,
) -> tuple[ConsentPurpose, ConsentAccessPolicy]:
    purpose = _create_purpose(
        code=f"{code}_purpose",
        reconsent_mode=reconsent_mode,
    )
    revision = publish_document_revision(
        document_code=f"{code}_document",
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v1",
    )
    policy = ConsentAccessPolicy.objects.create(
        code=code,
        title=f"Policy {code}",
        purpose=purpose,
        document=revision.document,
        resource_code=resource_code,
        action=action,
        on_missing_consent=on_missing_consent,
        on_outdated_consent=on_outdated_consent,
    )
    return purpose, policy


@pytest.mark.django_db
def test_consent_access_policy_requires_app_label_and_model_name_together() -> None:
    purpose, policy = _create_policy(
        code="policy_validation_pair",
        resource_code="shop.preorder",
        action="create",
    )

    policy.app_label = "shop"
    policy.model_name = ""

    with pytest.raises(ValidationError, match="model_name"):
        policy.save()

    policy.app_label = ""
    policy.model_name = "Preorder"

    with pytest.raises(ValidationError, match="app_label"):
        policy.save()

    purpose.refresh_from_db()


@pytest.mark.django_db
def test_consent_access_policy_rejects_invalid_time_window() -> None:
    _, policy = _create_policy(
        code="policy_validation_window",
        resource_code="shop.feedback",
        action="create",
    )

    policy.starts_at = timezone.now()
    policy.ends_at = policy.starts_at - timedelta(minutes=5)

    with pytest.raises(ValidationError, match="ends_at"):
        policy.save()


@pytest.mark.django_db
@override_settings(
    DJANGO_152FZ_CONSENT={constants.CONFIG_ENABLE_ACCESS_POLICIES: False}
)
def test_evaluate_consent_access_is_neutral_when_feature_is_disabled() -> None:
    _create_policy(
        code="policy_feature_disabled",
        resource_code="shop.preorder",
        action="create",
    )

    result = evaluate_consent_access(
        resource_code="shop.preorder",
        action="create",
        anonymous_token="anon-feature-disabled",
    )

    assert result["enabled"] is False
    assert result["matched_policy"] is False
    assert result["allowed"] is True
    assert result["resolution"] == constants.ACCESS_POLICY_RESOLUTION_ALLOW
    assert result["reason"] == "feature_disabled"


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={constants.CONFIG_ENABLE_ACCESS_POLICIES: True})
def test_evaluate_consent_access_is_neutral_when_no_policy_matches() -> None:
    result = evaluate_consent_access(
        resource_code="shop.unknown",
        action="create",
        anonymous_token="anon-no-policy",
    )

    assert result["enabled"] is True
    assert result["matched_policy"] is False
    assert result["allowed"] is True
    assert result["reason"] == "no_matching_policy"


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={constants.CONFIG_ENABLE_ACCESS_POLICIES: True})
def test_evaluate_consent_access_denies_when_required_consent_is_missing() -> None:
    purpose, policy = _create_policy(
        code="policy_missing_deny",
        resource_code="shop.preorder",
        action="create",
    )

    result = evaluate_consent_access(
        resource_code="shop.preorder",
        action="create",
        anonymous_token="anon-missing",
    )

    assert result["matched_policy"] is True
    assert result["allowed"] is False
    assert result["resolution"] == constants.ACCESS_POLICY_RESOLUTION_DENY
    assert result["reason"] == "missing_consent"
    assert result["policy_code"] == policy.code
    assert result["purpose_code"] == purpose.code
    assert result["document_code"] == policy.document.code
    assert result["consent_status"] is None

    with pytest.raises(ConsentAccessDenied, match="policy_missing_deny"):
        assert_consent_access(
            resource_code="shop.preorder",
            action="create",
            anonymous_token="anon-missing",
        )


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={constants.CONFIG_ENABLE_ACCESS_POLICIES: True})
def test_evaluate_consent_access_allows_current_consent() -> None:
    purpose, policy = _create_policy(
        code="policy_current_allow",
        resource_code="shop.profile",
        action="update",
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token="anon-current",
    )

    result = evaluate_consent_access(
        resource_code="shop.profile",
        action="update",
        anonymous_token="anon-current",
    )

    assert result["allowed"] is True
    assert result["resolution"] == constants.ACCESS_POLICY_RESOLUTION_ALLOW
    assert result["reason"] == "current_consent"
    assert result["consent_status"] == ConsentRecord.Status.CURRENT


@pytest.mark.parametrize(
    ("reconsent_mode", "expected_allowed", "expected_resolution", "expected_reason"),
    [
        (
            constants.RECONSENT_MODE_SOFT,
            True,
            constants.ACCESS_POLICY_RESOLUTION_ALLOW,
            "outdated_soft_reconsent",
        ),
        (
            constants.RECONSENT_MODE_HARD,
            False,
            constants.ACCESS_POLICY_RESOLUTION_DENY,
            "outdated_hard_reconsent",
        ),
    ],
)
@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={constants.CONFIG_ENABLE_ACCESS_POLICIES: True})
def test_evaluate_consent_access_respects_reconsent_mode_for_outdated_consent(
    reconsent_mode: str,
    expected_allowed: bool,
    expected_resolution: str,
    expected_reason: str,
) -> None:
    purpose, policy = _create_policy(
        code=f"policy_outdated_{reconsent_mode}",
        resource_code=f"shop.module.{reconsent_mode}",
        action="use",
        reconsent_mode=reconsent_mode,
    )
    accept_consent(
        purpose_code=purpose.code,
        document_code=policy.document.code,
        anonymous_token=f"anon-{reconsent_mode}",
    )
    publish_document_revision(
        document_code=policy.document.code,
        purpose_code=purpose.code,
        content_format="plain_text",
        content_text="v2",
    )

    result = evaluate_consent_access(
        resource_code=f"shop.module.{reconsent_mode}",
        action="use",
        anonymous_token=f"anon-{reconsent_mode}",
    )

    assert result["allowed"] is expected_allowed
    assert result["resolution"] == expected_resolution
    assert result["reason"] == expected_reason
    assert result["consent_status"] == ConsentRecord.Status.OUTDATED


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={constants.CONFIG_ENABLE_ACCESS_POLICIES: True})
def test_assert_consent_access_can_allow_read_only_resolution() -> None:
    _purpose, _policy = _create_policy(
        code="policy_read_only",
        resource_code="shop.read_only",
        action="update",
        on_missing_consent=constants.ACCESS_POLICY_ACTION_READ_ONLY,
    )

    result = evaluate_consent_access(
        resource_code="shop.read_only",
        action="update",
        anonymous_token="anon-read-only",
    )

    assert result["allowed"] is False
    assert result["read_only"] is True
    assert result["resolution"] == constants.ACCESS_POLICY_RESOLUTION_READ_ONLY

    with pytest.raises(ConsentAccessDenied):
        assert_consent_access(
            resource_code="shop.read_only",
            action="update",
            anonymous_token="anon-read-only",
        )

    allowed_result = assert_consent_access(
        resource_code="shop.read_only",
        action="update",
        anonymous_token="anon-read-only",
        allow_read_only=True,
    )

    assert allowed_result["read_only"] is True


@pytest.mark.django_db
@override_settings(DJANGO_152FZ_CONSENT={constants.CONFIG_ENABLE_ACCESS_POLICIES: True})
def test_evaluate_consent_access_can_request_redirect_to_consent() -> None:
    _create_policy(
        code="policy_redirect",
        resource_code="shop.redirect",
        action="create",
        on_missing_consent=constants.ACCESS_POLICY_ACTION_REDIRECT_TO_CONSENT,
    )

    result = evaluate_consent_access(
        resource_code="shop.redirect",
        action="create",
        anonymous_token="anon-redirect",
    )

    assert result["allowed"] is False
    assert result["read_only"] is False
    assert result["redirect_to_consent"] is True
    assert (
        result["resolution"] == constants.ACCESS_POLICY_RESOLUTION_REDIRECT_TO_CONSENT
    )
