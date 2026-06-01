"""Service layer for the cookie module."""

from __future__ import annotations

import hashlib
import logging
import re
from calendar import monthrange
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.db import DEFAULT_DB_ALIAS, IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from .integration_contract import (
    ConsentError,
    build_audit_context,
    constants,
    get_cookie_banner_settings,
    get_cookie_runtime_settings,
    get_default_cookie_category_codes,
    is_cookies_enabled,
    log_module_operation,
    trigger_cookie_runtime_event,
)
from .models import (
    COOKIE_BANNER_EDITABLE_TEXT_FIELDS,
    COOKIE_BANNER_PROTECTED_TEXT_FIELDS,
    COOKIE_BANNER_TEXT_FIELDS,
    COOKIE_BANNER_TEXT_PRESETS,
    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR,
    DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION,
    CookieAdminSettings,
    CookieBannerRevision,
    CookieBannerState,
    CookieBannerTextPreset,
    CookieCategory,
    CookieConsentEvent,
    CookieConsentRecord,
    CookiePolicyRevision,
    CookiePolicyRevisionRegistryItem,
    CookiePolicyTextPreset,
    CookieRegistryItem,
    normalize_categories_snapshot,
)

COOKIE_RUNTIME_GEO_SIGNAL_RU = "ru"
COOKIE_RUNTIME_GEO_SIGNAL_NON_RU = "non_ru"
COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN = "unknown"
_runtime_logger = logging.getLogger("django_cookies_152fz.runtime")
_ALLOWED_COOKIE_RUNTIME_GEO_SIGNALS = frozenset(
    {
        COOKIE_RUNTIME_GEO_SIGNAL_RU,
        COOKIE_RUNTIME_GEO_SIGNAL_NON_RU,
        COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN,
    }
)
COOKIE_RUNTIME_EVENT_CONTRACT_VERSION = "1.0"
COOKIE_RUNTIME_DOM_EVENT_CONTRACT = {
    "version": COOKIE_RUNTIME_EVENT_CONTRACT_VERSION,
    "namespace": "dz152fz",
    "events": {
        "runtime_applied": "dz152fz:cookie-runtime:applied",
        "runtime_cleanup_applied": "dz152fz:cookie-runtime:cleanup-applied",
        "banner_opened": "dz152fz:cookie-banner:opened",
        "banner_closed": "dz152fz:cookie-banner:closed",
        "banner_custom_opened": "dz152fz:cookie-banner:custom-opened",
        "banner_action_submitted": "dz152fz:cookie-banner:action-submitted",
    },
}
COOKIE_POLICY_REVISION_TEXT_RU_SHORT = """Политика использования cookie

Оператор: [полное наименование / ФИО оператора], адрес: [адрес], ИНН/ОГРН: [реквизиты].
Сайт: [домен сайта].
Контакт по вопросам персональных данных: [email или иной канал связи].

На сайте используются обязательные и необязательные cookie. Обязательные cookie нужны для базовой работы сайта
и безопасности. Необязательные категории (аналитика, функциональные и маркетинговые cookie) включаются
только после явного выбора пользователя.

Пользователь может принять все cookie, оставить только обязательные категории или настроить выбор по категориям.
Изменить выбор можно в любой момент на странице настроек cookie."""
COOKIE_POLICY_REVISION_TEXT_RU_FULL = """Политика использования файлов cookie

1. Общие положения
Оператор [полное наименование / ФИО оператора], адрес: [адрес], ИНН/ОГРН: [реквизиты], использует cookie
на сайте [домен сайта] для обеспечения его работоспособности, безопасности и улучшения качества сервиса.
Контакт по вопросам персональных данных: [email или иной канал связи].

2. Какие данные собираются
С использованием cookie могут обрабатываться технические сведения: IP-адрес, дата и время визита, адреса страниц,
источник перехода, параметры браузера и устройства, язык интерфейса, технические идентификаторы.

3. Категории cookie
Обязательные cookie необходимы для функционирования сайта.
Необязательные cookie (аналитические, функциональные, маркетинговые) активируются только после выбора пользователя.

4. Управление настройками
Пользователь может:
- принять все cookie;
- оставить только обязательные cookie;
- выбрать отдельные категории cookie.

Настройки можно изменить в любой момент на странице настроек cookie.

5. Внешние сервисы
Если на сайте используются внешние сервисы, оператор указывает их перечень и назначение в настройках cookie
или в отдельной документации проекта."""
DEFAULT_COOKIE_POLICY_REVISION_TEXT_RU = COOKIE_POLICY_REVISION_TEXT_RU_SHORT
COOKIE_POLICY_REVISION_TEXT_EN_SHORT = """Cookie policy

Operator: [full legal name], address: [address], tax ID/registration: [details].
Website: [domain].
Privacy contact: [email or another contact channel].

The website uses required and optional cookies. Required cookies support core
site operation and security. Optional categories (analytics, functional, and
marketing cookies) are enabled only after explicit user selection.

Users can accept all cookies, keep required-only categories, or configure
category-level preferences. Preferences can be updated at any time on the
cookie settings page."""
COOKIE_POLICY_REVISION_TEXT_EN_FULL = """Cookie policy

1. General
Operator [full legal name], address: [address], tax ID/registration: [details],
uses cookies on [domain] to provide website operation, security, and service
quality improvements. Privacy contact: [email or another channel].

2. Data processed
When cookies are used, technical data may be processed, including IP address,
visit date and time, page URLs, referrer, browser/device parameters, interface
language, and technical identifiers.

3. Cookie categories
Required cookies are needed for website operation.
Optional cookies (analytics, functional, marketing) are enabled only after an
explicit user choice.

4. Preference management
Users can:
- accept all cookies;
- keep required cookies only;
- select optional categories manually.

Preferences can be changed at any time on the cookie settings page.

5. Third-party services
If third-party services are used, the operator provides their list and purposes
in cookie settings or in separate project documentation."""
COOKIE_POLICY_TEXT_VARIANT_SHORT = "short"
COOKIE_POLICY_TEXT_VARIANT_FULL = "full"
COOKIE_POLICY_TEXT_VARIANT_SHORT_EN = "short_en"
COOKIE_POLICY_TEXT_VARIANT_FULL_EN = "full_en"
COOKIE_POLICY_TEXT_VARIANTS = {
    COOKIE_POLICY_TEXT_VARIANT_SHORT: {
        "title": "Short box policy text (RU)",
        "content_text": COOKIE_POLICY_REVISION_TEXT_RU_SHORT,
    },
    COOKIE_POLICY_TEXT_VARIANT_FULL: {
        "title": "Full box policy text (RU)",
        "content_text": COOKIE_POLICY_REVISION_TEXT_RU_FULL,
    },
    COOKIE_POLICY_TEXT_VARIANT_SHORT_EN: {
        "title": "Short box policy text (EN)",
        "content_text": COOKIE_POLICY_REVISION_TEXT_EN_SHORT,
    },
    COOKIE_POLICY_TEXT_VARIANT_FULL_EN: {
        "title": "Full box policy text (EN)",
        "content_text": COOKIE_POLICY_REVISION_TEXT_EN_FULL,
    },
}
COOKIE_BANNER_DECISION_ACTION_ACCEPT_ALL = "accept_all"
COOKIE_BANNER_DECISION_ACTION_REJECT_ALL = "reject_all"
COOKIE_BANNER_DECISION_ACTION_REQUIRED_ONLY = "required_only"
COOKIE_BANNER_DECISION_ACTION_SAVE_CUSTOM = "save_custom"
COOKIE_BANNER_DECISION_ACTIONS = frozenset(
    {
        COOKIE_BANNER_DECISION_ACTION_ACCEPT_ALL,
        COOKIE_BANNER_DECISION_ACTION_REJECT_ALL,
        COOKIE_BANNER_DECISION_ACTION_REQUIRED_ONLY,
        COOKIE_BANNER_DECISION_ACTION_SAVE_CUSTOM,
    }
)


def _normalize_human_text(value: str) -> str:
    return str(value or "").strip()


