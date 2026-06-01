"""System checks for the optional `verified_consents` app.

These checks enforce the roadmap principle that `verified_consents` is not an
independent consent domain and cannot be installed without the base
`django_consent_152fz` app.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Django dynamic ORM/admin attributes are not fully inferable by pyright.
from collections.abc import Set as AbstractSet

from django.conf import settings as django_settings
from django.core.checks import Error, Tags, register
from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from django_consent_152fz import constants
from django_consent_152fz.verified_consents.models import (
    VerifiedConsentFormPolicy,
    VerifiedConsentPolicy,
)


@register(Tags.compatibility)
def check_verified_consents_base_app(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Make sure the optional app is installed only together with the base app."""
    installed_apps = set(getattr(django_settings, "INSTALLED_APPS", []))
    if "django_consent_152fz" in installed_apps:
        return []

    return [
        Error(
            f"'{constants.VERIFIED_CONSENTS_APP}' requires 'django_consent_152fz' "
            "in INSTALLED_APPS.",
            id="django_consent_152fz_verified_consents.E001",
        )
    ]


@register(Tags.compatibility)
def check_verified_form_policies_have_base_policy(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check that a form-level verified override does not exist without a base policy."""
    required_modes = {
        VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED,
        VerifiedConsentFormPolicy.VerificationModeOverride.GOSKEY_REQUIRED,
        VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_OR_GOSKEY,
    }
    active_form_policies = _get_active_form_policies_with_verified_override(
        required_modes=required_modes
    )
    if active_form_policies is None:
        return []

    active_policy_pairs = _get_active_policy_pairs()
    errors = []
    for form_policy in active_form_policies:
        pair = (form_policy.purpose_id, form_policy.document_id)
        if pair in active_policy_pairs:
            continue
        errors.append(
            Error(
                _(
                    "Form policy '%(form_code)s' for flow "
                    "'%(purpose_code)s/%(document_code)s' uses "
                    "'%(mode)s' but no active Verified Consent Policy is configured "
                    "for this flow."
                )
                % {
                    "form_code": form_policy.form_code,
                    "purpose_code": form_policy.purpose.code,
                    "document_code": form_policy.document.code,
                    "mode": form_policy.verification_mode_override,
                },
                id="django_consent_152fz_verified_consents.E002",
            )
        )
    return errors


@register(Tags.compatibility)
def check_verified_form_policies_match_forms_scope(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check that the required verified mode is allowed by the flow scope."""
    required_modes = {
        VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_REQUIRED,
        VerifiedConsentFormPolicy.VerificationModeOverride.GOSKEY_REQUIRED,
        VerifiedConsentFormPolicy.VerificationModeOverride.PAPER_OR_GOSKEY,
    }
    active_form_policies = _get_active_form_policies_with_verified_override(
        required_modes=required_modes
    )
    if active_form_policies is None:
        return []

    active_policies = _get_active_policy_map()
    errors = []
    allowed_form_scopes = {
        VerifiedConsentPolicy.FlowScope.BOTH,
        VerifiedConsentPolicy.FlowScope.FORMS_ONLY,
    }
    for form_policy in active_form_policies:
        pair = (form_policy.purpose_id, form_policy.document_id)
        policy = active_policies.get(pair)
        if policy is None:
            continue
        if policy.flow_scope in allowed_form_scopes:
            continue
        errors.append(
            Error(
                _(
                    "Form policy '%(form_code)s' for flow "
                    "'%(purpose_code)s/%(document_code)s' uses "
                    "'%(mode)s', but base policy flow_scope '%(flow_scope)s' "
                    "does not include forms."
                )
                % {
                    "form_code": form_policy.form_code,
                    "purpose_code": form_policy.purpose.code,
                    "document_code": form_policy.document.code,
                    "mode": form_policy.verification_mode_override,
                    "flow_scope": policy.flow_scope,
                },
                id="django_consent_152fz_verified_consents.E003",
            )
        )
    return errors


def _get_active_policy_queryset():
    """Return the queryset of active policies in the current time window."""
    now = timezone.now()
    return (
        VerifiedConsentPolicy.objects.select_related("purpose", "document")
        .filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )


def _get_active_policy_pairs() -> set[tuple[int, int]]:
    """Return stream keys with an active verified policy."""
    policy_map = _get_active_policy_map()
    return set(policy_map.keys())


def _get_active_policy_map() -> dict[tuple[int, int], VerifiedConsentPolicy]:
    """Return a map of `(purpose_id, document_id) -> policy` for active policies."""
    try:
        return {
            (policy.purpose_id, policy.document_id): policy
            for policy in _get_active_policy_queryset()
        }
    except DatabaseError:
        return {}


def _get_active_form_policies_with_verified_override(
    *,
    required_modes: AbstractSet[str],
) -> list[VerifiedConsentFormPolicy] | None:
    """Return active form policies with a verified-required override.

    Returns `None` when the tables are not ready yet, for example during an
    early check before migrations have been applied.
    """
    try:
        return list(
            VerifiedConsentFormPolicy.objects.select_related("purpose", "document")
            .filter(is_active=True)
            .filter(verification_mode_override__in=required_modes)
            .order_by("id")
        )
    except DatabaseError:
        return None
