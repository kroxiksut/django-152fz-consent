"""Boxed consent goals for the 152-FZ starter kit."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from django_consent_152fz import constants
from django_consent_152fz.core.models import ConsentPurpose

CORE_152FZ_STARTER_PURPOSE_TEMPLATES: dict[str, dict[str, object]] = {
    "contact_feedback": {
        "code": "contact_feedback",
        "title": _("Обратная связь и ответы на обращения"),
        "description": _(
            "Используется для обработки обращений из формы обратной связи и "
            "подготовки ответа пользователю."
        ),
        "fields_config": [
            {"name": "full_name", "required": True},
            {"name": "email", "required": True},
            {"name": "message", "required": True},
        ],
    },
    "newsletter_signup": {
        "code": "newsletter_signup",
        "title": _("Email-рассылка и информирование"),
        "description": _(
            "Используется для подписки на новости, сервисные дайджесты и "
            "маркетинговые рассылки."
        ),
        "fields_config": [
            {"name": "email", "required": True},
            {"name": "first_name", "required": False},
        ],
    },
    "service_account": {
        "code": "service_account",
        "title": _("Регистрация и обслуживание аккаунта"),
        "description": _(
            "Используется для создания учётной записи, аутентификации и "
            "поддержки базовых сервисных операций пользователя."
        ),
        "fields_config": [
            {"name": "email", "required": True},
            {"name": "phone", "required": False},
            {"name": "password_hash", "required": True},
        ],
    },
    "support_request": {
        "code": "support_request",
        "title": _("Поддержка пользователей и обработка запросов"),
        "description": _(
            "Используется для обработки обращений в поддержку, диагностики "
            "проблем и обратной связи по уже оказанным услугам."
        ),
        "fields_config": [
            {"name": "full_name", "required": False},
            {"name": "email", "required": True},
            {"name": "phone", "required": False},
            {"name": "request_text", "required": True},
        ],
    },
    "job_application": {
        "code": "job_application",
        "title": _("Отклик на вакансию и кадровый резерв"),
        "description": _(
            "Используется для приёма резюме, сопроводительных писем и "
            "организации коммуникации с кандидатами."
        ),
        "fields_config": [
            {"name": "full_name", "required": True},
            {"name": "email", "required": True},
            {"name": "phone", "required": False},
            {"name": "birth_date", "required": False},
            {"name": "request_text", "required": False},
        ],
    },
    "order_processing": {
        "code": "order_processing",
        "title": _("Оформление и сопровождение заказа"),
        "description": _(
            "Используется для подтверждения заказа, связи с клиентом и "
            "сопровождения исполнения заявки."
        ),
        "fields_config": [
            {"name": "full_name", "required": True},
            {"name": "email", "required": True},
            {"name": "phone", "required": True},
            {"name": "contacts", "required": False},
            {"name": "request_text", "required": False},
        ],
    },
}


def bootstrap_starter_purposes(*, using: str = "default") -> dict[str, Any]:
    """Create/update starter consent purposes idempotently."""
    summary = {
        "created": 0,
        "updated": 0,
        "total": len(CORE_152FZ_STARTER_PURPOSE_TEMPLATES),
    }
    for purpose in CORE_152FZ_STARTER_PURPOSE_TEMPLATES.values():
        _, created = ConsentPurpose.objects.using(using).update_or_create(
            code=str(purpose["code"]),
            defaults={
                "title": purpose["title"],
                "description": purpose.get("description", ""),
                "fields_config": list(
                    cast(Iterable[dict[str, Any]], purpose.get("fields_config", []))
                ),
                "withdraw_strategy": constants.WITHDRAW_STRATEGY_BLOCK,
                "reconsent_mode": constants.RECONSENT_MODE_SOFT,
                "consent_frequency_policy": (
                    constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED
                ),
                "subject_availability_policy": (
                    constants.SUBJECT_AVAILABILITY_AUTHENTICATED_AND_ANONYMOUS
                ),
                "is_experimental": False,
                "is_active": True,
            },
        )
        if created:
            summary["created"] += 1
        else:
            summary["updated"] += 1
    return summary


def bootstrap_starter_purposes_post_migrate(
    sender, **kwargs
):  # pragma: no cover - post_migrate hook
    using = kwargs.get("using", "default")
    return bootstrap_starter_purposes(using=using)