def _normalize_language_code(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    return normalized


def _preferred_cookie_banner_preset_code_for_language(language_code: str) -> str:
    normalized = _normalize_language_code(language_code)
    if normalized.startswith("en"):
        return constants.COOKIE_BANNER_TEXT_PRESET_EN_BALANCED
    return constants.COOKIE_BANNER_TEXT_PRESET_RU_BALANCED


DEFAULT_COOKIE_CATEGORY_TEXTS: dict[str, dict[str, Any]] = {
    "necessary": {
        "title": "Обязательные cookie",
        "description": (
            "Cookie для балансировки "
            "нагрузки, входа в "
            "аккаунт, отправки "
            "форм, базовой "
            "безопасности и "
            "сохранения настроек "
            "конфиденциальности."
        ),
    },
    "functional": {
        "title": "Функциональные cookie",
        "description": (
            "Cookie для запоминания "
            "выбора пользователя, "
            "персонализации "
            "интерфейса и "
            "улучшения возможностей "
            "сайта."
        ),
    },
    "analytics": {
        "title": "Аналитические cookie",
        "description": (
            "Cookie для статистики "
            "использования сайта, "
            "оценки популярности "
            "контента и анализа "
            "пользовательских "
            "сценариев."
        ),
    },
    "marketing": {
        "title": "Рекламные и таргетинговые cookie",
        "description": (
            "Cookie для поведенческой "
            "рекламы, ограничения "
            "частоты показов и "
            "взаимодействия с "
            "рекламными партнёрами."
        ),
    },
}
LEGACY_DEFAULT_COOKIE_CATEGORY_TEXTS: dict[str, dict[str, Any]] = {
    "necessary": {
        "title": "Необходимые",
        "description": "Технические cookie для базовой работы сайта и безопасности.",
    },
    "functional": {
        "title": "Функциональные",
        "description": (
            "Cookie для сохранения пользовательских настроек и удобства интерфейса."
        ),
    },
    "analytics": {
        "title": "Аналитические",
        "description": "Cookie для анализа посещаемости и улучшения качества сервиса.",
    },
    "marketing": {
        "title": "Маркетинговые",
        "description": "Cookie для персонализации контента и рекламных материалов.",
    },
}

LEGACY_DEFAULT_COOKIE_CATEGORY_TITLE_ALIASES: dict[str, set[str]] = {
    "necessary": {"Необходимые"},
    "functional": {"Функциональные"},
    "analytics": {"Аналитические"},
    "marketing": {"Маркетинговые"},
}

LEGACY_DEFAULT_COOKIE_CATEGORY_DESCRIPTION_ALIASES: dict[str, set[str]] = {
    "necessary": {"Технические cookie для базовой работы сайта и безопасности."},
    "functional": {
        "Cookie для сохранения пользовательских настроек и удобства интерфейса."
    },
    "analytics": {"Cookie для анализа посещаемости и улучшения качества сервиса."},
    "marketing": {"Cookie для персонализации контента и рекламных материалов."},
}
# Comment
COOKIE_RUNTIME_CONSENT_EVENT_NAMES = {
    CookieConsentEvent.EventType.ACCEPTED: "cookie_consent.accepted",
    CookieConsentEvent.EventType.UPDATED: "cookie_consent.updated",
    CookieConsentEvent.EventType.OUTDATED: "cookie_consent.outdated",
}


def ensure_default_cookie_categories() -> list[CookieCategory]:
    """Function ensure_default_cookie_categories documentation."""

    created_or_updated: list[CookieCategory] = []
    for index, code in enumerate(get_default_cookie_category_codes(), start=1):
        localized_texts = DEFAULT_COOKIE_CATEGORY_TEXTS.get(code, {})
        defaults = {
            "title": str(
                localized_texts.get("title") or code.replace("_", " ").title()
            ),
            "description": str(localized_texts.get("description") or ""),
            "is_required": code == "necessary",
            "sort_order": index,
            "is_active": True,
        }
        category, created = CookieCategory.objects.get_or_create(
            code=code,
            defaults=defaults,
        )
        if not created:
            updated = False
            legacy_texts = LEGACY_DEFAULT_COOKIE_CATEGORY_TEXTS.get(code, {})
            legacy_title_values = {
                str(legacy_texts.get("title") or ""),
                *LEGACY_DEFAULT_COOKIE_CATEGORY_TITLE_ALIASES.get(code, set()),
            }
            if not category.title or category.title in legacy_title_values:
                category.title = defaults["title"]
                updated = True
            legacy_description_values = {
                str(legacy_texts.get("description") or ""),
                *LEGACY_DEFAULT_COOKIE_CATEGORY_DESCRIPTION_ALIASES.get(code, set()),
            }
            if (
                not category.description
                or category.description in legacy_description_values
            ):
                category.description = defaults["description"]
                updated = True
            if category.sort_order != index:
                category.sort_order = index
                updated = True
            if code == "necessary" and not category.is_required:
                category.is_required = True
                updated = True
            if not category.is_active:
                category.is_active = True
                updated = True
            if updated:
                category.save()
        created_or_updated.append(category)
    return created_or_updated


def snapshot_active_cookie_categories() -> list[dict[str, object]]:
    """Function snapshot_active_cookie_categories documentation."""

    categories = list(
        CookieCategory.objects.filter(is_active=True).order_by("sort_order", "code")
    )
    if not categories:
        ensure_default_cookie_categories()
        categories = list(
            CookieCategory.objects.filter(is_active=True).order_by("sort_order", "code")
        )
    return [
        {
            "code": category.code,
            "title": category.title,
            "description": category.description,
            "is_required": category.is_required,
            "sort_order": category.sort_order,
        }
        for category in categories
    ]


def snapshot_active_cookie_registry_items(
    *,
    category_codes: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    """Function snapshot_active_cookie_registry_items documentation."""

    qs = CookieRegistryItem.objects.select_related("category").filter(
        is_active=True,
        category__is_active=True,
    )
    normalized_category_codes = {
        str(code).strip() for code in (category_codes or []) if str(code).strip()
    }
    if normalized_category_codes:
        qs = qs.filter(category__code__in=normalized_category_codes)

    return [
        {
            "code": item.code,
            "category_code": item.category.code,
            "category_title": item.category.title,
            "category_is_required": item.category.is_required,
            "provider": item.provider,
            "purpose": item.purpose,
            "retention": item.retention,
            "cookie_names": list(item.cookie_names),
            "src_url": item.src_url,
            "clear_strategy": item.clear_strategy,
        }
        for item in qs.order_by("category__sort_order", "category__code", "code")
    ]


def get_cookie_policy_text_variants() -> dict[str, dict[str, Any]]:
    """Function get_cookie_policy_text_variants documentation."""

    ensure_default_cookie_policy_text_presets()
    db_presets = {
        preset.code: preset
        for preset in CookiePolicyTextPreset.objects.filter(is_active=True)
    }
    variants: dict[str, dict[str, Any]] = {}
    for variant_code, variant_payload in COOKIE_POLICY_TEXT_VARIANTS.items():
        db_preset = db_presets.get(variant_code)
        variants[variant_code] = {
            "code": variant_code,
            "title": (
                str(db_preset.title)
                if db_preset is not None
                else str(variant_payload["title"])
            ),
            "content_text": (
                str(db_preset.content_text)
                if db_preset is not None
                else str(variant_payload["content_text"])
            ),
        }
    return variants


def _resolve_cookie_policy_text_variant(variant_code: str) -> dict[str, str]:
    normalized_code = str(variant_code or "").strip().lower()
    variant = get_cookie_policy_text_variants().get(normalized_code)
    if variant is None:
        raise ConsentError(
            _(
                "Неизвестный вариант текста cookie-policy: %(variant)s. "
                "Ожидается один из: %(allowed)s."
            )
            % {
                "variant": repr(variant_code),
                "allowed": ", ".join(COOKIE_POLICY_TEXT_VARIANTS),
            }
        )
    return dict(variant)


def ensure_default_cookie_policy_text_presets() -> list[CookiePolicyTextPreset]:
    """Function ensure_default_cookie_policy_text_presets documentation."""

    created_or_updated: list[CookiePolicyTextPreset] = []
    for variant_code, variant_payload in COOKIE_POLICY_TEXT_VARIANTS.items():
        default_title = _normalize_human_text(str(variant_payload["title"]))
        default_content_text = _normalize_human_text(
            str(variant_payload["content_text"])
        )
        preset, created = CookiePolicyTextPreset.objects.get_or_create(
            code=variant_code,
            defaults={
                "title": default_title,
                "content_text": default_content_text,
                "is_box_template": True,
                "is_active": True,
            },
        )
        if not created:
            updated = False
            normalized_title = _normalize_human_text(str(preset.title or ""))
            normalized_content_text = _normalize_human_text(
                str(preset.content_text or "")
            )
            if not normalized_title:
                preset.title = default_title
                updated = True
            elif normalized_title != str(preset.title):
                preset.title = normalized_title
                updated = True
            if not normalized_content_text:
                preset.content_text = default_content_text
                updated = True
            elif normalized_content_text != str(preset.content_text):
                preset.content_text = normalized_content_text
                updated = True
            if not preset.is_active:
                preset.is_active = True
                updated = True
            if updated:
                preset.save()
        created_or_updated.append(preset)
    for preset in CookiePolicyTextPreset.objects.all().order_by("id"):
        updated = False
        normalized_title = _normalize_human_text(str(preset.title or ""))
        normalized_content_text = _normalize_human_text(str(preset.content_text or ""))
        if normalized_title and normalized_title != str(preset.title):
            preset.title = normalized_title
            updated = True
        if normalized_content_text and normalized_content_text != str(
            preset.content_text
        ):
            preset.content_text = normalized_content_text
            updated = True
        if updated:
            preset.save(update_fields=["title", "content_text", "updated_at"])
    return created_or_updated


def _next_cookie_policy_revision_version() -> int:
    return (
        CookiePolicyRevision.objects.order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1


def _create_cookie_policy_revision(
    *,
    content_text: str,
    is_active: bool,
    is_box_template: bool,
    categories_snapshot: Iterable[Mapping[str, object]] | None = None,
) -> CookiePolicyRevision:
    raw_snapshot = (
        list(categories_snapshot)
        if categories_snapshot is not None
        else snapshot_active_cookie_categories()
    )
    snapshot = normalize_categories_snapshot(raw_snapshot)
    if not snapshot:
        raise ConsentError(
            _("Нельзя опубликовать политику cookie без активных категорий.")
        )

    revision = CookiePolicyRevision.objects.create(
        version=_next_cookie_policy_revision_version(),
        format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
        content_text=content_text,
        categories_snapshot=snapshot,
        is_active=is_active,
        is_box_template=is_box_template,
        published_at=timezone.now() if is_active else None,
    )
    sync_cookie_policy_revision_registry_items(policy_revision=revision)
    if is_active:
        CookiePolicyRevision.objects.exclude(pk=revision.pk).update(is_active=False)
        mark_outdated_cookie_consents(
            policy_revision=revision,
            audit_context={"source": "cookies.publish"},
        )
    return revision


def _find_box_policy_revision_by_variant(
    *,
    variant_code: str,
) -> CookiePolicyRevision | None:
    variant_payload = _resolve_cookie_policy_text_variant(variant_code)
    return (
        CookiePolicyRevision.objects.filter(
            format=CookiePolicyRevision.ContentFormat.PLAIN_TEXT,
            is_box_template=True,
            content_text=variant_payload["content_text"],
        )
        .order_by("-version", "-id")
        .first()
    )


@transaction.atomic
def ensure_default_cookie_policy_variants(
    *,
    using: str = DEFAULT_DB_ALIAS,
) -> dict[str, object]:
    """Function ensure_default_cookie_policy_variants documentation."""

    if not is_cookies_enabled():
        return {"created": False, "reason": "cookies_disabled", "created_variants": []}

    manager = CookiePolicyRevision.objects.using(using)
    active_revision = (
        manager.filter(is_active=True)
        .order_by("-published_at", "-version", "-id")
        .first()
    )

    ensure_default_cookie_categories()
    snapshot = snapshot_active_cookie_categories()
    created_variants: list[str] = []
    revisions_by_variant: dict[str, CookiePolicyRevision] = {}

    for variant_code in (
        COOKIE_POLICY_TEXT_VARIANT_SHORT,
        COOKIE_POLICY_TEXT_VARIANT_FULL,
    ):
        existing = _find_box_policy_revision_by_variant(variant_code=variant_code)
        if existing is not None:
            revisions_by_variant[variant_code] = existing
            continue

        variant_payload = _resolve_cookie_policy_text_variant(variant_code)
        should_activate = (
            active_revision is None and variant_code == COOKIE_POLICY_TEXT_VARIANT_SHORT
        )
        revision = _create_cookie_policy_revision(
            content_text=variant_payload["content_text"],
            is_active=should_activate,
            is_box_template=True,
            categories_snapshot=snapshot,
        )
        revisions_by_variant[variant_code] = revision
        created_variants.append(variant_code)
        if should_activate:
            active_revision = revision

    if active_revision is None:
        active_revision = (
            manager.filter(is_active=True)
            .order_by("-published_at", "-version", "-id")
            .first()
        )

    active_box_variant = None
    if active_revision is not None:
        for variant_code, variant_payload in COOKIE_POLICY_TEXT_VARIANTS.items():
            if active_revision.content_text == variant_payload["content_text"]:
                active_box_variant = variant_code
                break

    short_revision = revisions_by_variant.get(COOKIE_POLICY_TEXT_VARIANT_SHORT)
    full_revision = revisions_by_variant.get(COOKIE_POLICY_TEXT_VARIANT_FULL)
    return {
        "created": bool(created_variants),
        "created_variants": created_variants,
        "active_revision_id": active_revision.pk if active_revision else None,
        "active_revision_version": (
            active_revision.version if active_revision else None
        ),
        "active_box_variant": active_box_variant,
        "short_revision_id": short_revision.pk if short_revision else None,
        "full_revision_id": full_revision.pk if full_revision else None,
    }


@transaction.atomic
def publish_box_cookie_policy_variant(*, variant_code: str) -> CookiePolicyRevision:
    """Function publish_box_cookie_policy_variant documentation."""

    ensure_default_cookie_categories()
    snapshot = snapshot_active_cookie_categories()
    variant_payload = _resolve_cookie_policy_text_variant(variant_code)
    return _create_cookie_policy_revision(
        content_text=variant_payload["content_text"],
        is_active=True,
        is_box_template=True,
        categories_snapshot=snapshot,
    )


@transaction.atomic
def create_custom_cookie_policy_draft_from_variant(
    *,
    variant_code: str,
) -> CookiePolicyRevision:
    """Function create_custom_cookie_policy_draft_from_variant documentation."""

    ensure_default_cookie_categories()
    snapshot = snapshot_active_cookie_categories()
    variant_payload = _resolve_cookie_policy_text_variant(variant_code)
    return _create_cookie_policy_revision(
        content_text=variant_payload["content_text"],
        is_active=False,
        is_box_template=False,
        categories_snapshot=snapshot,
    )


@transaction.atomic
def clone_cookie_policy_revision_as_draft(
    *,
    source_revision: CookiePolicyRevision,
) -> CookiePolicyRevision:
    """Function clone_cookie_policy_revision_as_draft documentation."""

    if source_revision.pk is None:
        raise ConsentError(_("Исходная редакция cookie-policy должна быть сохранена."))
    clone = CookiePolicyRevision.objects.create(
        version=_next_cookie_policy_revision_version(),
        format=source_revision.format,
        content_text=source_revision.content_text,
        content_file=source_revision.content_file,
        categories_snapshot=list(source_revision.categories_snapshot),
        cloned_from=source_revision,
        is_active=False,
        is_box_template=False,
        published_at=None,
    )
    sync_cookie_policy_revision_registry_items(policy_revision=clone)
    log_module_operation(
        operation_code="service.cookies.clone_policy_revision_as_draft",
        source="cookies.services",
        target_model="django_cookies_152fz.CookiePolicyRevision",
        target_id=str(clone.pk),
        summary="Cloned cookie policy revision as draft.",
        payload={"source_revision_id": source_revision.pk},
        result={"version": clone.version},
    )
    return clone


def publish_cookie_policy_revision(
    *,
    content_format: str,
    content_text: str = "",
    content_file=None,
    categories_snapshot: Iterable[Mapping[str, object]] | None = None,
    is_box_template: bool = False,
) -> CookiePolicyRevision:
    """Function publish_cookie_policy_revision documentation."""

    raw_snapshot = (
        list(categories_snapshot)
        if categories_snapshot is not None
        else snapshot_active_cookie_categories()
    )
    snapshot = normalize_categories_snapshot(raw_snapshot)
    if not snapshot:
        raise ConsentError(
            _("Нельзя опубликовать политику cookie без активных категорий.")
        )

    latest_version = (
        CookiePolicyRevision.objects.order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    )
    revision = CookiePolicyRevision.objects.create(
        version=latest_version + 1,
        format=content_format,
        content_text=content_text,
        content_file=content_file,
        categories_snapshot=snapshot,
        is_active=True,
        is_box_template=is_box_template,
        published_at=timezone.now(),
    )
    sync_cookie_policy_revision_registry_items(policy_revision=revision)
    CookiePolicyRevision.objects.exclude(pk=revision.pk).update(is_active=False)
    mark_outdated_cookie_consents(
        policy_revision=revision,
        audit_context={"source": "cookies.publish"},
    )
    log_module_operation(
        operation_code="service.cookies.publish_policy_revision",
        source="cookies.services",
        target_model="django_cookies_152fz.CookiePolicyRevision",
        target_id=str(revision.pk),
        summary="Published cookie policy revision.",
        result={
            "version": revision.version,
            "is_box_template": bool(is_box_template),
            "categories_count": len(snapshot),
        },
    )
    return revision


@transaction.atomic
def bootstrap_default_cookie_policy_revision(
    *,
    using: str = DEFAULT_DB_ALIAS,
) -> dict[str, object]:
    """Function bootstrap_default_cookie_policy_revision documentation."""

    result = ensure_default_cookie_policy_variants(using=using)
    if not result["created"]:
        payload = {
            "created": False,
            "reason": result.get("reason") or "box_variants_already_exist",
            "created_variants": [],
            "active_revision_id": result.get("active_revision_id"),
            "active_revision_version": result.get("active_revision_version"),
            "active_box_variant": result.get("active_box_variant"),
            "short_revision_id": result.get("short_revision_id"),
            "full_revision_id": result.get("full_revision_id"),
        }
        log_module_operation(
            operation_code="service.cookies.bootstrap_default_policy_revision",
            source="cookies.services",
            target_model="django_cookies_152fz.CookiePolicyRevision",
            summary="Bootstrap default cookie policy revisions skipped.",
            payload={"database": using},
            result=payload,
        )
        return payload

    created_variants_raw = result.get("created_variants")
    created_variants_payload = (
        [str(item) for item in created_variants_raw]
        if isinstance(created_variants_raw, list)
        else []
    )
    payload = {
        "created": True,
        "created_variants": created_variants_payload,
        "active_revision_id": result.get("active_revision_id"),
        "active_revision_version": result.get("active_revision_version"),
        "active_box_variant": result.get("active_box_variant"),
        "short_revision_id": result.get("short_revision_id"),
        "full_revision_id": result.get("full_revision_id"),
    }
    log_module_operation(
        operation_code="service.cookies.bootstrap_default_policy_revision",
        source="cookies.services",
        target_model="django_cookies_152fz.CookiePolicyRevision",
        target_id=str(payload.get("active_revision_id") or ""),
        summary="Bootstrapped default cookie policy revisions.",
        payload={"database": using},
        result=payload,
    )
    return payload


def bootstrap_default_cookie_policy_revision_post_migrate(
    sender,
    app_config=None,
    verbosity: int = 1,
    using: str = DEFAULT_DB_ALIAS,
    **kwargs,
) -> dict[str, object]:
    """Function bootstrap_default_cookie_policy_revision_post_migrate documentation."""

    return bootstrap_default_cookie_policy_revision(using=using)


def publish_cookie_banner_revision(
    *,
    is_active: bool = True,
    **revision_fields,
) -> CookieBannerRevision:
    """Function publish_cookie_banner_revision documentation."""

    normalized_fields = _normalize_cookie_banner_revision_fields(
        revision_fields=revision_fields
    )
    latest_version = (
        CookieBannerRevision.objects.order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    )
    revision = CookieBannerRevision.objects.create(
        version=latest_version + 1,
        is_active=is_active,
        published_at=timezone.now() if is_active else None,
        **normalized_fields,
    )
    if is_active:
        CookieBannerRevision.objects.exclude(pk=revision.pk).update(is_active=False)
    log_module_operation(
        operation_code="service.cookies.publish_banner_revision",
        source="cookies.services",
        target_model="django_cookies_152fz.CookieBannerRevision",
        target_id=str(revision.pk),
        summary="Published cookie banner revision.",
        result={"version": revision.version, "is_active": bool(is_active)},
    )
    return revision


@transaction.atomic
def clone_cookie_banner_revision_as_draft(
    *,
    source_revision: CookieBannerRevision,
) -> CookieBannerRevision:
    """Function clone_cookie_banner_revision_as_draft documentation."""

    if source_revision.pk is None:
        raise ConsentError(_("Исходная редакция cookie-баннера должна быть сохранена."))

    clone_fields = {
        "launcher_label": source_revision.launcher_label,
        "eyebrow_text": source_revision.eyebrow_text,
        "title_text": source_revision.title_text,
        "description_text": source_revision.description_text,
        "reconsent_notice_text": source_revision.reconsent_notice_text,
        "reask_notice_text": source_revision.reask_notice_text,
        "accept_all_label": source_revision.accept_all_label,
        "reject_label": source_revision.reject_label,
        "required_only_label": source_revision.required_only_label,
        "customize_label": source_revision.customize_label,
        "custom_section_summary": source_revision.custom_section_summary,
        "required_section_title": source_revision.required_section_title,
        "required_section_empty_text": source_revision.required_section_empty_text,
        "optional_section_title": source_revision.optional_section_title,
        "optional_section_empty_text": source_revision.optional_section_empty_text,
        "save_custom_label": source_revision.save_custom_label,
        "preferences_link_label": source_revision.preferences_link_label,
        "dismiss_label": source_revision.dismiss_label,
        "close_tooltip_text": source_revision.close_tooltip_text,
        "close_aria_label": source_revision.close_aria_label,
        "noscript_text": source_revision.noscript_text,
        "noscript_link_label": source_revision.noscript_link_label,
        "banner_variant": source_revision.banner_variant,
        "consent_ui_variant": source_revision.consent_ui_variant,
        "reconsent_notice_variant": source_revision.reconsent_notice_variant,
        "text_preset_code": source_revision.text_preset_code,
        "mobile_text_preset_code": source_revision.mobile_text_preset_code,
        "layout_variant": source_revision.layout_variant,
        "theme_variant": source_revision.theme_variant,
        "desktop_position": source_revision.desktop_position,
        "mobile_position": source_revision.mobile_position,
        "color_preset": source_revision.color_preset,
        "custom_bg_color": source_revision.custom_bg_color,
        "custom_text_color": source_revision.custom_text_color,
        "custom_primary_color": source_revision.custom_primary_color,
        "custom_primary_text_color": source_revision.custom_primary_text_color,
        "custom_border_color": source_revision.custom_border_color,
        "custom_surface_color": source_revision.custom_surface_color,
        "custom_overlay_color": source_revision.custom_overlay_color,
        "panel_padding_px": source_revision.panel_padding_px,
        "section_gap_px": source_revision.section_gap_px,
        "button_gap_px": source_revision.button_gap_px,
        "overlay_opacity": source_revision.overlay_opacity,
        "show_media_slot": source_revision.show_media_slot,
        "media_slot_type": source_revision.media_slot_type,
        "media_icon_emoji": source_revision.media_icon_emoji,
        "media_image_url": source_revision.media_image_url,
        "media_image_alt": source_revision.media_image_alt,
        "mobile_banner_variant": source_revision.mobile_banner_variant,
        "mobile_consent_ui_variant": source_revision.mobile_consent_ui_variant,
        "mobile_reconsent_notice_variant": source_revision.mobile_reconsent_notice_variant,
        "show_close_control": source_revision.show_close_control,
        "close_control_placement": source_revision.close_control_placement,
        "mobile_close_control_placement": source_revision.mobile_close_control_placement,
        "show_reject_action": source_revision.show_reject_action,
        "mobile_show_close_control": source_revision.mobile_show_close_control,
        "mobile_show_reject_action": source_revision.mobile_show_reject_action,
        "blocking_mode_until_choice": source_revision.blocking_mode_until_choice,
        "mobile_blocking_mode_until_choice": source_revision.mobile_blocking_mode_until_choice,
        "hide_launcher_after_decision": source_revision.hide_launcher_after_decision,
        "mobile_hide_launcher_after_decision": source_revision.mobile_hide_launcher_after_decision,
        "keep_visible_after_accept_all": source_revision.keep_visible_after_accept_all,
        "mobile_keep_visible_after_accept_all": source_revision.mobile_keep_visible_after_accept_all,
        "keep_visible_after_required_only": source_revision.keep_visible_after_required_only,
        "mobile_keep_visible_after_required_only": source_revision.mobile_keep_visible_after_required_only,
        "keep_visible_after_save_custom": source_revision.keep_visible_after_save_custom,
        "mobile_keep_visible_after_save_custom": source_revision.mobile_keep_visible_after_save_custom,
        "hide_for_bots_override": source_revision.hide_for_bots_override,
    }
    clone = CookieBannerRevision.objects.create(
        version=(
            CookieBannerRevision.objects.order_by("-version")
            .values_list("version", flat=True)
            .first()
            or 0
        )
        + 1,
        cloned_from=source_revision,
        is_active=False,
        is_box_template=False,
        published_at=None,
        **clone_fields,
    )
    log_module_operation(
        operation_code="service.cookies.clone_banner_revision_as_draft",
        source="cookies.services",
        target_model="django_cookies_152fz.CookieBannerRevision",
        target_id=str(clone.pk),
        summary="Cloned cookie banner revision as draft.",
        payload={"source_revision_id": source_revision.pk},
        result={"version": clone.version},
    )
    return clone


def get_active_cookie_banner_revision() -> CookieBannerRevision | None:
    """Function get_active_cookie_banner_revision documentation."""

    return (
        CookieBannerRevision.objects.filter(is_active=True)
        .order_by("-published_at", "-version", "-id")
        .first()
    )


def get_cookie_empty_categories_display_options() -> dict[str, object]:
    """Resolve effective display options for empty optional categories block."""

    banner_settings = get_cookie_banner_settings()
    effective_show_empty_category_block = bool(
        banner_settings.get(constants.CONFIG_COOKIE_BANNER_SHOW_EMPTY_CATEGORY_BLOCK, False)
    )
    effective_show_customize_action_without_optional = bool(
        banner_settings.get(
            constants.CONFIG_COOKIE_BANNER_SHOW_CUSTOMIZE_ACTION_WITHOUT_OPTIONAL,
            False,
        )
    )
    effective_empty_category_block_text = str(
        banner_settings.get(constants.CONFIG_COOKIE_BANNER_EMPTY_CATEGORY_BLOCK_TEXT, "")
        or ""
    ).strip()

    admin_settings = (
        CookieAdminSettings.objects.only(
            "show_empty_category_block_override",
            "show_customize_action_without_optional_override",
            "empty_category_block_text_override",
            "updated_at",
        )
        .order_by("-updated_at", "-id")
        .first()
    )
    if admin_settings is None:
        return {
            "show_empty_category_block": effective_show_empty_category_block,
            "show_customize_action_without_optional": (
                effective_show_customize_action_without_optional
            ),
            "empty_category_block_text": effective_empty_category_block_text,
        }

    if admin_settings.show_empty_category_block_override is not None:
        effective_show_empty_category_block = bool(
            admin_settings.show_empty_category_block_override
        )
    if admin_settings.show_customize_action_without_optional_override is not None:
        effective_show_customize_action_without_optional = bool(
            admin_settings.show_customize_action_without_optional_override
        )
    admin_text_override = str(
        admin_settings.empty_category_block_text_override or ""
    ).strip()
    if admin_text_override:
        effective_empty_category_block_text = admin_text_override

    return {
        "show_empty_category_block": effective_show_empty_category_block,
        "show_customize_action_without_optional": (
            effective_show_customize_action_without_optional
        ),
        "empty_category_block_text": effective_empty_category_block_text,
    }


def get_cookie_banner_configuration() -> dict[str, object]:
    """Function get_cookie_banner_configuration documentation."""

    revision = get_active_cookie_banner_revision()
    if revision is None:
        banner_settings = get_cookie_banner_settings()
        (
            text_preset_code,
            text_values,
        ) = _resolve_cookie_banner_text_preset(
            preset_code=banner_settings[constants.CONFIG_COOKIE_BANNER_TEXT_PRESET]
        )
        visual_tokens = _build_cookie_banner_visual_tokens(
            color_preset=str(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["color_preset"]
            ),
            custom_bg_color="",
            custom_text_color="",
            custom_primary_color="",
            custom_primary_text_color="",
            custom_border_color="",
            custom_surface_color="",
            custom_overlay_color="",
            panel_padding_px=int(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["panel_padding_px"]
            ),
            section_gap_px=int(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["section_gap_px"]
            ),
            button_gap_px=int(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["button_gap_px"]
            ),
            overlay_opacity=int(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["overlay_opacity"]
            ),
        )
        return {
            "revision_id": None,
            "revision_version": None,
            "is_published": False,
            "published_at": None,
            "is_box_template": False,
            **dict(DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION),
            **dict(DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR),
            **dict(text_values),
            "text_preset_code": text_preset_code,
            "mobile_text_preset_code": "",
            "effective_mobile_text_preset_code": text_preset_code,
            "banner_variant": banner_settings[constants.CONFIG_COOKIE_BANNER_VARIANT],
            "consent_ui_variant": banner_settings[
                constants.CONFIG_COOKIE_BANNER_CONSENT_UI_VARIANT
            ],
            "reconsent_notice_variant": banner_settings[
                constants.CONFIG_COOKIE_BANNER_RECONSENT_NOTICE_VARIANT
            ],
            "mobile_banner_variant": "",
            "mobile_consent_ui_variant": "",
            "mobile_reconsent_notice_variant": "",
            "mobile_close_control_placement": "",
            "mobile_show_close_control": None,
            "mobile_show_reject_action": None,
            "mobile_blocking_mode_until_choice": None,
            "mobile_hide_launcher_after_decision": None,
            "mobile_keep_visible_after_accept_all": None,
            "mobile_keep_visible_after_required_only": None,
            "mobile_keep_visible_after_save_custom": None,
            "hide_for_bots_override": None,
            "color_preset": visual_tokens["color_preset"],
            "custom_bg_color": "",
            "custom_text_color": "",
            "custom_primary_color": "",
            "custom_primary_text_color": "",
            "custom_border_color": "",
            "custom_surface_color": "",
            "custom_overlay_color": "",
            "panel_padding_px": _normalize_int_range(
                visual_tokens["panel_padding_px"], minimum=8, maximum=48, fallback=16
            ),
            "section_gap_px": _normalize_int_range(
                visual_tokens["section_gap_px"], minimum=4, maximum=32, fallback=12
            ),
            "button_gap_px": _normalize_int_range(
                visual_tokens["button_gap_px"], minimum=4, maximum=24, fallback=10
            ),
            "overlay_opacity": _normalize_int_range(
                visual_tokens["overlay_opacity"], minimum=0, maximum=85, fallback=48
            ),
            "visual_style": str(visual_tokens["inline_style"]),
            "show_media_slot": bool(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["show_media_slot"]
            ),
            "media_slot_type": str(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_slot_type"]
            ),
            "media_icon_emoji": str(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_icon_emoji"]
            ),
            "media_image_url": "",
            "media_image_alt": str(
                DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_image_alt"]
            ),
            "mobile_overrides": {
                "text_values": dict(text_values),
                "banner_variant": banner_settings[
                    constants.CONFIG_COOKIE_BANNER_VARIANT
                ],
                "consent_ui_variant": banner_settings[
                    constants.CONFIG_COOKIE_BANNER_CONSENT_UI_VARIANT
                ],
                "reconsent_notice_variant": banner_settings[
                    constants.CONFIG_COOKIE_BANNER_RECONSENT_NOTICE_VARIANT
                ],
                "close_control_placement": DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
                    "close_control_placement"
                ],
                "show_close_control": bool(
                    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["show_close_control"]
                ),
                "show_reject_action": bool(
                    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["show_reject_action"]
                ),
                "blocking_mode_until_choice": bool(
                    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
                        "blocking_mode_until_choice"
                    ]
                ),
                "hide_launcher_after_decision": bool(
                    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
                        "hide_launcher_after_decision"
                    ]
                ),
                "keep_visible_after_accept_all": bool(
                    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
                        "keep_visible_after_accept_all"
                    ]
                ),
                "keep_visible_after_required_only": bool(
                    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
                        "keep_visible_after_required_only"
                    ]
                ),
                "keep_visible_after_save_custom": bool(
                    DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
                        "keep_visible_after_save_custom"
                    ]
                ),
            },
            "visual_tokens": visual_tokens,
            **get_cookie_banner_variant_contract(),
        }
    return serialize_cookie_banner_revision(revision=revision)


