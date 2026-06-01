"""Django system checks for early package configuration validation.

The idea for these checks appeared back in section 3.1 as part of the scaffold,
but they now serve later roadmap items as well. System checks make it possible
to surface errors at application startup or through `manage.py check`, instead
of discovering them in the middle of a request.
"""

from __future__ import annotations

from django.core.checks import Error, Tags, register

from . import constants
from .exceptions import ConsentConfigurationError
from .settings import (
    get_admin_navigation_settings,
    get_document_templates_settings,
    get_feature_flags,
    get_fields_config,
    get_public_api_settings,
    get_purposes_config,
    get_sample_documents_settings,
    get_subject_consents_settings,
    is_api_app_installed,
    use_api,
)


@register(Tags.compatibility)
def check_api_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check that the optional API layer is enabled correctly.

    The validation covers three conditions:
    - the `USE_API_152FZ` flag;
    - the presence of `django_consent_152fz.api` in `INSTALLED_APPS`;
    - the availability of DRF.

    This is tied to roadmap item 6, but the check runs at the core package level
    so configuration errors are caught before they reach runtime.
    """
    errors = []

    try:
        api_enabled = use_api()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E016",
            )
        )
        return errors

    if api_enabled and not is_api_app_installed():
        errors.append(
            Error(
                (
                    f"{constants.SETTING_USE_API}=True requires "
                    f"'{constants.API_APP}' in INSTALLED_APPS."
                ),
                id="django_consent_152fz.E001",
            )
        )

    if api_enabled:
        from .api.dependencies import get_missing_drf_message, is_drf_available

        if not is_drf_available():
            errors.append(
                Error(
                    get_missing_drf_message(),
                    id="django_consent_152fz.E002",
                )
            )

    return errors


@register(Tags.compatibility)
def check_public_api_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check the throttling/discovery settings of the public API loop."""
    errors = []
    try:
        get_public_api_settings()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E027",
            )
        )
    return errors


@register(Tags.compatibility)
def check_fields_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check the configuration of the POP field registry in clause 4.1."""
    errors = []
    try:
        get_fields_config()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E010",
            )
        )

    return errors


@register(Tags.compatibility)
def check_feature_flags_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check the basic feature flags and their dependency matrix."""
    errors = []
    try:
        get_feature_flags()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E012",
            )
        )

    return errors


@register(Tags.compatibility)
def check_verified_consents_installation(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Legacy no-op: verified app availability is now app/policy-driven."""
    return []


@register(Tags.compatibility)
def check_admin_navigation_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check settings optional admin navigation customization."""

    errors = []
    try:
        get_admin_navigation_settings()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E023",
            )
        )
    return errors


@register(Tags.compatibility)
def check_sample_documents_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check the bootstrap contract settings of the boxed sample documents."""
    errors = []
    try:
        get_sample_documents_settings()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E019",
            )
        )
    return errors


@register(Tags.compatibility)
def check_subject_consents_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check the settings contract self-service consent page of the subject."""

    errors = []
    try:
        get_subject_consents_settings()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E025",
            )
        )
    return errors


@register(Tags.compatibility)
def check_document_templates_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Check settings contract markdown-first document templates."""

    errors = []
    try:
        get_document_templates_settings()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E026",
            )
        )
    return errors


@register(Tags.compatibility)
def check_purposes_settings(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Validate the processing-purposes configuration.

    Fields are validated first, because the purpose config can reference them.
    If the fields are already broken, there is no point duplicating a cascade
    of purpose-related errors.
    """
    errors = []
    try:
        get_fields_config()
    except ConsentConfigurationError:
        # The field error is already surfaced by a separate check id (E010).
        return errors

    try:
        get_purposes_config()
    except ConsentConfigurationError as exc:
        errors.append(
            Error(
                str(exc),
                id="django_consent_152fz.E011",
            )
        )

    return errors
