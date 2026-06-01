"""Normalization and validation of package configuration.

This module started as a simple wrapper around Django settings in section 3.1,
but as the core evolved it became the single entry point for reading config.

The key idea is simple:
- read only raw values from `django.conf.settings`;
- expose only validated and normalized structures;
- raise configuration errors early and explicitly.

This reduces coupling between package apps: models, services, templates, and
system checks receive a predictable contract instead of an arbitrary dict.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings as django_settings

from . import constants
from .exceptions import ConsentConfigurationError

# Basic configuration that allows the package to start even without explicit
# custom settings. This matters especially during alpha and for tests.
DEFAULT_CONFIG: dict[str, Any] = {
    constants.CONFIG_ENABLE_CORE: True,
    constants.CONFIG_ENABLE_VERIFIED_CONSENTS: False,
    constants.CONFIG_ENABLE_ACCESS_POLICIES: False,
    constants.CONFIG_SAMPLE_DOCUMENTS: {},
    constants.CONFIG_SUBJECT_CONSENTS: {},
    "fields": {},
    "fields_mode": "extend",
    "purposes": {},
}

# We keep API defaults separately because the API module is optional, but its
# settings contract still has to exist ahead of time.
DEFAULT_API_SETTINGS: dict[str, Any] = {
    constants.SETTING_API_PREFIX: "api/consents/v1/",
    constants.SETTING_API_SAFE_ROOT_STUBS_ENABLED: True,
    constants.SETTING_API_INCLUDE_SCHEMA: True,
    constants.SETTING_API_AUTH_CLASSES: [],
    constants.SETTING_API_PERMISSION_CLASSES: [],
    constants.SETTING_PUBLIC_API_ENABLED: False,
    constants.SETTING_PUBLIC_API_PREFIX: "api/consents/public/v1/",
    constants.SETTING_PUBLIC_API_ALLOWED_PURPOSES: [],
    constants.SETTING_PUBLIC_API_SHOW_ROOT: True,
    constants.SETTING_PUBLIC_API_THROTTLE_ENABLED: True,
    constants.SETTING_PUBLIC_API_THROTTLE_IP_RATE: "120/hour",
    constants.SETTING_PUBLIC_API_THROTTLE_ANON_RATE: "60/hour",
    constants.SETTING_PUBLIC_API_THROTTLE_IP_WRITE_FLOOR_RATE: "30/minute",
    constants.SETTING_TRUSTED_PROXY_IPS: [],
    constants.SETTING_TRUSTED_PROXY_HOPS: 0,
    constants.SETTING_ANON_TOKEN_TTL_SECONDS: 60 * 60 * 24 * 365,
    constants.SETTING_ANON_TOKEN_REVOKE_ON_ATTACH: True,
    constants.SETTING_PUBLIC_STATUS_FAIL_LIMIT: 10,
    constants.SETTING_PUBLIC_STATUS_FAIL_WINDOW_SECONDS: 60 * 10,
}

# A starter set of personal-data fields.
# It provides a quick start and also serves as the format standard for custom
# extensions from section 4.1.
STANDARD_FIELDS: dict[str, dict[str, str]] = {
    "full_name": {"label": "ФИО"},
    "nickname": {"label": "Никнейм"},
    "email": {"label": "Электронная почта"},
    "birth_date": {"label": "Дата рождения"},
    "phone": {"label": "Телефон"},
    "contacts": {"label": "Контакты из сообщения в этой форме"},
    "address": {"label": "Адрес"},
    "request_text": {"label": "Текст обращения"},
}


# The regular expression defines the canonical format for all code values so
# field, purpose, document, and similar codes stay predictable across layers.
_FIELD_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_THROTTLE_RATE_RE = re.compile(r"^\d+/(sec|second|min|minute|hour|day)$")
_FIELDS_MODE_EXTEND = "extend"
_FIELDS_MODE_REPLACE = "replace"
_ALLOWED_FIELDS_MODES = frozenset({_FIELDS_MODE_EXTEND, _FIELDS_MODE_REPLACE})
_ALLOWED_WITHDRAW_STRATEGIES = frozenset(constants.WITHDRAW_STRATEGIES)
_ALLOWED_RECONSENT_MODES = frozenset(constants.RECONSENT_MODES)
_ALLOWED_CONSENT_FREQUENCIES = frozenset(constants.CONSENT_FREQUENCIES)
_ALLOWED_SUBJECT_AVAILABILITIES = frozenset(constants.SUBJECT_AVAILABILITIES)
DEFAULT_SAMPLE_DOCUMENTS_SETTINGS = {
    constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: (
        constants.SAMPLE_DOCUMENTS_LOAD_MODE_COMMAND
    ),
}
_ALLOWED_SAMPLE_DOCUMENTS_LOAD_MODES = frozenset(constants.SAMPLE_DOCUMENTS_LOAD_MODES)
DEFAULT_DOCUMENT_TEMPLATES_SETTINGS = {
    constants.CONFIG_DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMAT: (
        constants.DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMAT_MARKDOWN
    ),
    constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_EDITOR_MODE: (
        constants.DOCUMENT_TEMPLATES_EDITOR_MODE_TEXTAREA
    ),
    constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET: "",
    constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET_ATTRS: {},
    constants.CONFIG_DOCUMENT_TEMPLATES_HTML_TO_PDF_HOOK: "",
}
_ALLOWED_DOCUMENT_TEMPLATE_TEXT_FORMATS = frozenset(
    constants.DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMATS
)
_ALLOWED_DOCUMENT_TEMPLATE_EDITOR_MODES = frozenset(
    constants.DOCUMENT_TEMPLATES_EDITOR_MODES
)
DEFAULT_SUBJECT_CONSENTS_SETTINGS = {
    constants.CONFIG_SUBJECT_CONSENTS_OPEN_MODE: (
        constants.SUBJECT_CONSENTS_OPEN_MODE_PAGE
    ),
    constants.CONFIG_SUBJECT_CONSENTS_ALLOW_ANONYMOUS_WITHDRAW: True,
    constants.CONFIG_SUBJECT_CONSENTS_INPUT_MODE: (
        constants.SUBJECT_CONSENTS_INPUT_MODE_CHECKBOX
    ),
    constants.CONFIG_SUBJECT_CONSENTS_CHECKBOX_REQUIRED: True,
    constants.CONFIG_SUBJECT_CONSENTS_DECLINE_ACTION: (
        constants.SUBJECT_CONSENTS_DECLINE_ACTION_BLOCK_SUBMIT
    ),
    constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_ENABLED: True,
    constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_TEXT: (
        "Если вы не согласны на обработку персональных данных, "
        "мы не сможем связаться с вами по заявке."
    ),
}
_ALLOWED_SUBJECT_CONSENTS_OPEN_MODES = frozenset(constants.SUBJECT_CONSENTS_OPEN_MODES)
_ALLOWED_SUBJECT_CONSENTS_INPUT_MODES = frozenset(
    constants.SUBJECT_CONSENTS_INPUT_MODES
)
_ALLOWED_SUBJECT_CONSENTS_DECLINE_ACTIONS = frozenset(
    constants.SUBJECT_CONSENTS_DECLINE_ACTIONS
)
DEFAULT_ADMIN_NAVIGATION_SETTINGS = {
    constants.CONFIG_ADMIN_NAVIGATION_ENABLED: False,
    constants.CONFIG_ADMIN_NAVIGATION_APP_ORDER: [],
    constants.CONFIG_ADMIN_NAVIGATION_COLLAPSED_APPS: [],
    constants.CONFIG_ADMIN_NAVIGATION_CONSENT_APPS: [
        "django_consent_152fz",
        "django_consent_152fz_cookies",
        "verified_consents",
    ],
    constants.CONFIG_ADMIN_NAVIGATION_SECTION_TITLE: "Согласия 152-ФЗ",
}
_FEATURE_FLAG_DEFAULTS = {
    constants.CONFIG_ENABLE_CORE: True,
    constants.CONFIG_ENABLE_VERIFIED_CONSENTS: False,
    constants.CONFIG_ENABLE_ACCESS_POLICIES: False,
}


def get_config() -> dict[str, Any]:
    """Return the top-level package configuration as a plain dict.

    We deliberately copy the mapping into a new dict so later code does not
    work directly with Django settings and mutate it by accident.
    """
    config = getattr(django_settings, constants.SETTING_CONFIG, None)
    if config is None:
        config = getattr(
            django_settings,
            constants.SETTING_CONFIG_LEGACY,
            DEFAULT_CONFIG,
        )
    if not isinstance(config, Mapping):
        raise ConsentConfigurationError(
            f"{constants.SETTING_CONFIG} must be a mapping/dict."
        )
    return dict(config)


def use_api() -> bool:
    """Check whether the optional API layer is enabled.

    This is a separate flag from having `django_consent_152fz.api` in
    INSTALLED_APPS: the app may be installed but still disabled by settings.
    """
    value = getattr(django_settings, constants.SETTING_USE_API, False)
    if not isinstance(value, bool):
        raise ConsentConfigurationError(f"{constants.SETTING_USE_API} must be a bool.")
    return value


def get_api_setting(name: str) -> Any:
    """Revert a specific API setting with a safe fallback to defaults."""
    default = DEFAULT_API_SETTINGS.get(name)
    return getattr(django_settings, name, default)


def get_public_api_settings() -> dict[str, Any]:
    """Return and validate the runtime settings of the public API circuit."""
    return {
        constants.SETTING_PUBLIC_API_ENABLED: _normalize_bool(
            value=get_api_setting(constants.SETTING_PUBLIC_API_ENABLED),
            config_path=constants.SETTING_PUBLIC_API_ENABLED,
        ),
        constants.SETTING_PUBLIC_API_SHOW_ROOT: _normalize_bool(
            value=get_api_setting(constants.SETTING_PUBLIC_API_SHOW_ROOT),
            config_path=constants.SETTING_PUBLIC_API_SHOW_ROOT,
        ),
        constants.SETTING_PUBLIC_API_THROTTLE_ENABLED: _normalize_bool(
            value=get_api_setting(constants.SETTING_PUBLIC_API_THROTTLE_ENABLED),
            config_path=constants.SETTING_PUBLIC_API_THROTTLE_ENABLED,
        ),
        constants.SETTING_PUBLIC_API_THROTTLE_IP_RATE: _normalize_throttle_rate(
            value=get_api_setting(constants.SETTING_PUBLIC_API_THROTTLE_IP_RATE),
            config_path=constants.SETTING_PUBLIC_API_THROTTLE_IP_RATE,
        ),
        constants.SETTING_PUBLIC_API_THROTTLE_ANON_RATE: _normalize_throttle_rate(
            value=get_api_setting(constants.SETTING_PUBLIC_API_THROTTLE_ANON_RATE),
            config_path=constants.SETTING_PUBLIC_API_THROTTLE_ANON_RATE,
        ),
        constants.SETTING_PUBLIC_API_THROTTLE_IP_WRITE_FLOOR_RATE: (
            _normalize_throttle_rate(
                value=get_api_setting(
                    constants.SETTING_PUBLIC_API_THROTTLE_IP_WRITE_FLOOR_RATE
                ),
                config_path=constants.SETTING_PUBLIC_API_THROTTLE_IP_WRITE_FLOOR_RATE,
            )
        ),
        constants.SETTING_TRUSTED_PROXY_IPS: _normalize_ip_list(
            value=get_api_setting(constants.SETTING_TRUSTED_PROXY_IPS),
            config_path=constants.SETTING_TRUSTED_PROXY_IPS,
        ),
        constants.SETTING_TRUSTED_PROXY_HOPS: _normalize_non_negative_int(
            value=get_api_setting(constants.SETTING_TRUSTED_PROXY_HOPS),
            config_path=constants.SETTING_TRUSTED_PROXY_HOPS,
        ),
        constants.SETTING_ANON_TOKEN_TTL_SECONDS: _normalize_non_negative_int(
            value=get_api_setting(constants.SETTING_ANON_TOKEN_TTL_SECONDS),
            config_path=constants.SETTING_ANON_TOKEN_TTL_SECONDS,
        ),
        constants.SETTING_ANON_TOKEN_REVOKE_ON_ATTACH: _normalize_bool(
            value=get_api_setting(constants.SETTING_ANON_TOKEN_REVOKE_ON_ATTACH),
            config_path=constants.SETTING_ANON_TOKEN_REVOKE_ON_ATTACH,
        ),
        constants.SETTING_PUBLIC_STATUS_FAIL_LIMIT: _normalize_non_negative_int(
            value=get_api_setting(constants.SETTING_PUBLIC_STATUS_FAIL_LIMIT),
            config_path=constants.SETTING_PUBLIC_STATUS_FAIL_LIMIT,
        ),
        constants.SETTING_PUBLIC_STATUS_FAIL_WINDOW_SECONDS: _normalize_non_negative_int(
            value=get_api_setting(constants.SETTING_PUBLIC_STATUS_FAIL_WINDOW_SECONDS),
            config_path=constants.SETTING_PUBLIC_STATUS_FAIL_WINDOW_SECONDS,
        ),
    }


def get_standard_fields() -> dict[str, dict[str, Any]]:
    """Return the starter field registry as a new mutable dict.

    The copy prevents merging user values from mutating the global
    `STANDARD_FIELDS`.
    """
    return {code: dict(field_config) for code, field_config in STANDARD_FIELDS.items()}


def get_fields_config() -> dict[str, dict[str, Any]]:
    """Load and validate the personal-data field registry.

    Two modes are supported:
    - `extend`: the starter field set is extended by user-defined fields;
    - `replace`: the user takes full control of the registry.

    This logic belongs to roadmap item 4.1, but it is defined here because the
    settings layer must be the single source of truth for the config format.

    Supported config format:
    DJANGO_CONSENT_152FZ = {
        "fields_mode": "extend" | "replace",  # optional, defaults to "extend"
        "fields": {
            "field_code": {"label": "Human-readable label", ...},
        },
    }

    Keys and enum values stay in English because they are part of the package's
    public configuration contract, not free text.
    """
    config = get_config()
    fields_mode = _validate_fields_mode(config.get("fields_mode", _FIELDS_MODE_EXTEND))
    configured_fields = _normalize_fields(config.get("fields", {}))

    if fields_mode == _FIELDS_MODE_REPLACE:
        return configured_fields

    merged_fields = get_standard_fields()
    merged_fields.update(configured_fields)
    return merged_fields


def get_feature_flags() -> dict[str, bool]:
    """Return and validate the package feature flags.

    It is important not only to coerce values to bool, but also to check the
    dependencies between flags.

    Supported config format:
    DJANGO_CONSENT_152FZ = {
        "enable_core": True,
        "enable_verified_consents": False,
        "enable_access_policies": False,
    }
    """
    config = get_config()
    config_path = constants.SETTING_CONFIG
    flags = {
        name: _normalize_bool(
            value=config.get(name, default),
            config_path=f'{config_path}["{name}"]',
        )
        for name, default in _FEATURE_FLAG_DEFAULTS.items()
    }
    return flags


def is_core_enabled() -> bool:
    """Flag to enable basic consent-flow."""
    return get_feature_flags()[constants.CONFIG_ENABLE_CORE]


def is_verified_consents_enabled() -> bool:
    """Check whether the verified-consents boundary is available.

    Starting with block 16.10, the verified/paper scenario is considered part
    of the base contract layer, and enablement is determined by installing the
    optional app in `INSTALLED_APPS`. The `enable_verified_consents` flag
    remains only as a legacy compatibility setting.
    """
    return is_verified_consents_app_installed()


def is_verified_consents_app_installed() -> bool:
    """Check if the Django application has verified_consents connected."""
    installed_apps = set(getattr(django_settings, "INSTALLED_APPS", []))
    return constants.VERIFIED_CONSENTS_APP in installed_apps


def is_api_app_installed() -> bool:
    """Check if the optional API app is connected."""
    installed_apps = set(getattr(django_settings, "INSTALLED_APPS", []))
    return constants.API_APP in installed_apps


def is_access_policies_enabled() -> bool:
    """Flag for enabling the access policies module."""
    return get_feature_flags()[constants.CONFIG_ENABLE_ACCESS_POLICIES]


def get_sample_documents_settings() -> dict[str, str]:
    """Return the bootstrap settings for starter sample documents.

    The public contract here is deliberately minimal: the package only manages
    the initial loading mode for curated samples from section 4.3, not how the
    integrator later turns them into live documents.
    """
    config = get_config()
    config_path = f'{constants.SETTING_CONFIG}["{constants.CONFIG_SAMPLE_DOCUMENTS}"]'
    raw_sample_documents = config.get(
        constants.CONFIG_SAMPLE_DOCUMENTS,
        DEFAULT_SAMPLE_DOCUMENTS_SETTINGS,
    )
    if raw_sample_documents in (None, {}):
        raw_sample_documents = DEFAULT_SAMPLE_DOCUMENTS_SETTINGS
    if not isinstance(raw_sample_documents, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")

    sample_documents = dict(DEFAULT_SAMPLE_DOCUMENTS_SETTINGS)
    sample_documents.update(dict(raw_sample_documents))
    return {
        constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE: _normalize_choice(
            value=sample_documents.get(
                constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE,
                DEFAULT_SAMPLE_DOCUMENTS_SETTINGS[
                    constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE}"]'
            ),
            allowed_values=_ALLOWED_SAMPLE_DOCUMENTS_LOAD_MODES,
        ),
    }


def get_sample_documents_load_mode() -> str:
    """Return the normalized loading mode for sample documents."""
    return get_sample_documents_settings()[constants.CONFIG_SAMPLE_DOCUMENTS_LOAD_MODE]


def is_sample_documents_auto_bootstrap_enabled() -> bool:
    """Check if post-migrate auto-bootstrap of boxed samples is enabled."""
    return get_sample_documents_load_mode() == constants.SAMPLE_DOCUMENTS_LOAD_MODE_AUTO


def get_document_templates_settings() -> dict[str, Any]:
    """Return and validate legal-document template settings.

    This contract intentionally keeps the WYSIWYG and HTML->PDF pipeline
    optional: the core works on a markdown-first flow without mandatory editor
    dependencies.
    """

    config = get_config()
    config_path = f'{constants.SETTING_CONFIG}["{constants.CONFIG_DOCUMENT_TEMPLATES}"]'
    raw_templates = config.get(
        constants.CONFIG_DOCUMENT_TEMPLATES,
        DEFAULT_DOCUMENT_TEMPLATES_SETTINGS,
    )
    if raw_templates in (None, {}):
        raw_templates = DEFAULT_DOCUMENT_TEMPLATES_SETTINGS
    if not isinstance(raw_templates, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")

    templates_config = dict(DEFAULT_DOCUMENT_TEMPLATES_SETTINGS)
    templates_config.update(dict(raw_templates))

    return {
        constants.CONFIG_DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMAT: _normalize_choice(
            value=templates_config.get(
                constants.CONFIG_DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMAT,
                DEFAULT_DOCUMENT_TEMPLATES_SETTINGS[
                    constants.CONFIG_DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMAT
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMAT}"]'
            ),
            allowed_values=_ALLOWED_DOCUMENT_TEMPLATE_TEXT_FORMATS,
        ),
        constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_EDITOR_MODE: _normalize_choice(
            value=templates_config.get(
                constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_EDITOR_MODE,
                DEFAULT_DOCUMENT_TEMPLATES_SETTINGS[
                    constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_EDITOR_MODE
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_EDITOR_MODE}"]'
            ),
            allowed_values=_ALLOWED_DOCUMENT_TEMPLATE_EDITOR_MODES,
        ),
        constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET: _normalize_optional_string(
            value=templates_config.get(
                constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET,
                DEFAULT_DOCUMENT_TEMPLATES_SETTINGS[
                    constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET}"]'
            ),
        ),
        constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET_ATTRS: _normalize_string_mapping(
            value=templates_config.get(
                constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET_ATTRS,
                DEFAULT_DOCUMENT_TEMPLATES_SETTINGS[
                    constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET_ATTRS
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET_ATTRS}"]'
            ),
        ),
        constants.CONFIG_DOCUMENT_TEMPLATES_HTML_TO_PDF_HOOK: _normalize_callable_path(
            value=templates_config.get(
                constants.CONFIG_DOCUMENT_TEMPLATES_HTML_TO_PDF_HOOK,
                DEFAULT_DOCUMENT_TEMPLATES_SETTINGS[
                    constants.CONFIG_DOCUMENT_TEMPLATES_HTML_TO_PDF_HOOK
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_DOCUMENT_TEMPLATES_HTML_TO_PDF_HOOK}"]'
            ),
        ),
    }


def get_subject_consents_settings() -> dict[str, Any]:
    """Return and validate the settings of the self-service consent page of the subject."""

    config = get_config()
    config_path = f'{constants.SETTING_CONFIG}["{constants.CONFIG_SUBJECT_CONSENTS}"]'
    raw_subject_consents_config = config.get(
        constants.CONFIG_SUBJECT_CONSENTS,
        DEFAULT_SUBJECT_CONSENTS_SETTINGS,
    )
    if raw_subject_consents_config in (None, {}):
        raw_subject_consents_config = DEFAULT_SUBJECT_CONSENTS_SETTINGS
    if not isinstance(raw_subject_consents_config, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")

    subject_consents_config = dict(DEFAULT_SUBJECT_CONSENTS_SETTINGS)
    subject_consents_config.update(dict(raw_subject_consents_config))

    return {
        constants.CONFIG_SUBJECT_CONSENTS_OPEN_MODE: _normalize_choice(
            value=subject_consents_config.get(
                constants.CONFIG_SUBJECT_CONSENTS_OPEN_MODE,
                DEFAULT_SUBJECT_CONSENTS_SETTINGS[
                    constants.CONFIG_SUBJECT_CONSENTS_OPEN_MODE
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SUBJECT_CONSENTS_OPEN_MODE}"]'
            ),
            allowed_values=_ALLOWED_SUBJECT_CONSENTS_OPEN_MODES,
        ),
        constants.CONFIG_SUBJECT_CONSENTS_ALLOW_ANONYMOUS_WITHDRAW: _normalize_bool(
            value=subject_consents_config.get(
                constants.CONFIG_SUBJECT_CONSENTS_ALLOW_ANONYMOUS_WITHDRAW,
                DEFAULT_SUBJECT_CONSENTS_SETTINGS[
                    constants.CONFIG_SUBJECT_CONSENTS_ALLOW_ANONYMOUS_WITHDRAW
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SUBJECT_CONSENTS_ALLOW_ANONYMOUS_WITHDRAW}"]'
            ),
        ),
        constants.CONFIG_SUBJECT_CONSENTS_INPUT_MODE: _normalize_choice(
            value=subject_consents_config.get(
                constants.CONFIG_SUBJECT_CONSENTS_INPUT_MODE,
                DEFAULT_SUBJECT_CONSENTS_SETTINGS[
                    constants.CONFIG_SUBJECT_CONSENTS_INPUT_MODE
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SUBJECT_CONSENTS_INPUT_MODE}"]'
            ),
            allowed_values=_ALLOWED_SUBJECT_CONSENTS_INPUT_MODES,
        ),
        constants.CONFIG_SUBJECT_CONSENTS_CHECKBOX_REQUIRED: _normalize_bool(
            value=subject_consents_config.get(
                constants.CONFIG_SUBJECT_CONSENTS_CHECKBOX_REQUIRED,
                DEFAULT_SUBJECT_CONSENTS_SETTINGS[
                    constants.CONFIG_SUBJECT_CONSENTS_CHECKBOX_REQUIRED
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SUBJECT_CONSENTS_CHECKBOX_REQUIRED}"]'
            ),
        ),
        constants.CONFIG_SUBJECT_CONSENTS_DECLINE_ACTION: _normalize_choice(
            value=subject_consents_config.get(
                constants.CONFIG_SUBJECT_CONSENTS_DECLINE_ACTION,
                DEFAULT_SUBJECT_CONSENTS_SETTINGS[
                    constants.CONFIG_SUBJECT_CONSENTS_DECLINE_ACTION
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SUBJECT_CONSENTS_DECLINE_ACTION}"]'
            ),
            allowed_values=_ALLOWED_SUBJECT_CONSENTS_DECLINE_ACTIONS,
        ),
        constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_ENABLED: _normalize_bool(
            value=subject_consents_config.get(
                constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_ENABLED,
                DEFAULT_SUBJECT_CONSENTS_SETTINGS[
                    constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_ENABLED
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_ENABLED}"]'
            ),
        ),
        constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_TEXT: _normalize_non_empty_string(
            value=subject_consents_config.get(
                constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_TEXT,
                DEFAULT_SUBJECT_CONSENTS_SETTINGS[
                    constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_TEXT
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_TEXT}"]'
            ),
        ),
    }


def get_subject_consents_open_mode() -> str:
    """Return the normalized document opening mode to the self-service UI."""
    return get_subject_consents_settings()[constants.CONFIG_SUBJECT_CONSENTS_OPEN_MODE]


def get_subject_consents_capture_settings() -> dict[str, Any]:
    """Restore the settings of the consent capture block for web forms."""
    settings = get_subject_consents_settings()
    return {
        "input_mode": settings[constants.CONFIG_SUBJECT_CONSENTS_INPUT_MODE],
        "checkbox_required": settings[
            constants.CONFIG_SUBJECT_CONSENTS_CHECKBOX_REQUIRED
        ],
        "decline_action": settings[constants.CONFIG_SUBJECT_CONSENTS_DECLINE_ACTION],
        "decline_warning_enabled": settings[
            constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_ENABLED
        ],
        "decline_warning_text": settings[
            constants.CONFIG_SUBJECT_CONSENTS_DECLINE_WARNING_TEXT
        ],
    }


def is_anonymous_withdraw_enabled() -> bool:
    """Check whether withdrawal of consent is allowed for anonymous subjects."""
    return get_subject_consents_settings()[
        constants.CONFIG_SUBJECT_CONSENTS_ALLOW_ANONYMOUS_WITHDRAW
    ]


def get_admin_navigation_settings() -> dict[str, object]:
    """Return and validate optional custom admin navigation settings."""

    config = get_config()
    config_path = f'{constants.SETTING_CONFIG}["{constants.CONFIG_ADMIN_NAVIGATION}"]'
    raw_navigation_config = config.get(
        constants.CONFIG_ADMIN_NAVIGATION,
        DEFAULT_ADMIN_NAVIGATION_SETTINGS,
    )
    if raw_navigation_config in (None, {}):
        raw_navigation_config = DEFAULT_ADMIN_NAVIGATION_SETTINGS
    if not isinstance(raw_navigation_config, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")

    navigation_config = dict(DEFAULT_ADMIN_NAVIGATION_SETTINGS)
    navigation_config.update(dict(raw_navigation_config))

    return {
        constants.CONFIG_ADMIN_NAVIGATION_ENABLED: _normalize_bool(
            value=navigation_config.get(
                constants.CONFIG_ADMIN_NAVIGATION_ENABLED,
                DEFAULT_ADMIN_NAVIGATION_SETTINGS[
                    constants.CONFIG_ADMIN_NAVIGATION_ENABLED
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_ADMIN_NAVIGATION_ENABLED}"]'
            ),
        ),
        constants.CONFIG_ADMIN_NAVIGATION_APP_ORDER: _normalize_string_list(
            value=navigation_config.get(
                constants.CONFIG_ADMIN_NAVIGATION_APP_ORDER,
                DEFAULT_ADMIN_NAVIGATION_SETTINGS[
                    constants.CONFIG_ADMIN_NAVIGATION_APP_ORDER
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_ADMIN_NAVIGATION_APP_ORDER}"]'
            ),
        ),
        constants.CONFIG_ADMIN_NAVIGATION_COLLAPSED_APPS: _normalize_string_list(
            value=navigation_config.get(
                constants.CONFIG_ADMIN_NAVIGATION_COLLAPSED_APPS,
                DEFAULT_ADMIN_NAVIGATION_SETTINGS[
                    constants.CONFIG_ADMIN_NAVIGATION_COLLAPSED_APPS
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_ADMIN_NAVIGATION_COLLAPSED_APPS}"]'
            ),
        ),
        constants.CONFIG_ADMIN_NAVIGATION_CONSENT_APPS: _normalize_string_list(
            value=navigation_config.get(
                constants.CONFIG_ADMIN_NAVIGATION_CONSENT_APPS,
                DEFAULT_ADMIN_NAVIGATION_SETTINGS[
                    constants.CONFIG_ADMIN_NAVIGATION_CONSENT_APPS
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_ADMIN_NAVIGATION_CONSENT_APPS}"]'
            ),
        ),
        constants.CONFIG_ADMIN_NAVIGATION_SECTION_TITLE: _normalize_non_empty_string(
            value=navigation_config.get(
                constants.CONFIG_ADMIN_NAVIGATION_SECTION_TITLE,
                DEFAULT_ADMIN_NAVIGATION_SETTINGS[
                    constants.CONFIG_ADMIN_NAVIGATION_SECTION_TITLE
                ],
            ),
            config_path=(
                f'{config_path}["{constants.CONFIG_ADMIN_NAVIGATION_SECTION_TITLE}"]'
            ),
        ),
    }


def get_purposes_config() -> dict[str, dict[str, Any]]:
    """Return normalized personal-data processing purposes.

    This is a direct bridge to section 4.2: later these data will be used to
    register `ConsentPurpose`, but the format and validation must be ready in
    advance at the scaffold and configuration layer.

    Supported config format:
    DJANGO_CONSENT_152FZ = {
        "purposes": {
            "purpose_code": {
                "label": "Purpose title",
                "description": "Optional description",
                "fields": ["full_name", "email"],
                "withdraw_strategy": "block" | "delete",
                "reconsent_mode": "soft_reconsent" | "hard_reconsent",
                "consent_frequency_policy": "once_until_outdated" | "every_time",
                "subject_availability_policy": (
                    "authenticated_only" | "authenticated_and_anonymous"
                ),
                "is_experimental": False,
                "is_active": True,
            },
        },
    }

    Key names and allowed machine-readable values (`block`, `soft_reconsent`,
    etc.) stay in English because that is how the package code reads them and
    integration tests may depend on them.
    """
    config = get_config()
    fields_config = get_fields_config()
    return _normalize_purposes(
        raw_purposes=config.get("purposes", {}),
        available_field_codes=set(fields_config),
    )


def _validate_fields_mode(value: Any) -> str:
    """Check the strategy for merging boxed and custom fields."""
    if not isinstance(value, str) or value not in _ALLOWED_FIELDS_MODES:
        raise ConsentConfigurationError(
            f'{constants.SETTING_CONFIG}["fields_mode"] must be one of: '
            f"{', '.join(sorted(_ALLOWED_FIELDS_MODES))}."
        )
    return value


def _normalize_fields(raw_fields: Any) -> dict[str, dict[str, Any]]:
    """Convert raw field descriptions into a normalized dictionary."""
    config_path = f'{constants.SETTING_CONFIG}["fields"]'
    if not isinstance(raw_fields, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")

    normalized_fields: dict[str, dict[str, Any]] = {}
    for code, field_config in raw_fields.items():
        normalized_code = _validate_code(code, config_path=config_path, what="key")
        normalized_fields[normalized_code] = _normalize_field_config(
            field_config, config_path=f'{config_path}["{normalized_code}"]'
        )
    return normalized_fields


def _validate_code(raw_code: Any, *, config_path: str, what: str) -> str:
    """Check the code value for emptiness and canonical format."""
    if not isinstance(raw_code, str) or not raw_code:
        raise ConsentConfigurationError(
            f"{config_path} {what}s must be non-empty strings."
        )
    if not _FIELD_CODE_RE.fullmatch(raw_code):
        raise ConsentConfigurationError(
            f'{config_path} {what} "{raw_code}" must match pattern "[a-z][a-z0-9_]*".'
        )
    return raw_code


def _normalize_field_config(raw_config: Any, *, config_path: str) -> dict[str, Any]:
    """Check the minimal contract for a single field.

    Right now only `label` is required because that is enough for the starter
    UI and serialization. The format can grow later.
    """
    if not isinstance(raw_config, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")
    field_config = dict(raw_config)

    raw_label = field_config.get("label")
    if not isinstance(raw_label, str) or not raw_label.strip():
        raise ConsentConfigurationError(
            f'{config_path} must contain non-empty string key "label".'
        )

    return field_config


def _normalize_purposes(
    *, raw_purposes: Any, available_field_codes: set[str]
) -> dict[str, dict[str, Any]]:
    """Validate all processing targets from the user configuration."""
    config_path = f'{constants.SETTING_CONFIG}["purposes"]'
    if not isinstance(raw_purposes, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")

    normalized_purposes: dict[str, dict[str, Any]] = {}
    for code, purpose_config in raw_purposes.items():
        normalized_code = _validate_code(code, config_path=config_path, what="key")
        purpose_path = f'{config_path}["{normalized_code}"]'
        normalized_purposes[normalized_code] = _normalize_purpose_config(
            raw_config=purpose_config,
            config_path=purpose_path,
            available_field_codes=available_field_codes,
        )

    return normalized_purposes


def _normalize_purpose_config(
    *, raw_config: Any, config_path: str, available_field_codes: set[str]
) -> dict[str, Any]:
    """Normalize the config for a single processing purpose.

    Here we immediately convert the user format into a more stable shape that
    is easier to use in services and models without extra validation on every
    call.
    """
    if not isinstance(raw_config, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")

    purpose_config = dict(raw_config)
    label = purpose_config.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ConsentConfigurationError(
            f'{config_path} must contain non-empty string key "label".'
        )

    description = purpose_config.get("description", "")
    if not isinstance(description, str):
        raise ConsentConfigurationError(
            f'{config_path}["description"] must be a string.'
        )

    fields = _normalize_purpose_fields(
        raw_fields=purpose_config.get("fields", []),
        config_path=f'{config_path}["fields"]',
        available_field_codes=available_field_codes,
    )

    withdraw_strategy = _normalize_purpose_choice(
        value=purpose_config.get(
            "withdraw_strategy",
            constants.WITHDRAW_STRATEGY_BLOCK,
        ),
        config_path=f'{config_path}["withdraw_strategy"]',
        allowed_values=_ALLOWED_WITHDRAW_STRATEGIES,
    )
    reconsent_mode = _normalize_purpose_choice(
        value=purpose_config.get(
            "reconsent_mode",
            constants.RECONSENT_MODE_SOFT,
        ),
        config_path=f'{config_path}["reconsent_mode"]',
        allowed_values=_ALLOWED_RECONSENT_MODES,
    )
    consent_frequency_policy = _normalize_purpose_choice(
        value=purpose_config.get(
            "consent_frequency_policy",
            constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED,
        ),
        config_path=f'{config_path}["consent_frequency_policy"]',
        allowed_values=_ALLOWED_CONSENT_FREQUENCIES,
    )
    subject_availability_policy = _normalize_purpose_choice(
        value=purpose_config.get(
            "subject_availability_policy",
            constants.SUBJECT_AVAILABILITY_AUTHENTICATED_AND_ANONYMOUS,
        ),
        config_path=f'{config_path}["subject_availability_policy"]',
        allowed_values=_ALLOWED_SUBJECT_AVAILABILITIES,
    )
    is_experimental = _normalize_bool(
        value=purpose_config.get("is_experimental", False),
        config_path=f'{config_path}["is_experimental"]',
    )
    is_active = _normalize_bool(
        value=purpose_config.get("is_active", True),
        config_path=f'{config_path}["is_active"]',
    )

    return {
        # Externally, the config allows the `label` key, and inside the domain model
        # It is more convenient to work with the `title` field. We do normalization here so that
        # do not spread knowledge about the user format throughout the code.
        "title": label.strip(),
        "description": description.strip(),
        "fields": fields,
        "withdraw_strategy": withdraw_strategy,
        "reconsent_mode": reconsent_mode,
        "consent_frequency_policy": consent_frequency_policy,
        "subject_availability_policy": subject_availability_policy,
        "is_experimental": is_experimental,
        "is_active": is_active,
    }


def _normalize_purpose_fields(
    *, raw_fields: Any, config_path: str, available_field_codes: set[str]
) -> list[str]:
    """Validate the field list for a processing purpose.

    This protects against three classes of errors at once:
    - an invalid value type;
    - a reference to a non-existent field;
    - duplication of the same field within one purpose.
    """
    if not isinstance(raw_fields, list):
        raise ConsentConfigurationError(f"{config_path} must be a list.")

    normalized_fields: list[str] = []
    for index, field_code in enumerate(raw_fields):
        item_path = f"{config_path}[{index}]"
        normalized_code = _validate_code(
            field_code,
            config_path=item_path,
            what="value",
        )

        if normalized_code not in available_field_codes:
            raise ConsentConfigurationError(
                f'{item_path} references unknown field "{normalized_code}".'
            )
        if normalized_code in normalized_fields:
            raise ConsentConfigurationError(
                f'{config_path} contains duplicate field "{normalized_code}".'
            )
        normalized_fields.append(normalized_code)

    return normalized_fields


def _normalize_purpose_choice(
    *, value: Any, config_path: str, allowed_values: frozenset[str]
) -> str:
    """Check one of the enumerated values ​​of the purpose config."""
    return _normalize_choice(
        value=value,
        config_path=config_path,
        allowed_values=allowed_values,
    )


def _normalize_choice(
    *, value: Any, config_path: str, allowed_values: frozenset[str]
) -> str:
    if not isinstance(value, str) or value not in allowed_values:
        raise ConsentConfigurationError(
            f"{config_path} must be one of: {', '.join(sorted(allowed_values))}."
        )
    return value


def _normalize_bool(*, value: Any, config_path: str) -> bool:
    """It is hard to check that the flag is specified as a bool and not a truthy string."""
    if not isinstance(value, bool):
        raise ConsentConfigurationError(f"{config_path} must be a boolean.")
    return value


def _normalize_non_empty_string(*, value: Any, config_path: str) -> str:
    normalized = _normalize_optional_string(value=value, config_path=config_path)
    if not normalized:
        raise ConsentConfigurationError(f"{config_path} must be a non-empty string.")
    return normalized


def _normalize_optional_string(*, value: Any, config_path: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ConsentConfigurationError(f"{config_path} must be a string.")
    return value.strip()


def _normalize_optional_domain(*, value: Any, config_path: str) -> str:
    normalized = _normalize_optional_string(value=value, config_path=config_path)
    if not normalized:
        return ""
    parsed = urlsplit(f"//{normalized}")
    if (
        parsed.scheme
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port is not None
    ):
        raise ConsentConfigurationError(
            f"{config_path} must contain only host/domain without scheme, port or path."
        )
    host = parsed.hostname or ""
    if not host:
        raise ConsentConfigurationError(f"{config_path} must be a valid host/domain.")
    return host.lstrip(".").lower()


def _normalize_string_list(*, value: Any, config_path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ConsentConfigurationError(f"{config_path} must be a list or tuple.")
    normalized_values: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{config_path}[{index}]"
        normalized_item = _normalize_non_empty_string(
            value=item,
            config_path=item_path,
        )
        dedupe_key = normalized_item.lower()
        if dedupe_key in seen:
            raise ConsentConfigurationError(
                f'{config_path} contains duplicate value "{normalized_item}".'
            )
        seen.add(dedupe_key)
        normalized_values.append(normalized_item)
    return normalized_values


def _normalize_string_mapping(*, value: Any, config_path: str) -> dict[str, str]:
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise ConsentConfigurationError(f"{config_path} must be a mapping/dict.")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in dict(value).items():
        key = _normalize_non_empty_string(
            value=raw_key,
            config_path=f"{config_path}.<key>",
        )
        normalized_value = _normalize_optional_string(
            value=raw_value,
            config_path=f'{config_path}["{key}"]',
        )
        normalized[key] = normalized_value
    return normalized


def _normalize_ip_list(*, value: Any, config_path: str) -> list[str]:
    normalized_values = _normalize_string_list(value=value, config_path=config_path)
    normalized_ips: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(normalized_values):
        item_path = f"{config_path}[{index}]"
        try:
            normalized_ip = str(ip_address(item))
        except ValueError as exc:
            raise ConsentConfigurationError(
                f"{item_path} must be a valid IPv4/IPv6 address."
            ) from exc
        if normalized_ip in seen:
            raise ConsentConfigurationError(
                f'{config_path} contains duplicate value "{normalized_ip}".'
            )
        seen.add(normalized_ip)
        normalized_ips.append(normalized_ip)
    return normalized_ips


def _normalize_callable_path(*, value: Any, config_path: str) -> str | object:
    if value is None:
        return ""
    if callable(value):
        return value
    return _normalize_optional_string(value=value, config_path=config_path)


def _normalize_non_negative_int(*, value: Any, config_path: str) -> int:
    """Validate non-negative integer for lifecycle settings."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConsentConfigurationError(
            f"{config_path} must be a non-negative integer."
        )
    return value


def _normalize_throttle_rate(*, value: Any, config_path: str) -> str:
    normalized = _normalize_non_empty_string(value=value, config_path=config_path)
    if not _THROTTLE_RATE_RE.fullmatch(normalized):
        raise ConsentConfigurationError(
            f"{config_path} must match '<count>/<period>' (e.g. 60/hour)."
        )
    return normalized
