"""Helpers for the optional API dependency checks."""

from __future__ import annotations

from importlib.util import find_spec

from django_consent_152fz import constants
from django_consent_152fz.exceptions import ConsentConfigurationError

_DRF_MODULE = "rest_framework"


def is_drf_available() -> bool:
    """Return whether Django REST framework is available."""
    return find_spec(_DRF_MODULE) is not None


def get_missing_drf_message() -> str:
    """Build the error message used when DRF is missing."""
    return (
        f"{constants.SETTING_USE_API}=True requires Django REST framework. "
        "Install the optional dependency `django-consent-152fz[api]` "
        "or add `djangorestframework` before enabling the API module."
    )


def require_drf() -> None:
    """Require Django REST framework for the optional API app."""
    if is_drf_available():
        return
    raise ConsentConfigurationError(get_missing_drf_message())
