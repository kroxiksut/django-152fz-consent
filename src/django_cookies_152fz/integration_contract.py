"""Standalone integration contract for django_cookies_152fz.

This module keeps cookie runtime integration standalone.
Cookies can run independently without consent-layer coupling.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import (
    AlreadyRegistered,  # pyright: ignore[reportAttributeAccessIssue]
)
from django.utils import timezone

SETTING_COOKIE_CONFIG = "DJANGO_COOKIES_152FZ"
SETTING_COOKIE_CONFIG_LEGACY = "DJANGO_152FZ_COOKIES"
ANONYMOUS_TOKEN_COOKIE_NAME = "django_cookies_152fz_anonymous"
ANONYMOUS_TOKEN_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
_operation_logger = logging.getLogger("django_cookies_152fz.operations")


@dataclass(frozen=True)
class _CookieConstants:
    COOKIES_APP: str = "django_cookies_152fz"
    CONFIG_ENABLE_COOKIES: str = "enable_cookies"
    CONFIG_DEFAULT_COOKIE_CATEGORY_CODES: str = "default_cookie_category_codes"
    CONFIG_COOKIE_BANNER: str = "cookie_banner"
    CONFIG_COOKIE_RUNTIME: str = "cookie_runtime"
    CONFIG_COOKIE_RETENTION: str = "cookie_retention"
    CONFIG_COOKIE_BANNER_PREFERENCES_PAGE_TEMPLATE: str = "preferences_page_template"
    CONFIG_COOKIE_BANNER_BOOTSTRAP_INITIAL_REVISION: str = "bootstrap_initial_revision"
    CONFIG_COOKIE_BANNER_VARIANT: str = "banner_variant"
    CONFIG_COOKIE_BANNER_CONSENT_UI_VARIANT: str = "consent_ui_variant"
    CONFIG_COOKIE_BANNER_RECONSENT_NOTICE_VARIANT: str = "reconsent_notice_variant"
    CONFIG_COOKIE_BANNER_TEXT_PRESET: str = "text_preset"
    CONFIG_COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK: str = (
        "show_empty_category_block"
    )
    CONFIG_COOKIE_BANNER_SHOW_CUSTOMIZE_ACTION_WITHOUT_OPTIONAL: str = (
        "show_customize_action_without_optional"
    )
    CONFIG_COOKIE_BANNER_EMPTY_CATEGORY_BLOCK_TEXT: str = "empty_category_block_text"
    CONFIG_COOKIE_RUNTIME_FORCE_BANNER: str = "force_banner"
    CONFIG_COOKIE_RUNTIME_PREVIEW_PARAM: str = "preview_param"
    CONFIG_COOKIE_RUNTIME_CUSTOM_CSS_URL: str = "custom_css_url"
    CONFIG_COOKIE_RUNTIME_CUSTOM_JS_URL: str = "custom_js_url"
    CONFIG_COOKIE_RUNTIME_HIDE_FOR_BOTS: str = "hide_for_bots"
    CONFIG_COOKIE_RUNTIME_BOT_PATTERNS: str = "bot_patterns"
    CONFIG_COOKIE_RUNTIME_USER_AGENT_MODE: str = "user_agent_mode"
    CONFIG_COOKIE_RUNTIME_SHARED_SUBDOMAIN: str = "shared_subdomain"
    CONFIG_COOKIE_RUNTIME_SITE_DOMAIN: str = "site_domain"
    CONFIG_COOKIE_RUNTIME_COOKIE_DOMAIN: str = "cookie_domain"
    CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_HOPS: str = "trusted_proxy_hops"
    CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_IPS: str = "trusted_proxy_ips"
    CONFIG_COOKIE_RUNTIME_GEO_SIGNAL_HOOK: str = "geo_signal_hook"
    CONFIG_COOKIE_RETENTION_BATCH_SIZE: str = "batch_size"
    CONFIG_COOKIE_RETENTION_EVENTS_OLDER_THAN_DAYS: str = "events_older_than_days"
    CONFIG_COOKIE_RETENTION_EVENTS_MAX_COUNT: str = "events_max_count"
    CONFIG_COOKIE_RETENTION_RECORDS_OLDER_THAN_DAYS: str = "records_older_than_days"
    CONFIG_COOKIE_RETENTION_RECORDS_MAX_COUNT: str = "records_max_count"
    CONFIG_COOKIE_RETENTION_BANNER_STATES_OLDER_THAN_DAYS: str = (
        "banner_states_older_than_days"
    )
    CONFIG_COOKIE_RETENTION_BANNER_STATES_MAX_COUNT: str = "banner_states_max_count"
    CONFIG_COOKIE_RETENTION_PRIVATE_EVENTS_OLDER_THAN_DAYS: str = (
        "private_events_older_than_days"
    )
    CONFIG_COOKIE_RETENTION_PRIVATE_RECORDS_OLDER_THAN_DAYS: str = (
        "private_records_older_than_days"
    )
    CONFIG_COOKIE_RETENTION_PRIVATE_SIGNAL_PATHS: str = "private_signal_paths"
    CONFIG_COOKIE_RETENTION_PROTECT_CURRENT_RECORDS: str = "protect_current_records"
    COOKIE_BANNER_VARIANT_BAR: str = "bar"
    COOKIE_BANNER_VARIANT_CARD: str = "card"
    COOKIE_BANNER_VARIANT_MODAL: str = "modal"
    COOKIE_BANNER_VARIANTS: tuple[str, ...] = ("bar", "card", "modal")
    COOKIE_BANNER_CONSENT_UI_VARIANT_INLINE: str = "inline"
    COOKIE_BANNER_CONSENT_UI_VARIANT_PANEL: str = "panel"
    COOKIE_BANNER_CONSENT_UI_VARIANTS: tuple[str, ...] = ("inline", "panel")
    COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_INLINE: str = "inline"
    COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_ALERT: str = "alert"
    COOKIE_BANNER_RECONSENT_NOTICE_VARIANTS: tuple[str, ...] = (
        "inline",
        "alert",
    )
    COOKIE_BANNER_TEXT_PRESET_RU_BALANCED: str = "ru_balanced"
    COOKIE_BANNER_TEXT_PRESET_RU_FORMAL: str = "ru_formal"
    COOKIE_BANNER_TEXT_PRESET_RU_COMPACT: str = "ru_compact"
    COOKIE_BANNER_TEXT_PRESET_EN_BALANCED: str = "en_balanced"
    COOKIE_BANNER_TEXT_PRESET_EN_FORMAL: str = "en_formal"
    COOKIE_BANNER_TEXT_PRESET_EN_COMPACT: str = "en_compact"
    COOKIE_BANNER_TEXT_PRESET_AUTO: str = "auto"
    COOKIE_CONSENT_STATUS_CURRENT: str = "current"
    COOKIE_CONSENT_STATUS_OUTDATED: str = "outdated"
    COOKIE_EVENT_ACCEPTED: str = "accepted"
    COOKIE_EVENT_UPDATED: str = "updated"
    COOKIE_EVENT_OUTDATED: str = "outdated"


constants = _CookieConstants()


class ConsentError(Exception):
    """Cookie-domain exception for standalone mode."""


class ReadOnlyAdminMixin:
    """Mixin for visible but immutable admin entities."""

    def get_readonly_fields(self, request, obj=None):
        model = getattr(self, "model", None)
        if model is None:
            return []
        return [
            *[field.name for field in model._meta.fields],
            *[field.name for field in model._meta.many_to_many],
        ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class AssignmentRestrictedAdminMixin:
    """Mixin with optional assignment-flag based access control."""

    change_permission_flags: str | Iterable[str] | None = None
    view_permission_flags: str | Iterable[str] | None = None
    superuser_only = False

    def _has_admin_access(
        self,
        request,
        *,
        permission_flags: str | Iterable[str] | None,
    ) -> bool:
        user = getattr(request, "user", None)
        if not bool(getattr(user, "is_active", False)):
            return False
        if self.superuser_only:
            return bool(getattr(user, "is_superuser", False))
        if bool(getattr(user, "is_superuser", False)):
            return True
        assignment = getattr(user, "personal_data_manager_assignment", None)
        if assignment is None or not bool(getattr(assignment, "is_active", False)):
            return False
        normalized_flags = _normalize_permission_flags(permission_flags)
        if not normalized_flags:
            return True
        return any(bool(getattr(assignment, flag, False)) for flag in normalized_flags)

    def has_module_permission(self, request) -> bool:
        flags = self.view_permission_flags
        if flags is None:
            flags = self.change_permission_flags
        return self._has_admin_access(request, permission_flags=flags)

    def has_view_permission(self, request, obj=None) -> bool:
        flags = self.view_permission_flags
        if flags is None:
            flags = self.change_permission_flags
        return self._has_admin_access(request, permission_flags=flags)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._has_admin_access(
            request,
            permission_flags=self.change_permission_flags,
        )

    def has_add_permission(self, request) -> bool:
        return self.has_change_permission(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self.has_change_permission(request, obj=obj)


class PublishableRevisionAdminMixin:
    def assign_next_version(self, obj, *, latest_version: int = 0) -> None:
        current = int(getattr(obj, "version", 0) or 0)
        if current <= 0:
            obj.version = int(latest_version or 0) + 1

    def ensure_published_at(self, obj, *, now_value=None) -> None:
        if not hasattr(obj, "published_at"):
            return
        if bool(getattr(obj, "is_active", False)):
            if getattr(obj, "published_at", None) is None:
                obj.published_at = now_value or timezone.now()
        else:
            obj.published_at = None


class ConsentAuditContextForm(forms.Form):
    anonymous_token = forms.CharField(required=False, widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class ModuleOperationAuditLog:
    class Status:
        SUCCESS = "success"
        ERROR = "error"
        DRY_RUN = "dry_run"


def safe_register_admin_models(site: admin.sites.AdminSite, registrations):
    for model, admin_class in registrations:
        try:
            site.register(model, admin_class)
        except AlreadyRegistered:
            continue


def log_module_operation(*args, **kwargs) -> dict[str, Any]:
    if args:
        raise TypeError("log_module_operation accepts keyword arguments only.")
    payload = dict(kwargs)
    operation_code = str(payload.pop("operation_code", "") or "").strip()
    source = str(payload.pop("source", "") or "").strip()
    status = (
        str(payload.pop("status", ModuleOperationAuditLog.Status.SUCCESS) or "").strip()
        or ModuleOperationAuditLog.Status.SUCCESS
    )
    summary = str(payload.pop("summary", "") or "").strip()
    target_model = str(payload.pop("target_model", "") or "").strip()
    target_id = str(payload.pop("target_id", "") or "").strip()
    actor_user = payload.pop("actor_user", None)
    actor_user_id = getattr(actor_user, "pk", None)
    actor_username_getter = getattr(actor_user, "get_username", None)
    actor_username = (
        str(actor_username_getter()) if callable(actor_username_getter) else ""
    )
    event_payload = payload.pop("payload", None)
    result_payload = payload.pop("result", None)
    operation_record = {
        "operation_code": operation_code,
        "source": source,
        "status": status,
        "summary": summary,
        "target_model": target_model,
        "target_id": target_id,
        "actor_user_id": actor_user_id,
        "actor_username": actor_username,
        "payload": event_payload,
        "result": result_payload,
        "extra": payload,
        "occurred_at": timezone.now().isoformat(),
    }
    _operation_logger.info(
        "cookie_module_operation %s",
        json.dumps(_json_safe(operation_record), ensure_ascii=False, sort_keys=True),
    )
    return operation_record


def build_audit_context(*, source: str = "cookies.runtime", **kwargs) -> dict[str, Any]:
    return {"source": source, **kwargs}


def trigger_cookie_audit_archive(*args, **kwargs) -> None:
    return None


def trigger_cookie_runtime_event(*args, **kwargs) -> None:
    return None


def build_request_audit_context(
    request,
    *,
    source: str = "template_ui.cookies",
    anonymous_token: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = get_request_anonymous_token(request, anonymous_token=anonymous_token)
    client_meta = _build_client_meta(request)
    merged_extra_meta = dict(extra_meta or {})
    if client_meta:
        merged_extra_meta["client"] = _merge_nested_dicts(
            dict(merged_extra_meta.get("client") or {}),
            client_meta,
        )
    payload = build_audit_context(
        source=source,
        anonymous_token=token,
        ip_address=_get_client_ip(request),
        user_agent=_get_header(request, "User-Agent"),
        locale=str(getattr(request, "LANGUAGE_CODE", "") or ""),
        request_id=_get_header(request, "X-Request-ID"),
    )
    if merged_extra_meta:
        payload["extra_meta"] = merged_extra_meta
    return payload


def get_cookie_runtime_allowed_hosts(request=None) -> set[str]:
    allowed_hosts: set[str] = {
        str(v).strip() for v in getattr(settings, "ALLOWED_HOSTS", []) if str(v).strip()
    }
    if request is not None:
        try:
            host = str(request.get_host() or "").strip()
            if host:
                allowed_hosts.add(host)
        except Exception:
            pass
    site_domain = str(get_cookie_runtime_settings().get("site_domain") or "").strip()
    if site_domain:
        allowed_hosts.add(site_domain)
    return allowed_hosts


def get_request_anonymous_token(
    request,
    *,
    anonymous_token: str | None = None,
    ensure_anonymous_token: bool = False,
) -> str:
    token = str(anonymous_token or "").strip()
    if not token:
        token = _get_cookie_value(request, ANONYMOUS_TOKEN_COOKIE_NAME)
    if ensure_anonymous_token and not token:
        token = generate_anonymous_token()
    return token


def generate_anonymous_token() -> str:
    return secrets.token_urlsafe(24)


def persist_anonymous_token(response, anonymous_token: str) -> None:
    token = str(anonymous_token or "").strip()
    if not token:
        return
    runtime_settings = get_cookie_runtime_settings()
    cookie_domain = _normalize_cookie_domain(
        runtime_settings.get("cookie_domain"),
        setting_name=constants.CONFIG_COOKIE_RUNTIME_COOKIE_DOMAIN,
    )
    # The cookies package is independent of consent: it manages only its own
    # cookie and does not touch cookies belonging to other packages. (Previously
    # the consent cookie `django_consent_152fz_anonymous` was deleted here —
    # a leftover from when cookies lived inside consent; that broke the
    # consent cookie when both packages were installed together.)
    response.set_cookie(
        ANONYMOUS_TOKEN_COOKIE_NAME,
        token,
        max_age=ANONYMOUS_TOKEN_COOKIE_MAX_AGE,
        domain=cookie_domain,
        secure=True,
        httponly=True,
        samesite="Lax",
    )


def get_request_consent_subject(
    request,
    *,
    anonymous_token: str | None = None,
    ensure_anonymous_token: bool = False,
):
    token = get_request_anonymous_token(
        request,
        anonymous_token=anonymous_token,
        ensure_anonymous_token=ensure_anonymous_token,
    )
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user, ""
    return None, token


def get_cookie_banner_settings() -> dict[str, Any]:
    cookie_cfg = _get_cookie_section(constants.CONFIG_COOKIE_BANNER)
    return {
        constants.CONFIG_COOKIE_BANNER_BOOTSTRAP_INITIAL_REVISION: bool(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_BOOTSTRAP_INITIAL_REVISION, True
            )
        ),
        constants.CONFIG_COOKIE_BANNER_PREFERENCES_PAGE_TEMPLATE: str(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_PREFERENCES_PAGE_TEMPLATE,
                "django_cookies_152fz/cookie_preferences.html",
            )
        ),
        constants.CONFIG_COOKIE_BANNER_VARIANT: str(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_VARIANT,
                constants.COOKIE_BANNER_VARIANT_CARD,
            )
        ),
        constants.CONFIG_COOKIE_BANNER_CONSENT_UI_VARIANT: str(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_CONSENT_UI_VARIANT,
                constants.COOKIE_BANNER_CONSENT_UI_VARIANT_PANEL,
            )
        ),
        constants.CONFIG_COOKIE_BANNER_RECONSENT_NOTICE_VARIANT: str(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_RECONSENT_NOTICE_VARIANT,
                constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_INLINE,
            )
        ),
        constants.CONFIG_COOKIE_BANNER_TEXT_PRESET: str(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_TEXT_PRESET,
                constants.COOKIE_BANNER_TEXT_PRESET_RU_BALANCED,
            )
        ),
        constants.CONFIG_COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK: bool(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK,
                False,
            )
        ),
        constants.CONFIG_COOKIE_BANNER_SHOW_CUSTOMIZE_ACTION_WITHOUT_OPTIONAL: bool(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_SHOW_CUSTOMIZE_ACTION_WITHOUT_OPTIONAL,
                False,
            )
        ),
        constants.CONFIG_COOKIE_BANNER_EMPTY_CATEGORY_BLOCK_TEXT: str(
            cookie_cfg.get(
                constants.CONFIG_COOKIE_BANNER_EMPTY_CATEGORY_BLOCK_TEXT,
                "",
            )
            or ""
        ),
    }


def get_cookie_runtime_settings() -> dict[str, Any]:
    cfg = _get_cookie_section(constants.CONFIG_COOKIE_RUNTIME)
    default_patterns = [
        "googlebot",
        "yandexbot",
        "bingbot",
        "duckduckbot",
        "baiduspider",
        "slurp",
        "facebookexternalhit",
        "twitterbot",
        "linkedinbot",
        "crawler",
        "spider",
        "bot",
    ]
    raw_patterns = cfg.get(
        constants.CONFIG_COOKIE_RUNTIME_BOT_PATTERNS, default_patterns
    )
    if not isinstance(raw_patterns, (list, tuple)):
        raw_patterns = default_patterns
    normalized_patterns = [str(v).strip() for v in raw_patterns if str(v).strip()]
    if not normalized_patterns:
        normalized_patterns = default_patterns

    return {
        constants.CONFIG_COOKIE_RUNTIME_FORCE_BANNER: bool(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_FORCE_BANNER, False)
        ),
        constants.CONFIG_COOKIE_RUNTIME_PREVIEW_PARAM: str(
            cfg.get(
                constants.CONFIG_COOKIE_RUNTIME_PREVIEW_PARAM, "cookie_banner_preview"
            )
            or "cookie_banner_preview"
        ),
        constants.CONFIG_COOKIE_RUNTIME_CUSTOM_CSS_URL: str(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_CUSTOM_CSS_URL, "") or ""
        ),
        constants.CONFIG_COOKIE_RUNTIME_CUSTOM_JS_URL: str(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_CUSTOM_JS_URL, "") or ""
        ),
        constants.CONFIG_COOKIE_RUNTIME_HIDE_FOR_BOTS: bool(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_HIDE_FOR_BOTS, True)
        ),
        constants.CONFIG_COOKIE_RUNTIME_BOT_PATTERNS: normalized_patterns,
        constants.CONFIG_COOKIE_RUNTIME_USER_AGENT_MODE: str(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_USER_AGENT_MODE, "all") or "all"
        ),
        constants.CONFIG_COOKIE_RUNTIME_SHARED_SUBDOMAIN: bool(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_SHARED_SUBDOMAIN, False)
        ),
        constants.CONFIG_COOKIE_RUNTIME_SITE_DOMAIN: str(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_SITE_DOMAIN, "") or ""
        ),
        constants.CONFIG_COOKIE_RUNTIME_COOKIE_DOMAIN: str(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_COOKIE_DOMAIN, "") or ""
        ),
        constants.CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_HOPS: cfg.get(
            constants.CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_HOPS,
            getattr(settings, "TRUSTED_PROXY_152FZ_HOPS", 0),
        ),
        constants.CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_IPS: cfg.get(
            constants.CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_IPS,
            getattr(settings, "TRUSTED_PROXY_152FZ_IPS", []),
        ),
        constants.CONFIG_COOKIE_RUNTIME_GEO_SIGNAL_HOOK: str(
            cfg.get(constants.CONFIG_COOKIE_RUNTIME_GEO_SIGNAL_HOOK, "") or ""
        ),
    }


def get_default_cookie_category_codes() -> list[str]:
    root = _get_cookie_settings_root()
    defaults = root.get(constants.CONFIG_DEFAULT_COOKIE_CATEGORY_CODES)
    if isinstance(defaults, (list, tuple)):
        return [str(v).strip() for v in defaults if str(v).strip()]
    return ["necessary"]


def get_cookie_retention_settings() -> dict[str, Any]:
    cfg = _get_cookie_section(constants.CONFIG_COOKIE_RETENTION)
    return {
        constants.CONFIG_COOKIE_RETENTION_BATCH_SIZE: int(
            cfg.get(constants.CONFIG_COOKIE_RETENTION_BATCH_SIZE, 500)
        ),
        constants.CONFIG_COOKIE_RETENTION_EVENTS_OLDER_THAN_DAYS: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_EVENTS_OLDER_THAN_DAYS
        ),
        constants.CONFIG_COOKIE_RETENTION_EVENTS_MAX_COUNT: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_EVENTS_MAX_COUNT
        ),
        constants.CONFIG_COOKIE_RETENTION_RECORDS_OLDER_THAN_DAYS: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_RECORDS_OLDER_THAN_DAYS
        ),
        constants.CONFIG_COOKIE_RETENTION_RECORDS_MAX_COUNT: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_RECORDS_MAX_COUNT
        ),
        constants.CONFIG_COOKIE_RETENTION_BANNER_STATES_OLDER_THAN_DAYS: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_BANNER_STATES_OLDER_THAN_DAYS
        ),
        constants.CONFIG_COOKIE_RETENTION_BANNER_STATES_MAX_COUNT: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_BANNER_STATES_MAX_COUNT
        ),
        constants.CONFIG_COOKIE_RETENTION_PRIVATE_EVENTS_OLDER_THAN_DAYS: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_PRIVATE_EVENTS_OLDER_THAN_DAYS
        ),
        constants.CONFIG_COOKIE_RETENTION_PRIVATE_RECORDS_OLDER_THAN_DAYS: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_PRIVATE_RECORDS_OLDER_THAN_DAYS
        ),
        constants.CONFIG_COOKIE_RETENTION_PRIVATE_SIGNAL_PATHS: cfg.get(
            constants.CONFIG_COOKIE_RETENTION_PRIVATE_SIGNAL_PATHS, []
        ),
        constants.CONFIG_COOKIE_RETENTION_PROTECT_CURRENT_RECORDS: bool(
            cfg.get(constants.CONFIG_COOKIE_RETENTION_PROTECT_CURRENT_RECORDS, True)
        ),
    }


def is_cookies_enabled() -> bool:
    root = _get_cookie_settings_root()
    return bool(root.get(constants.CONFIG_ENABLE_COOKIES, True))


def _get_cookie_settings_root() -> dict[str, Any]:
    cfg = getattr(settings, SETTING_COOKIE_CONFIG, None)
    if cfg is None:
        cfg = getattr(settings, SETTING_COOKIE_CONFIG_LEGACY, None)
    if isinstance(cfg, dict):
        return cfg
    return {}


def _get_cookie_section(section_key: str) -> dict[str, Any]:
    section = _get_cookie_settings_root().get(section_key)
    if isinstance(section, dict):
        return dict(section)
    return {}


def _get_header(request, header_name: str) -> str:
    headers = getattr(request, "headers", None)
    if headers is not None:
        return str(headers.get(header_name, "") or "")
    meta_name = f"HTTP_{header_name.upper().replace('-', '_')}"
    return str(getattr(request, "META", {}).get(meta_name, "") or "")


def _get_client_ip(request) -> str:
    remote_addr = str(getattr(request, "META", {}).get("REMOTE_ADDR", "") or "").strip()
    if not _is_valid_ip_address(remote_addr):
        remote_addr = ""
    runtime_settings = get_cookie_runtime_settings()
    trusted_proxy_hops = _coerce_non_negative_int(
        runtime_settings.get(constants.CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_HOPS),
    )
    if trusted_proxy_hops <= 0:
        return remote_addr
    trusted_proxy_ips = {
        ip
        for ip in (
            str(value).strip()
            for value in (
                runtime_settings.get(
                    constants.CONFIG_COOKIE_RUNTIME_TRUSTED_PROXY_IPS, []
                )
                or []
            )
        )
        if ip and _is_valid_ip_address(ip)
    }
    if trusted_proxy_ips and remote_addr not in trusted_proxy_ips:
        return remote_addr
    forwarded_for = _get_header(request, "X-Forwarded-For")
    forwarded_chain = [
        item.strip() for item in forwarded_for.split(",") if item.strip()
    ]
    if len(forwarded_chain) < trusted_proxy_hops:
        return remote_addr
    candidate_ip = forwarded_chain[-trusted_proxy_hops]
    if _is_valid_ip_address(candidate_ip):
        return candidate_ip
    return remote_addr


def _get_cookie_value(request, cookie_name: str) -> str:
    return str(getattr(request, "COOKIES", {}).get(cookie_name, "") or "").strip()


def _normalize_permission_flags(
    permission_flags: str | Iterable[str] | None,
) -> tuple[str, ...]:
    if permission_flags is None:
        return ()
    if isinstance(permission_flags, str):
        return (permission_flags,)
    return tuple(str(flag) for flag in permission_flags)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _build_client_meta(request) -> dict[str, str]:
    user_agent = _get_header(request, "User-Agent")
    accept_language = _get_header(request, "Accept-Language")
    locale = str(getattr(request, "LANGUAGE_CODE", "") or "")
    country_code, country_source = _resolve_country_context(
        locale=locale,
        accept_language=accept_language,
        headers=getattr(request, "headers", {}),
    )
    browser_name, browser_version_major = _parse_browser_meta(user_agent)
    os_family, os_version_major = _parse_os_meta(user_agent)

    client: dict[str, str] = {}
    if country_code:
        client["country_code"] = country_code
        client["country_source"] = country_source
    if browser_name:
        client["browser_name"] = browser_name
    if browser_version_major:
        client["browser_version_major"] = browser_version_major
    if os_family:
        client["os_family"] = os_family
    if os_version_major:
        client["os_version_major"] = os_version_major
    return client


def _resolve_country_context(
    *,
    locale: str,
    accept_language: str,
    headers,
) -> tuple[str, str]:
    for header_name in (
        "CF-IPCountry",
        "X-Country-Code",
        "X-Geo-Country",
        "X-Appengine-Country",
    ):
        value = str(headers.get(header_name, "") or "").strip()
        if _is_iso_country_code(value):
            return value.upper(), f"header:{header_name.lower()}"

    for candidate in (locale, accept_language):
        country = _extract_country_from_locale(candidate)
        if country:
            return country, "locale"
    return "", ""


def _extract_country_from_locale(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    first = raw_value.split(",", 1)[0].split(";", 1)[0].strip()
    if not first:
        return ""
    first = first.replace("_", "-")
    if "-" not in first:
        return ""
    region = first.rsplit("-", 1)[-1]
    return region.upper() if _is_iso_country_code(region) else ""


def _is_iso_country_code(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{2}", str(value or "").strip()))


def _parse_browser_meta(user_agent: str) -> tuple[str, str]:
    ua = str(user_agent or "")
    patterns = (
        ("Edge", r"Edg/(\d+)"),
        ("Chrome", r"Chrome/(\d+)"),
        ("Firefox", r"Firefox/(\d+)"),
        ("Safari", r"Version/(\d+).+Safari/"),
        ("Opera", r"OPR/(\d+)"),
    )
    for browser_name, pattern in patterns:
        match = re.search(pattern, ua)
        if match:
            return browser_name, match.group(1)
    return "", ""


def _parse_os_meta(user_agent: str) -> tuple[str, str]:
    ua = str(user_agent or "")
    os_patterns = (
        ("Windows", r"Windows NT (\d+)"),
        ("Android", r"Android (\d+)"),
        ("iOS", r"OS (\d+)_"),
        ("macOS", r"Mac OS X (\d+)_"),
    )
    for os_name, pattern in os_patterns:
        match = re.search(pattern, ua)
        if match:
            return os_name, match.group(1)
    if "Linux" in ua:
        return "Linux", ""
    return "", ""


def _merge_nested_dicts(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_nested_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_cookie_domain(value: object, *, setting_name: str) -> str | None:
    domain = str(value or "").strip()
    if not domain:
        return None
    normalized = domain[1:] if domain.startswith(".") else domain
    if (
        not normalized
        or "." not in normalized
        or "/" in normalized
        or ":" in normalized
        or ".." in normalized
    ):
        raise ConsentError(
            f"Invalid {setting_name}: use a plain domain like example.com or .example.com."
        )
    labels = normalized.split(".")
    for label in labels:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label):
            raise ConsentError(
                f"Invalid {setting_name}: each domain label must use letters, digits, or '-'."
            )
    return normalized


def _is_valid_ip_address(value: str) -> bool:
    if not value:
        return False
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def _coerce_non_negative_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return 0
        try:
            parsed = int(normalized)
        except ValueError:
            return 0
        return parsed if parsed > 0 else 0
    normalized = str(value).strip()
    if not normalized:
        return 0
    try:
        parsed = int(normalized)
    except ValueError:
        return 0
    return parsed if parsed > 0 else 0
