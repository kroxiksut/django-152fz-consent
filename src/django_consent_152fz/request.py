"""Сбор request-derived контекста для UI-слоя пункта 5.

Модуль связывает HTML/template потоки с ядром пакета:
- определяет, кто именно является субъектом (`user` или `anonymous_token`);
- нормализует HTTP/client metadata в схему `audit_context`;
- сохраняет анонимный токен между запросами через cookie.

Так UI-слой остаётся тонкой транспортной оболочкой над сервисами пункта 4.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import time
from datetime import timedelta
from ipaddress import ip_address
from typing import Any

from django.core.cache import cache
from django.core.exceptions import DisallowedHost
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.translation import get_language_from_request

from django_consent_152fz import constants
from django_consent_152fz.core.models import RevokedAnonymousToken
from django_consent_152fz.core.services import build_audit_context
from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.settings import (
    get_api_setting,
    get_public_api_settings,
)

ANONYMOUS_TOKEN_COOKIE_NAME = "django_consent_152fz_anonymous"
ANONYMOUS_TOKEN_HEADER_NAME = "X-Anonymous-Token"
ANONYMOUS_TOKEN_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
ANONYMOUS_TOKEN_PREFIX = "v1"
logger = logging.getLogger(__name__)


def build_request_audit_context(
    request: HttpRequest,
    *,
    source: str,
    anonymous_token: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collects the canonical `audit_context` from an HTTP request."""

    _, resolved_token = get_request_consent_subject(
        request,
        anonymous_token=anonymous_token,
    )
    return build_audit_context(
        source=source,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
        locale=get_language_from_request(request) or "",
        request_id=request.headers.get("X-Request-ID", ""),
        session_key_hash=_build_session_key_hash(
            request=request,
            anonymous_token=resolved_token,
        ),
        request=_build_request_meta(request),
        client=_build_client_meta(request),
        client_hints=_build_client_hints(request),
        extra_meta=extra_meta,
    )


def get_request_consent_subject(
    request: HttpRequest,
    *,
    anonymous_token: str | None = None,
    ensure_anonymous_token: bool = False,
):
    """Returns the subject of the thread as `(user, anonymous_token)`."""

    token = get_request_anonymous_token(
        request,
        anonymous_token=anonymous_token,
        ensure_anonymous_token=ensure_anonymous_token,
    )
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        return user, ""
    return None, token


def get_request_anonymous_token(
    request: HttpRequest,
    *,
    anonymous_token: str | None = None,
    ensure_anonymous_token: bool = False,
    strict_validation: bool = False,
    allow_query_token: bool = True,
) -> str:
    """Извлекает или при необходимости создаёт `anonymous_token`.

    Порядок источников здесь осознанный:
    1. Явно переданный аргумент `anonymous_token`.
       Его используют API views, когда токен уже извлечён из JSON payload.
    2. Параметры текущего HTTP-запроса (`POST` / `GET`).
       Это основной путь для template/UI сценариев.
    3. Cookie ранее сохранённого анонимного субъекта.

    Такой порядок нужен затем, чтобы API и HTML-слой пользовались одним helper,
    но при этом JSON API не зависел от того, как Django наполняет `request.POST`.
    """

    token = (anonymous_token or "").strip()
    if not token:
        token = str(request.headers.get(ANONYMOUS_TOKEN_HEADER_NAME, "")).strip()
    if not token:
        token = _get_request_value(
            request,
            "anonymous_token",
            allow_query=allow_query_token,
        )
    if not token:
        token = str(request.COOKIES.get(ANONYMOUS_TOKEN_COOKIE_NAME, "")).strip()
    if token:
        try:
            ensure_anonymous_token_is_usable(token)
        except ConsentError:
            if strict_validation:
                raise
            token = ""
    if ensure_anonymous_token and not token:
        token = generate_anonymous_token()
    return token


def generate_anonymous_token() -> str:
    """Generates a persistent random token for an anonymous subject."""
    issued_at = int(time.time())
    return f"{ANONYMOUS_TOKEN_PREFIX}.{issued_at}.{secrets.token_urlsafe(24)}"