def serialize_cookie_banner_revision(
    *,
    revision: CookieBannerRevision,
) -> dict[str, object]:
    """Function serialize_cookie_banner_revision documentation."""

    banner_variant = _normalize_choice_or_fallback(
        value=revision.banner_variant,
        allowed=frozenset(constants.COOKIE_BANNER_VARIANTS),
        fallback=_resolve_banner_variant_from_legacy_layout(revision.layout_variant),
    )
    consent_ui_variant = _normalize_choice_or_fallback(
        value=revision.consent_ui_variant,
        allowed=frozenset(constants.COOKIE_BANNER_CONSENT_UI_VARIANTS),
        fallback=_resolve_consent_ui_variant_from_legacy_layout(
            revision.layout_variant
        ),
    )
    reconsent_notice_variant = _normalize_choice_or_fallback(
        value=revision.reconsent_notice_variant,
        allowed=frozenset(constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANTS),
        fallback=_resolve_reconsent_notice_variant_from_legacy_theme(
            revision.theme_variant
        ),
    )
    text_preset_code, text_preset_values = _resolve_cookie_banner_text_preset(
        preset_code=revision.text_preset_code
    )
    mobile_text_preset_code = _normalize_mobile_text_preset_code(
        revision.mobile_text_preset_code
    )
    effective_mobile_text_preset_code = mobile_text_preset_code or text_preset_code
    _, effective_mobile_text_values = _resolve_cookie_banner_text_preset(
        preset_code=effective_mobile_text_preset_code
    )
    resolved_text_values = (
        text_preset_values if bool(revision.is_box_template) else None
    )
    mobile_banner_variant = _normalize_choice_or_empty(
        value=revision.mobile_banner_variant,
        allowed=frozenset(constants.COOKIE_BANNER_VARIANTS),
    )
    mobile_consent_ui_variant = _normalize_choice_or_empty(
        value=revision.mobile_consent_ui_variant,
        allowed=frozenset(constants.COOKIE_BANNER_CONSENT_UI_VARIANTS),
    )
    mobile_reconsent_notice_variant = _normalize_choice_or_empty(
        value=revision.mobile_reconsent_notice_variant,
        allowed=frozenset(constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANTS),
    )
    mobile_close_control_placement = _normalize_choice_or_empty(
        value=revision.mobile_close_control_placement,
        allowed=frozenset(
            {
                CookieBannerRevision.CloseControlPlacement.LEFT,
                CookieBannerRevision.CloseControlPlacement.RIGHT,
            }
        ),
    )
    visual_tokens = _build_cookie_banner_visual_tokens(
        color_preset=str(revision.color_preset or "light"),
        custom_bg_color=revision.custom_bg_color,
        custom_text_color=revision.custom_text_color,
        custom_primary_color=revision.custom_primary_color,
        custom_primary_text_color=revision.custom_primary_text_color,
        custom_border_color=revision.custom_border_color,
        custom_surface_color=revision.custom_surface_color,
        custom_overlay_color=revision.custom_overlay_color,
        panel_padding_px=revision.panel_padding_px,
        section_gap_px=revision.section_gap_px,
        button_gap_px=revision.button_gap_px,
        overlay_opacity=revision.overlay_opacity,
    )

    return {
        "revision_id": revision.pk,
        "revision_version": revision.version,
        "is_published": bool(revision.is_active),
        "published_at": revision.published_at,
        "is_box_template": bool(revision.is_box_template),
        "text_preset_code": text_preset_code,
        "mobile_text_preset_code": mobile_text_preset_code,
        "effective_mobile_text_preset_code": effective_mobile_text_preset_code,
        "launcher_label": (
            str(resolved_text_values["launcher_label"])
            if resolved_text_values is not None
            else revision.launcher_label
        ),
        "eyebrow_text": (
            str(resolved_text_values["eyebrow_text"])
            if resolved_text_values is not None
            else revision.eyebrow_text
        ),
        "title_text": (
            str(resolved_text_values["title_text"])
            if resolved_text_values is not None
            else revision.title_text
        ),
        "description_text": (
            str(resolved_text_values["description_text"])
            if resolved_text_values is not None
            else revision.description_text
        ),
        "reconsent_notice_text": (
            str(resolved_text_values["reconsent_notice_text"])
            if resolved_text_values is not None
            else revision.reconsent_notice_text
        ),
        "reask_notice_text": (
            str(resolved_text_values["reask_notice_text"])
            if resolved_text_values is not None
            else revision.reask_notice_text
        ),
        "accept_all_label": (
            str(resolved_text_values["accept_all_label"])
            if resolved_text_values is not None
            else revision.accept_all_label
        ),
        "reject_label": (
            str(resolved_text_values["reject_label"])
            if resolved_text_values is not None
            else revision.reject_label
        ),
        "required_only_label": (
            str(resolved_text_values["required_only_label"])
            if resolved_text_values is not None
            else revision.required_only_label
        ),
        "customize_label": (
            str(resolved_text_values["customize_label"])
            if resolved_text_values is not None
            else revision.customize_label
        ),
        "custom_section_summary": (
            str(resolved_text_values["custom_section_summary"])
            if resolved_text_values is not None
            else revision.custom_section_summary
        ),
        "required_section_title": (
            str(resolved_text_values["required_section_title"])
            if resolved_text_values is not None
            else revision.required_section_title
        ),
        "required_section_empty_text": (
            str(resolved_text_values["required_section_empty_text"])
            if resolved_text_values is not None
            else revision.required_section_empty_text
        ),
        "optional_section_title": (
            str(resolved_text_values["optional_section_title"])
            if resolved_text_values is not None
            else revision.optional_section_title
        ),
        "optional_section_empty_text": (
            str(resolved_text_values["optional_section_empty_text"])
            if resolved_text_values is not None
            else revision.optional_section_empty_text
        ),
        "save_custom_label": (
            str(resolved_text_values["save_custom_label"])
            if resolved_text_values is not None
            else revision.save_custom_label
        ),
        "preferences_link_label": (
            str(resolved_text_values["preferences_link_label"])
            if resolved_text_values is not None
            else revision.preferences_link_label
        ),
        "dismiss_label": (
            str(resolved_text_values["dismiss_label"])
            if resolved_text_values is not None
            else revision.dismiss_label
        ),
        "close_tooltip_text": revision.close_tooltip_text,
        "close_aria_label": revision.close_aria_label,
        "noscript_text": (
            str(resolved_text_values["noscript_text"])
            if resolved_text_values is not None
            else revision.noscript_text
        ),
        "noscript_link_label": (
            str(resolved_text_values["noscript_link_label"])
            if resolved_text_values is not None
            else revision.noscript_link_label
        ),
        "banner_variant": banner_variant,
        "consent_ui_variant": consent_ui_variant,
        "reconsent_notice_variant": reconsent_notice_variant,
        "layout_variant": revision.layout_variant,
        "theme_variant": revision.theme_variant,
        "desktop_position": revision.desktop_position,
        "mobile_position": revision.mobile_position,
        "color_preset": visual_tokens["color_preset"],
        "custom_bg_color": revision.custom_bg_color,
        "custom_text_color": revision.custom_text_color,
        "custom_primary_color": revision.custom_primary_color,
        "custom_primary_text_color": revision.custom_primary_text_color,
        "custom_border_color": revision.custom_border_color,
        "custom_surface_color": revision.custom_surface_color,
        "custom_overlay_color": revision.custom_overlay_color,
        "panel_padding_px": _normalize_int_range(
            visual_tokens["panel_padding_px"], minimum=8, maximum=48, fallback=16
        ),
        "section_gap_px": _normalize_int_range(
            visual_tokens["section_gap_px"], minimum=4, maximum=32, fallback=12
        ),
        "button_gap_px": _normalize_int_range(
            visual_tokens["button_gap_px"], minimum=4, maximum=24, fallback=10
        ),
        "overlay_opacity": _normalize_int_range(
            visual_tokens["overlay_opacity"], minimum=0, maximum=85, fallback=48
        ),
        "visual_style": str(visual_tokens["inline_style"]),
        "show_media_slot": bool(revision.show_media_slot),
        "media_slot_type": str(revision.media_slot_type or "icon"),
        "media_icon_emoji": str(revision.media_icon_emoji or ""),
        "media_image_url": str(revision.media_image_url or ""),
        "media_image_alt": str(revision.media_image_alt or ""),
        "mobile_banner_variant": mobile_banner_variant,
        "mobile_consent_ui_variant": mobile_consent_ui_variant,
        "mobile_reconsent_notice_variant": mobile_reconsent_notice_variant,
        "show_close_control": bool(revision.show_close_control),
        "close_control_placement": str(revision.close_control_placement),
        "mobile_close_control_placement": mobile_close_control_placement,
        "show_reject_action": bool(revision.show_reject_action),
        "mobile_show_close_control": revision.mobile_show_close_control,
        "mobile_show_reject_action": revision.mobile_show_reject_action,
        "blocking_mode_until_choice": bool(revision.blocking_mode_until_choice),
        "mobile_blocking_mode_until_choice": (
            revision.mobile_blocking_mode_until_choice
        ),
        "hide_launcher_after_decision": bool(revision.hide_launcher_after_decision),
        "mobile_hide_launcher_after_decision": (
            revision.mobile_hide_launcher_after_decision
        ),
        "keep_visible_after_accept_all": bool(revision.keep_visible_after_accept_all),
        "mobile_keep_visible_after_accept_all": (
            revision.mobile_keep_visible_after_accept_all
        ),
        "keep_visible_after_required_only": bool(
            revision.keep_visible_after_required_only
        ),
        "mobile_keep_visible_after_required_only": (
            revision.mobile_keep_visible_after_required_only
        ),
        "keep_visible_after_save_custom": bool(revision.keep_visible_after_save_custom),
        "mobile_keep_visible_after_save_custom": (
            revision.mobile_keep_visible_after_save_custom
        ),
        "hide_for_bots_override": revision.hide_for_bots_override,
        "mobile_overrides": {
            "text_values": dict(effective_mobile_text_values),
            "banner_variant": mobile_banner_variant or banner_variant,
            "consent_ui_variant": (mobile_consent_ui_variant or consent_ui_variant),
            "reconsent_notice_variant": (
                mobile_reconsent_notice_variant or reconsent_notice_variant
            ),
            "close_control_placement": (
                mobile_close_control_placement or str(revision.close_control_placement)
            ),
            "show_close_control": _resolve_mobile_bool_override(
                revision.mobile_show_close_control,
                bool(revision.show_close_control),
            ),
            "show_reject_action": _resolve_mobile_bool_override(
                revision.mobile_show_reject_action,
                bool(revision.show_reject_action),
            ),
            "blocking_mode_until_choice": _resolve_mobile_bool_override(
                revision.mobile_blocking_mode_until_choice,
                bool(revision.blocking_mode_until_choice),
            ),
            "hide_launcher_after_decision": _resolve_mobile_bool_override(
                revision.mobile_hide_launcher_after_decision,
                bool(revision.hide_launcher_after_decision),
            ),
            "keep_visible_after_accept_all": _resolve_mobile_bool_override(
                revision.mobile_keep_visible_after_accept_all,
                bool(revision.keep_visible_after_accept_all),
            ),
            "keep_visible_after_required_only": _resolve_mobile_bool_override(
                revision.mobile_keep_visible_after_required_only,
                bool(revision.keep_visible_after_required_only),
            ),
            "keep_visible_after_save_custom": _resolve_mobile_bool_override(
                revision.mobile_keep_visible_after_save_custom,
                bool(revision.keep_visible_after_save_custom),
            ),
        },
        "visual_tokens": visual_tokens,
        **get_cookie_banner_variant_contract(),
    }


