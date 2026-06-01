from __future__ import annotations

import pytest
from django.test import override_settings

from django_consent_152fz.core.models import ConsentPurpose
from django_consent_152fz.core.services import register_purposes_from_config


@pytest.mark.django_db
def test_register_purposes_from_config_creates_records() -> None:
    config = {
        "fields": {
            "email": {"label": "Электронная почта"},
            "nickname": {"label": "Никнейм"},
        },
        "purposes": {
            "account_basic": {
                "label": "Регистрация",
                "fields": ["email", "nickname"],
                "withdraw_strategy": "block",
                "reconsent_mode": "soft_reconsent",
                "consent_frequency_policy": "once_until_outdated",
                "subject_availability_policy": "authenticated_and_anonymous",
            }
        },
    }

    with override_settings(DJANGO_152FZ_CONSENT=config):
        created = register_purposes_from_config()

    assert len(created) == 1
    purpose = ConsentPurpose.objects.get(code="account_basic")
    assert purpose.title == "Регистрация"
    assert purpose.fields_config == ["email", "nickname"]
    assert purpose.withdraw_strategy == "block"
    assert purpose.reconsent_mode == "soft_reconsent"
    assert purpose.consent_frequency_policy == "once_until_outdated"
    assert purpose.subject_availability_policy == "authenticated_and_anonymous"


@pytest.mark.django_db
def test_register_purposes_from_config_updates_existing_record() -> None:
    initial_config = {
        "fields": {
            "email": {"label": "Электронная почта"},
        },
        "purposes": {
            "account_basic": {
                "label": "Регистрация",
                "fields": ["email"],
                "withdraw_strategy": "block",
                "reconsent_mode": "soft_reconsent",
            }
        },
    }
    updated_config = {
        "fields": {
            "email": {"label": "Электронная почта"},
        },
        "purposes": {
            "account_basic": {
                "label": "Регистрация и обслуживание",
                "fields": ["email"],
                "withdraw_strategy": "delete",
                "reconsent_mode": "hard_reconsent",
                "consent_frequency_policy": "every_time",
                "subject_availability_policy": "authenticated_only",
                "is_experimental": True,
                "is_active": False,
            }
        },
    }

    with override_settings(DJANGO_152FZ_CONSENT=initial_config):
        register_purposes_from_config()

    with override_settings(DJANGO_152FZ_CONSENT=updated_config):
        register_purposes_from_config()

    assert ConsentPurpose.objects.filter(code="account_basic").count() == 1
    purpose = ConsentPurpose.objects.get(code="account_basic")
    assert purpose.title == "Регистрация и обслуживание"
    assert purpose.withdraw_strategy == "delete"
    assert purpose.reconsent_mode == "hard_reconsent"
    assert purpose.consent_frequency_policy == "every_time"
    assert purpose.subject_availability_policy == "authenticated_only"
    assert purpose.is_experimental is True
    assert purpose.is_active is False