def revoke_anonymous_token(*, anonymous_token: str) -> None:
    token = str(anonymous_token or "").strip()
    if not token:
        return
    token_hash = _token_hash(token)
    expires_at = _resolve_token_expiry_datetime(token)
    RevokedAnonymousToken.objects.update_or_create(
        token_hash=token_hash,
        defaults={"expires_at": expires_at},
    )
    cache.set(
        _revoked_token_cache_key(token), True, timeout=ANONYMOUS_TOKEN_COOKIE_MAX_AGE
    )


def ensure_anonymous_token_is_usable(anonymous_token: str) -> None:
    token = str(anonymous_token or "").strip()
    if not token:
        raise ConsentError("anonymous_token must be a non-empty string.")
    if cache.get(_revoked_token_cache_key(token)):
        raise ConsentError("anonymous_token is no longer valid.")
    token_hash = _token_hash(token)
    revoked_token = RevokedAnonymousToken.objects.filter(token_hash=token_hash).first()
    if revoked_token is not None:
        if (
            revoked_token.expires_at is None
            or revoked_token.expires_at > timezone.now()
        ):
            cache.set(
                _revoked_token_cache_key(token),
                True,
                timeout=ANONYMOUS_TOKEN_COOKIE_MAX_AGE,
            )
            raise ConsentError("anonymous_token is no longer valid.")
    if _is_token_expired(token):
        raise ConsentError("anonymous_token has expired.")


def persist_anonymous_token(response: HttpResponse, *, anonymous_token: str) -> None:
    """Сохраняет `anonymous_token` в cookie ответа.

    Это позволяет template UI, cookie-flow и анонимным contact/preorder
    сценариям видеть одного и того же субъекта в разных HTTP-запросах.
    """

    token = anonymous_token.strip()
    if not token:
        return
    response.set_cookie(
        ANONYMOUS_TOKEN_COOKIE_NAME,
        token,
        max_age=ANONYMOUS_TOKEN_COOKIE_MAX_AGE,
        secure=True,
        httponly=True,
        samesite="Lax",
    )


def _get_client_ip(request: HttpRequest) -> str | None:
    remote_addr = str(request.META.get("REMOTE_ADDR") or "").strip()
    if not _is_valid_ip_address(remote_addr):
        remote_addr = ""

    public_api_settings = get_public_api_settings()
    trusted_proxy_hops = int(public_api_settings[constants.SETTING_TRUSTED_PROXY_HOPS])
    if trusted_proxy_hops <= 0:
        return remote_addr or None

    trusted_proxy_ips = set(public_api_settings[constants.SETTING_TRUSTED_PROXY_IPS])
    if trusted_proxy_ips and remote_addr not in trusted_proxy_ips:
        return remote_addr or None

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    forwarded_chain = [
        item.strip() for item in forwarded_for.split(",") if item.strip()
    ]
    if len(forwarded_chain) < trusted_proxy_hops:
        return remote_addr or None

    candidate_ip = forwarded_chain[-trusted_proxy_hops]
    if _is_valid_ip_address(candidate_ip):
        return candidate_ip
    return remote_addr or None


def _build_session_key_hash(
    *,
    request: HttpRequest,
    anonymous_token: str | None,
) -> str:
    """Builds a sha256 hash of a session key or anonymous token instead of storing the source."""

    session = getattr(request, "session", None)
    session_key = getattr(session, "session_key", None)
    raw_value = str(session_key or anonymous_token or "").strip()
    if not raw_value:
        return ""
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _build_request_meta(request: HttpRequest) -> dict[str, Any]:
    """Collects a secure minimum of HTTP metadata for auditing."""

    meta: dict[str, Any] = {
        "path": request.path,
        "method": request.method,
        "scheme": request.scheme,
    }
    try:
        meta["host"] = request.get_host()
    except DisallowedHost as exc:
        logger.warning("Request host rejected by Django host validation: %s", exc)

    referrer = request.headers.get("Referer", "")
    if referrer:
        meta["referrer"] = referrer
    return meta


