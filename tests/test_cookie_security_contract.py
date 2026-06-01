from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from django_cookies_152fz.integration_contract import (
    ANONYMOUS_TOKEN_COOKIE_NAME,
    ConsentError,
    _get_client_ip,
    get_request_anonymous_token,
    persist_anonymous_token,
)


def test_get_request_anonymous_token_ignores_query_param() -> None:
    request = RequestFactory().get("/cookies/?anonymous_token=query-token")

    token = get_request_anonymous_token(request)

    assert token == ""


def test_get_request_anonymous_token_reads_cookie() -> None:
    request = RequestFactory().get("/cookies/")
    request.COOKIES[ANONYMOUS_TOKEN_COOKIE_NAME] = "cookie-token"

    token = get_request_anonymous_token(request)

    assert token == "cookie-token"


@override_settings(
    DJANGO_COOKIES_152FZ={
        "cookie_runtime": {
            "cookie_domain": ".example.test",
        }
    }
)
def test_persist_anonymous_token_sets_secure_cookie() -> None:
    response = HttpResponse()

    persist_anonymous_token(response, anonymous_token="token-value")

    cookie = response.cookies[ANONYMOUS_TOKEN_COOKIE_NAME]
    assert cookie.value == "token-value"
    assert cookie["secure"] is True
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["domain"] == "example.test"
    # Cookies-пакет независим: persist управляет только своим cookie и не трогает
    # cookie consent-пакета.
    assert "django_consent_152fz_anonymous" not in response.cookies


@override_settings(
    DJANGO_COOKIES_152FZ={
        "cookie_runtime": {
            "cookie_domain": "https://example.test",
        }
    }
)
def test_persist_anonymous_token_rejects_invalid_cookie_domain() -> None:
    response = HttpResponse()

    try:
        persist_anonymous_token(response, anonymous_token="token-value")
    except ConsentError:
        pass
    else:
        raise AssertionError("Expected ConsentError for invalid cookie_domain")


def test_get_client_ip_ignores_xff_without_trusted_proxy_hops() -> None:
    request = RequestFactory().get(
        "/cookies/",
        HTTP_X_FORWARDED_FOR="1.2.3.4",
        REMOTE_ADDR="10.0.0.1",
    )

    assert _get_client_ip(request) == "10.0.0.1"


@override_settings(
    DJANGO_COOKIES_152FZ={
        "cookie_runtime": {
            "trusted_proxy_hops": 1,
            "trusted_proxy_ips": ["10.0.0.1"],
        }
    }
)
def test_get_client_ip_uses_xff_only_for_trusted_proxy_ip() -> None:
    trusted_request = RequestFactory().get(
        "/cookies/",
        HTTP_X_FORWARDED_FOR="1.2.3.4",
        REMOTE_ADDR="10.0.0.1",
    )
    untrusted_request = RequestFactory().get(
        "/cookies/",
        HTTP_X_FORWARDED_FOR="1.2.3.4",
        REMOTE_ADDR="203.0.113.10",
    )

    assert _get_client_ip(trusted_request) == "1.2.3.4"
    assert _get_client_ip(untrusted_request) == "203.0.113.10"
