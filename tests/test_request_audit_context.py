from __future__ import annotations

from django.test import RequestFactory, override_settings

from django_consent_152fz.request import build_request_audit_context
from django_cookies_152fz.integration_contract import (
    build_request_audit_context as build_cookie_request_audit_context,
)


def test_consent_request_audit_context_adds_country_and_browser_os_meta() -> None:
    request = RequestFactory().get(
        "/consent/document/signup/signup_doc/",
        HTTP_USER_AGENT=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9,en-US;q=0.8",
    )
    request.LANGUAGE_CODE = "ru-ru"

    context = build_request_audit_context(
        request,
        source="test.request.audit",
    )

    client_meta = context["extra_meta"]["client"]
    assert client_meta["country_code"] == "RU"
    assert client_meta["country_source"] == "locale"
    assert client_meta["browser_name"] == "Chrome"
    assert client_meta["browser_version_major"] == "124"
    assert client_meta["os_family"] == "Windows"
    assert client_meta["os_version_major"] == "10"


def test_cookie_request_audit_context_adds_country_and_browser_os_meta() -> None:
    request = RequestFactory().get(
        "/cookies/preferences/",
        HTTP_USER_AGENT=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
    )
    request.LANGUAGE_CODE = "en-us"

    context = build_cookie_request_audit_context(
        request,
        source="test.cookies.audit",
    )

    client_meta = context["extra_meta"]["client"]
    assert client_meta["country_code"] == "US"
    assert client_meta["country_source"] == "locale"
    assert client_meta["browser_name"] == "Firefox"
    assert client_meta["browser_version_major"] == "125"
    assert client_meta["os_family"] == "Windows"
    assert client_meta["os_version_major"] == "10"


@override_settings(
    TRUSTED_PROXY_152FZ_HOPS=1,
    TRUSTED_PROXY_152FZ_IPS=["10.0.0.10"],
)
def test_consent_request_audit_context_uses_xff_only_for_trusted_proxy() -> None:
    request = RequestFactory().get(
        "/consent/document/signup/signup_doc/",
        HTTP_X_FORWARDED_FOR="203.0.113.7",
        REMOTE_ADDR="10.0.0.10",
    )

    context = build_request_audit_context(
        request,
        source="test.request.audit.trusted_proxy",
    )

    assert context["ip_address"] == "203.0.113.7"


@override_settings(
    TRUSTED_PROXY_152FZ_HOPS=1,
    TRUSTED_PROXY_152FZ_IPS=["10.0.0.10"],
)
def test_consent_request_audit_context_ignores_xff_from_untrusted_remote_addr() -> None:
    request = RequestFactory().get(
        "/consent/document/signup/signup_doc/",
        HTTP_X_FORWARDED_FOR="203.0.113.7",
        REMOTE_ADDR="198.51.100.25",
    )

    context = build_request_audit_context(
        request,
        source="test.request.audit.untrusted_proxy",
    )

    assert context["ip_address"] == "198.51.100.25"
