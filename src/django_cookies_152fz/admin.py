"""Django admin for cookie module models."""

from __future__ import annotations

import csv
import json
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .integration_contract import (
    AssignmentRestrictedAdminMixin,
    ConsentError,
    PublishableRevisionAdminMixin,
    ReadOnlyAdminMixin,
    constants,
    log_module_operation,
    safe_register_admin_models,
)
from .models import (
    COOKIE_BANNER_PROTECTED_TEXT_FIELDS,
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
)
from .services import (
    COOKIE_POLICY_TEXT_VARIANT_FULL,
    COOKIE_POLICY_TEXT_VARIANT_SHORT,
    clone_cookie_banner_revision_as_draft,
    clone_cookie_policy_revision_as_draft,
    create_custom_cookie_policy_draft_from_variant,
    ensure_default_cookie_banner_text_presets,
    ensure_default_cookie_policy_text_presets,
    mark_outdated_cookie_consents,
    publish_box_cookie_policy_variant,
    snapshot_active_cookie_categories,
    sync_cookie_policy_revision_registry_items,
)

USER_LOOKUP = str(getattr(get_user_model(), "USERNAME_FIELD", "username"))


def _resolve_cookie_csv_delimiter() -> str:
    settings_obj = CookieAdminSettings.objects.order_by("-updated_at", "-id").first()
    if not settings_obj:
        return ","
    delimiter = str(getattr(settings_obj, "csv_export_delimiter", ",") or ",")
    return delimiter if delimiter in {",", ";", "\t", "|"} else ","


def _sanitize_csv_cell(value: object) -> str:
    text = str(value or "")
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def _set_verbose_names(model, field_labels: dict[str, object]) -> None:
    for field_name, label in field_labels.items():
        model._meta.get_field(field_name).verbose_name = label