def get_cookie_banner_text_presets() -> dict[str, dict[str, Any]]:
    """Function get_cookie_banner_text_presets documentation."""

    ensure_default_cookie_banner_text_presets()
    presets = {
        preset_code: dict(preset_values)
        for preset_code, preset_values in COOKIE_BANNER_TEXT_PRESETS.items()
    }
    for db_preset in CookieBannerTextPreset.objects.filter(is_active=True):
        presets[db_preset.code] = {
            "launcher_label": db_preset.launcher_label,
            "eyebrow_text": db_preset.eyebrow_text,
            "title_text": db_preset.title_text,
            "description_text": db_preset.description_text,
            "reconsent_notice_text": db_preset.reconsent_notice_text,
            "reask_notice_text": db_preset.reask_notice_text,
            "accept_all_label": db_preset.accept_all_label,
            "reject_label": db_preset.reject_label,
            "required_only_label": db_preset.required_only_label,
            "customize_label": db_preset.customize_label,
            "custom_section_summary": db_preset.custom_section_summary,
            "required_section_title": db_preset.required_section_title,
            "required_section_empty_text": db_preset.required_section_empty_text,
            "optional_section_title": db_preset.optional_section_title,
            "optional_section_empty_text": db_preset.optional_section_empty_text,
            "save_custom_label": db_preset.save_custom_label,
            "preferences_link_label": db_preset.preferences_link_label,
            "dismiss_label": db_preset.dismiss_label,
            "noscript_text": db_preset.noscript_text,
            "noscript_link_label": db_preset.noscript_link_label,
        }
    return presets


def ensure_default_cookie_banner_text_presets() -> list[CookieBannerTextPreset]:
    """Function ensure_default_cookie_banner_text_presets documentation."""

    created_or_updated: list[CookieBannerTextPreset] = []
    for preset_code, preset_values in COOKIE_BANNER_TEXT_PRESETS.items():
        normalized_text_values = {
            field_name: _normalize_human_text(str(preset_values[field_name]))
            for field_name in COOKIE_BANNER_TEXT_FIELDS
        }
        defaults = {
            "title": f"Коробочная заготовка {preset_code}",
            **normalized_text_values,
            "is_box_template": True,
            "is_active": True,
        }
        preset, created = CookieBannerTextPreset.objects.get_or_create(
            code=preset_code,
            defaults=defaults,
        )
        if not created:
            updated = False
            normalized_title = _normalize_human_text(str(preset.title or ""))
            if not normalized_title:
                preset.title = defaults["title"]
                updated = True
            elif normalized_title != str(preset.title):
                preset.title = normalized_title
                updated = True
            for field_name in COOKIE_BANNER_TEXT_FIELDS:
                current_value = str(getattr(preset, field_name) or "")
                normalized_value = _normalize_human_text(current_value)
                default_value = defaults[field_name]
                if not normalized_value:
                    setattr(preset, field_name, default_value)
                    updated = True
                elif normalized_value != current_value:
                    setattr(preset, field_name, normalized_value)
                    updated = True
            if not preset.is_active:
                preset.is_active = True
                updated = True
            if updated:
                preset.save()
        created_or_updated.append(preset)
    for preset in CookieBannerTextPreset.objects.all().order_by("id"):
        updated = False
        normalized_title = _normalize_human_text(str(preset.title or ""))
        if normalized_title and normalized_title != str(preset.title):
            preset.title = normalized_title
            updated = True
        for field_name in COOKIE_BANNER_TEXT_FIELDS:
            current_value = str(getattr(preset, field_name) or "")
            normalized_value = _normalize_human_text(current_value)
            if normalized_value and normalized_value != current_value:
                setattr(preset, field_name, normalized_value)
                updated = True
        if updated:
            preset.save()
    return created_or_updated


def get_cookie_banner_text_field_contract() -> dict[str, tuple[str, ...]]:
    """Function get_cookie_banner_text_field_contract documentation."""

    return {
        "editable_fields": COOKIE_BANNER_EDITABLE_TEXT_FIELDS,
        "protected_fields": COOKIE_BANNER_PROTECTED_TEXT_FIELDS,
    }


def get_cookie_banner_variant_contract() -> dict[str, object]:
    """Function get_cookie_banner_variant_contract documentation."""

    return {
        "variant_contract_version": "2.2",
        "variant_css_hooks": {
            "root": "dz152fz-cookie-banner",
            "panel": "dz152fz-cookie-banner__panel",
            "notice": "dz152fz-cookie-banner__notice",
            "custom_root": "dz152fz-cookie-banner__custom",
        },
        "variant_data_attributes": {
            "banner_variant": "data-cookie-banner-variant",
            "consent_ui_variant": "data-cookie-banner-consent-ui",
            "reconsent_notice_variant": ("data-cookie-banner-reconsent-variant"),
            "text_preset_code": "data-cookie-banner-text-preset",
            "mobile_text_preset_code": "data-cookie-banner-mobile-text-preset",
            "desktop_position": "data-cookie-banner-desktop-position",
            "mobile_position": "data-cookie-banner-mobile-position",
            "mobile_banner_variant": "data-cookie-banner-mobile-variant",
            "mobile_consent_ui_variant": "data-cookie-banner-mobile-consent-ui",
            "mobile_reconsent_notice_variant": (
                "data-cookie-banner-mobile-reconsent-variant"
            ),
        },
        "text_field_contract": get_cookie_banner_text_field_contract(),
    }


