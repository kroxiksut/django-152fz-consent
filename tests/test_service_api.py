from __future__ import annotations

from inspect import signature

from django_consent_152fz import service_api


def test_service_api_exports_expected_symbols() -> None:
    assert set(service_api.__all__) == {
        "accept_consent",
        "anonymize_subject_consents",
        "attach_anonymous_consents_to_user",
        "get_consent_status",
        "get_current_requirements",
        "get_provider_code",
        "register_purposes_from_config",
        "withdraw_consent",
    }
    assert tuple(service_api.__all__) == service_api.PUBLIC_SERVICE_API_V1


def test_get_provider_code_is_stable() -> None:
    assert service_api.get_provider_code() == "ru_152fz"


def test_service_api_signatures_are_stable() -> None:
    assert tuple(signature(service_api.accept_consent).parameters) == (
        "purpose_code",
        "document_code",
        "user",
        "anonymous_token",
        "kwargs",
    )
    assert tuple(signature(service_api.withdraw_consent).parameters) == (
        "purpose_code",
        "document_code",
        "user",
        "anonymous_token",
        "kwargs",
    )
    assert tuple(signature(service_api.get_consent_status).parameters) == (
        "purpose_code",
        "document_code",
        "user",
        "anonymous_token",
    )
    assert tuple(signature(service_api.get_current_requirements).parameters) == (
        "user",
        "anonymous_token",
    )
    assert tuple(signature(service_api.anonymize_subject_consents).parameters) == (
        "user",
        "anonymous_token",
        "purpose_code",
        "document_code",
        "kwargs",
    )


def test_core_facade_delegates_to_core_services(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(name: str):
        def _inner(**kwargs):
            calls.append((name, dict(kwargs)))
            return {"name": name}

        return _inner

    monkeypatch.setattr(
        service_api.core_services,
        "register_purposes_from_config",
        lambda: ["ok"],
    )
    monkeypatch.setattr(
        service_api.core_services,
        "get_current_requirements",
        _capture("get_current_requirements"),
    )
    monkeypatch.setattr(service_api.core_services, "accept_consent", _capture("accept"))
    monkeypatch.setattr(
        service_api.core_services, "withdraw_consent", _capture("withdraw")
    )
    monkeypatch.setattr(
        service_api.core_services, "get_consent_status", _capture("status")
    )
    monkeypatch.setattr(
        service_api.core_services,
        "attach_anonymous_consents_to_user",
        _capture("attach"),
    )
    monkeypatch.setattr(
        service_api.core_services,
        "anonymize_subject_consents",
        _capture("anonymize"),
    )

    assert service_api.register_purposes_from_config() == ["ok"]
    assert service_api.get_current_requirements(anonymous_token="anon") == {
        "name": "get_current_requirements"
    }
    assert service_api.accept_consent(
        purpose_code="signup",
        anonymous_token="anon",
        source="web",
    ) == {"name": "accept"}
    assert service_api.withdraw_consent(
        purpose_code="signup",
        anonymous_token="anon",
        source="web",
    ) == {"name": "withdraw"}
    assert service_api.get_consent_status(
        purpose_code="signup",
        anonymous_token="anon",
    ) == {"name": "status"}
    assert service_api.attach_anonymous_consents_to_user(
        user=object(),
        anonymous_token="anon",
    ) == {"name": "attach"}
    assert service_api.anonymize_subject_consents(
        anonymous_token="anon",
        reason="gdpr-like cleanup",
    ) == {"name": "anonymize"}

    assert calls[0] == (
        "get_current_requirements",
        {"user": None, "anonymous_token": "anon"},
    )
    assert calls[1] == (
        "accept",
        {
            "purpose_code": "signup",
            "document_code": None,
            "user": None,
            "anonymous_token": "anon",
            "source": "web",
        },
    )
    assert calls[2] == (
        "withdraw",
        {
            "purpose_code": "signup",
            "document_code": None,
            "user": None,
            "anonymous_token": "anon",
            "source": "web",
        },
    )
    assert calls[3] == (
        "status",
        {
            "purpose_code": "signup",
            "document_code": None,
            "user": None,
            "anonymous_token": "anon",
        },
    )
    assert calls[4][0] == "attach"
    assert calls[4][1]["anonymous_token"] == "anon"
    assert calls[5] == (
        "anonymize",
        {
            "user": None,
            "anonymous_token": "anon",
            "purpose_code": None,
            "document_code": None,
            "reason": "gdpr-like cleanup",
        },
    )