def _build_client_meta(request: HttpRequest) -> dict[str, Any]:
    """Collects best-effort client metadata from hidden fields and headers."""

    meta: dict[str, Any] = {}

    languages = _parse_languages(
        _get_request_value(request, "client_languages")
        or request.headers.get("Accept-Language", "")
    )
    if languages:
        meta["languages"] = languages

    timezone = _get_request_value(request, "client_timezone")
    if timezone:
        meta["timezone"] = timezone

    os_locale = _get_request_value(request, "client_os_locale")
    if os_locale:
        meta["os_locale"] = os_locale
    country_code, country_source = _resolve_country_context(
        locale=os_locale,
        accept_language=request.headers.get("Accept-Language", ""),
        headers=request.headers,
    )
    if country_code:
        meta["country_code"] = country_code
        meta["country_source"] = country_source

    user_agent = request.headers.get("User-Agent", "")
    browser_name, browser_version_major = _parse_browser_meta(user_agent)
    if browser_name:
        meta["browser_name"] = browser_name
    if browser_version_major:
        meta["browser_version_major"] = browser_version_major
    os_family, os_version_major = _parse_os_meta(user_agent)
    if os_family:
        meta["os_family"] = os_family
    if os_version_major:
        meta["os_version_major"] = os_version_major

    screen = _build_screen_meta(request)
    if screen:
        meta["screen"] = screen

    return meta


def _build_client_hints(request: HttpRequest) -> dict[str, Any]:
    """Retrieves a secure subset of Client Hints for audit_context."""

    hints: dict[str, Any] = {}
    for header_name, output_name in (
        ("Sec-CH-UA", "sec_ch_ua"),
        ("Sec-CH-UA-Platform", "sec_ch_ua_platform"),
        ("Sec-CH-UA-Mobile", "sec_ch_ua_mobile"),
    ):
        value = request.headers.get(header_name, "")
        if value:
            hints[output_name] = value
    return hints


def _resolve_country_context(
    *,
    locale: str,
    accept_language: str,
    headers: Any,
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


def _build_screen_meta(request: HttpRequest) -> dict[str, int]:
    width = _coerce_positive_int(_get_request_value(request, "client_screen_width"))
    height = _coerce_positive_int(_get_request_value(request, "client_screen_height"))
    screen: dict[str, int] = {}
    if width is not None:
        screen["width"] = width
    if height is not None:
        screen["height"] = height
    return screen


def _parse_languages(value: str) -> list[str]:
    """Normalizes languages ​​from a JSON list or `Accept-Language` string."""

    raw_value = value.strip()
    if not raw_value:
        return []

    if raw_value.startswith("["):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

    languages: list[str] = []
    for chunk in raw_value.split(","):
        language = chunk.split(";", 1)[0].strip()
        if language and language not in languages:
            languages.append(language)
    return languages


def _coerce_positive_int(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = int(normalized)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _get_request_value(
    request: HttpRequest,
    key: str,
    *,
    allow_query: bool = True,
) -> str:
    """Reads the value first from POST, then from GET, maintaining a single contract."""

    if request.method == "POST":
        value = request.POST.get(key, "")
        if value:
            return str(value).strip()
    if allow_query:
        return str(request.GET.get(key, "")).strip()
    return ""


def _revoked_token_cache_key(token: str) -> str:
    return f"dz152fz:anon_token:revoked:{_token_hash(token)}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_valid_ip_address(value: str) -> bool:
    if not value:
        return False
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def _resolve_token_ttl_seconds() -> int:
    return int(
        get_api_setting(constants.SETTING_ANON_TOKEN_TTL_SECONDS)
        or ANONYMOUS_TOKEN_COOKIE_MAX_AGE
    )


def _resolve_token_expiry_datetime(token: str):
    if _is_token_expired(token):
        return timezone.now()
    ttl_seconds = _resolve_token_ttl_seconds()
    if ttl_seconds <= 0:
        return None
    return timezone.now() + timedelta(seconds=ttl_seconds)


def _is_token_expired(token: str) -> bool:
    ttl_seconds = _resolve_token_ttl_seconds()
    if ttl_seconds <= 0:
        return False
    parts = token.split(".", 2)
    if len(parts) != 3 or parts[0] != ANONYMOUS_TOKEN_PREFIX:
        # Legacy tokens remain valid until replaced.
        return False
    try:
        issued_at = int(parts[1])
    except (TypeError, ValueError):
        return False
    return int(time.time()) > issued_at + ttl_seconds