def _localize_cookie_admin_field_labels() -> None:
    _set_verbose_names(
        CookieCategory,
        {
            "code": _("Код"),
            "title": _("Название"),
            "description": _("Описание"),
            "is_required": _("Обязательная категория"),
            "sort_order": _("Порядок сортировки"),
            "is_active": _("Активна"),
        },
    )
    _set_verbose_names(
        CookiePolicyRevision,
        {
            "version": _("Версия"),
            "format": _("Формат"),
            "content_text": _("Текст политики"),
            "content_file": _("Файл политики"),
            "categories_snapshot": _("Снимок категорий"),
            "cloned_from": _("Скопировано из ревизии"),
            "is_active": _("Опубликована"),
            "is_box_template": _("Коробочный шаблон"),
            "published_at": _("Дата публикации"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        },
    )
    _set_verbose_names(
        CookieRegistryItem,
        {
            "code": _("Код элемента реестра"),
            "category": _("Категория"),
            "provider": _("Поставщик"),
            "purpose": _("Назначение"),
            "retention": _("Срок хранения"),
            "cookie_names": _("Cookie-имена"),
            "src_url": _("URL скрипта"),
            "clear_strategy": _("Стратегия очистки"),
            "is_active": _("Активен"),
        },
    )
    _set_verbose_names(
        CookieBannerRevision,
        {
            "version": _("Версия"),
            "cloned_from": _("Скопировано из ревизии"),
            "launcher_label": _("Текст кнопки «Настройки cookie»"),
            "eyebrow_text": _("Подзаголовок"),
            "title_text": _("Заголовок"),
            "description_text": _("Описание"),
            "reconsent_notice_text": _("Текст уведомления о повторном согласии"),
            "reask_notice_text": _("Текст повторного запроса"),
            "accept_all_label": _("Кнопка: принять все"),
            "reject_label": _("Кнопка: отказаться от необязательных cookie"),
            "required_only_label": _("Кнопка: только необходимые"),
            "customize_label": _("Кнопка: выбрать категории"),
            "custom_section_summary": _("Заголовок блока выбора категорий"),
            "required_section_title": _("Заголовок обязательных категорий"),
            "required_section_empty_text": _("Пустой текст обязательных"),
            "optional_section_title": _("Заголовок необязательных категорий"),
            "optional_section_empty_text": _("Пустой текст необязательных"),
            "save_custom_label": _("Кнопка: сохранить выбор"),
            "preferences_link_label": _("Ссылка: полная страница"),
            "dismiss_label": _("Скрытый текст кнопки закрытия"),
            "close_tooltip_text": _("Подсказка кнопки закрытия"),
            "close_aria_label": _("ARIA-метка кнопки закрытия"),
            "noscript_text": _("Текст для режима без JavaScript"),
            "noscript_link_label": _("Ссылка для режима без JavaScript"),
            "banner_variant": _("Вариант баннера"),
            "consent_ui_variant": _("Вариант интерфейса согласия"),
            "reconsent_notice_variant": _("Вариант уведомления о повторном согласии"),
            "text_preset_code": _("Текстовая заготовка"),
            "mobile_text_preset_code": _(
                "Мобильная текстовая заготовка (переопределение)"
            ),
            "layout_variant": _("Устаревший режим компоновки"),
            "theme_variant": _("Устаревший режим темы"),
            "desktop_position": _("Позиция на компьютерах"),
            "mobile_position": _("Позиция на мобильных устройствах"),
            "mobile_banner_variant": _(
                "Мобильная версия: вариант баннера (переопределение)"
            ),
            "mobile_consent_ui_variant": _(
                "Мобильная версия: вариант интерфейса (переопределение)"
            ),
            "mobile_reconsent_notice_variant": (
                _(
                    "Мобильная версия: вариант уведомления о повторном согласии (переопределение)"
                )
            ),
            "show_close_control": _("Показывать кнопку закрытия"),
            "close_control_placement": _("Положение кнопки закрытия"),
            "mobile_close_control_placement": (
                _("Мобильная версия: положение кнопки закрытия (переопределение)")
            ),
            "show_reject_action": _("Показывать кнопку отклонения"),
            "mobile_show_close_control": (
                _("Мобильная версия: показывать кнопку закрытия (переопределение)")
            ),
            "mobile_show_reject_action": (
                _("Мобильная версия: показывать кнопку отклонения (переопределение)")
            ),
            "blocking_mode_until_choice": _("Блокирующий режим до выбора"),
            "mobile_blocking_mode_until_choice": (
                _("Мобильная версия: блокирующий режим до выбора (переопределение)")
            ),
            "hide_launcher_after_decision": (
                _("Скрывать 'Настройки cookie' после выбора пользователя")
            ),
            "mobile_hide_launcher_after_decision": (
                _(
                    "Мобильная версия: скрывать 'Настройки cookie' после выбора (переопределение)"
                )
            ),
            "keep_visible_after_accept_all": (
                _("Не закрывать баннер после 'принять все'")
            ),
            "keep_visible_after_required_only": (
                _("Не закрывать баннер после 'только необходимые'")
            ),
            "keep_visible_after_save_custom": (
                _("Не закрывать баннер после 'сохранить выбор'")
            ),
            "mobile_keep_visible_after_accept_all": (
                _(
                    "Мобильная версия: не закрывать после 'принять все' (переопределение)"
                )
            ),
            "mobile_keep_visible_after_required_only": (
                _(
                    "Мобильная версия: не закрывать после 'только необходимые' (переопределение)"
                )
            ),
            "mobile_keep_visible_after_save_custom": (
                _(
                    "Мобильная версия: не закрывать после 'сохранить выбор' (переопределение)"
                )
            ),
            "hide_for_bots_override": _(
                "Скрывать баннер для поисковых/технических ботов"
            ),
            "is_box_template": _("Коробочный шаблон"),
            "is_active": _("Активна"),
            "published_at": _("Дата публикации"),
            "created_at": _("Создана"),
            "updated_at": _("Обновлена"),
        },
    )
    _set_verbose_names(
        CookieConsentRecord,
        {
            "user": _("Пользователь"),
            "anonymous_token": _("Анонимный токен"),
            "policy_revision": _("Редакция политики"),
            "status": _("Статус"),
            "source": _("Источник"),
            "selected_categories": _("Выбранные категории"),
            "ip_address": _("IP-адрес"),
            "user_agent": _("User-Agent"),
            "locale": _("Локаль"),
            "request_id": _("Request ID"),
            "session_key_hash": _("Хеш ключа сессии"),
            "extra_meta": _("Дополнительные метаданные"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        },
    )
    _set_verbose_names(
        CookieConsentEvent,
        {
            "cookie_consent_record": _("Запись cookie-согласия"),
            "event_type": _("Тип события"),
            "source": _("Источник"),
            "ip_address": _("IP-адрес"),
            "user_agent": _("User-Agent"),
            "locale": _("Локаль"),
            "request_id": _("Request ID"),
            "session_key_hash": _("Хеш ключа сессии"),
            "payload": _("Данные события"),
            "extra_meta": _("Дополнительные метаданные"),
            "occurred_at": _("Время события"),
        },
    )
    _set_verbose_names(
        CookiePolicyRevisionRegistryItem,
        {
            "policy_revision": _("Редакция политики"),
            "registry_item": _("Элемент реестра"),
            "registry_code": _("Код элемента реестра"),
            "category_code": _("Код категории"),
            "provider": _("Поставщик"),
            "purpose": _("Назначение"),
            "retention": _("Срок хранения"),
            "cookie_names": _("Cookie-имена"),
            "src_url": _("URL скрипта"),
            "clear_strategy": _("Стратегия очистки"),
            "created_at": _("Создано"),
        },
    )
    _set_verbose_names(
        CookieAdminSettings,
        {
            "csv_export_delimiter": _("Разделитель CSV-экспорта"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        },
    )
    _set_verbose_names(
        CookieBannerState,
        {
            "user": _("Пользователь"),
            "anonymous_token": _("Анонимный токен"),
            "decision_action": _("Действие выбора"),
            "dismissed_at": _("Скрыт в"),
            "decided_at": _("Решение принято в"),
            "updated_at": _("Обновлено"),
        },
    )
    _set_verbose_names(
        CookiePolicyTextPreset,
        {
            "code": _("Код заготовки"),
            "title": _("Название заготовки"),
            "content_text": _("Текст заготовки"),
            "is_box_template": _("Коробочная заготовка"),
            "is_active": _("Активен"),
        },
    )
    _set_verbose_names(
        CookieBannerTextPreset,
        {
            "code": _("Код заготовки"),
            "title": _("Название заготовки"),
            "launcher_label": _("Текст кнопки «Настройки cookie»"),
            "eyebrow_text": _("Подзаголовок"),
            "title_text": _("Заголовок"),
            "description_text": _("Описание"),
            "reconsent_notice_text": _("Текст уведомления о повторном согласии"),
            "reask_notice_text": _("Текст повторного запроса"),
            "accept_all_label": _("Кнопка: принять все"),
            "reject_label": _("Кнопка: отказаться от необязательных cookie"),
            "required_only_label": _("Кнопка: только необходимые"),
            "customize_label": _("Кнопка: выбрать категории"),
            "custom_section_summary": _("Заголовок блока выбора категорий"),
            "required_section_title": _("Заголовок обязательных категорий"),
            "required_section_empty_text": _("Пустой текст обязательных"),
            "optional_section_title": _("Заголовок необязательных категорий"),
            "optional_section_empty_text": _("Пустой текст необязательных"),
            "save_custom_label": _("Кнопка: сохранить выбор"),
            "preferences_link_label": _("Ссылка: полная страница"),
            "dismiss_label": _("Скрытый текст кнопки закрытия"),
            "noscript_text": _("Текст для режима без JavaScript"),
            "noscript_link_label": _("Ссылка для режима без JavaScript"),
            "is_box_template": _("Коробочная заготовка"),
            "is_active": _("Активен"),
        },
    )


_localize_cookie_admin_field_labels()

COOKIE_POLICY_VARIANT_CHOICES: tuple[tuple[str, object], ...] = (
    (
        COOKIE_POLICY_TEXT_VARIANT_SHORT,
        _("Короткий коробочный текст"),
    ),
    (
        COOKIE_POLICY_TEXT_VARIANT_FULL,
        _("Полный коробочный текст"),
    ),
)


class CookieCategoryAdminForm(forms.ModelForm):
    class Meta:
        model = CookieCategory
        fields = "__all__"
        labels = {
            "code": _("Код категории"),
            "title": _("Название"),
            "description": _("Описание"),
            "is_required": _("Обязательная категория"),
            "sort_order": _("Порядок сортировки"),
            "is_active": _("Активна"),
        }
        help_texts = {
            "code": _(
                "Стабильный код категории cookie в контрактах согласия и среды "
                "выполнения."
            ),
            "title": _("Название категории, отображаемое пользователю."),
            "description": _("Пояснение назначения категории cookie."),
            "is_required": _(
                "Обязательная категория всегда включается независимо от выбора."
            ),
            "sort_order": _(
                "Порядок отображения категории в баннере и на странице настроек."
            ),
            "is_active": _(
                "Отключите категорию, чтобы исключить её из текущего выбора."
            ),
        }


class CookiePolicyRevisionAdminForm(forms.ModelForm):
    class Meta:
        model = CookiePolicyRevision
        fields = "__all__"
        labels = {
            "version": _("Версия"),
            "format": _("Формат"),
            "content_text": _("Текст политики"),
            "content_file": _("Файл политики"),
            "categories_snapshot": _("Снимок категорий"),
            "cloned_from": _("Скопировано из ревизии"),
            "is_active": _("Опубликована"),
            "is_box_template": _("Коробочный шаблон"),
            "published_at": _("Дата публикации"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        }
        help_texts = {
            "version": _("Версия редакции политики в версионируемом потоке."),
            "format": _("Формат содержимого политики: текст или файл."),
            "content_text": _("Текст редакции политики для текстового формата."),
            "content_file": _("Файл редакции политики для сценариев с файлом/PDF."),
            "categories_snapshot": _(
                "JSON-снимок активных категорий на момент публикации."
            ),
            "cloned_from": _(
                "Исходная ревизия, если запись создана через процесс клонирования/копирования."
            ),
            "is_active": _(
                "Активная редакция применяется в текущем процессе работы с cookie."
            ),
            "is_box_template": _("Флаг коробочного шаблона, поставляемого пакетом."),
            "published_at": _("Дата и время публикации редакции."),
            "created_at": _("Техническое время создания записи."),
            "updated_at": _("Техническое время последнего обновления."),
        }


class CookieRegistryItemAdminForm(forms.ModelForm):
    class Meta:
        model = CookieRegistryItem
        fields = "__all__"
        labels = {
            "code": _("Код элемента реестра"),
            "category": _("Категория"),
            "provider": _("Поставщик"),
            "purpose": _("Назначение"),
            "retention": _("Срок хранения"),
            "cookie_names": _("Cookie-имена"),
            "src_url": _("URL скрипта"),
            "clear_strategy": _("Стратегия очистки"),
            "is_active": _("Активен"),
        }
        help_texts = {
            "code": _(
                "Уникальный код элемента реестра cookie и скриптов времени выполнения."
            ),
            "category": _("Категория cookie, к которой относится элемент."),
            "provider": _("Поставщик cookie или скрипта."),
            "purpose": _(
                "Назначение элемента cookie/скрипта для информирования и аудита."
            ),
            "retention": _("Срок хранения данных cookie/скрипта."),
            "cookie_names": _("JSON-список имён cookie, связанных с элементом."),
            "src_url": _(
                "URL скрипта для загрузки во время выполнения с учётом согласия."
            ),
            "clear_strategy": _("Стратегия очистки при отзыве/изменении согласия."),
            "is_active": _("Включает или отключает элемент во время выполнения."),
        }


class CookieBannerRevisionAdminForm(forms.ModelForm):
    MOBILE_BOOLEAN_OVERRIDE_FIELDS = (
        "mobile_show_close_control",
        "mobile_show_reject_action",
        "mobile_blocking_mode_until_choice",
        "mobile_hide_launcher_after_decision",
        "mobile_keep_visible_after_accept_all",
        "mobile_keep_visible_after_required_only",
        "mobile_keep_visible_after_save_custom",
    )
    COLOR_FIELDS = (
        "custom_bg_color",
        "custom_text_color",
        "custom_primary_color",
        "custom_primary_text_color",
        "custom_border_color",
        "custom_surface_color",
        "custom_overlay_color",
    )
    mobile_show_close_control__inherit = forms.BooleanField(required=False)
    mobile_show_reject_action__inherit = forms.BooleanField(required=False)
    mobile_blocking_mode_until_choice__inherit = forms.BooleanField(required=False)
    mobile_hide_launcher_after_decision__inherit = forms.BooleanField(required=False)
    mobile_keep_visible_after_accept_all__inherit = forms.BooleanField(required=False)
    mobile_keep_visible_after_required_only__inherit = forms.BooleanField(
        required=False
    )
    mobile_keep_visible_after_save_custom__inherit = forms.BooleanField(required=False)

    class Meta:
        model = CookieBannerRevision
        fields = "__all__"
        labels = {
            "version": _("Версия"),
            "cloned_from": _("Скопировано из ревизии"),
            "launcher_label": _("Текст кнопки «Настройки cookie»"),
            "eyebrow_text": _("Подзаголовок"),
            "title_text": _("Заголовок"),
            "description_text": _("Описание"),
            "reconsent_notice_text": _("Текст уведомления о повторном согласии"),
            "reask_notice_text": _("Текст повторного запроса"),
            "accept_all_label": _("Кнопка: принять все"),
            "reject_label": _("Кнопка: отказаться от необязательных cookie"),
            "required_only_label": _("Кнопка: только необходимые"),
            "customize_label": _("Кнопка: выбрать категории"),
            "custom_section_summary": _("Заголовок блока выбора категорий"),
            "required_section_title": _("Заголовок обязательных категорий"),
            "required_section_empty_text": _("Пустой текст обязательных"),
            "optional_section_title": _("Заголовок необязательных категорий"),
            "optional_section_empty_text": _("Пустой текст необязательных"),
            "save_custom_label": _("Кнопка: сохранить выбор"),
            "preferences_link_label": _("Ссылка: полная страница"),
            "dismiss_label": _("Скрытый текст кнопки закрытия"),
            "close_tooltip_text": _("Подсказка кнопки закрытия"),
            "close_aria_label": _("ARIA-метка кнопки закрытия"),
            "noscript_text": _("Текст для режима без JavaScript"),
            "noscript_link_label": _("Ссылка для режима без JavaScript"),
            "banner_variant": _("Вариант баннера"),
            "consent_ui_variant": _("Вариант интерфейса согласия"),
            "reconsent_notice_variant": _("Вариант уведомления о повторном согласии"),
            "text_preset_code": _("Текстовая заготовка"),
            "mobile_text_preset_code": _(
                "Мобильная текстовая заготовка (переопределение)"
            ),
            "layout_variant": _("Устаревший режим компоновки"),
            "theme_variant": _("Устаревший режим темы"),
            "desktop_position": _("Позиция на компьютерах"),
            "mobile_position": _("Позиция на мобильных"),
            "color_preset": _("Цветовая заготовка"),
            "custom_bg_color": _("Пользовательский фон"),
            "custom_text_color": _("Пользовательский текст"),
            "custom_primary_color": _("Пользовательский акцентный цвет"),
            "custom_primary_text_color": _("Пользовательский текст акцентной кнопки"),
            "custom_border_color": _("Пользовательская граница"),
            "custom_surface_color": _("Пользовательская подложка"),
            "custom_overlay_color": _("Пользовательское затемнение фона"),
            "panel_padding_px": _("Внутренний отступ панели (px)"),
            "section_gap_px": _("Отступ между секциями (px)"),
            "button_gap_px": _("Отступ между кнопками (px)"),
            "overlay_opacity": _("Прозрачность затемнения (%)"),
            "show_media_slot": _("Показывать медиаблок"),
            "media_slot_type": _("Тип медиаблока"),
            "media_icon_emoji": _("Эмодзи для медиаблока"),
            "media_image_url": _("Адрес изображения для медиаблока"),
            "media_image_alt": _("Альтернативный текст изображения для доступности"),
            "mobile_banner_variant": _(
                "Мобильная версия: вариант баннера (переопределение)"
            ),
            "mobile_consent_ui_variant": _(
                "Мобильная версия: вариант интерфейса (переопределение)"
            ),
            "mobile_reconsent_notice_variant": _(
                "Мобильная версия: вариант уведомления о повторном согласии (переопределение)"
            ),
            "show_close_control": _("Показывать кнопку закрытия"),
            "close_control_placement": _("Положение кнопки закрытия"),
            "mobile_close_control_placement": _(
                "Мобильная версия: положение кнопки закрытия (переопределение)"
            ),
            "show_reject_action": _("Показывать кнопку отклонения"),
            "mobile_show_close_control": _(
                "Мобильная версия: показывать кнопку закрытия (переопределение)"
            ),
            "mobile_show_reject_action": _(
                "Мобильная версия: показывать кнопку отклонения (переопределение)"
            ),
            "blocking_mode_until_choice": _("Блокирующий режим до выбора"),
            "mobile_blocking_mode_until_choice": _(
                "Мобильная версия: блокирующий режим до выбора (переопределение)"
            ),
            "hide_launcher_after_decision": _(
                "Скрывать 'Настройки cookie' после выбора пользователя"
            ),
            "mobile_hide_launcher_after_decision": _(
                "Мобильная версия: скрывать 'Настройки cookie' после выбора (переопределение)"
            ),
            "keep_visible_after_accept_all": _(
                "Не закрывать баннер после 'принять все'"
            ),
            "keep_visible_after_required_only": _(
                "Не закрывать баннер после 'только необходимые'"
            ),
            "keep_visible_after_save_custom": _(
                "Не закрывать баннер после 'сохранить выбор'"
            ),
            "mobile_keep_visible_after_accept_all": _(
                "Мобильная версия: не закрывать после 'принять все' (переопределение)"
            ),
            "mobile_keep_visible_after_required_only": _(
                "Мобильная версия: не закрывать после 'только необходимые' (переопределение)"
            ),
            "mobile_keep_visible_after_save_custom": _(
                "Мобильная версия: не закрывать после 'сохранить выбор' (переопределение)"
            ),
            "hide_for_bots_override": _(
                "Скрывать баннер для поисковых/технических ботов"
            ),
            "is_box_template": _("Коробочный шаблон"),
            "is_active": _("Активна"),
            "published_at": _("Дата публикации"),
            "created_at": _("Создана"),
            "updated_at": _("Обновлена"),
        }
        help_texts = {
            "version": _("Версия редакции баннера в версионируемом потоке."),
            "cloned_from": _(
                "Исходная ревизия, если запись создана через процесс клонирования/копирования."
            ),
            "launcher_label": _("Текст кнопки/ссылки открытия настроек cookie."),
            "eyebrow_text": _("Короткий подзаголовок над основным заголовком баннера."),
            "title_text": _("Главный заголовок баннера cookie."),
            "description_text": _(
                "Основное описание назначения cookie и выбора категорий."
            ),
            "reconsent_notice_text": _(
                "Текст уведомления при необходимости re-consent."
            ),
            "reask_notice_text": _(
                "Текст повторного запроса после интервала повторного показа."
            ),
            "accept_all_label": _("Текст кнопки быстрого действия «принять все»."),
            "reject_label": _(
                "Текст кнопки быстрого действия «отказаться от необязательных cookie». "
            ),
            "required_only_label": _("Текст кнопки «только необходимые»."),
            "customize_label": _(
                "Текст кнопки открытия выбора пользовательских категорий."
            ),
            "custom_section_summary": _(
                "Заголовок/summary блока детальной настройки категорий."
            ),
            "required_section_title": _("Заголовок секции обязательных категорий."),
            "required_section_empty_text": _(
                "Текст, если обязательные категории не отображаются."
            ),
            "optional_section_title": _("Заголовок секции необязательных категорий."),
            "optional_section_empty_text": _(
                "Текст, если необязательные категории отсутствуют."
            ),
            "save_custom_label": _(
                "Текст кнопки сохранения пользовательского выбора категорий."
            ),
            "preferences_link_label": _(
                "Текст ссылки на полную страницу настроек cookie."
            ),
            "dismiss_label": _(
                "Скрытый (a11y) текст для кнопки закрытия/сворачивания."
            ),
            "close_tooltip_text": _(
                "Всплывающая подсказка кнопки закрытия блока запуска."
            ),
            "close_aria_label": _("ARIA-метка кнопки закрытия блока запуска."),
            "noscript_text": _("Текст блока для режима без JavaScript."),
            "noscript_link_label": _("Текст ссылки в блоке без JavaScript."),
            "banner_variant": _(
                "Визуальный вариант баннера: полоска, карточка или модальное окно."
            ),
            "consent_ui_variant": _(
                "Вариант интерфейса выбора категорий: встроенный или панель."
            ),
            "reconsent_notice_variant": _(
                "Вариант отображения уведомления о повторном согласии: встроенный или предупреждение."
            ),
            "text_preset_code": _(
                "Выбор текстовой заготовки для основной версии баннера на компьютерах."
            ),
            "mobile_text_preset_code": _(
                "Необязательное переопределение заготовки для мобильной версии; пусто — наследование основной заготовки."
            ),
            "layout_variant": _(
                "Устаревшее поле режима компоновки для обратной совместимости."
            ),
            "theme_variant": _("Устаревшее поле темы для обратной совместимости."),
            "desktop_position": _("Позиция баннера на компьютерах."),
            "mobile_position": _("Позиция баннера на мобильных устройствах."),
            "color_preset": _("Коробочная цветовая заготовка баннера."),
            "custom_bg_color": _("Опциональный HEX #RRGGBB для фона баннера."),
            "custom_text_color": _("Опциональный HEX #RRGGBB для текста баннера."),
            "custom_primary_color": _("Опциональный HEX #RRGGBB для основной кнопки."),
            "custom_primary_text_color": _(
                "Опциональный HEX #RRGGBB для текста основной кнопки."
            ),
            "custom_border_color": _("Опциональный HEX #RRGGBB для границ."),
            "custom_surface_color": _(
                "Опциональный HEX #RRGGBB для вторичной подложки."
            ),
            "custom_overlay_color": _("Опциональный HEX #RRGGBB для фона-затемнения."),
            "panel_padding_px": _(
                "Внутренние отступы панели. Безопасный диапазон: 8..48."
            ),
            "section_gap_px": _(
                "Отступ между секциями формы. Безопасный диапазон: 4..32."
            ),
            "button_gap_px": _("Отступ между кнопками. Безопасный диапазон: 4..24."),
            "overlay_opacity": _(
                "Прозрачность затемнения в процентах. Безопасный диапазон: 0..85."
            ),
            "show_media_slot": _(
                "Включает необязательный медиаблок в заголовке баннера."
            ),
            "media_slot_type": _(
                "Тип медиаблока: эмодзи-иконка или небольшое изображение."
            ),
            "media_icon_emoji": _("Эмодзи для простого сценария с иконкой."),
            "media_image_url": _(
                "Адрес или путь к изображению для медиаблока (без произвольного HTML)."
            ),
            "media_image_alt": _(
                "Альтернативный текст для доступности при использовании режима "
                "изображения."
            ),
            "mobile_banner_variant": _(
                "Необязательное переопределение варианта баннера для мобильной версии; пусто — наследование основной версии."
            ),
            "mobile_consent_ui_variant": _(
                "Необязательное переопределение интерфейса выбора категорий для мобильной версии; пусто — наследование основной версии."
            ),
            "mobile_reconsent_notice_variant": _(
                "Необязательное переопределение уведомления о повторном согласии для мобильной версии; пусто — наследование основной версии."
            ),
            "show_close_control": _(
                "Показывать кнопку закрытия рядом с кнопкой «Настройки cookie»."
            ),
            "close_control_placement": _(
                "Расположение кнопки закрытия относительно текста кнопки «Настройки cookie»."
            ),
            "mobile_close_control_placement": _(
                "Переопределение положения кнопки закрытия для мобильной версии; пусто — наследование основной версии."
            ),
            "show_reject_action": _("Показывать кнопку «Отклонить cookie»."),
            "mobile_show_close_control": _(
                "Переопределение показа кнопки закрытия для мобильной версии; пусто — наследование основной версии."
            ),
            "mobile_show_reject_action": _(
                "Переопределение показа кнопки отклонения для мобильной версии; пусто — наследование основной версии."
            ),
            "blocking_mode_until_choice": _(
                "Блокировать взаимодействие со страницей до первого явного выбора."
            ),
            "mobile_blocking_mode_until_choice": _(
                "Переопределение блокирующего режима для мобильной версии; пусто — наследование основной версии."
            ),
            "hide_launcher_after_decision": _(
                "Скрывать кнопку «Настройки cookie» после сохранённого выбора."
            ),
            "mobile_hide_launcher_after_decision": _(
                "Переопределение скрытия кнопки «Настройки cookie» для мобильной версии; пусто — наследование основной версии."
            ),
            "keep_visible_after_accept_all": _(
                "Если включено, баннер после «принять все» не закрывается и не сворачивается автоматически."
            ),
            "keep_visible_after_required_only": _(
                "Если включено, баннер после «только необходимые» не закрывается и не сворачивается автоматически."
            ),
            "keep_visible_after_save_custom": _(
                "Если включено, баннер после «сохранить выбор» не закрывается и не сворачивается автоматически."
            ),
            "mobile_keep_visible_after_accept_all": _(
                "Переопределение поведения после «принять все» для мобильной версии: оставить баннер открытым; пусто — наследование основной версии."
            ),
            "mobile_keep_visible_after_required_only": _(
                "Переопределение поведения после «только необходимые» для мобильной версии: оставить баннер открытым; пусто — наследование основной версии."
            ),
            "mobile_keep_visible_after_save_custom": _(
                "Переопределение поведения после «сохранить выбор» для мобильной версии: оставить баннер открытым; пусто — наследование основной версии."
            ),
            "hide_for_bots_override": _(
                "Переопределение скрытия для ботов: пусто — использовать `cookie_runtime.hide_for_bots` из настроек; включено — скрывать баннер для запросов с похожим на ботов заголовком User-Agent; выключено — показывать баннер даже ботам."
            ),
            "is_box_template": _("Признак коробочной (поставляемой пакетом) ревизии."),
            "is_active": _("Активная ревизия используется в рабочем режиме."),
            "published_at": _("Дата и время публикации ревизии."),
            "created_at": _("Техническое время создания записи."),
            "updated_at": _("Техническое время последнего обновления."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ensure_default_cookie_banner_text_presets()
        self._configure_mobile_boolean_override_checkboxes()
        self._configure_color_picker_widgets()
        self._widen_text_widgets()

        base_choices = self._build_banner_preset_choices()
        text_field = cast(forms.ChoiceField, self.fields["text_preset_code"])
        mobile_field = cast(forms.ChoiceField, self.fields["mobile_text_preset_code"])

        text_choices = list(base_choices)
        mobile_choices = [("", _("Наследовать основную заготовку"))] + list(
            base_choices
        )

        self._include_existing_preset_code(
            text_choices,
            str(getattr(self.instance, "text_preset_code", "") or ""),
        )
        self._include_existing_preset_code(
            text_choices,
            str(self.initial.get("text_preset_code", "") or ""),
        )
        self._include_existing_preset_code(
            mobile_choices,
            str(getattr(self.instance, "mobile_text_preset_code", "") or ""),
        )
        self._include_existing_preset_code(
            mobile_choices,
            str(self.initial.get("mobile_text_preset_code", "") or ""),
        )

        text_field.widget = forms.Select(choices=text_choices)
        text_field.choices = text_choices
        mobile_field.widget = forms.Select(choices=mobile_choices)
        mobile_field.choices = mobile_choices

        self._allowed_text_preset_codes = {
            str(code) for code, _ in text_choices if str(code)
        }
        self._allowed_mobile_text_preset_codes = {
            str(code) for code, _ in mobile_choices if str(code)
        }
        self._localize_choice_fields()

    def _configure_color_picker_widgets(self) -> None:
        for field_name in self.COLOR_FIELDS:
            field = self.fields.get(field_name)
            if field is None:
                continue
            field.widget = forms.TextInput(
                attrs={
                    "type": "color",
                    "class": "vTextField",
                    "style": "width: 64px; padding: 0;",
                }
            )

    def _widen_text_widgets(self) -> None:
        for field_name in (
            "title_text",
            "description_text",
            "reconsent_notice_text",
            "reask_notice_text",
            "custom_section_summary",
            "required_section_empty_text",
            "optional_section_empty_text",
            "noscript_text",
        ):
            field = self.fields.get(field_name)
            if field is None:
                continue
            widget = field.widget
            widget.attrs["style"] = "width: 100%; max-width: 1200px;"
            if isinstance(widget, forms.Textarea):
                widget.attrs["rows"] = max(int(widget.attrs.get("rows", 0) or 0), 3)

    def _configure_mobile_boolean_override_checkboxes(self) -> None:
        for field_name in self.MOBILE_BOOLEAN_OVERRIDE_FIELDS:
            field = self.fields.get(field_name)
            if field is None:
                continue
            current_value = self._resolve_initial_mobile_override_value(field_name)
            inherit_field_name = f"{field_name}__inherit"
            self.fields[inherit_field_name] = forms.BooleanField(
                required=False,
                initial=current_value is None,
                label=_("Наследовать основное значение"),
                help_text=_(
                    "Если включено, мобильная версия использует значение основной версии."
                ),
            )
            field.widget = forms.CheckboxInput()
            field.required = False
            field.initial = bool(current_value) if current_value is not None else False

    def _resolve_initial_mobile_override_value(self, field_name: str):
        if field_name in self.initial:
            return self.initial.get(field_name)
        if getattr(self.instance, "pk", None):
            return getattr(self.instance, field_name, None)
        return None

    def _localize_choice_fields(self) -> None:
        choice_labels_by_value: dict[str, dict[str, Any]] = {
            "banner_variant": {
                "bar": _("Полоска"),
                "card": _("Карточка"),
                "modal": _("Модальное окно"),
            },
            "mobile_banner_variant": {
                "bar": _("Полоска"),
                "card": _("Карточка"),
                "modal": _("Модальное окно"),
            },
            "consent_ui_variant": {
                "inline": _("Встроенный"),
                "panel": _("Панель"),
            },
            "mobile_consent_ui_variant": {
                "inline": _("Встроенный"),
                "panel": _("Панель"),
            },
            "reconsent_notice_variant": {
                "inline": _("Встроенный"),
                "alert": _("Предупреждение"),
            },
            "mobile_reconsent_notice_variant": {
                "inline": _("Встроенный"),
                "alert": _("Предупреждение"),
            },
            "media_slot_type": {
                "icon": _("Иконка"),
                "image": _("Изображение"),
            },
        }
        for field_name, label_map in choice_labels_by_value.items():
            field = self.fields.get(field_name)
            if field is None:
                continue
            field = cast(forms.ChoiceField, field)
            field_any: Any = field
            localized_choices: list[tuple[str, str]] = []
            for value, label in field_any.choices:
                str_value = str(value or "")
                if str_value in label_map:
                    localized_choices.append((value, str(label_map[str_value])))
                    continue
                if str_value == "":
                    localized_choices.append(
                        (value, str(_("Наследовать основное значение")))
                    )
                    continue
                localized_choices.append((value, str(label)))
            field_any.choices = localized_choices

    @staticmethod
    def _build_banner_preset_choices() -> list[tuple[str, str]]:
        boxed_title_overrides = {
            constants.COOKIE_BANNER_TEXT_PRESET_RU_BALANCED: _("Сбалансированный"),
            constants.COOKIE_BANNER_TEXT_PRESET_RU_FORMAL: _("Формальный"),
            constants.COOKIE_BANNER_TEXT_PRESET_RU_COMPACT: _("Компактный"),
            constants.COOKIE_BANNER_TEXT_PRESET_EN_BALANCED: _("Balanced"),
            constants.COOKIE_BANNER_TEXT_PRESET_EN_FORMAL: _("Formal"),
            constants.COOKIE_BANNER_TEXT_PRESET_EN_COMPACT: _("Compact"),
        }
        choices: list[tuple[str, str]] = []
        for preset in CookieBannerTextPreset.objects.filter(is_active=True).order_by(
            "is_box_template",
            "code",
        ):
            kind = _("коробочный") if preset.is_box_template else _("пользовательский")
            display_title = str(preset.title or "").strip()
            if preset.is_box_template:
                display_title = str(
                    boxed_title_overrides.get(preset.code, display_title)
                )
            choices.append((preset.code, f"{display_title} ({kind})"))
        return choices

    @staticmethod
    def _include_existing_preset_code(
        choices: list[tuple[str, Any]],
        preset_code: str,
    ) -> None:
        code = str(preset_code or "").strip()
        if not code:
            return
        if any(existing_code == code for existing_code, _ in choices):
            return
        choices.append((code, _("Устаревшая заготовка: %(code)s") % {"code": code}))

    def clean_text_preset_code(self) -> str:
        code = str(self.cleaned_data.get("text_preset_code") or "").strip()
        if code not in self._allowed_text_preset_codes:
            raise forms.ValidationError(
                _(
                    "Выберите текстовую заготовку из справочника. Ручной ввод кода не допускается."
                )
            )
        return code

    def clean_mobile_text_preset_code(self) -> str:
        code = str(self.cleaned_data.get("mobile_text_preset_code") or "").strip()
        if not code:
            return ""
        if code not in self._allowed_mobile_text_preset_codes:
            raise forms.ValidationError(
                _(
                    "Выберите заготовку для мобильной версии из справочника или оставьте пустым для наследования."
                )
            )
        return code

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data is None:
            cleaned_data = {}
        for field_name in self.MOBILE_BOOLEAN_OVERRIDE_FIELDS:
            inherit_field_name = f"{field_name}__inherit"
            if bool(cleaned_data.get(inherit_field_name)):
                cleaned_data[field_name] = None
            else:
                cleaned_data[field_name] = bool(cleaned_data.get(field_name))
        return cleaned_data


class CookiePolicyTextPresetAdminForm(forms.ModelForm):
    class Meta:
        model = CookiePolicyTextPreset
        fields = "__all__"
        labels = {
            "code": _("Код заготовки"),
            "title": _("Название заготовки"),
            "content_text": _("Текст заготовки"),
            "is_box_template": _("Коробочная заготовка"),
            "is_active": _("Активен"),
        }
        help_texts = {
            "code": _("Уникальный стабильный код текстовой заготовки политики cookie."),
            "title": _("Служебное название заготовки для админки."),
            "content_text": _(
                "Текст политики cookie, который будет подставляться в редакцию."
            ),
            "is_box_template": _(
                "Отмечает заготовку как коробочную (поставляется пакетом)."
            ),
            "is_active": _("Отключите заготовку, чтобы скрыть её из выбора."),
        }


class CookieBannerTextPresetAdminForm(forms.ModelForm):
    class Meta:
        model = CookieBannerTextPreset
        fields = "__all__"
        labels = {
            "code": _("Код заготовки"),
            "title": _("Название заготовки"),
            "launcher_label": _("Текст кнопки «Настройки cookie»"),
            "eyebrow_text": _("Подзаголовок"),
            "title_text": _("Заголовок"),
            "description_text": _("Описание"),
            "reconsent_notice_text": _("Текст уведомления о повторном согласии"),
            "reask_notice_text": _("Текст повторного запроса"),
            "accept_all_label": _("Кнопка: принять все"),
            "reject_label": _("Кнопка: отказаться от необязательных cookie"),
            "required_only_label": _("Кнопка: только необходимые"),
            "customize_label": _("Кнопка: выбрать категории"),
            "custom_section_summary": _("Заголовок блока выбора категорий"),
            "required_section_title": _("Заголовок обязательных категорий"),
            "required_section_empty_text": _("Пустой текст обязательных"),
            "optional_section_title": _("Заголовок необязательных категорий"),
            "optional_section_empty_text": _("Пустой текст необязательных"),
            "save_custom_label": _("Кнопка: сохранить выбор"),
            "preferences_link_label": _("Ссылка: полная страница"),
            "dismiss_label": _("Скрытый текст кнопки закрытия"),
            "noscript_text": _("Текст no-JS"),
            "noscript_link_label": _("Ссылка no-JS"),
            "is_box_template": _("Коробочная заготовка"),
            "is_active": _("Активен"),
        }
        help_texts = {
            "code": _(
                "Уникальный стабильный код текстовой заготовки интерфейса баннера."
            ),
            "title": _("Служебное название заготовки для админки."),
            "launcher_label": _("Текст кнопки/ссылки открытия настроек cookie."),
            "eyebrow_text": _("Короткий подзаголовок над основным заголовком баннера."),
            "title_text": _("Главный заголовок баннера cookie."),
            "description_text": _(
                "Основное описание назначения cookie и выбора категорий."
            ),
            "reconsent_notice_text": _(
                "Текст уведомления при необходимости повторного согласия."
            ),
            "reask_notice_text": _(
                "Текст повторного запроса после интервала повторного показа."
            ),
            "accept_all_label": _("Текст кнопки быстрого действия «принять все»."),
            "reject_label": _(
                "Текст кнопки быстрого действия «отказаться от необязательных cookie»."
            ),
            "required_only_label": _("Текст кнопки «только необходимые»."),
            "customize_label": _(
                "Текст кнопки открытия выбора пользовательских категорий."
            ),
            "custom_section_summary": _(
                "Заголовок/summary блока детальной настройки категорий."
            ),
            "required_section_title": _("Заголовок секции обязательных категорий."),
            "required_section_empty_text": _(
                "Текст, если обязательные категории не отображаются."
            ),
            "optional_section_title": _("Заголовок секции необязательных категорий."),
            "optional_section_empty_text": _(
                "Текст, если необязательные категории отсутствуют."
            ),
            "save_custom_label": _(
                "Текст кнопки сохранения пользовательского выбора категорий."
            ),
            "preferences_link_label": _(
                "Текст ссылки на полную страницу настроек cookie."
            ),
            "dismiss_label": _(
                "Скрытый (a11y) текст для кнопки закрытия/сворачивания."
            ),
            "noscript_text": _("Текст блока для режима без JavaScript."),
            "noscript_link_label": _("Текст ссылки в блоке для режима без JavaScript."),
            "is_box_template": _(
                "Отмечает заготовку как коробочную (поставляется пакетом)."
            ),
            "is_active": _("Отключите заготовку, чтобы скрыть её из выбора."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in (
            "title_text",
            "description_text",
            "reconsent_notice_text",
            "reask_notice_text",
            "custom_section_summary",
            "required_section_empty_text",
            "optional_section_empty_text",
            "noscript_text",
        ):
            field = self.fields.get(field_name)
            if field is None:
                continue
            widget = field.widget
            widget.attrs["style"] = "width: 100%; max-width: 1200px;"
            if isinstance(widget, forms.Textarea):
                widget.attrs["rows"] = max(int(widget.attrs.get("rows", 0) or 0), 3)


class CookiePolicyRevisionRegistryItemInline(admin.TabularInline):
    """Read-only inline snapshot for a published cookie policy revision."""

    model = CookiePolicyRevisionRegistryItem
    extra = 0
    can_delete = False
    show_change_link = False
    fields = (
        "registry_code",
        "category_code",
        "provider",
        "retention",
        "clear_strategy",
        "src_url",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


class CookieAdminSettingsAdminForm(forms.ModelForm):
    class Meta:
        model = CookieAdminSettings
        fields = "__all__"
        labels = {
            "csv_export_delimiter": _("Разделитель CSV-экспорта"),
            "show_empty_category_block_override": _(
                "Override: show empty category block"
            ),
            "show_customize_action_without_optional_override": _(
                "Override: show customize action without optional categories"
            ),
            "empty_category_block_text_override": _(
                "Override: empty category block text"
            ),
        }
        help_texts = {
            "csv_export_delimiter": _(
                "Разделитель по умолчанию для CSV-экспорта записей и событий cookie-согласия в админке."
            ),
            "show_empty_category_block_override": _(
                "If enabled, shows the empty categories section even when no optional categories are configured. Leave empty to use settings.py value."
            ),
            "show_customize_action_without_optional_override": _(
                "If enabled, keeps the customize action visible even when optional categories are absent. Leave empty to use settings.py value."
            ),
            "empty_category_block_text_override": _(
                "Custom text for the empty categories section. Leave empty to use settings.py value."
            ),
        }


class CookieCategoryAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for cookie categories included in policy snapshots."""

    form = CookieCategoryAdminForm
    change_permission_flags = "can_manage_documents"
    list_display = ("code", "title", "is_required", "sort_order", "is_active")
    list_display_links = ("code", "title")
    list_filter = ("is_required", "is_active")
    search_fields = ("code", "title", "description")


class CookiePolicyRevisionAdmin(
    PublishableRevisionAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Admin for cookie-policy revisions with automatic consent outdate."""

    form = CookiePolicyRevisionAdminForm
    change_list_template = (
        "admin/django_cookies_152fz/cookiepolicyrevision/change_list.html"
    )
    change_permission_flags = "can_publish_revisions"
    view_permission_flags = ("can_publish_revisions", "can_manage_documents")
    list_display = (
        "version",
        "source_revision",
        "format",
        "is_active",
        "is_box_template",
        "published_at",
        "updated_at",
    )
    list_display_links = ("version", "format", "published_at")
    list_filter = ("format", "is_active", "is_box_template")
    search_fields = ("content_text",)
    readonly_fields = (
        "version",
        "cloned_from",
        "is_box_template",
        "published_at",
        "created_at",
        "updated_at",
    )
    inlines = (CookiePolicyRevisionRegistryItemInline,)
    actions = ("clone_selected_revisions_as_drafts",)

    @admin.display(description=_("Исходная ревизия"))
    def source_revision(self, obj) -> str:
        if obj.cloned_from_id:
            return f"v{obj.cloned_from.version}"
        return "—"

    def get_urls(self):
        return [
            path(
                "publish-box-variant/",
                self.admin_site.admin_view(self.publish_box_variant_view),
                name="django_cookies_152fz_cookiepolicyrevision_publish_box_variant",
            ),
            path(
                "create-custom-draft-from-box-variant/",
                self.admin_site.admin_view(
                    self.create_custom_draft_from_box_variant_view
                ),
                name="django_cookies_152fz_cookiepolicyrevision_create_custom_draft",
            ),
            *super().get_urls(),
        ]

    def changelist_view(self, request, extra_context=None):
        context = dict(extra_context or {})
        context["policy_variant_tools"] = self._build_policy_variant_tools()
        return super().changelist_view(request, extra_context=context)

    def _policy_changelist_url(self) -> str:
        return reverse("admin:django_cookies_152fz_cookiepolicyrevision_changelist")

    def _resolve_policy_variant(self, request) -> str:
        return (
            str(request.POST.get("variant") or request.GET.get("variant") or "")
            .strip()
            .lower()
        )

    def _is_known_policy_variant(self, variant: str) -> bool:
        known_variants = {str(code) for code, _ in COOKIE_POLICY_VARIANT_CHOICES}
        return variant in known_variants

    def _build_policy_variant_tools(self) -> list[dict[str, str]]:
        publish_label = str(
            _("Опубликовать выбранный коробочный вариант текста политики")
        )
        draft_label = str(
            _("Создать пользовательский черновик из выбранного коробочного варианта")
        )
        tools: list[dict[str, str]] = []
        for variant_code, variant_title in COOKIE_POLICY_VARIANT_CHOICES:
            variant = str(variant_code)
            title = str(variant_title)
            publish_url = (
                reverse(
                    "admin:django_cookies_152fz_cookiepolicyrevision_publish_box_variant"
                )
                + f"?variant={variant}"
            )
            draft_url = (
                reverse(
                    "admin:django_cookies_152fz_cookiepolicyrevision_create_custom_draft"
                )
                + f"?variant={variant}"
            )
            tools.append(
                {
                    "publish_label": f"{publish_label}: {title}",
                    "publish_url": publish_url,
                    "draft_label": f"{draft_label}: {title}",
                    "draft_url": draft_url,
                }
            )
        return tools

    def publish_box_variant_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        variant = self._resolve_policy_variant(request)
        if not self._is_known_policy_variant(variant):
            self.message_user(
                request,
                _("Выберите вариант текста политики для этого действия."),
                level=messages.ERROR,
            )
            return redirect(self._policy_changelist_url())
        try:
            revision = publish_box_cookie_policy_variant(variant_code=variant)
        except ConsentError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return redirect(self._policy_changelist_url())
        self.message_user(
            request,
            _("Опубликован коробочный вариант политики. Новая ревизия: v%(version)s.")
            % {"version": revision.version},
            level=messages.SUCCESS,
        )
        log_module_operation(
            operation_code="admin.cookies.publish_box_policy_variant",
            actor_user=request.user,
            source="admin.cookies.policy_revision",
            target_model="django_cookies_152fz.CookiePolicyRevision",
            target_id=str(revision.pk),
            summary="Published boxed cookie policy variant.",
            payload={"variant": variant},
            result={"version": revision.version},
        )
        return redirect(self._policy_changelist_url())

    def create_custom_draft_from_box_variant_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        variant = self._resolve_policy_variant(request)
        if not self._is_known_policy_variant(variant):
            self.message_user(
                request,
                _("Выберите вариант текста политики для этого действия."),
                level=messages.ERROR,
            )
            return redirect(self._policy_changelist_url())
        try:
            revision = create_custom_cookie_policy_draft_from_variant(
                variant_code=variant
            )
        except ConsentError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return redirect(self._policy_changelist_url())
        self.message_user(
            request,
            _(
                "Создан пользовательский черновик из коробочного варианта. Ревизия: v%(version)s."
            )
            % {"version": revision.version},
            level=messages.SUCCESS,
        )
        log_module_operation(
            operation_code="admin.cookies.create_custom_draft_policy_variant",
            actor_user=request.user,
            source="admin.cookies.policy_revision",
            target_model="django_cookies_152fz.CookiePolicyRevision",
            target_id=str(revision.pk),
            summary="Created custom draft from boxed cookie policy variant.",
            payload={"variant": variant},
            result={"version": revision.version},
        )
        return redirect(self._policy_changelist_url())

    @admin.action(
        description=_(
            "Клонировать выбранные редакции политики как пользовательские черновики"
        )
    )
    def clone_selected_revisions_as_drafts(self, request, queryset) -> None:
        cloned = 0
        for source_revision in queryset.order_by("pk"):
            clone_cookie_policy_revision_as_draft(source_revision=source_revision)
            cloned += 1
        self.message_user(
            request,
            _("Создано %(count)d черновиков политики из выбранных редакций.")
            % {"count": cloned},
            level=messages.SUCCESS,
        )
        log_module_operation(
            operation_code="admin.cookies.clone_policy_revisions",
            actor_user=request.user,
            source="admin.cookies.policy_revision",
            target_model="django_cookies_152fz.CookiePolicyRevision",
            summary=_(
                "Клонирование выбранных редакций политики в пользовательские черновики."
            ),
            payload={"selected_count": queryset.count()},
            result={"cloned_count": cloned},
        )

    def has_change_permission(self, request, obj=None) -> bool:
        if obj is not None and bool(getattr(obj, "is_box_template", False)):
            return False
        return super().has_change_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and bool(getattr(obj, "is_box_template", False)):
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_queryset(self, request, queryset) -> None:
        protected_count = queryset.filter(is_box_template=True).count()
        deletable_queryset = queryset.exclude(is_box_template=True)
        if protected_count:
            self.message_user(
                request,
                _(
                    "Это коробочная ревизия: защищённые текстовые поля доступны только для чтения. Чтобы редактировать тексты, создайте пользовательскую копию ревизии."
                ),
                level=messages.WARNING,
            )
        if deletable_queryset.exists():
            super().delete_queryset(request, deletable_queryset)

    def save_model(self, request, obj, form, change) -> None:
        """Assign version, publish policy, and outdate previous current records."""

        if not change:
            latest_version = (
                CookiePolicyRevision.objects.order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            )
            self.assign_next_version(obj, latest_version=latest_version)

        if not obj.categories_snapshot:
            obj.categories_snapshot = snapshot_active_cookie_categories()
        self.ensure_published_at(obj, now_value=timezone.now())

        super().save_model(request, obj, form, change)
        sync_cookie_policy_revision_registry_items(policy_revision=obj)

        if obj.is_active:
            CookiePolicyRevision.objects.exclude(pk=obj.pk).update(is_active=False)
            mark_outdated_cookie_consents(
                policy_revision=obj,
                audit_context={"source": "admin.cookies.publish"},
            )
            log_module_operation(
                operation_code="admin.cookies.publish_policy_revision",
                actor_user=request.user,
                source="admin.cookies.policy_revision",
                target_model="django_cookies_152fz.CookiePolicyRevision",
                target_id=str(obj.pk),
                summary="Published cookie policy revision.",
                result={"version": obj.version},
            )


class CookieBannerRevisionAdmin(
    PublishableRevisionAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Admin for published banner text and presentation revisions."""

    form = CookieBannerRevisionAdminForm
    save_as = True
    change_permission_flags = "can_publish_revisions"
    view_permission_flags = ("can_publish_revisions", "can_manage_documents")
    list_display = (
        "version",
        "source_revision",
        "is_active",
        "text_preset_code",
        "mobile_text_preset_code",
        "banner_variant",
        "consent_ui_variant",
        "reconsent_notice_variant",
        "layout_variant",
        "theme_variant",
        "desktop_position",
        "mobile_position",
        "is_box_template",
        "published_at",
        "updated_at",
    )
    list_display_links = ("version", "text_preset_code")
    list_filter = (
        "is_active",
        "text_preset_code",
        "banner_variant",
        "consent_ui_variant",
        "reconsent_notice_variant",
        "layout_variant",
        "theme_variant",
        "desktop_position",
        "mobile_position",
        "is_box_template",
    )
    search_fields = (
        "launcher_label",
        "eyebrow_text",
        "title_text",
        "description_text",
    )
    readonly_fields = ("version", "published_at", "created_at", "updated_at")
    actions = ("clone_selected_revisions_as_drafts",)
    fieldsets = (
        (
            _("Ревизия"),
            {
                "fields": (
                    "version",
                    "cloned_from",
                    "is_active",
                    "is_box_template",
                    ("text_preset_code", "mobile_text_preset_code"),
                    "published_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            _("Тексты"),
            {
                "fields": (
                    "protected_texts_notice",
                    "launcher_label",
                    "eyebrow_text",
                    "title_text",
                    "description_text",
                    "reconsent_notice_text",
                    "reask_notice_text",
                    "accept_all_label",
                    "reject_label",
                    "required_only_label",
                    "customize_label",
                    "custom_section_summary",
                    "required_section_title",
                    "required_section_empty_text",
                    "optional_section_title",
                    "optional_section_empty_text",
                    "save_custom_label",
                    "preferences_link_label",
                    "dismiss_label",
                    "close_tooltip_text",
                    "close_aria_label",
                    "noscript_text",
                    "noscript_link_label",
                )
            },
        ),
        (
            _("Варианты отображения"),
            {
                "fields": (
                    ("banner_variant", "mobile_banner_variant"),
                    ("consent_ui_variant", "mobile_consent_ui_variant"),
                    (
                        "reconsent_notice_variant",
                        "mobile_reconsent_notice_variant",
                    ),
                )
            },
        ),
        (
            _("Визуальная настройка"),
            {
                "fields": (
                    "reset_colors_control",
                    "color_preset",
                    (
                        "custom_bg_color",
                        "custom_text_color",
                        "custom_border_color",
                    ),
                    (
                        "custom_primary_color",
                        "custom_primary_text_color",
                        "custom_surface_color",
                    ),
                    "custom_overlay_color",
                    ("panel_padding_px", "section_gap_px", "button_gap_px"),
                    "overlay_opacity",
                    "show_media_slot",
                    ("media_slot_type", "media_icon_emoji"),
                    ("media_image_url", "media_image_alt"),
                )
            },
        ),
        (
            _("Устаревшие поля совместимости"),
            {
                "description": _(
                    "Поля сохранены для обратной совместимости с прежней схемой "
                    "компоновки, темы и позиционирования."
                ),
                "fields": (
                    "layout_variant",
                    "theme_variant",
                    "desktop_position",
                    "mobile_position",
                ),
            },
        ),
        (
            _("Видимость и кнопка закрытия"),
            {
                "description": _(
                    "Параметры сгруппированы парами: слева — основная версия "
                    "(desktop), справа — мобильное переопределение. "
                    "Кнопка закрытия скрывает баннер без фиксации согласия. "
                    "Параметры видимости после выбора управляют только "
                    "отображением баннера и не меняют статус согласия. "
                    "Блокирующий режим удерживает баннер открытым до явного "
                    "выбора пользователя."
                ),
                "fields": (
                    ("desktop_column_heading", "mobile_column_heading"),
                    ("show_close_control", "mobile_show_close_control"),
                    "mobile_show_close_control__inherit",
                    ("close_control_placement", "mobile_close_control_placement"),
                    ("show_reject_action", "mobile_show_reject_action"),
                    "mobile_show_reject_action__inherit",
                    (
                        "blocking_mode_until_choice",
                        "mobile_blocking_mode_until_choice",
                    ),
                    "mobile_blocking_mode_until_choice__inherit",
                    (
                        "hide_launcher_after_decision",
                        "mobile_hide_launcher_after_decision",
                    ),
                    "mobile_hide_launcher_after_decision__inherit",
                    (
                        "keep_visible_after_accept_all",
                        "mobile_keep_visible_after_accept_all",
                    ),
                    "mobile_keep_visible_after_accept_all__inherit",
                    (
                        "keep_visible_after_required_only",
                        "mobile_keep_visible_after_required_only",
                    ),
                    "mobile_keep_visible_after_required_only__inherit",
                    (
                        "keep_visible_after_save_custom",
                        "mobile_keep_visible_after_save_custom",
                    ),
                    "mobile_keep_visible_after_save_custom__inherit",
                    "hide_for_bots_override",
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        readonly_fields.extend(
            (
                "cloned_from",
                "protected_texts_notice",
                "desktop_column_heading",
                "mobile_column_heading",
                "reset_colors_control",
            )
        )
        if obj is not None and obj.is_box_template:
            readonly_fields.extend(COOKIE_BANNER_PROTECTED_TEXT_FIELDS)
        return tuple(dict.fromkeys(readonly_fields))

    @admin.display(description="")
    def desktop_column_heading(self, obj) -> str:
        return format_html("<strong>{}</strong>", _("Настольная версия"))

    @admin.display(description="")
    def mobile_column_heading(self, obj) -> str:
        return format_html("<strong>{}</strong>", _("Мобильная версия"))

    @admin.display(description=_("Сброс цветовых настроек"))
    def reset_colors_control(self, obj) -> str:
        return format_html(
            '<button type="button" class="button" id="dz152fz-reset-banner-colors">'
            "{}"
            "</button>"
            '<p class="help">{}</p>',
            _("Сбросить цвета по умолчанию"),
            _(
                "Возвращает цветовую заготовку и пользовательские цветовые поля к значениям по умолчанию."
            ),
        )

    @admin.display(description=_("Статус редактирования текстов"))
    def protected_texts_notice(self, obj) -> str:
        if obj is None:
            return str(
                _("Поля текста можно редактировать в пользовательских ревизиях.")
            )
        if obj.is_box_template:
            return format_html(
                "{}",
                _(
                    "Это коробочная ревизия: защищённые текстовые поля доступны только для чтения. Чтобы редактировать тексты, создайте пользовательскую копию ревизии."
                ),
            )
        return str(
            _(
                "Это пользовательская ревизия: все текстовые поля доступны для редактирования."
            )
        )

    @admin.display(description=_("Исходная ревизия"))
    def source_revision(self, obj) -> str:
        if obj.cloned_from_id:
            return f"v{obj.cloned_from.version}"
        return "—"

    @admin.action(
        description=_(
            "Клонировать выбранные редакции баннера как пользовательские черновики"
        )
    )
    def clone_selected_revisions_as_drafts(self, request, queryset) -> None:
        cloned = 0
        for source_revision in queryset.order_by("pk"):
            clone_cookie_banner_revision_as_draft(source_revision=source_revision)
            cloned += 1
        self.message_user(
            request,
            _("Создано %(count)d черновиков баннера из выбранных редакций.")
            % {"count": cloned},
            level=messages.SUCCESS,
        )
        log_module_operation(
            operation_code="admin.cookies.clone_banner_revisions",
            actor_user=request.user,
            source="admin.cookies.banner_revision",
            target_model="django_cookies_152fz.CookieBannerRevision",
            summary=_(
                "Клонирование выбранных редакций баннера в пользовательские черновики."
            ),
            payload={"selected_count": queryset.count()},
            result={"cloned_count": cloned},
        )

    def save_model(self, request, obj, form, change) -> None:
        if not change:
            latest_version = (
                CookieBannerRevision.objects.order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            )
            self.assign_next_version(obj, latest_version=latest_version)

        self.ensure_published_at(obj, now_value=timezone.now())

        super().save_model(request, obj, form, change)

        if obj.is_active:
            CookieBannerRevision.objects.exclude(pk=obj.pk).update(is_active=False)
            log_module_operation(
                operation_code="admin.cookies.publish_banner_revision",
                actor_user=request.user,
                source="admin.cookies.banner_revision",
                target_model="django_cookies_152fz.CookieBannerRevision",
                target_id=str(obj.pk),
                summary="Published cookie banner revision.",
                result={"version": obj.version},
            )

    class Media:
        js = ("django_cookies_152fz/admin/cookie_banner_revision_admin.js",)


class CookieConsentRecordAdmin(
    ReadOnlyAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Read-only admin for cookie consent records."""

    change_permission_flags = None
    list_display = (
        "id",
        "policy_revision",
        "status",
        "subject_display",
        "source",
        "created_at",
        "updated_at",
    )
    list_display_links = ("subject_display", "policy_revision", "status", "created_at")
    list_filter = ("status", "policy_revision")
    search_fields = ("anonymous_token", "request_id", f"user__{USER_LOOKUP}")
    raw_id_fields = ("user", "policy_revision")
    list_select_related = ("user", "policy_revision")

    @admin.display(description=_("Subject"))
    def subject_display(self, obj) -> str:
        """Render authenticated user or anonymous token as subject."""

        if obj.user_id:
            return str(obj.user)
        return obj.anonymous_token


class CookieRegistryItemAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for live cookie/script registry items used by runtime."""

    form = CookieRegistryItemAdminForm
    change_permission_flags = "can_manage_documents"
    list_display = (
        "code",
        "category",
        "provider",
        "clear_strategy",
        "is_active",
    )
    list_display_links = ("code", "category")
    list_filter = ("category", "clear_strategy", "is_active")
    search_fields = (
        "code",
        "category__code",
        "provider",
        "purpose",
        "retention",
        "src_url",
    )
    raw_id_fields = ("category",)


class CookieConsentEventAdmin(
    ReadOnlyAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Read-only admin for cookie consent events."""

    change_permission_flags = None
    actions = ("export_selected_records",)
    list_display = (
        "id",
        "cookie_consent_record",
        "event_type",
        "source",
        "occurred_at",
    )
    list_display_links = (
        "cookie_consent_record",
        "event_type",
        "source",
        "occurred_at",
    )
    list_filter = ("event_type", "source")
    search_fields = ("request_id", "cookie_consent_record__anonymous_token")
    raw_id_fields = ("cookie_consent_record",)
    list_select_related = (
        "cookie_consent_record",
        "cookie_consent_record__user",
        "cookie_consent_record__policy_revision",
    )

    @admin.action(
        description=_("Экспортировать выбранные события в CSV"),
        permissions=["view"],
    )
    def export_selected_records(self, request, queryset) -> HttpResponse:
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            'attachment; filename="cookie-consent-events.csv"'
        )
        writer = csv.writer(response, delimiter=_resolve_cookie_csv_delimiter())
        writer.writerow(
            [
                "id",
                "cookie_consent_record_id",
                "event_type",
                "source",
                "ip_address",
                "user_agent",
                "locale",
                "request_id",
                "session_key_hash",
                "payload",
                "extra_meta",
                "occurred_at",
                "created_at",
            ]
        )
        for event in queryset.order_by("id"):
            writer.writerow(
                [
                    event.pk,
                    event.cookie_consent_record_id,
                    _sanitize_csv_cell(event.event_type),
                    _sanitize_csv_cell(event.source),
                    _sanitize_csv_cell(event.ip_address or ""),
                    _sanitize_csv_cell(event.user_agent),
                    _sanitize_csv_cell(event.locale),
                    _sanitize_csv_cell(event.request_id),
                    _sanitize_csv_cell(event.session_key_hash),
                    _sanitize_csv_cell(
                        json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
                    ),
                    _sanitize_csv_cell(
                        json.dumps(event.extra_meta, ensure_ascii=False, sort_keys=True)
                    ),
                    event.occurred_at.isoformat(),
                    event.created_at.isoformat(),
                ]
            )
        return response

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def has_view_permission(self, request, obj=None) -> bool:
        return super().has_view_permission(request, obj=obj)


class CookieAdminSettingsAdmin(
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Admin for singleton cookie admin settings."""

    form = CookieAdminSettingsAdminForm
    superuser_only = True
    list_display = (
        "csv_export_delimiter",
        "show_empty_category_block_override",
        "show_customize_action_without_optional_override",
        "updated_at",
    )
    list_display_links = ("csv_export_delimiter",)
    fields = (
        "csv_export_delimiter",
        "show_empty_category_block_override",
        "show_customize_action_without_optional_override",
        "empty_category_block_text_override",
    )

    def has_add_permission(self, request) -> bool:
        if not super().has_add_permission(request):
            return False
        return not CookieAdminSettings.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class CookiePolicyRevisionRegistryItemAdmin(
    ReadOnlyAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Read-only admin for registry snapshots of cookie policy revisions."""

    change_permission_flags = None
    list_display = (
        "id",
        "policy_revision",
        "registry_code",
        "category_code",
        "provider",
        "clear_strategy",
    )
    list_display_links = ("registry_code", "category_code", "policy_revision")
    list_filter = ("category_code", "clear_strategy", "policy_revision")
    search_fields = (
        "registry_code",
        "category_code",
        "provider",
        "purpose",
        "src_url",
    )
    raw_id_fields = ("policy_revision", "registry_item")


class CookieBannerStateAdmin(
    ReadOnlyAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Read-only admin for server-side banner lifecycle state."""

    change_permission_flags = None
    list_display = (
        "id",
        "subject_display",
        "decision_action",
        "dismissed_at",
        "decided_at",
        "updated_at",
    )
    list_display_links = (
        "subject_display",
        "decision_action",
        "decided_at",
        "updated_at",
    )
    list_filter = ("decision_action",)
    search_fields = ("anonymous_token", f"user__{USER_LOOKUP}")
    raw_id_fields = ("user",)
    list_select_related = ("user",)

    @admin.display(description=_("Subject"))
    def subject_display(self, obj) -> str:
        if obj.user_id:
            return str(obj.user)
        return str(obj.anonymous_token or "")


class CookiePolicyTextPresetAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for editable cookie policy text presets."""

    change_permission_flags = "can_manage_documents"
    form = CookiePolicyTextPresetAdminForm
    list_display = ("code", "title", "is_box_template", "is_active", "updated_at")
    list_display_links = ("code", "title")
    list_filter = ("is_box_template", "is_active")
    search_fields = ("code", "title", "content_text")
    readonly_fields = ("is_box_template",)
    actions = ("clone_selected_as_custom_presets",)

    @admin.action(description=_("Clone selected policy presets as custom presets"))
    def clone_selected_as_custom_presets(self, request, queryset) -> None:
        cloned = 0
        for preset in queryset.order_by("pk"):
            base_code = f"{preset.code}_custom"
            code = base_code
            index = 1
            while CookiePolicyTextPreset.objects.filter(code=code).exists():
                index += 1
                code = f"{base_code}_{index}"
            CookiePolicyTextPreset.objects.create(
                code=code,
                title=f"{preset.title} ({_('копия')})",
                content_text=preset.content_text,
                is_box_template=False,
                is_active=True,
            )
            cloned += 1
        self.message_user(
            request,
            _("Created %(count)d custom policy presets.") % {"count": cloned},
            level=messages.SUCCESS,
        )

    def changelist_view(self, request, extra_context=None):
        ensure_default_cookie_policy_text_presets()
        return super().changelist_view(request, extra_context=extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        ensure_default_cookie_policy_text_presets()
        return super().add_view(
            request,
            form_url=form_url,
            extra_context=extra_context,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        ensure_default_cookie_policy_text_presets()
        return super().change_view(
            request,
            object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    def has_change_permission(self, request, obj=None) -> bool:
        if obj is not None and bool(getattr(obj, "is_box_template", False)):
            return False
        return super().has_change_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and bool(getattr(obj, "is_box_template", False)):
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_queryset(self, request, queryset) -> None:
        protected_count = queryset.filter(is_box_template=True).count()
        deletable_queryset = queryset.exclude(is_box_template=True)
        if protected_count:
            self.message_user(
                request,
                _(
                    "Это коробочная ревизия: защищённые текстовые поля доступны только для чтения. Чтобы редактировать тексты, создайте пользовательскую копию ревизии."
                ),
                level=messages.WARNING,
            )
        if deletable_queryset.exists():
            super().delete_queryset(request, deletable_queryset)


class CookieBannerTextPresetAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for editable cookie banner text presets."""

    change_permission_flags = "can_manage_documents"
    form = CookieBannerTextPresetAdminForm
    list_display = ("code", "title", "is_box_template", "is_active", "updated_at")
    list_display_links = ("code", "title")
    list_filter = ("is_box_template", "is_active")
    search_fields = ("code", "title")
    readonly_fields = ("is_box_template",)
    actions = ("clone_selected_as_custom_presets",)

    @admin.action(description=_("Clone selected banner presets as custom presets"))
    def clone_selected_as_custom_presets(self, request, queryset) -> None:
        cloned = 0
        for preset in queryset.order_by("pk"):
            base_code = f"{preset.code}_custom"
            code = base_code
            index = 1
            while CookieBannerTextPreset.objects.filter(code=code).exists():
                index += 1
                code = f"{base_code}_{index}"
            clone = CookieBannerTextPreset.objects.create(
                code=code,
                title=f"{preset.title} ({_('копия')})",
                launcher_label=preset.launcher_label,
                eyebrow_text=preset.eyebrow_text,
                title_text=preset.title_text,
                description_text=preset.description_text,
                reconsent_notice_text=preset.reconsent_notice_text,
                reask_notice_text=preset.reask_notice_text,
                accept_all_label=preset.accept_all_label,
                reject_label=preset.reject_label,
                required_only_label=preset.required_only_label,
                customize_label=preset.customize_label,
                custom_section_summary=preset.custom_section_summary,
                required_section_title=preset.required_section_title,
                required_section_empty_text=preset.required_section_empty_text,
                optional_section_title=preset.optional_section_title,
                optional_section_empty_text=preset.optional_section_empty_text,
                save_custom_label=preset.save_custom_label,
                preferences_link_label=preset.preferences_link_label,
                dismiss_label=preset.dismiss_label,
                noscript_text=preset.noscript_text,
                noscript_link_label=preset.noscript_link_label,
                is_box_template=False,
                is_active=True,
            )
            cloned += 1
            del clone
        self.message_user(
            request,
            _("Created %(count)d custom banner presets.") % {"count": cloned},
            level=messages.SUCCESS,
        )

    def changelist_view(self, request, extra_context=None):
        ensure_default_cookie_banner_text_presets()
        return super().changelist_view(request, extra_context=extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        ensure_default_cookie_banner_text_presets()
        return super().add_view(
            request,
            form_url=form_url,
            extra_context=extra_context,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        ensure_default_cookie_banner_text_presets()
        return super().change_view(
            request,
            object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    def has_change_permission(self, request, obj=None) -> bool:
        if obj is not None and bool(getattr(obj, "is_box_template", False)):
            return False
        return super().has_change_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and bool(getattr(obj, "is_box_template", False)):
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_queryset(self, request, queryset) -> None:
        protected_count = queryset.filter(is_box_template=True).count()
        deletable_queryset = queryset.exclude(is_box_template=True)
        if protected_count:
            self.message_user(
                request,
                _(
                    "Это коробочная ревизия: защищённые текстовые поля доступны только для чтения. Чтобы редактировать тексты, создайте пользовательскую копию ревизии."
                ),
                level=messages.WARNING,
            )
        if deletable_queryset.exists():
            super().delete_queryset(request, deletable_queryset)


def register_admin(site: admin.sites.AdminSite) -> None:
    """Register cookie admin models via explicit app-level contract."""

    safe_register_admin_models(
        site,
        registrations=(
            (CookieAdminSettings, CookieAdminSettingsAdmin),
            (CookieCategory, CookieCategoryAdmin),
            (CookiePolicyRevision, CookiePolicyRevisionAdmin),
            (CookieBannerRevision, CookieBannerRevisionAdmin),
            (CookieConsentRecord, CookieConsentRecordAdmin),
            (CookieRegistryItem, CookieRegistryItemAdmin),
            (CookieConsentEvent, CookieConsentEventAdmin),
            (CookiePolicyRevisionRegistryItem, CookiePolicyRevisionRegistryItemAdmin),
            (CookieBannerState, CookieBannerStateAdmin),
            (CookiePolicyTextPreset, CookiePolicyTextPresetAdmin),
            (CookieBannerTextPreset, CookieBannerTextPresetAdmin),
        ),
    )


register_admin(admin.site)
