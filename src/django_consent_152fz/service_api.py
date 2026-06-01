"""Stable public facade for the package service API.

The module defines the smallest possible external surface for integrations,
including the future router layer, so callers do not depend directly on the
internal structure of `core.services`.

Any change to the public function set is a contract change and must be
accompanied by documentation updates and roadmap tracking.
"""

from __future__ import annotations

from typing import Any

from django_consent_152fz import constants
from django_consent_152fz.core import services as core_services


def get_provider_code() -> str:
    """Return the stable provider code for router integrations."""
    return constants.PROVIDER_CODE


def register_purposes_from_config() -> Any:
    """Synchronize `ConsentPurpose` objects from the project configuration."""
    return core_services.register_purposes_from_config()


def get_current_requirements(
    *,
    user: Any = None,
    anonymous_token: str | None = None,
) -> Any:
    """Obtain current consent requirements for the subject."""
    return core_services.get_current_requirements(
        user=user,
        anonymous_token=anonymous_token,
    )


def accept_consent(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user: Any = None,
    anonymous_token: str | None = None,
    **kwargs: Any,
) -> Any:
    """Issue consent through the canonical `core` service path."""
    return core_services.accept_consent(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
        **kwargs,
    )


def withdraw_consent(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user: Any = None,
    anonymous_token: str | None = None,
    **kwargs: Any,
) -> Any:
    """Withdraw consent through the canonical `core` service path."""
    return core_services.withdraw_consent(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
        **kwargs,
    )


def get_consent_status(
    *,
    purpose_code: str,
    document_code: str | None = None,
    user: Any = None,
    anonymous_token: str | None = None,
) -> Any:
    """Get consent status according to `purpose + document`."""
    return core_services.get_consent_status(
        purpose_code=purpose_code,
        document_code=document_code,
        user=user,
        anonymous_token=anonymous_token,
    )


def attach_anonymous_consents_to_user(*, user: Any, anonymous_token: str) -> Any:
    """Link anonymous core consent records to a user after login."""
    return core_services.attach_anonymous_consents_to_user(
        user=user,
        anonymous_token=anonymous_token,
    )


def anonymize_subject_consents(
    *,
    user: Any = None,
    anonymous_token: str | None = None,
    purpose_code: str | None = None,
    document_code: str | None = None,
    **kwargs: Any,
) -> Any:
    """Anonymize the subject's consent records via the canonical service path."""
    return core_services.anonymize_subject_consents(
        user=user,
        anonymous_token=anonymous_token,
        purpose_code=purpose_code,
        document_code=document_code,
        **kwargs,
    )


PUBLIC_SERVICE_API_V1: tuple[str, ...] = (
    "accept_consent",
    "anonymize_subject_consents",
    "attach_anonymous_consents_to_user",
    "get_consent_status",
    "get_current_requirements",
    "get_provider_code",
    "register_purposes_from_config",
    "withdraw_consent",
)

__all__ = [
    "accept_consent",
    "anonymize_subject_consents",
    "attach_anonymous_consents_to_user",
    "get_consent_status",
    "get_current_requirements",
    "get_provider_code",
    "register_purposes_from_config",
    "withdraw_consent",
]