@transaction.atomic
def bootstrap_cookie_banner_revision(
    *,
    using: str = DEFAULT_DB_ALIAS,
) -> dict[str, object]:
    """Function bootstrap_cookie_banner_revision documentation."""

    if not is_cookies_enabled():
        return {"created": False, "reason": "cookies_disabled"}

    banner_settings = get_cookie_banner_settings()
    if not bool(
        banner_settings[constants.CONFIG_COOKIE_BANNER_BOOTSTRAP_INITIAL_REVISION]
    ):
        return {"created": False, "reason": "bootstrap_disabled"}

    manager = CookieBannerRevision.objects.using(using)
    if manager.exists():
        return {"created": False, "reason": "already_exists"}

    revision = manager.create(
        version=1,
        is_active=True,
        is_box_template=True,
        published_at=timezone.now(),
        **_normalize_cookie_banner_revision_fields(
            revision_fields={
                "text_preset_code": banner_settings[
                    constants.CONFIG_COOKIE_BANNER_TEXT_PRESET
                ],
                "banner_variant": banner_settings[
                    constants.CONFIG_COOKIE_BANNER_VARIANT
                ],
                "consent_ui_variant": banner_settings[
                    constants.CONFIG_COOKIE_BANNER_CONSENT_UI_VARIANT
                ],
                "reconsent_notice_variant": banner_settings[
                    constants.CONFIG_COOKIE_BANNER_RECONSENT_NOTICE_VARIANT
                ],
            }
        ),
    )
    return {
        "created": True,
        "revision_id": revision.pk,
        "revision_version": revision.version,
        "text_preset_code": revision.text_preset_code,
    }


def bootstrap_cookie_banner_revision_post_migrate(
    sender,
    app_config=None,
    verbosity: int = 1,
    using: str = DEFAULT_DB_ALIAS,
    **kwargs,
) -> dict[str, object]:
    """Function bootstrap_cookie_banner_revision_post_migrate documentation."""

    return bootstrap_cookie_banner_revision(using=using)


def _normalize_cookie_banner_revision_fields(
    *,
    revision_fields: Mapping[str, object],
) -> dict[str, object]:
    fields = dict(revision_fields)
    text_preset_code, text_preset_values = _resolve_cookie_banner_text_preset(
        preset_code=fields.get("text_preset_code")
    )
    fields["text_preset_code"] = text_preset_code
    fields["mobile_text_preset_code"] = _normalize_mobile_text_preset_code(
        fields.get("mobile_text_preset_code")
    )

    for field_name in COOKIE_BANNER_TEXT_FIELDS:
        value = fields.get(field_name)
        if value is None or str(value).strip() == "":
            fields[field_name] = text_preset_values[field_name]
    for field_name in ("close_tooltip_text", "close_aria_label"):
        value = fields.get(field_name)
        if value is None or str(value).strip() == "":
            fields[field_name] = DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[field_name]
        else:
            fields[field_name] = str(value).strip()

    if bool(fields.get("is_box_template")):
        for field_name in COOKIE_BANNER_PROTECTED_TEXT_FIELDS:
            fields[field_name] = text_preset_values[field_name]
    fields["show_close_control"] = bool(
        fields.get(
            "show_close_control",
            DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["show_close_control"],
        )
    )
    fields["close_control_placement"] = _normalize_choice_or_fallback(
        value=fields.get("close_control_placement"),
        allowed=frozenset(
            {
                CookieBannerRevision.CloseControlPlacement.LEFT,
                CookieBannerRevision.CloseControlPlacement.RIGHT,
            }
        ),
        fallback=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["close_control_placement"],
    )
    fields["mobile_close_control_placement"] = _normalize_choice_or_empty(
        value=fields.get("mobile_close_control_placement"),
        allowed=frozenset(
            {
                CookieBannerRevision.CloseControlPlacement.LEFT,
                CookieBannerRevision.CloseControlPlacement.RIGHT,
            }
        ),
    )
    fields["show_reject_action"] = bool(
        fields.get(
            "show_reject_action",
            DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["show_reject_action"],
        )
    )
    fields["blocking_mode_until_choice"] = bool(
        fields.get(
            "blocking_mode_until_choice",
            DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["blocking_mode_until_choice"],
        )
    )
    fields["hide_launcher_after_decision"] = bool(
        fields.get(
            "hide_launcher_after_decision",
            DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["hide_launcher_after_decision"],
        )
    )
    for field_name in (
        "keep_visible_after_accept_all",
        "keep_visible_after_required_only",
        "keep_visible_after_save_custom",
    ):
        fields[field_name] = bool(
            fields.get(
                field_name,
                DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[field_name],
            )
        )
    for field_name in (
        "mobile_show_close_control",
        "mobile_show_reject_action",
        "mobile_blocking_mode_until_choice",
        "mobile_hide_launcher_after_decision",
        "mobile_keep_visible_after_accept_all",
        "mobile_keep_visible_after_required_only",
        "mobile_keep_visible_after_save_custom",
    ):
        value = fields.get(field_name)
        if value in (None, ""):
            fields[field_name] = None
            continue
        fields[field_name] = bool(value)
    hide_for_bots_override_value = fields.get("hide_for_bots_override")
    if hide_for_bots_override_value in (None, ""):
        fields["hide_for_bots_override"] = None
    else:
        fields["hide_for_bots_override"] = bool(hide_for_bots_override_value)

    fields["banner_variant"] = _normalize_choice_or_fallback(
        value=fields.get("banner_variant"),
        allowed=frozenset(constants.COOKIE_BANNER_VARIANTS),
        fallback=_resolve_banner_variant_from_legacy_layout(
            fields.get("layout_variant")
        ),
    )
    fields["consent_ui_variant"] = _normalize_choice_or_fallback(
        value=fields.get("consent_ui_variant"),
        allowed=frozenset(constants.COOKIE_BANNER_CONSENT_UI_VARIANTS),
        fallback=_resolve_consent_ui_variant_from_legacy_layout(
            fields.get("layout_variant")
        ),
    )
    fields["reconsent_notice_variant"] = _normalize_choice_or_fallback(
        value=fields.get("reconsent_notice_variant"),
        allowed=frozenset(constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANTS),
        fallback=_resolve_reconsent_notice_variant_from_legacy_theme(
            fields.get("theme_variant")
        ),
    )
    fields["mobile_banner_variant"] = _normalize_choice_or_empty(
        value=fields.get("mobile_banner_variant"),
        allowed=frozenset(constants.COOKIE_BANNER_VARIANTS),
    )
    fields["mobile_consent_ui_variant"] = _normalize_choice_or_empty(
        value=fields.get("mobile_consent_ui_variant"),
        allowed=frozenset(constants.COOKIE_BANNER_CONSENT_UI_VARIANTS),
    )
    fields["mobile_reconsent_notice_variant"] = _normalize_choice_or_empty(
        value=fields.get("mobile_reconsent_notice_variant"),
        allowed=frozenset(constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANTS),
    )
    fields["desktop_position"] = _normalize_choice_or_fallback(
        value=fields.get("desktop_position"),
        allowed=frozenset(
            {
                CookieBannerRevision.DesktopPosition.BOTTOM_RIGHT,
                CookieBannerRevision.DesktopPosition.BOTTOM_LEFT,
                CookieBannerRevision.DesktopPosition.CENTER,
                CookieBannerRevision.DesktopPosition.BOTTOM_FULLWIDTH,
            }
        ),
        fallback=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["desktop_position"],
    )
    fields["mobile_position"] = _normalize_choice_or_fallback(
        value=fields.get("mobile_position"),
        allowed=frozenset(
            {
                CookieBannerRevision.MobilePosition.BOTTOM,
                CookieBannerRevision.MobilePosition.TOP,
                CookieBannerRevision.MobilePosition.CENTER,
                CookieBannerRevision.MobilePosition.BOTTOM_FULLWIDTH,
            }
        ),
        fallback=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["mobile_position"],
    )
    fields["color_preset"] = _normalize_choice_or_fallback(
        value=fields.get("color_preset"),
        allowed=frozenset({"light", "contrast", "forest", "sand"}),
        fallback=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["color_preset"],
    )
    for color_field in (
        "custom_bg_color",
        "custom_text_color",
        "custom_primary_color",
        "custom_primary_text_color",
        "custom_border_color",
        "custom_surface_color",
        "custom_overlay_color",
    ):
        fields[color_field] = _normalize_hex_color(fields.get(color_field))
    fields["panel_padding_px"] = _normalize_int_range(
        fields.get("panel_padding_px"),
        minimum=8,
        maximum=48,
        fallback=int(DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["panel_padding_px"]),
    )
    fields["section_gap_px"] = _normalize_int_range(
        fields.get("section_gap_px"),
        minimum=4,
        maximum=32,
        fallback=int(DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["section_gap_px"]),
    )
    fields["button_gap_px"] = _normalize_int_range(
        fields.get("button_gap_px"),
        minimum=4,
        maximum=24,
        fallback=int(DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["button_gap_px"]),
    )
    fields["overlay_opacity"] = _normalize_int_range(
        fields.get("overlay_opacity"),
        minimum=0,
        maximum=85,
        fallback=int(DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["overlay_opacity"]),
    )
    fields["show_media_slot"] = bool(
        fields.get(
            "show_media_slot",
            DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["show_media_slot"],
        )
    )
    media_slot_type = str(
        fields.get(
            "media_slot_type",
            DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_slot_type"],
        )
        or ""
    ).strip()
    if media_slot_type not in {"icon", "image"}:
        media_slot_type = "icon"
    fields["media_slot_type"] = media_slot_type
    fields["media_icon_emoji"] = str(fields.get("media_icon_emoji") or "").strip()
    media_image_url = str(fields.get("media_image_url") or "").strip()
    fields["media_image_url"] = media_image_url
    fields["media_image_alt"] = str(
        fields.get("media_image_alt")
        or DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_image_alt"]
    ).strip()
    return fields


def _resolve_cookie_banner_text_preset(
    *,
    preset_code: object,
) -> tuple[str, dict[str, str]]:
    normalized_code = str(preset_code or "").strip().lower()
    presets = get_cookie_banner_text_presets()
    if normalized_code == constants.COOKIE_BANNER_TEXT_PRESET_AUTO:
        normalized_code = _preferred_cookie_banner_preset_code_for_language(
            get_language() or ""
        )
    if normalized_code not in presets:
        preferred_code = _preferred_cookie_banner_preset_code_for_language(
            get_language() or ""
        )
        normalized_code = (
            preferred_code
            if preferred_code in presets
            else constants.COOKIE_BANNER_TEXT_PRESET_RU_BALANCED
        )
    return normalized_code, dict(presets[normalized_code])


def _resolve_banner_variant_from_legacy_layout(layout_variant: object) -> str:
    if str(layout_variant or "").strip() == CookieBannerRevision.LayoutVariant.WIDE:
        return constants.COOKIE_BANNER_VARIANT_MODAL
    return constants.COOKIE_BANNER_VARIANT_CARD


def _resolve_consent_ui_variant_from_legacy_layout(layout_variant: object) -> str:
    if str(layout_variant or "").strip() == CookieBannerRevision.LayoutVariant.WIDE:
        return constants.COOKIE_BANNER_CONSENT_UI_VARIANT_PANEL
    return constants.COOKIE_BANNER_CONSENT_UI_VARIANT_INLINE


def _resolve_reconsent_notice_variant_from_legacy_theme(theme_variant: object) -> str:
    if str(theme_variant or "").strip() == CookieBannerRevision.ThemeVariant.CONTRAST:
        return constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_ALERT
    return constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_INLINE


def _normalize_choice_or_fallback(
    *,
    value: object,
    allowed: frozenset[str],
    fallback: str,
) -> str:
    normalized = str(value or "").strip()
    if normalized in allowed:
        return normalized
    return fallback


def _normalize_choice_or_empty(*, value: object, allowed: frozenset[str]) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized in allowed:
        return normalized
    return ""


def _resolve_mobile_bool_override(value: object, fallback: bool) -> bool:
    if value is None:
        return fallback
    return bool(value)


def _normalize_int_range(
    value: object, *, minimum: int, maximum: int, fallback: int
) -> int:
    try:
        if isinstance(value, bool):
            raise TypeError("bool is not supported")
        if isinstance(value, int):
            number = value
        else:
            number = int(str(value))
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def _normalize_hex_color(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if re.fullmatch(r"#[0-9a-f]{6}", normalized):
        return normalized
    return ""


def _coerce_object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _coerce_object_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _build_cookie_banner_visual_tokens(
    *,
    color_preset: str,
    custom_bg_color: object,
    custom_text_color: object,
    custom_primary_color: object,
    custom_primary_text_color: object,
    custom_border_color: object,
    custom_surface_color: object,
    custom_overlay_color: object,
    panel_padding_px: object,
    section_gap_px: object,
    button_gap_px: object,
    overlay_opacity: object,
) -> dict[str, object]:
    preset = str(color_preset or "light").strip().lower()
    if preset not in {"light", "contrast", "forest", "sand"}:
        preset = "light"
    padding = _normalize_int_range(panel_padding_px, minimum=8, maximum=48, fallback=20)
    section_gap = _normalize_int_range(
        section_gap_px, minimum=4, maximum=32, fallback=14
    )
    button_gap = _normalize_int_range(button_gap_px, minimum=4, maximum=24, fallback=10)
    opacity = _normalize_int_range(overlay_opacity, minimum=0, maximum=85, fallback=55)

    style_parts = [
        f"--dz152fz-cookie-banner-panel-padding:{padding}px",
        f"--dz152fz-cookie-banner-section-gap:{section_gap}px",
        f"--dz152fz-cookie-banner-button-gap:{button_gap}px",
        f"--dz152fz-cookie-banner-overlay-opacity:{opacity}",
    ]
    color_map = {
        "--dz152fz-cookie-banner-bg": _normalize_hex_color(custom_bg_color),
        "--dz152fz-cookie-banner-text": _normalize_hex_color(custom_text_color),
        "--dz152fz-cookie-banner-primary": _normalize_hex_color(custom_primary_color),
        "--dz152fz-cookie-banner-primary-text": _normalize_hex_color(
            custom_primary_text_color
        ),
        "--dz152fz-cookie-banner-border": _normalize_hex_color(custom_border_color),
        "--dz152fz-cookie-banner-surface": _normalize_hex_color(custom_surface_color),
        "--dz152fz-cookie-banner-overlay": _normalize_hex_color(custom_overlay_color),
    }
    for css_var, css_value in color_map.items():
        if css_value:
            style_parts.append(f"{css_var}:{css_value}")

    return {
        "color_preset": preset,
        "panel_padding_px": padding,
        "section_gap_px": section_gap,
        "button_gap_px": button_gap,
        "overlay_opacity": opacity,
        "inline_style": ";".join(style_parts),
    }


def _normalize_mobile_text_preset_code(value: object) -> str:
    normalized_code = str(value or "").strip().lower()
    if not normalized_code:
        return ""
    presets = get_cookie_banner_text_presets()
    if normalized_code in presets:
        return normalized_code
    return ""


def get_cookie_runtime_dom_event_contract() -> dict[str, object]:
    """Function get_cookie_runtime_dom_event_contract documentation."""

    # Comment
    return {
        "version": str(COOKIE_RUNTIME_DOM_EVENT_CONTRACT["version"]),
        "namespace": str(COOKIE_RUNTIME_DOM_EVENT_CONTRACT["namespace"]),
        "events": dict(COOKIE_RUNTIME_DOM_EVENT_CONTRACT["events"]),
    }


def get_cookie_requirements(
    *,
    user=None,
    anonymous_token: str | None = None,
    request=None,
) -> dict:
    """Function get_cookie_requirements documentation."""

    request_state = _build_cookie_runtime_request_state(request=request)

    if not is_cookies_enabled():
        return {
            "enabled": False,
            "has_policy": False,
            "policy_revision_id": None,
            "policy_revision_version": None,
            "categories": [],
            "status": None,
            "selected_categories": [],
            "required_categories": [],
            "optional_categories": [],
            "registry_items": [],
            "requires_reconsent": False,
            "runtime": _default_cookie_runtime_payload(request_state=request_state),
        }

    revision = _get_latest_active_policy_revision()
    if revision is None:
        return {
            "enabled": True,
            "has_policy": False,
            "policy_revision_id": None,
            "policy_revision_version": None,
            "categories": [],
            "status": None,
            "selected_categories": [],
            "required_categories": [],
            "optional_categories": [],
            "registry_items": [],
            "requires_reconsent": False,
            "runtime": _default_cookie_runtime_payload(
                enabled=True,
                request_state=request_state,
            ),
        }

    status = get_cookie_status(user=user, anonymous_token=anonymous_token)
    categories = normalize_categories_snapshot(revision.categories_snapshot)
    registry_items = get_published_cookie_registry_items(policy_revision=revision)
    payload = {
        "enabled": True,
        "has_policy": True,
        "policy_revision_id": revision.pk,
        "policy_revision_version": revision.version,
        "categories": categories,
        "status": status["status"],
        "selected_categories": status["selected_categories"],
        "required_categories": [
            item["code"] for item in categories if item["is_required"]
        ],
        "optional_categories": [
            item["code"] for item in categories if not item["is_required"]
        ],
        "registry_items": registry_items,
        "requires_reconsent": status["requires_reconsent"],
    }
    payload["runtime"] = build_cookie_runtime_payload(
        requirements=payload,
        request_state=request_state,
    )
    return payload


def build_cookie_runtime_payload(
    *,
    requirements: Mapping[str, object],
    request_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Function build_cookie_runtime_payload documentation."""

    if not bool(requirements.get("enabled")) or not bool(
        requirements.get("has_policy")
    ):
        return _default_cookie_runtime_payload(
            enabled=bool(requirements.get("enabled")),
            policy_revision_id=requirements.get("policy_revision_id"),
            policy_revision_version=requirements.get("policy_revision_version"),
            status=requirements.get("status"),
            request_state=request_state,
        )

    selected_categories_raw = _coerce_object_list(
        requirements.get("selected_categories")
    )
    selected_categories = [
        str(code).strip() for code in selected_categories_raw if str(code).strip()
    ]
    consent_status = requirements.get("status")
    consent_allows_runtime = consent_status == CookieConsentRecord.Status.CURRENT
    # Comment
    allowed_categories = list(selected_categories) if consent_allows_runtime else []
    registry_items = [
        _coerce_object_dict(item)
        for item in _coerce_object_list(requirements.get("registry_items"))
        if isinstance(item, Mapping)
    ]
    request_state_payload = _serialize_cookie_runtime_request_state(
        request_state=request_state
    )

    return {
        "enabled": True,
        "policy_revision_id": requirements.get("policy_revision_id"),
        "policy_revision_version": requirements.get("policy_revision_version"),
        "status": consent_status,
        "strict_default_deny": True,
        "consent_allows_runtime": consent_allows_runtime,
        "event_contract": get_cookie_runtime_dom_event_contract(),
        **request_state_payload,
        "selected_categories": selected_categories,
        "allowed_categories": allowed_categories,
        "script_items": [
            dict(item)
            for item in registry_items
            if str(item.get("src_url") or "").strip()
        ],
        "cleanup_items": [
            dict(item)
            for item in registry_items
            if _coerce_object_list(item.get("cookie_names"))
            or str(item.get("clear_strategy") or "")
            != CookieRegistryItem.ClearStrategy.NONE
        ],
    }


def _default_cookie_runtime_payload(
    *,
    enabled: bool = False,
    policy_revision_id: object = None,
    policy_revision_version: object = None,
    status: object = None,
    request_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "enabled": enabled,
        "policy_revision_id": policy_revision_id,
        "policy_revision_version": policy_revision_version,
        "status": status,
        "strict_default_deny": True,
        "consent_allows_runtime": False,
        "event_contract": get_cookie_runtime_dom_event_contract(),
        **_serialize_cookie_runtime_request_state(request_state=request_state),
        "selected_categories": [],
        "allowed_categories": [],
        "script_items": [],
        "cleanup_items": [],
    }


def _serialize_cookie_runtime_request_state(
    *,
    request_state: Mapping[str, object] | None,
) -> dict[str, object]:
    state = dict(request_state or {})
    return {
        "hide_for_bots": bool(state.get("hide_for_bots", True)),
        "is_bot_request": bool(state.get("is_bot_request", False)),
        "bot_pattern": str(state.get("bot_pattern") or ""),
        "user_agent_collection_mode": str(
            state.get("user_agent_collection_mode") or "all"
        ),
        "shared_subdomain": bool(state.get("shared_subdomain", False)),
        "site_domain": str(state.get("site_domain") or ""),
        "cookie_domain": str(state.get("cookie_domain") or ""),
        "geo_signal": str(state.get("geo_signal") or COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN),
    }


def _build_cookie_runtime_request_state(*, request=None) -> dict[str, object]:
    runtime_settings = get_cookie_runtime_settings()
    banner_config = get_cookie_banner_configuration()
    hide_for_bots_override = banner_config.get("hide_for_bots_override")
    hide_for_bots = (
        bool(runtime_settings["hide_for_bots"])
        if hide_for_bots_override is None
        else bool(hide_for_bots_override)
    )
    user_agent = ""
    if request is not None:
        user_agent = str(request.headers.get("User-Agent", "") or "")
    bot_pattern = _match_cookie_runtime_bot_pattern(
        user_agent=user_agent,
        bot_patterns=runtime_settings["bot_patterns"],
    )
    return {
        "hide_for_bots": hide_for_bots,
        "is_bot_request": bool(bot_pattern),
        "bot_pattern": bot_pattern,
        "user_agent_collection_mode": str(runtime_settings["user_agent_mode"] or "all"),
        "shared_subdomain": bool(runtime_settings["shared_subdomain"]),
        "site_domain": str(runtime_settings["site_domain"] or ""),
        "cookie_domain": str(runtime_settings["cookie_domain"] or ""),
        "geo_signal": _resolve_cookie_runtime_geo_signal(
            request=request,
            geo_signal_hook=runtime_settings["geo_signal_hook"],
        ),
    }


def _match_cookie_runtime_bot_pattern(
    *,
    user_agent: str,
    bot_patterns: Iterable[str],
) -> str:
    normalized_user_agent = user_agent.strip().lower()
    if not normalized_user_agent:
        return ""
    for raw_pattern in bot_patterns:
        normalized_pattern = str(raw_pattern).strip().lower()
        if normalized_pattern and normalized_pattern in normalized_user_agent:
            return str(raw_pattern).strip()
    return ""


def _resolve_cookie_runtime_geo_signal(
    *,
    request,
    geo_signal_hook,
) -> str:
    if not geo_signal_hook:
        return COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN
    hook = geo_signal_hook
    if isinstance(hook, str):
        try:
            hook = import_string(hook)
        except ImportError:
            _runtime_logger.warning(
                "Failed to import cookie geo_signal_hook '%s'; fallback to unknown.",
                geo_signal_hook,
            )
            return COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN
    if not callable(hook):
        _runtime_logger.warning(
            "Configured cookie geo_signal_hook is not callable (%r); fallback to unknown.",
            hook,
        )
        return COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN
    try:
        # Comment
        resolved_signal = hook(request=request)
    except Exception:
        _runtime_logger.exception("cookie geo_signal_hook failed; fallback to unknown.")
        return COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN
    return _normalize_cookie_runtime_geo_signal(resolved_signal)


def _normalize_cookie_runtime_geo_signal(value: object) -> str:
    normalized_value = str(value or "").strip().lower().replace("-", "_")
    if normalized_value not in _ALLOWED_COOKIE_RUNTIME_GEO_SIGNALS:
        return COOKIE_RUNTIME_GEO_SIGNAL_UNKNOWN
    return normalized_value


def get_active_cookie_policy_revision() -> CookiePolicyRevision | None:
    """Function get_active_cookie_policy_revision documentation."""

    return _get_latest_active_policy_revision()


@transaction.atomic
def sync_cookie_policy_revision_registry_items(
    *,
    policy_revision: CookiePolicyRevision,
) -> list[CookiePolicyRevisionRegistryItem]:
    """Function sync_cookie_policy_revision_registry_items documentation."""

    if policy_revision.pk is None:
        raise ConsentError(
            _(
                "Редакция политики cookie должна быть сохранена до синхронизации registry items."
            )
        )

    category_codes = {
        str(item["code"])
        for item in normalize_categories_snapshot(policy_revision.categories_snapshot)
    }
    live_items = list(
        CookieRegistryItem.objects.select_related("category")
        .filter(
            is_active=True,
            category__is_active=True,
            category__code__in=category_codes,
        )
        .order_by("category__sort_order", "category__code", "code")
    )

    policy_revision.registry_items.all().delete()  # pyright: ignore[reportAttributeAccessIssue]
    snapshots = [
        CookiePolicyRevisionRegistryItem(
            policy_revision=policy_revision,
            registry_item=item,
            registry_code=item.code,
            category_code=item.category.code,
            provider=item.provider,
            purpose=item.purpose,
            retention=item.retention,
            cookie_names=list(item.cookie_names),
            src_url=item.src_url,
            clear_strategy=item.clear_strategy,
        )
        for item in live_items
    ]
    if snapshots:
        CookiePolicyRevisionRegistryItem.objects.bulk_create(snapshots)
    result = list(
        policy_revision.registry_items.order_by(  # pyright: ignore[reportAttributeAccessIssue]
            "category_code",
            "registry_code",
        )
    )
    log_module_operation(
        operation_code="service.cookies.sync_policy_registry_snapshot",
        source="cookies.services",
        target_model="django_cookies_152fz.CookiePolicyRevision",
        target_id=str(policy_revision.pk),
        summary="Synchronized policy revision registry snapshot.",
        result={"snapshot_items_count": len(result)},
    )
    return result


def get_published_cookie_registry_items(
    *,
    policy_revision: CookiePolicyRevision | None = None,
) -> list[dict[str, object]]:
    """Function get_published_cookie_registry_items documentation."""

    revision = policy_revision or _get_latest_active_policy_revision()
    if revision is None:
        return []

    category_map = {
        str(item["code"]): item
        for item in normalize_categories_snapshot(revision.categories_snapshot)
    }
    snapshots = list(
        revision.registry_items.order_by("category_code", "registry_code", "id")  # pyright: ignore[reportAttributeAccessIssue]
    )
    if snapshots:
        return [
            _serialize_cookie_registry_snapshot(
                snapshot=snapshot,
                category_map=category_map,
            )
            for snapshot in snapshots
        ]

    # Comment
    return snapshot_active_cookie_registry_items(
        category_codes=category_map.keys(),
    )


@transaction.atomic
def attach_anonymous_cookie_consents_to_user(
    *,
    user,
    anonymous_token: str,
) -> list[CookieConsentRecord]:
    """Function attach_anonymous_cookie_consents_to_user documentation."""

    _validate_cookie_subject_user(user=user)
    token = _require_anonymous_token(anonymous_token)

    records = list(
        CookieConsentRecord.objects.filter(
            user__isnull=True,
            anonymous_token=token,
        ).order_by("created_at", "id")
    )
    for record in records:
        record.user = user
        record.anonymous_token = ""
        record.save(update_fields=["user", "anonymous_token", "updated_at"])
    return records


@transaction.atomic
def attach_anonymous_cookie_banner_state_to_user(
    *,
    user,
    anonymous_token: str,
) -> CookieBannerState | None:
    """Function attach_anonymous_cookie_banner_state_to_user documentation."""

    _validate_cookie_subject_user(user=user)
    token = _require_anonymous_token(anonymous_token)

    user_state = (
        CookieBannerState.objects.filter(user=user)
        .order_by("-updated_at", "-id")
        .first()
    )
    anonymous_state = (
        CookieBannerState.objects.filter(
            user__isnull=True,
            anonymous_token=token,
        )
        .order_by("-updated_at", "-id")
        .first()
    )
    if anonymous_state is None:
        return user_state
    if user_state is None:
        anonymous_state.user = user
        anonymous_state.anonymous_token = None
        anonymous_state.save(update_fields=["user", "anonymous_token", "updated_at"])
        return anonymous_state

    user_state.dismissed_at = _latest_datetime(
        user_state.dismissed_at,
        anonymous_state.dismissed_at,
    )
    user_state.decided_at = _latest_datetime(
        user_state.decided_at,
        anonymous_state.decided_at,
    )
    user_state.save(update_fields=["dismissed_at", "decided_at", "updated_at"])
    anonymous_state.delete()
    return user_state


@transaction.atomic
def attach_anonymous_cookie_data_to_user(
    *,
    user,
    anonymous_token: str,
) -> dict[str, object]:
    """Function attach_anonymous_cookie_data_to_user documentation."""

    return {
        "records": attach_anonymous_cookie_consents_to_user(
            user=user,
            anonymous_token=anonymous_token,
        ),
        "banner_state": attach_anonymous_cookie_banner_state_to_user(
            user=user,
            anonymous_token=anonymous_token,
        ),
    }


def get_cookie_banner_state(*, user=None, anonymous_token: str | None = None) -> dict:
    """Function get_cookie_banner_state documentation."""

    banner_config = get_cookie_banner_configuration()
    if not is_cookies_enabled():
        return {
            "enabled": False,
            "has_policy": False,
            "should_show": False,
            "state": None,
            "is_dismissed": False,
            "is_decided": False,
            "is_reask_due": False,
            "reask_reason": None,
            "requires_reconsent": False,
            "has_decision": False,
            "dismissed_at": None,
            "decided_at": None,
            "banner_state_id": None,
            "decision_action": "",
            "keep_visible_after_decision": False,
            "blocking_mode_enabled": False,
            "blocking_mode_active": False,
            "blocking_gate_open": False,
            "initial_visit": False,
            "reopen_after_saved_choice": False,
            "default_choice_action": "",
        }

    revision = _get_latest_active_policy_revision()
    if revision is None:
        return {
            "enabled": True,
            "has_policy": False,
            "should_show": False,
            "state": None,
            "is_dismissed": False,
            "is_decided": False,
            "is_reask_due": False,
            "reask_reason": None,
            "requires_reconsent": False,
            "has_decision": False,
            "dismissed_at": None,
            "decided_at": None,
            "banner_state_id": None,
            "decision_action": "",
            "keep_visible_after_decision": False,
            "blocking_mode_enabled": False,
            "blocking_mode_active": False,
            "blocking_gate_open": False,
            "initial_visit": False,
            "reopen_after_saved_choice": False,
            "default_choice_action": "",
        }

    token = (anonymous_token or "").strip()
    status = get_cookie_status(user=user, anonymous_token=token or None)
    banner_state = _subject_banner_state(user=user, anonymous_token=token)
    dismissed_at = banner_state.dismissed_at if banner_state is not None else None
    decided_at = (
        banner_state.decided_at
        if banner_state is not None and banner_state.decided_at is not None
        else status["decided_at"]
    )
    reask_reason = None
    is_reask_due = False
    decision_action = ""
    keep_visible_after_decision = False
    if banner_state is not None:
        decision_action = _normalize_cookie_banner_decision_action(
            banner_state.decision_action
        )

    if status["requires_reconsent"]:
        # Comment
        state = "shown"
        should_show = True
    elif status["is_current"]:
        # Comment
        if dismissed_at is not None:
            is_reask_due = _is_cookie_banner_reask_due(decided_at=dismissed_at)
            should_show = is_reask_due
            state = "shown" if is_reask_due else "dismissed"
            if is_reask_due:
                reask_reason = "dismiss_interval_elapsed"
        else:
            is_reask_due = _is_cookie_banner_reask_due(decided_at=decided_at)
            keep_visible_after_decision = _should_keep_banner_visible_after_decision(
                banner_config=banner_config,
                decision_action=decision_action,
            )
            should_show = is_reask_due or keep_visible_after_decision
            state = "shown" if should_show else "decided"
            if is_reask_due:
                reask_reason = "decision_interval_elapsed"
    elif dismissed_at is not None:
        is_reask_due = _is_cookie_banner_reask_due(decided_at=dismissed_at)
        should_show = is_reask_due
        state = "shown" if is_reask_due else "dismissed"
        if is_reask_due:
            reask_reason = "dismiss_interval_elapsed"
    else:
        state = "shown"
        should_show = True

    blocking_mode_enabled = bool(banner_config.get("blocking_mode_until_choice", False))
    has_meaningful_choice = bool(
        status["is_current"] and decision_action in COOKIE_BANNER_DECISION_ACTIONS
    )
    initial_visit = bool(
        banner_state is None
        and dismissed_at is None
        and not status["is_current"]
        and not status["requires_reconsent"]
    )
    reopen_after_saved_choice = bool(
        has_meaningful_choice and should_show and not initial_visit
    )
    default_choice_action = (
        decision_action
        if decision_action in COOKIE_BANNER_DECISION_ACTIONS
        else (
            COOKIE_BANNER_DECISION_ACTION_ACCEPT_ALL
            if should_show and not has_meaningful_choice
            else ""
        )
    )
    blocking_mode_active = bool(
        blocking_mode_enabled and should_show and not has_meaningful_choice
    )

    return {
        "enabled": True,
        "has_policy": True,
        "should_show": should_show,
        "state": state,
        "is_dismissed": state == "dismissed",
        "is_decided": state == "decided",
        "is_reask_due": is_reask_due,
        "reask_reason": reask_reason,
        "requires_reconsent": status["requires_reconsent"],
        "has_decision": status["is_current"],
        "dismissed_at": dismissed_at,
        "decided_at": decided_at,
        "banner_state_id": banner_state.pk if banner_state is not None else None,
        "decision_action": decision_action,
        "keep_visible_after_decision": keep_visible_after_decision,
        "blocking_mode_enabled": blocking_mode_enabled,
        "blocking_mode_active": blocking_mode_active,
        # Viewport-independent basis for blocking: the banner is shown and
        # a meaningful choice has not yet been made. Desktop/mobile differ only by
        # the enable flag, so the gate is returned separately for the client.
        "blocking_gate_open": bool(should_show and not has_meaningful_choice),
        "initial_visit": initial_visit,
        "reopen_after_saved_choice": reopen_after_saved_choice,
        "default_choice_action": default_choice_action,
    }


def _normalize_cookie_banner_decision_action(raw_value: object) -> str:
    normalized = str(raw_value or "").strip().lower()
    if normalized in COOKIE_BANNER_DECISION_ACTIONS:
        return normalized
    return ""


def _should_keep_banner_visible_after_decision(
    *,
    banner_config: Mapping[str, object],
    decision_action: str,
) -> bool:
    normalized_action = _normalize_cookie_banner_decision_action(decision_action)
    if normalized_action == COOKIE_BANNER_DECISION_ACTION_ACCEPT_ALL:
        return bool(banner_config.get("keep_visible_after_accept_all", False))
    # reject_all and required_only lead to the same outcome — only required
    # cookies are kept, so banner visibility after them is controlled by the
    # shared keep_visible_after_required_only flag (a separate flag for
    # reject_all is intentionally absent).
    if normalized_action in (
        COOKIE_BANNER_DECISION_ACTION_REQUIRED_ONLY,
        COOKIE_BANNER_DECISION_ACTION_REJECT_ALL,
    ):
        return bool(banner_config.get("keep_visible_after_required_only", False))
    if normalized_action == COOKIE_BANNER_DECISION_ACTION_SAVE_CUSTOM:
        return bool(banner_config.get("keep_visible_after_save_custom", False))
    return False


@transaction.atomic
def dismiss_cookie_banner(
    *,
    user=None,
    anonymous_token: str | None = None,
    audit_context: Mapping[str, object] | None = None,
) -> CookieBannerState:
    """Function dismiss_cookie_banner documentation."""

    if not is_cookies_enabled():
        raise ConsentError(_("Cookie-модуль отключён."))

    token = (anonymous_token or "").strip()
    if user is None and not token:
        raise ConsentError(
            _(
                "Для закрытия cookie-баннера нужен авторизованный пользователь или anonymous_token."
            )
        )
    if user is not None and token:
        attach_anonymous_cookie_data_to_user(user=user, anonymous_token=token)

    normalized_audit_context = _normalize_cookie_audit_context(
        audit_context=audit_context,
        source=str((audit_context or {}).get("source") or "cookies.banner.dismiss"),
    )
    state = _get_or_create_subject_banner_state(user=user, anonymous_token=token)
    state.dismissed_at = _resolve_cookie_state_occurred_at(normalized_audit_context)
    if user is not None:
        state.anonymous_token = None
    state.save()
    _trigger_cookie_runtime_integration_event(
        event_name="cookie_banner.dismissed",
        user=user,
        anonymous_token=token,
        banner_state=state,
        audit_context=normalized_audit_context,
        payload={"reason": "banner_dismissed"},
        occurred_at=state.dismissed_at,
    )
    return state


@transaction.atomic
def accept_cookie_preferences(
    *,
    selected_categories: Iterable[str] | None = None,
    policy_revision: CookiePolicyRevision | None = None,
    user=None,
    anonymous_token: str | None = None,
    decision_action: str = COOKIE_BANNER_DECISION_ACTION_SAVE_CUSTOM,
    source: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    locale: str = "",
    request_id: str = "",
    session_key_hash: str = "",
    extra_meta: Mapping[str, object] | None = None,
    audit_context: Mapping[str, object] | None = None,
) -> CookieConsentRecord:
    """Function accept_cookie_preferences documentation."""

    if not is_cookies_enabled():
        raise ConsentError(_("Cookie-модуль отключён."))

    revision = policy_revision or _require_latest_active_policy_revision()
    token = (anonymous_token or "").strip()
    if user is None and not token:
        raise ConsentError(
            _(
                "Для выбора настроек cookie нужен авторизованный пользователь или anonymous_token."
            )
        )
    if user is not None and token:
        attach_anonymous_cookie_data_to_user(user=user, anonymous_token=token)

    normalized_audit_context = _normalize_cookie_audit_context(
        audit_context=audit_context,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        locale=locale,
        request_id=request_id,
        session_key_hash=session_key_hash,
        extra_meta=extra_meta,
    )
    normalized_categories = _normalize_selected_categories(
        revision=revision,
        selected_categories=selected_categories or [],
    )
    record_anonymous_token = "" if user is not None else token
    decision_occurred_at = _resolve_cookie_state_occurred_at(normalized_audit_context)
    subject_qs = _subject_records_qs(
        user=user,
        anonymous_token=token,
    ).select_for_update()
    prior_record_exists = subject_qs.exists()
    duplicate_current = (
        subject_qs.filter(
            policy_revision=revision,
            status=CookieConsentRecord.Status.CURRENT,
            selected_categories=normalized_categories,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if duplicate_current is not None:
        # Comment
        _record_cookie_banner_decision(
            user=user,
            anonymous_token=token,
            occurred_at=decision_occurred_at,
            decision_action=decision_action,
        )
        return duplicate_current

    _mark_current_records_outdated(
        records=subject_qs.filter(status=CookieConsentRecord.Status.CURRENT),
        audit_context=normalized_audit_context,
        reason="preferences_updated",
        current_revision=revision,
    )

    record: CookieConsentRecord
    try:
        with transaction.atomic():
            record = CookieConsentRecord.objects.create(
                user=user,
                anonymous_token=record_anonymous_token,
                policy_revision=revision,
                selected_categories=normalized_categories,
                status=CookieConsentRecord.Status.CURRENT,
                source=str(normalized_audit_context.get("source") or ""),
                ip_address=normalized_audit_context.get("ip_address"),
                user_agent=str(normalized_audit_context.get("user_agent") or ""),
                locale=str(normalized_audit_context.get("locale") or ""),
                request_id=str(normalized_audit_context.get("request_id") or ""),
                session_key_hash=str(
                    normalized_audit_context.get("session_key_hash") or ""
                ),
                extra_meta=_coerce_object_dict(
                    normalized_audit_context.get("extra_meta")
                ),
            )
    except IntegrityError:
        existing_current = (
            _subject_records_qs(user=user, anonymous_token=token)
            .filter(status=CookieConsentRecord.Status.CURRENT)
            .order_by("-created_at", "-id")
            .first()
        )
        if existing_current is not None:
            return existing_current
        raise
    _create_cookie_event(
        record=record,
        event_type=(
            CookieConsentEvent.EventType.UPDATED
            if prior_record_exists
            else CookieConsentEvent.EventType.ACCEPTED
        ),
        audit_context=normalized_audit_context,
        payload={
            "policy_revision_id": revision.pk,
            "policy_revision_version": revision.version,
            "selected_categories": normalized_categories,
        },
    )
    _record_cookie_banner_decision(
        user=user,
        anonymous_token=token,
        occurred_at=decision_occurred_at,
        decision_action=decision_action,
    )
    return record


def get_cookie_status(*, user=None, anonymous_token: str | None = None) -> dict:
    """Function get_cookie_status documentation."""

    revision = _get_latest_active_policy_revision()
    token = (anonymous_token or "").strip()

    if not is_cookies_enabled():
        return {
            "enabled": False,
            "status": None,
            "is_current": False,
            "is_outdated": False,
            "requires_reconsent": False,
            "record_id": None,
            "policy_revision_id": None,
            "record_revision_id": None,
            "selected_categories": [],
        }

    latest_record = None
    if user is not None or token:
        latest_record = (
            _subject_records_qs(user=user, anonymous_token=token)
            .select_related("policy_revision")
            .order_by("-created_at", "-id")
            .first()
        )

    effective_status = None
    selected_categories: list[str] = []
    if latest_record is not None:
        selected_categories = list(latest_record.selected_categories)
        effective_status = latest_record.status
        if (
            latest_record.status == CookieConsentRecord.Status.CURRENT
            and revision is not None
            and latest_record.policy_revision_id != revision.pk  # pyright: ignore[reportAttributeAccessIssue]
        ):
            effective_status = CookieConsentRecord.Status.OUTDATED

    return {
        "enabled": True,
        "status": effective_status,
        "is_current": effective_status == CookieConsentRecord.Status.CURRENT,
        "is_outdated": effective_status == CookieConsentRecord.Status.OUTDATED,
        "requires_reconsent": effective_status == CookieConsentRecord.Status.OUTDATED,
        "record_id": latest_record.pk if latest_record else None,
        "policy_revision_id": revision.pk if revision else None,
        "policy_revision_version": revision.version if revision else None,
        "record_revision_id": (
            latest_record.policy_revision_id if latest_record else None  # pyright: ignore[reportAttributeAccessIssue]
        ),
        "selected_categories": selected_categories,
        "decided_at": latest_record.created_at if latest_record else None,
    }


def mark_outdated_cookie_consents(
    *,
    policy_revision: CookiePolicyRevision | None = None,
    user=None,
    anonymous_token: str | None = None,
    audit_context: Mapping[str, object] | None = None,
) -> list[CookieConsentRecord]:
    """Function mark_outdated_cookie_consents documentation."""

    current_revision = policy_revision or _get_latest_active_policy_revision()
    if current_revision is None:
        return []

    token = (anonymous_token or "").strip()
    qs = CookieConsentRecord.objects.select_related("policy_revision").filter(
        status=CookieConsentRecord.Status.CURRENT
    )
    if user is not None and token:
        qs = qs.filter(Q(user=user) | Q(user__isnull=True, anonymous_token=token))
    elif user is not None:
        qs = qs.filter(user=user)
    elif token:
        qs = qs.filter(anonymous_token=token)

    outdated_records = list(qs.exclude(policy_revision=current_revision))
    normalized_audit_context = _normalize_cookie_audit_context(
        audit_context=audit_context,
        source=str((audit_context or {}).get("source") or "cookies.outdated"),
    )
    _mark_current_records_outdated(
        records=outdated_records,
        audit_context=normalized_audit_context,
        reason="policy_revision_updated",
        current_revision=current_revision,
    )
    return outdated_records


def _mark_current_records_outdated(
    *,
    records,
    audit_context: Mapping[str, object],
    reason: str,
    current_revision: CookiePolicyRevision,
) -> None:
    """Function _mark_current_records_outdated documentation."""

    for record in records:
        if record.status != CookieConsentRecord.Status.CURRENT:
            continue
        record.status = CookieConsentRecord.Status.OUTDATED
        record.save(update_fields=["status", "updated_at"])
        _create_cookie_event(
            record=record,
            event_type=CookieConsentEvent.EventType.OUTDATED,
            audit_context=audit_context,
            payload={
                "reason": reason,
                "current_policy_revision_id": current_revision.pk,
                "current_policy_revision_version": current_revision.version,
            },
        )


def _create_cookie_event(
    *,
    record: CookieConsentRecord,
    event_type: str,
    audit_context: Mapping[str, object],
    payload: Mapping[str, object] | None = None,
) -> CookieConsentEvent:
    """Function _create_cookie_event documentation."""

    event = CookieConsentEvent.objects.create(
        cookie_consent_record=record,
        event_type=event_type,
        source=str(audit_context.get("source") or ""),
        ip_address=audit_context.get("ip_address"),
        user_agent=str(audit_context.get("user_agent") or ""),
        locale=str(audit_context.get("locale") or ""),
        request_id=str(audit_context.get("request_id") or ""),
        session_key_hash=str(audit_context.get("session_key_hash") or ""),
        payload=dict(payload or {}),
        extra_meta=_coerce_object_dict(audit_context.get("extra_meta")),
    )
    _trigger_cookie_runtime_integration_event(
        event_name=_resolve_cookie_runtime_consent_event_name(event_type),
        user=record.user,
        anonymous_token=record.anonymous_token,
        record=record,
        audit_context=audit_context,
        consent_event_type=event_type,
        payload=payload,
        occurred_at=event.occurred_at,
    )
    return event


def _resolve_cookie_runtime_consent_event_name(event_type: str) -> str:
    event_name_map = cast(Mapping[str, str], COOKIE_RUNTIME_CONSENT_EVENT_NAMES)
    mapped_name = event_name_map.get(str(event_type))
    if mapped_name:
        return mapped_name
    normalized_event_type = str(event_type or "").strip().lower().replace(" ", "_")
    if not normalized_event_type:
        normalized_event_type = "unknown"
    return f"cookie_consent.{normalized_event_type}"


def _trigger_cookie_runtime_integration_event(
    *,
    event_name: str,
    user,
    anonymous_token: str,
    audit_context: Mapping[str, object] | None,
    consent_event_type: str = "",
    record: CookieConsentRecord | None = None,
    banner_state: CookieBannerState | None = None,
    payload: Mapping[str, object] | None = None,
    occurred_at=None,
) -> None:
    # Comment
    subject_user_id = None
    if record is not None and record.user_id:  # pyright: ignore[reportAttributeAccessIssue]
        subject_user_id = record.user_id  # pyright: ignore[reportAttributeAccessIssue]
    elif user is not None:
        subject_user_id = getattr(user, "pk", None)

    subject_kind = "authenticated" if subject_user_id is not None else "anonymous"
    has_anonymous_token = bool(
        (anonymous_token or "").strip()
        or (record is not None and (record.anonymous_token or "").strip())
        or (banner_state is not None and (banner_state.anonymous_token or "").strip())
    )
    occurred_at_value = occurred_at
    if occurred_at_value is None and audit_context is not None:
        occurred_at_value = audit_context.get("occurred_at")
    normalized_audit_context = dict(audit_context or {})
    consent_payload = None
    if record is not None:
        policy_revision_version = getattr(record.policy_revision, "version", None)
        consent_payload = {
            "record_id": record.pk,
            "event_type": str(consent_event_type or ""),
            "status": record.status,
            "policy_revision_id": record.policy_revision_id,  # pyright: ignore[reportAttributeAccessIssue]
            "policy_revision_version": policy_revision_version,
            "selected_categories": list(record.selected_categories),
            "is_current": record.status == CookieConsentRecord.Status.CURRENT,
            "is_outdated": record.status == CookieConsentRecord.Status.OUTDATED,
        }
    banner_payload = None
    if banner_state is not None:
        banner_payload = {
            "state_id": banner_state.pk,
            "dismissed_at": _serialize_cookie_runtime_hook_datetime(
                banner_state.dismissed_at
            ),
            "decided_at": _serialize_cookie_runtime_hook_datetime(
                banner_state.decided_at
            ),
        }

    runtime_payload = {
        "contract_version": COOKIE_RUNTIME_EVENT_CONTRACT_VERSION,
        "event_name": str(event_name),
        "occurred_at": _serialize_cookie_runtime_hook_datetime(occurred_at_value),
        "source": str(normalized_audit_context.get("source") or ""),
        "subject": {
            "kind": subject_kind,
            "user_id": subject_user_id,
            "anonymous_token_present": has_anonymous_token,
        },
        "consent": consent_payload,
        "banner": banner_payload,
        "event_payload": dict(payload or {}),
        "audit": {
            "request_id": str(normalized_audit_context.get("request_id") or ""),
            "session_key_hash": str(
                normalized_audit_context.get("session_key_hash") or ""
            ),
            "ip_address": normalized_audit_context.get("ip_address"),
            "locale": str(normalized_audit_context.get("locale") or ""),
            "has_user_agent": bool(
                str(normalized_audit_context.get("user_agent") or "")
            ),
        },
        "extra_meta": _coerce_object_dict(normalized_audit_context.get("extra_meta")),
    }
    # Comment
    trigger_cookie_runtime_event(runtime_payload)


def _serialize_cookie_runtime_hook_datetime(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _serialize_cookie_registry_snapshot(
    *,
    snapshot: CookiePolicyRevisionRegistryItem,
    category_map: Mapping[str, object],
) -> dict[str, object]:
    category_snapshot = _coerce_object_dict(category_map.get(snapshot.category_code))
    return {
        "code": snapshot.registry_code,
        "category_code": snapshot.category_code,
        "category_title": str(category_snapshot.get("title") or ""),
        "category_is_required": bool(category_snapshot.get("is_required", False)),
        "provider": snapshot.provider,
        "purpose": snapshot.purpose,
        "retention": snapshot.retention,
        "cookie_names": list(snapshot.cookie_names),
        "src_url": snapshot.src_url,
        "clear_strategy": snapshot.clear_strategy,
    }


def _get_latest_active_policy_revision() -> CookiePolicyRevision | None:
    """Function _get_latest_active_policy_revision documentation."""

    return (
        CookiePolicyRevision.objects.filter(is_active=True)
        .order_by("-published_at", "-version", "-id")
        .first()
    )


def _require_latest_active_policy_revision() -> CookiePolicyRevision:
    """Function _require_latest_active_policy_revision documentation."""

    revision = _get_latest_active_policy_revision()
    if revision is None:
        raise ConsentError(_("Активная редакция политики cookie не найдена."))
    return revision


def _normalize_selected_categories(
    *,
    revision: CookiePolicyRevision,
    selected_categories: Iterable[str],
) -> list[str]:
    """Function _normalize_selected_categories documentation."""

    snapshot = normalize_categories_snapshot(revision.categories_snapshot)
    allowed_codes = {str(item["code"]) for item in snapshot}
    required_codes = {
        str(item["code"]) for item in snapshot if bool(item["is_required"])
    }
    normalized = set(required_codes)
    normalized.update(
        str(code).strip() for code in selected_categories if str(code).strip()
    )
    unknown_codes = sorted(normalized - allowed_codes)
    if unknown_codes:
        raise ConsentError(
            _("Выбраны неизвестные cookie-категории: %(codes)s.")
            % {"codes": ", ".join(unknown_codes)}
        )
    return sorted(normalized)


def _subject_records_qs(*, user, anonymous_token: str):
    qs = CookieConsentRecord.objects.all()
    if user is not None and anonymous_token:
        return qs.filter(
            Q(user=user) | Q(user__isnull=True, anonymous_token=anonymous_token)
        )
    if user is not None:
        return qs.filter(user=user)
    if anonymous_token:
        return qs.filter(anonymous_token=anonymous_token)
    return qs.none()


def _normalize_cookie_audit_context(
    *,
    audit_context: Mapping[str, object] | None = None,
    source: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    locale: str = "",
    request_id: str = "",
    session_key_hash: str = "",
    extra_meta: Mapping[str, object] | None = None,
) -> dict:
    normalized_audit_context = build_audit_context(
        audit_context=audit_context,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        locale=locale,
        request_id=request_id,
        session_key_hash=session_key_hash,
        extra_meta=extra_meta,
    )
    return _apply_cookie_runtime_audit_policy(audit_context=normalized_audit_context)


def _apply_cookie_runtime_audit_policy(
    *,
    audit_context: Mapping[str, object],
) -> dict[str, object]:
    runtime_settings = get_cookie_runtime_settings()
    normalized_audit_context = dict(audit_context)
    raw_user_agent = str(normalized_audit_context.get("user_agent") or "")
    bot_pattern = _match_cookie_runtime_bot_pattern(
        user_agent=raw_user_agent,
        bot_patterns=runtime_settings["bot_patterns"],
    )

    extra_meta = _coerce_object_dict(normalized_audit_context.get("extra_meta"))
    cookie_runtime_meta = _coerce_object_dict(extra_meta.get("cookie_runtime"))
    cookie_runtime_meta["user_agent_mode"] = str(
        runtime_settings["user_agent_mode"] or "all"
    )
    cookie_runtime_meta["is_bot_request"] = bool(bot_pattern)
    if bot_pattern:
        cookie_runtime_meta["bot_pattern"] = bot_pattern

    user_agent_mode = str(runtime_settings["user_agent_mode"] or "all")
    if user_agent_mode == "off":
        normalized_audit_context["user_agent"] = ""
    elif user_agent_mode == "unique":
        normalized_audit_context["user_agent"] = ""
        if raw_user_agent:
            cookie_runtime_meta["user_agent_sha256"] = hashlib.sha256(
                raw_user_agent.encode("utf-8")
            ).hexdigest()

    if cookie_runtime_meta:
        extra_meta["cookie_runtime"] = cookie_runtime_meta
    normalized_audit_context["extra_meta"] = extra_meta
    return normalized_audit_context


def _subject_banner_state(
    *,
    user,
    anonymous_token: str,
) -> CookieBannerState | None:
    if user is not None:
        user_state = (
            CookieBannerState.objects.filter(user=user)
            .order_by("-updated_at", "-id")
            .first()
        )
        if user_state is not None:
            return user_state
    token = anonymous_token.strip()
    if token:
        return (
            CookieBannerState.objects.filter(
                user__isnull=True,
                anonymous_token=token,
            )
            .order_by("-updated_at", "-id")
            .first()
        )
    return None


def _get_or_create_subject_banner_state(
    *,
    user,
    anonymous_token: str,
) -> CookieBannerState:
    token = anonymous_token.strip()
    existing_state = _subject_banner_state(user=user, anonymous_token=token)
    if existing_state is not None:
        if user is not None and existing_state.user_id is None:  # pyright: ignore[reportAttributeAccessIssue]
            existing_state.user = user
            existing_state.anonymous_token = None
            existing_state.save(update_fields=["user", "anonymous_token", "updated_at"])
        return existing_state
    if user is None and not token:
        raise ConsentError(
            _(
                "Для состояния cookie-баннера нужен авторизованный пользователь или anonymous_token."
            )
        )
    return CookieBannerState.objects.create(
        user=user,
        anonymous_token=None if user is not None else token,
    )


def _record_cookie_banner_decision(
    *,
    user,
    anonymous_token: str,
    occurred_at,
    decision_action: str = COOKIE_BANNER_DECISION_ACTION_SAVE_CUSTOM,
) -> CookieBannerState:
    state = _get_or_create_subject_banner_state(
        user=user,
        anonymous_token=anonymous_token,
    )
    state.decided_at = occurred_at
    state.decision_action = _normalize_cookie_banner_decision_action(decision_action)
    # Comment
    state.dismissed_at = None
    if user is not None:
        state.anonymous_token = None
    state.save()
    _trigger_cookie_runtime_integration_event(
        event_name="cookie_banner.decided",
        user=user,
        anonymous_token=anonymous_token,
        banner_state=state,
        audit_context={"occurred_at": occurred_at},
        payload={
            "state": "decided",
            "decision_action": state.decision_action,
        },
        occurred_at=state.decided_at,
    )
    return state


def _is_cookie_banner_reask_due(*, decided_at) -> bool:
    if decided_at is None:
        return False

    banner_settings = get_cookie_banner_settings()
    reask_after_days = int(banner_settings.get("reask_after_days") or 0)
    reask_after_months = int(banner_settings.get("reask_after_months") or 0)
    if not reask_after_days and not reask_after_months:
        return False

    threshold = decided_at
    if reask_after_days:
        threshold = decided_at + timedelta(days=reask_after_days)
    elif reask_after_months:
        threshold = _add_months(decided_at, reask_after_months)
    return timezone.now() >= threshold


def _add_months(value, months: int):
    if months <= 0:
        return value

    total_months = value.month - 1 + months
    year = value.year + total_months // 12
    month = total_months % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _latest_datetime(*values):
    resolved_values = [value for value in values if value is not None]
    if not resolved_values:
        return None
    return max(resolved_values)


def _resolve_cookie_state_occurred_at(audit_context: Mapping[str, object]) -> object:
    return audit_context.get("occurred_at") or timezone.now()


def _validate_cookie_subject_user(*, user) -> None:
    UserModel = get_user_model()
    if not isinstance(user, UserModel):
        raise ConsentError(_("user должен быть экземпляром AUTH_USER_MODEL."))


def _require_anonymous_token(anonymous_token: str) -> str:
    token = anonymous_token.strip()
    if not token:
        raise ConsentError(_("anonymous_token должен быть непустой строкой."))
    return token
