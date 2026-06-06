"Cookie module models: categories, policy revisions, banner, and audit events."

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import cast
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .integration_contract import constants

_COOKIE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_AUDIT_JSON_FIELD_BYTES = 64 * 1024
# Root keys written by the system itself (importers → import_meta,
# retention → retention_private). User-supplied extra_meta/payload must not
# override them, otherwise the dedup fingerprint or private markers can be forged.
_RESERVED_AUDIT_ROOT_KEYS = frozenset({"retention_private", "import_meta"})
DEFAULT_COOKIE_BANNER_REVISION_TEXTS: dict[str, object] = {
    "launcher_label": _("Настройки cookie"),
    "eyebrow_text": _("Настройки cookie"),
    "title_text": (
        _("Мы используем cookie для работы сайта и настройки дополнительных категорий.")
    ),
    "description_text": (
        _(
            "Обязательные категории включены всегда. Необязательные категории "
            "можно разрешить сразу, оставить выключенными или выбрать вручную."
        )
    ),
    "reconsent_notice_text": (
        _("Доступна новая редакция cookie-policy. Обновите свой выбор категорий.")
    ),
    "reask_notice_text": (
        _(
            "Мы периодически уточняем выбор cookie-категорий. Подтвердите или "
            "обновите настройки."
        )
    ),
    "accept_all_label": _("Принять все"),
    "reject_label": _("Отказаться от необязательных cookie"),
    "required_only_label": _("Только необходимые cookie"),
    "customize_label": _("Выбрать категории"),
    "custom_section_summary": _("Собственный выбор категорий"),
    "required_section_title": _("Обязательные категории"),
    "required_section_empty_text": _("Нет обязательных категорий."),
    "optional_section_title": _("Необязательные категории"),
    "optional_section_empty_text": (
        _("Сейчас нет дополнительных категорий для выбора.")
    ),
    "save_custom_label": _("Сохранить выбор"),
    "preferences_link_label": _("Полная страница настроек"),
    "dismiss_label": _("Свернуть"),
    "noscript_text": _("Если JavaScript отключён, можно открыть"),
    "noscript_link_label": _("страницу настроек cookie"),
}
COOKIE_BANNER_TEXT_FIELDS = (
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
    "noscript_text",
    "noscript_link_label",
)
# Fields that are safe to edit via the admin/UI templates.
COOKIE_BANNER_EDITABLE_TEXT_FIELDS = (
    "launcher_label",
    "eyebrow_text",
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
    "noscript_text",
    "noscript_link_label",
)
# Fields with legally agreed wording; changed only deliberately.
COOKIE_BANNER_PROTECTED_TEXT_FIELDS = (
    "title_text",
    "description_text",
    "reconsent_notice_text",
    "reask_notice_text",
)

COOKIE_BANNER_TEXT_PRESETS: dict[str, dict[str, object]] = {
    constants.COOKIE_BANNER_TEXT_PRESET_RU_BALANCED: dict(
        DEFAULT_COOKIE_BANNER_REVISION_TEXTS
    ),
    constants.COOKIE_BANNER_TEXT_PRESET_RU_FORMAL: {
        **DEFAULT_COOKIE_BANNER_REVISION_TEXTS,
        "launcher_label": _("Управление cookie"),
        "eyebrow_text": _("Cookie-настройки"),
        "accept_all_label": _("Разрешить все"),
        "required_only_label": _("Оставить только обязательные"),
        "customize_label": _("Настроить выбор"),
    },
    constants.COOKIE_BANNER_TEXT_PRESET_RU_COMPACT: {
        **DEFAULT_COOKIE_BANNER_REVISION_TEXTS,
        "launcher_label": _("Cookie"),
        "eyebrow_text": _("Cookie"),
        "description_text": (
            _(
                "Обязательные cookie включены всегда. Дополнительные можно "
                "включить или оставить отключёнными."
            )
        ),
        "customize_label": _("Выбрать вручную"),
        "custom_section_summary": _("Точный выбор"),
        "save_custom_label": _("Сохранить"),
    },
}

COOKIE_BANNER_TEXT_PRESETS.update(
    {
        constants.COOKIE_BANNER_TEXT_PRESET_EN_BALANCED: {
            "launcher_label": "Cookie settings",
            "eyebrow_text": "Cookie settings",
            "title_text": "We use cookies to run the site and to manage optional categories.",
            "description_text": (
                "Required categories are always enabled. Optional categories can be "
                "allowed all at once, kept disabled, or configured manually."
            ),
            "reconsent_notice_text": (
                "A new cookie policy revision is available. Please review and update your selection."
            ),
            "reask_notice_text": (
                "We periodically ask to confirm cookie categories. Please confirm or update your settings."
            ),
            "accept_all_label": "Accept all",
            "reject_label": "Reject optional cookies",
            "required_only_label": "Required only",
            "customize_label": "Customize",
            "custom_section_summary": "Custom category selection",
            "required_section_title": "Required categories",
            "required_section_empty_text": "No required categories are configured.",
            "optional_section_title": "Optional categories",
            "optional_section_empty_text": "No optional categories are available now.",
            "save_custom_label": "Save selection",
            "preferences_link_label": "Open full preferences page",
            "dismiss_label": "Dismiss",
            "noscript_text": "If JavaScript is disabled, open the",
            "noscript_link_label": "cookie settings page",
        },
        constants.COOKIE_BANNER_TEXT_PRESET_EN_FORMAL: {
            "launcher_label": "Cookie management",
            "eyebrow_text": "Cookie preferences",
            "title_text": (
                "This site uses cookies to ensure operation and to manage optional categories."
            ),
            "description_text": (
                "Required categories remain enabled at all times. Optional categories are "
                "processed only after your explicit selection."
            ),
            "reconsent_notice_text": (
                "An updated cookie policy revision is now active. Please refresh your choice."
            ),
            "reask_notice_text": (
                "Cookie preferences require periodic confirmation. Please confirm or update your choice."
            ),
            "accept_all_label": "Allow all",
            "reject_label": "Keep optional disabled",
            "required_only_label": "Required only",
            "customize_label": "Configure manually",
            "custom_section_summary": "Detailed category control",
            "required_section_title": "Required categories",
            "required_section_empty_text": "Required categories are not configured.",
            "optional_section_title": "Optional categories",
            "optional_section_empty_text": "No optional categories are currently available.",
            "save_custom_label": "Save settings",
            "preferences_link_label": "Open full preferences page",
            "dismiss_label": "Close",
            "noscript_text": "JavaScript is disabled. Open the",
            "noscript_link_label": "cookie settings page",
        },
        constants.COOKIE_BANNER_TEXT_PRESET_EN_COMPACT: {
            "launcher_label": "Cookies",
            "eyebrow_text": "Cookies",
            "title_text": "Choose how optional cookies are used on this site.",
            "description_text": (
                "Required cookies stay enabled. You can accept optional cookies or keep them disabled."
            ),
            "reconsent_notice_text": "Cookie policy was updated. Please review your choice.",
            "reask_notice_text": "Please confirm your cookie settings.",
            "accept_all_label": "Accept all",
            "reject_label": "Reject optional",
            "required_only_label": "Required only",
            "customize_label": "Custom",
            "custom_section_summary": "Custom selection",
            "required_section_title": "Required",
            "required_section_empty_text": "No required categories.",
            "optional_section_title": "Optional",
            "optional_section_empty_text": "No optional categories.",
            "save_custom_label": "Save",
            "preferences_link_label": "Full settings page",
            "dismiss_label": "Hide",
            "noscript_text": "JavaScript is disabled. Open",
            "noscript_link_label": "cookie settings",
        },
    }
)

DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION = {
    "banner_variant": constants.COOKIE_BANNER_VARIANT_CARD,
    "consent_ui_variant": constants.COOKIE_BANNER_CONSENT_UI_VARIANT_PANEL,
    "reconsent_notice_variant": (
        constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_INLINE
    ),
    "text_preset_code": constants.COOKIE_BANNER_TEXT_PRESET_AUTO,
    "layout_variant": "compact",
    "theme_variant": "light",
    "desktop_position": "bottom_right",
    "mobile_position": "bottom",
    "mobile_text_preset_code": "",
    "mobile_banner_variant": "",
    "mobile_consent_ui_variant": "",
    "mobile_reconsent_notice_variant": "",
    "mobile_close_control_placement": "",
    "color_preset": "light",
    "custom_bg_color": "",
    "custom_text_color": "",
    "custom_primary_color": "",
    "custom_primary_text_color": "",
    "custom_border_color": "",
    "custom_surface_color": "",
    "custom_overlay_color": "",
    "panel_padding_px": 20,
    "section_gap_px": 14,
    "button_gap_px": 10,
    "overlay_opacity": 55,
    "show_media_slot": False,
    "media_slot_type": "icon",
    "media_icon_emoji": "🍪",
    "media_image_url": "",
    "media_image_alt": _("Иконка cookie"),
}
DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR = {
    "show_close_control": True,
    "close_control_placement": "right",
    "show_reject_action": False,
    "blocking_mode_until_choice": False,
    "hide_launcher_after_decision": False,
    "keep_visible_after_accept_all": False,
    "keep_visible_after_required_only": False,
    "keep_visible_after_save_custom": False,
    "mobile_show_close_control": None,
    "mobile_show_reject_action": None,
    "mobile_blocking_mode_until_choice": None,
    "mobile_hide_launcher_after_decision": None,
    "mobile_keep_visible_after_accept_all": None,
    "mobile_keep_visible_after_required_only": None,
    "mobile_keep_visible_after_save_custom": None,
    "hide_for_bots_override": None,
    "close_tooltip_text": _("Закрыть баннер cookie"),
    "close_aria_label": _("Закрыть баннер cookie"),
}

DEFAULT_COOKIE_POLICY_TEXT_PRESETS = {
    "short": {
        "title": _("Короткий коробочный текст политики cookie"),
    },
    "full": {
        "title": _("Полный коробочный текст политики cookie"),
    },
}


def _normalize_codes(values: Iterable[str]) -> list[str]:
    "Normalizes a list of category codes and removes duplicates while preserving order."

    normalized: list[str] = []
    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            continue
        if not _COOKIE_CODE_RE.fullmatch(value):
            raise ValidationError(
                _(
                    'Код cookie "%(value)s" должен соответствовать шаблону "[a-z][a-z0-9_]*".'
                )
                % {"value": value}
            )
        if value not in normalized:
            normalized.append(value)
    return normalized


def _validate_audit_json_object(
    *,
    field_name: str,
    value: object,
    reserved_root_keys: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    if not isinstance(value, dict):
        return _('Поле "%(field_name)s" должно содержать JSON-объект.') % {
            "field_name": field_name
        }
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(payload.encode("utf-8")) > _MAX_AUDIT_JSON_FIELD_BYTES:
        return _(
            'Поле "%(field_name)s" превышает лимит %(limit)s байт для JSON-значения.'
        ) % {"field_name": field_name, "limit": _MAX_AUDIT_JSON_FIELD_BYTES}
    conflict_keys = sorted(set(value).intersection(reserved_root_keys))
    if conflict_keys:
        return _(
            'Поле "%(field_name)s" содержит зарезервированные ключи: %(keys)s.'
        ) % {"field_name": field_name, "keys": ", ".join(conflict_keys)}
    return None


def _normalize_string_list(
    values: object,
    *,
    field_name: str,
) -> list[str]:
    "Validates that the value is a list of non-empty strings."

    if not isinstance(values, list):
        raise ValidationError(
            _('Поле "%(field_name)s" должно быть списком.') % {"field_name": field_name}
        )

    normalized: list[str] = []
    for index, raw_value in enumerate(values):
        value = str(raw_value).strip()
        if not value:
            raise ValidationError(
                _('Элемент "%(field_name)s[%(index)s]" должен быть непустой строкой.')
                % {"field_name": field_name, "index": index}
            )
        if value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_src_url(value: object, *, field_name: str = "src_url") -> str:
    "Allows only a URL/path to a script and blocks inline/executable values."

    normalized = str(value or "").strip()
    if normalized and not _is_allowed_absolute_or_root_relative_url(normalized):
        raise ValidationError(
            _('Поле "%(field_name)s" должно содержать только URL/путь к скрипту.')
            % {"field_name": field_name}
        )
    return normalized


def _is_allowed_absolute_or_root_relative_url(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    if normalized.startswith("/"):
        return not normalized.startswith("//")
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def _normalize_non_empty_text(value: object, *, field_name: str) -> str:
    "Converts the value to a string and validates that it is not empty."

    normalized = str(value or "").strip()
    if not normalized:
        raise ValidationError(
            _('Поле "%(field_name)s" не может быть пустым.')
            % {"field_name": field_name}
        )
    return normalized


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    "Converts a #RRGGBB hex color to an RGB tuple."

    color = str(hex_color or "").strip().lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _relative_luminance(hex_color: str) -> float:
    "Calculates the relative luminance of a color using the WCAG formula."

    def _to_linear(channel: int) -> float:
        value = channel / 255.0
        if value <= 0.03928:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = _hex_to_rgb(hex_color)
    return (
        0.2126 * _to_linear(red)
        + 0.7152 * _to_linear(green)
        + 0.0722 * _to_linear(blue)
    )


def _has_min_contrast(
    bg_color: str, text_color: str, *, min_ratio: float = 4.5
) -> bool:
    "Checks the minimum contrast ratio between background and text colors."

    bg_lum = _relative_luminance(bg_color)
    text_lum = _relative_luminance(text_color)
    lighter = max(bg_lum, text_lum)
    darker = min(bg_lum, text_lum)
    ratio = (lighter + 0.05) / (darker + 0.05)
    return ratio >= min_ratio


class CookieCategory(models.Model):
    "A cookie category in the registry and policy (required/optional)."

    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Cookie-категория")
        verbose_name_plural = _("Cookie-категории")
        ordering = ["sort_order", "code"]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()
        if not _COOKIE_CODE_RE.fullmatch(self.code):
            raise ValidationError(
                {"code": _('code должен соответствовать шаблону "[a-z][a-z0-9_]*".')}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class CookiePolicyRevision(models.Model):
    "A versioned revision of the cookie-policy page/document."

    class ContentFormat(models.TextChoices):
        PLAIN_TEXT = "plain_text", _("Обычный текст")
        MARKDOWN = "markdown", _("Разметка Markdown")
        HTML = "html", _("Разметка HTML")
        PDF_FILE = "pdf_file", _("PDF-файл")

    class MediaSlotType(models.TextChoices):
        ICON = "icon", _("Иконка")
        IMAGE = "image", _("Изображение")

    version = models.PositiveIntegerField(default=1, unique=True)
    format = models.CharField(
        max_length=32,
        choices=ContentFormat.choices,
        default=ContentFormat.PLAIN_TEXT,
    )
    content_text = models.TextField(blank=True)
    content_file = models.FileField(
        upload_to="django_cookies_152fz/policies/",
        blank=True,
    )
    categories_snapshot = models.JSONField(default=list)
    cloned_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cloned_revisions",
        verbose_name=_("Скопировано из редакции"),
    )
    is_active = models.BooleanField(default=True)
    is_box_template = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Редакция cookie-policy")
        verbose_name_plural = _("Редакции cookie-policy")
        ordering = ["-published_at", "-version", "-id"]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()

        text_formats = {
            self.ContentFormat.PLAIN_TEXT,
            self.ContentFormat.MARKDOWN,
            self.ContentFormat.HTML,
        }
        text_value = (self.content_text or "").strip()
        has_file = bool(self.content_file)
        errors: dict[str, object] = {}

        if self.format in text_formats:
            if not text_value:
                errors["content_text"] = _(
                    "content_text обязателен для текстовых форматов."
                )
            if has_file:
                errors["content_file"] = _(
                    "content_file должен быть пустым для текстовых форматов."
                )

        if self.format == self.ContentFormat.PDF_FILE:
            if not has_file:
                errors["content_file"] = _(
                    "content_file обязателен для формата pdf_file."
                )
            if text_value:
                errors["content_text"] = _(
                    "content_text должен быть пустым для формата pdf_file."
                )

        try:
            self.categories_snapshot = normalize_categories_snapshot(
                self.categories_snapshot
            )
        except ValidationError as exc:
            errors["categories_snapshot"] = str(exc)

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"cookie-policy:v{self.version}"


class CookiePolicyTextPreset(models.Model):
    "A text preset for quickly creating a cookie-policy draft."

    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=255)
    content_text = models.TextField()
    is_box_template = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Текстовая заготовка политики cookie")
        verbose_name_plural = _("Текстовые заготовки политики cookie")
        ordering = ["code", "-id"]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()
        self.code = str(self.code or "").strip().lower()
        self.title = str(self.title or "").strip()
        self.content_text = str(self.content_text or "")
        errors: dict[str, object] = {}
        if not self.code:
            errors["code"] = _("code не может быть пустым.")
        if not self.title:
            errors["title"] = _("title не может быть пустым.")
        if not self.content_text.strip():
            errors["content_text"] = _("content_text не может быть пустым.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class CookieRegistryItem(models.Model):
    "An entry in the technical cookie/script registry with metadata and cleanup settings."

    class ClearStrategy(models.TextChoices):
        NONE = "none", _("Нет")
        BEST_EFFORT_DELETE = "best_effort_delete", _("Удалить по возможности")
        ADAPTER_HOOK = "adapter_hook", _("Хук адаптера")

    code = models.CharField(max_length=64, unique=True)
    category = models.ForeignKey(
        CookieCategory,
        on_delete=models.PROTECT,
        related_name="registry_items",
    )
    provider = models.CharField(max_length=255)
    purpose = models.TextField()
    retention = models.CharField(max_length=255, blank=True)
    cookie_names = models.JSONField(default=list, blank=True)
    src_url = models.CharField(max_length=500, blank=True)
    clear_strategy = models.CharField(
        max_length=32,
        choices=ClearStrategy.choices,
        default=ClearStrategy.NONE,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Элемент cookie-реестра")
        verbose_name_plural = _("Элементы cookie-реестра")
        ordering = ["code"]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()

        errors: dict[str, object] = {}
        if not _COOKIE_CODE_RE.fullmatch(self.code):
            errors["code"] = _('code должен соответствовать шаблону "[a-z][a-z0-9_]*".')

        self.provider = str(self.provider or "").strip()
        if not self.provider:
            errors["provider"] = _("provider не может быть пустым.")

        self.purpose = str(self.purpose or "").strip()
        if not self.purpose:
            errors["purpose"] = _("purpose не может быть пустым.")

        self.retention = str(self.retention or "").strip()

        try:
            self.cookie_names = _normalize_string_list(
                self.cookie_names,
                field_name="cookie_names",
            )
        except ValidationError as exc:
            errors["cookie_names"] = str(exc)

        try:
            # Comment
            self.src_url = _normalize_src_url(self.src_url)
        except ValidationError as exc:
            errors["src_url"] = str(exc)

        if (
            self.is_active
            and self.category_id  # pyright: ignore[reportAttributeAccessIssue]
            and not bool(self.category.is_active)
        ):
            errors["category"] = _(
                "Активный элемент реестра требует активную cookie-категорию."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class CookiePolicyRevisionRegistryItem(models.Model):
    "A registry item snapshot bound to a specific policy revision."

    policy_revision = models.ForeignKey(
        CookiePolicyRevision,
        on_delete=models.CASCADE,
        related_name="registry_items",
    )
    registry_item = models.ForeignKey(
        CookieRegistryItem,
        on_delete=models.PROTECT,
        related_name="revision_snapshots",
    )
    registry_code = models.CharField(max_length=64)
    category_code = models.CharField(max_length=64)
    provider = models.CharField(max_length=255)
    purpose = models.TextField()
    retention = models.CharField(max_length=255, blank=True)
    cookie_names = models.JSONField(default=list, blank=True)
    src_url = models.CharField(max_length=500, blank=True)
    clear_strategy = models.CharField(
        max_length=32,
        choices=CookieRegistryItem.ClearStrategy.choices,
        default=CookieRegistryItem.ClearStrategy.NONE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Элемент реестра редакции cookie-policy")
        verbose_name_plural = _("Элементы реестра редакции cookie-policy")
        ordering = ["category_code", "registry_code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["policy_revision", "registry_item"],
                name="cookie_policy_revision_registry_item_unique_link",
            ),
        ]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()

        errors: dict[str, object] = {}
        if not _COOKIE_CODE_RE.fullmatch(self.registry_code):
            errors["registry_code"] = _(
                'registry_code должен соответствовать шаблону "[a-z][a-z0-9_]*".'
            )
        if not _COOKIE_CODE_RE.fullmatch(self.category_code):
            errors["category_code"] = _(
                'category_code должен соответствовать шаблону "[a-z][a-z0-9_]*".'
            )

        self.provider = str(self.provider or "").strip()
        if not self.provider:
            errors["provider"] = _("provider не может быть пустым.")

        self.purpose = str(self.purpose or "").strip()
        if not self.purpose:
            errors["purpose"] = _("purpose не может быть пустым.")

        self.retention = str(self.retention or "").strip()

        try:
            self.cookie_names = _normalize_string_list(
                self.cookie_names,
                field_name="cookie_names",
            )
        except ValidationError as exc:
            errors["cookie_names"] = str(exc)

        try:
            self.src_url = _normalize_src_url(self.src_url)
        except ValidationError as exc:
            errors["src_url"] = str(exc)

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.policy_revision}:{self.registry_code}"


class CookieBannerRevision(models.Model):
    "A versioned configuration of the cookie banner and its behaviour."

    class LayoutVariant(models.TextChoices):
        COMPACT = "compact", _("Компактный")
        WIDE = "wide", _("Широкий")

    class ThemeVariant(models.TextChoices):
        LIGHT = "light", _("Светлый")
        CONTRAST = "contrast", _("Контрастный")

    class DesktopPosition(models.TextChoices):
        BOTTOM_RIGHT = "bottom_right", _("Снизу справа")
        BOTTOM_LEFT = "bottom_left", _("Снизу слева")
        CENTER = "center", _("По центру экрана")
        BOTTOM_FULLWIDTH = "bottom_fullwidth", _("Снизу на всю ширину")

    class MobilePosition(models.TextChoices):
        BOTTOM = "bottom", _("Снизу")
        TOP = "top", _("Сверху")
        CENTER = "center", _("По центру экрана")
        BOTTOM_FULLWIDTH = "bottom_fullwidth", _("Снизу на всю ширину")

    class CloseControlPlacement(models.TextChoices):
        LEFT = "left", _("Слева")
        RIGHT = "right", _("Справа")

    class BannerVariant(models.TextChoices):
        BAR = constants.COOKIE_BANNER_VARIANT_BAR, _("Плашка")
        CARD = constants.COOKIE_BANNER_VARIANT_CARD, _("Карточка")
        MODAL = constants.COOKIE_BANNER_VARIANT_MODAL, _("Модальное окно")

    class ConsentUiVariant(models.TextChoices):
        INLINE = constants.COOKIE_BANNER_CONSENT_UI_VARIANT_INLINE, _("Встроенный")
        PANEL = constants.COOKIE_BANNER_CONSENT_UI_VARIANT_PANEL, _("Панель")

    class ReconsentNoticeVariant(models.TextChoices):
        INLINE = (
            constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_INLINE,
            _("Встроенный"),
        )
        ALERT = constants.COOKIE_BANNER_RECONSENT_NOTICE_VARIANT_ALERT, _("Оповещение")

    class TextPreset(models.TextChoices):
        AUTO = (
            constants.COOKIE_BANNER_TEXT_PRESET_AUTO,
            _("Auto (locale-based)"),
        )
        RU_BALANCED = (
            constants.COOKIE_BANNER_TEXT_PRESET_RU_BALANCED,
            _("Сбалансированный (RU)"),
        )
        RU_FORMAL = (
            constants.COOKIE_BANNER_TEXT_PRESET_RU_FORMAL,
            _("Формальный (RU)"),
        )
        RU_COMPACT = (
            constants.COOKIE_BANNER_TEXT_PRESET_RU_COMPACT,
            _("Компактный (RU)"),
        )
        EN_BALANCED = (
            constants.COOKIE_BANNER_TEXT_PRESET_EN_BALANCED,
            _("Balanced (EN)"),
        )
        EN_FORMAL = (
            constants.COOKIE_BANNER_TEXT_PRESET_EN_FORMAL,
            _("Formal (EN)"),
        )
        EN_COMPACT = (
            constants.COOKIE_BANNER_TEXT_PRESET_EN_COMPACT,
            _("Compact (EN)"),
        )

    class ColorPreset(models.TextChoices):
        LIGHT = "light", _("Светлый")
        CONTRAST = "contrast", _("Контрастный")
        CUSTOM = "custom", _("Пользовательские цвета")

    class MediaSlotType(models.TextChoices):
        ICON = "icon", _("Иконка")
        IMAGE = "image", _("Изображение")

    version = models.PositiveIntegerField(default=1, unique=True)
    launcher_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["launcher_label"],
    )
    eyebrow_text = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["eyebrow_text"],
    )
    title_text = models.TextField(
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["title_text"]
    )
    description_text = models.TextField(
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["description_text"]
    )
    reconsent_notice_text = models.TextField(
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["reconsent_notice_text"]
    )
    reask_notice_text = models.TextField(
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["reask_notice_text"]
    )
    accept_all_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["accept_all_label"],
    )
    reject_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["reject_label"],
        verbose_name=_("Надпись кнопки отказа"),
    )
    required_only_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["required_only_label"],
    )
    customize_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["customize_label"],
    )
    custom_section_summary = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["custom_section_summary"],
    )
    required_section_title = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["required_section_title"],
    )
    required_section_empty_text = models.CharField(
        max_length=255,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["required_section_empty_text"],
    )
    optional_section_title = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["optional_section_title"],
    )
    optional_section_empty_text = models.CharField(
        max_length=255,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["optional_section_empty_text"],
    )
    save_custom_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["save_custom_label"],
    )
    preferences_link_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["preferences_link_label"],
    )
    dismiss_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["dismiss_label"],
    )
    close_tooltip_text = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["close_tooltip_text"],
        verbose_name=_("Подсказка кнопки закрытия"),
    )
    close_aria_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["close_aria_label"],
        verbose_name=_("ARIA-метка кнопки закрытия"),
    )
    noscript_text = models.CharField(
        max_length=255,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["noscript_text"],
    )
    noscript_link_label = models.CharField(
        max_length=128,
        default=DEFAULT_COOKIE_BANNER_REVISION_TEXTS["noscript_link_label"],
    )
    banner_variant = models.CharField(
        max_length=32,
        choices=BannerVariant.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["banner_variant"],
    )
    consent_ui_variant = models.CharField(
        max_length=32,
        choices=ConsentUiVariant.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["consent_ui_variant"],
    )
    reconsent_notice_variant = models.CharField(
        max_length=32,
        choices=ReconsentNoticeVariant.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["reconsent_notice_variant"],
    )
    mobile_banner_variant = models.CharField(
        max_length=32,
        choices=BannerVariant.choices,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["mobile_banner_variant"],
    )
    mobile_consent_ui_variant = models.CharField(
        max_length=32,
        choices=ConsentUiVariant.choices,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION[
            "mobile_consent_ui_variant"
        ],
    )
    mobile_reconsent_notice_variant = models.CharField(
        max_length=32,
        choices=ReconsentNoticeVariant.choices,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION[
            "mobile_reconsent_notice_variant"
        ],
    )
    text_preset_code = models.CharField(
        max_length=32,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["text_preset_code"],
    )
    mobile_text_preset_code = models.CharField(
        max_length=32,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["mobile_text_preset_code"],
    )
    layout_variant = models.CharField(
        max_length=32,
        choices=LayoutVariant.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["layout_variant"],
    )
    theme_variant = models.CharField(
        max_length=32,
        choices=ThemeVariant.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["theme_variant"],
    )
    desktop_position = models.CharField(
        max_length=32,
        choices=DesktopPosition.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["desktop_position"],
    )
    mobile_position = models.CharField(
        max_length=32,
        choices=MobilePosition.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["mobile_position"],
    )
    color_preset = models.CharField(
        max_length=32,
        choices=ColorPreset.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["color_preset"],
        verbose_name=_("Цветовая заготовка"),
    )
    custom_bg_color = models.CharField(max_length=16, blank=True, default="")
    custom_text_color = models.CharField(max_length=16, blank=True, default="")
    custom_primary_color = models.CharField(max_length=16, blank=True, default="")
    custom_primary_text_color = models.CharField(max_length=16, blank=True, default="")
    custom_border_color = models.CharField(max_length=16, blank=True, default="")
    custom_surface_color = models.CharField(max_length=16, blank=True, default="")
    custom_overlay_color = models.CharField(max_length=16, blank=True, default="")
    panel_padding_px = models.PositiveIntegerField(
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["panel_padding_px"]
    )
    section_gap_px = models.PositiveIntegerField(
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["section_gap_px"]
    )
    button_gap_px = models.PositiveIntegerField(
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["button_gap_px"]
    )
    overlay_opacity = models.PositiveIntegerField(
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["overlay_opacity"]
    )
    show_media_slot = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["show_media_slot"],
        verbose_name=_("Показывать медиаблок"),
    )
    media_slot_type = models.CharField(
        max_length=16,
        choices=MediaSlotType.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_slot_type"],
        verbose_name=_("Тип медиаблока"),
    )
    media_icon_emoji = models.CharField(
        max_length=8,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_icon_emoji"],
        verbose_name=_("Эмодзи для медиаблока"),
    )
    media_image_url = models.CharField(
        max_length=255,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_image_url"],
        verbose_name=_("URL изображения для медиаблока"),
    )
    media_image_alt = models.CharField(
        max_length=128,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION["media_image_alt"],
        verbose_name=_("Альтернативный текст изображения медиаблока"),
    )
    show_close_control = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["show_close_control"],
        verbose_name=_("Показывать кнопку закрытия"),
    )
    close_control_placement = models.CharField(
        max_length=16,
        choices=CloseControlPlacement.choices,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["close_control_placement"],
        verbose_name=_("Расположение кнопки закрытия"),
    )
    mobile_close_control_placement = models.CharField(
        max_length=16,
        choices=CloseControlPlacement.choices,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_PRESENTATION[
            "mobile_close_control_placement"
        ],
        verbose_name=_(
            "Переопределение расположения кнопки закрытия для мобильной версии"
        ),
    )
    show_reject_action = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["show_reject_action"],
        verbose_name=_("Показывать кнопку отказа"),
    )
    mobile_show_close_control = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["mobile_show_close_control"],
        verbose_name=_("Переопределение показа кнопки закрытия для мобильной версии"),
    )
    mobile_show_reject_action = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["mobile_show_reject_action"],
        verbose_name=_("Переопределение показа кнопки отказа для мобильной версии"),
    )
    blocking_mode_until_choice = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["blocking_mode_until_choice"],
        verbose_name=_("Блокирующий режим до выбора"),
        help_text=_(
            "Блокировать взаимодействие со страницей, пока пользователь явно не выберет настройки cookie."
        ),
    )
    mobile_blocking_mode_until_choice = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "mobile_blocking_mode_until_choice"
        ],
        verbose_name=_("Переопределение блокирующего режима для мобильной версии"),
    )
    hide_launcher_after_decision = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["hide_launcher_after_decision"],
        verbose_name=_("Скрывать кнопку настроек после выбора"),
    )
    mobile_hide_launcher_after_decision = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "mobile_hide_launcher_after_decision"
        ],
        verbose_name=_("Переопределение скрытия кнопки настроек для мобильной версии"),
    )
    keep_visible_after_accept_all = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "keep_visible_after_accept_all"
        ],
        verbose_name=_("Оставлять баннер видимым после действия «принять все»"),
    )
    keep_visible_after_required_only = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "keep_visible_after_required_only"
        ],
        verbose_name=_("Оставлять баннер видимым после действия «только обязательные»"),
    )
    keep_visible_after_save_custom = models.BooleanField(
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "keep_visible_after_save_custom"
        ],
        verbose_name=_(
            "Оставлять баннер видимым после действия «сохранить выбранные категории»"
        ),
    )
    mobile_keep_visible_after_accept_all = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "mobile_keep_visible_after_accept_all"
        ],
        verbose_name=_(
            "Переопределение видимости баннера после «принять все» для мобильной версии"
        ),
    )
    mobile_keep_visible_after_required_only = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "mobile_keep_visible_after_required_only"
        ],
        verbose_name=_(
            "Переопределение видимости баннера после «только обязательные» для мобильной версии"
        ),
    )
    mobile_keep_visible_after_save_custom = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR[
            "mobile_keep_visible_after_save_custom"
        ],
        verbose_name=_(
            "Переопределение видимости баннера после «сохранить выбранные категории» для мобильной версии"
        ),
    )
    hide_for_bots_override = models.BooleanField(
        null=True,
        blank=True,
        default=DEFAULT_COOKIE_BANNER_REVISION_BEHAVIOR["hide_for_bots_override"],
        verbose_name=_("Переопределение скрытия для ботов"),
        help_text=_(
            "Переопределение скрытия для ботов во время выполнения: пусто — "
            "использовать значение из настроек, включено — скрывать баннер для "
            "определённых ботов, выключено — показывать баннер."
        ),
    )
    cloned_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cloned_banner_revisions",
        verbose_name=_("Скопировано из редакции"),
    )
    is_box_template = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Редакция cookie-баннера")
        verbose_name_plural = _("Редакции cookie-баннера")
        ordering = ["-published_at", "-version", "-id"]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()

        errors: dict[str, object] = {}
        # Comment
        for field_name in (
            *COOKIE_BANNER_TEXT_FIELDS,
            "close_tooltip_text",
            "close_aria_label",
        ):
            try:
                setattr(
                    self,
                    field_name,
                    _normalize_non_empty_text(
                        getattr(self, field_name),
                        field_name=field_name,
                    ),
                )
            except ValidationError as exc:
                errors[field_name] = str(exc)

        for color_field in (
            "custom_bg_color",
            "custom_text_color",
            "custom_primary_color",
            "custom_primary_text_color",
            "custom_border_color",
            "custom_surface_color",
            "custom_overlay_color",
        ):
            raw_value = str(getattr(self, color_field) or "").strip()
            if not raw_value:
                setattr(self, color_field, "")
                continue
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", raw_value):
                errors[color_field] = _("Используйте HEX-цвет в формате #RRGGBB.")
                continue
            setattr(self, color_field, raw_value.lower())

        self.panel_padding_px = max(8, min(48, int(self.panel_padding_px or 0)))
        self.section_gap_px = max(4, min(32, int(self.section_gap_px or 0)))
        self.button_gap_px = max(4, min(24, int(self.button_gap_px or 0)))
        self.overlay_opacity = max(0, min(85, int(self.overlay_opacity or 0)))
        self.show_media_slot = bool(self.show_media_slot)
        self.media_slot_type = str(self.media_slot_type or "icon").strip()
        self.media_icon_emoji = str(self.media_icon_emoji or "").strip()
        self.media_image_url = str(self.media_image_url or "").strip()
        self.media_image_alt = str(self.media_image_alt or "").strip()
        if self.media_slot_type not in {
            self.MediaSlotType.ICON,
            self.MediaSlotType.IMAGE,
        }:
            self.media_slot_type = self.MediaSlotType.ICON
        if self.media_image_url and not _is_allowed_absolute_or_root_relative_url(
            self.media_image_url
        ):
            errors["media_image_url"] = _(
                "media_image_url должен быть безопасным URL/путём."
            )
        if self.show_media_slot and self.media_slot_type == self.MediaSlotType.IMAGE:
            if not self.media_image_url:
                errors["media_image_url"] = _(
                    "Для слота изображения обязателен media_image_url."
                )
            if not self.media_image_alt:
                errors["media_image_alt"] = _(
                    "Для слота изображения обязателен media_image_alt."
                )

        bg = str(self.custom_bg_color or "")
        text = str(self.custom_text_color or "")
        if bg and text and not _has_min_contrast(bg, text):
            errors["custom_text_color"] = _(
                "Цвет фона и текста должен обеспечивать читаемый контраст."
            )

        if errors:
            raise ValidationError(errors)

    @classmethod
    def text_presets(cls) -> dict[str, dict[str, object]]:
        return {
            preset_code: dict(preset_values)
            for preset_code, preset_values in COOKIE_BANNER_TEXT_PRESETS.items()
        }

    @classmethod
    def text_field_contract(cls) -> dict[str, tuple[str, ...]]:
        return {
            "editable_fields": COOKIE_BANNER_EDITABLE_TEXT_FIELDS,
            "protected_fields": COOKIE_BANNER_PROTECTED_TEXT_FIELDS,
        }

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"cookie-banner:v{self.version}"


class CookieBannerTextPreset(models.Model):
    "A text preset for composing the banner without manually filling every field."

    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=255)
    launcher_label = models.CharField(max_length=128)
    eyebrow_text = models.CharField(max_length=128)
    title_text = models.TextField()
    description_text = models.TextField()
    reconsent_notice_text = models.TextField()
    reask_notice_text = models.TextField()
    accept_all_label = models.CharField(max_length=128)
    reject_label = models.CharField(max_length=128)
    required_only_label = models.CharField(max_length=128)
    customize_label = models.CharField(max_length=128)
    custom_section_summary = models.CharField(max_length=128)
    required_section_title = models.CharField(max_length=128)
    required_section_empty_text = models.CharField(max_length=255)
    optional_section_title = models.CharField(max_length=128)
    optional_section_empty_text = models.CharField(max_length=255)
    save_custom_label = models.CharField(max_length=128)
    preferences_link_label = models.CharField(max_length=128)
    dismiss_label = models.CharField(max_length=128)
    noscript_text = models.CharField(max_length=255)
    noscript_link_label = models.CharField(max_length=128)
    is_box_template = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Текстовая заготовка cookie-баннера")
        verbose_name_plural = _("Текстовые заготовки cookie-баннера")
        ordering = ["code", "-id"]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()
        self.code = str(self.code or "").strip().lower()
        self.title = str(self.title or "").strip()
        errors: dict[str, object] = {}
        if not self.code:
            errors["code"] = _("code не может быть пустым.")
        if not self.title:
            errors["title"] = _("title не может быть пустым.")
        for field_name in COOKIE_BANNER_TEXT_FIELDS:
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                errors[field_name] = _("%(field_name)s не может быть пустым.") % {
                    "field_name": field_name
                }
            setattr(self, field_name, value)
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class CookieConsentRecord(models.Model):
    "The current cookie-policy consent state for a subject."

    class Status(models.TextChoices):
        CURRENT = constants.COOKIE_CONSENT_STATUS_CURRENT, _("Актуальная")
        OUTDATED = constants.COOKIE_CONSENT_STATUS_OUTDATED, _("Устаревшая")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cookie_consent_records",
    )
    anonymous_token = models.CharField(max_length=128, blank=True)
    policy_revision = models.ForeignKey(
        CookiePolicyRevision,
        on_delete=models.PROTECT,
        related_name="records",
    )
    selected_categories = models.JSONField(default=list)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.CURRENT,
    )
    source = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    locale = models.CharField(max_length=32, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    session_key_hash = models.CharField(max_length=128, blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Запись cookie-согласия")
        verbose_name_plural = _("Записи cookie-согласий")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="cookie_rec_status_created_idx",
            ),
            models.Index(
                fields=["anonymous_token", "created_at"],
                name="cookie_rec_token_created_idx",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="cookie_rec_user_created_idx",
            ),
            models.Index(
                fields=["policy_revision", "created_at"],
                name="cookie_rec_policy_created_idx",
            ),
            models.Index(fields=["updated_at"], name="cookie_rec_updated_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(
                    status=constants.COOKIE_CONSENT_STATUS_CURRENT,
                    user__isnull=False,
                ),
                name="cookie_rec_current_user_unique",
            ),
            models.UniqueConstraint(
                fields=["anonymous_token"],
                condition=models.Q(
                    status=constants.COOKIE_CONSENT_STATUS_CURRENT,
                    user__isnull=True,
                    anonymous_token__gt="",
                ),
                name="cookie_rec_current_token_unique",
            ),
        ]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()

        errors: dict[str, object] = {}
        if not self.user_id and not (self.anonymous_token or "").strip():  # pyright: ignore[reportAttributeAccessIssue]
            errors["anonymous_token"] = _(
                "anonymous_token обязателен, когда пользователь не указан."
            )

        try:
            selected = _normalize_codes(self.selected_categories)
        except ValidationError as exc:
            errors["selected_categories"] = str(exc)
            selected = []

        if self.policy_revision_id:  # pyright: ignore[reportAttributeAccessIssue]
            snapshot = normalize_categories_snapshot(
                self.policy_revision.categories_snapshot
            )
            allowed_codes = {str(item["code"]) for item in snapshot}
            required_codes = {
                str(item["code"]) for item in snapshot if bool(item["is_required"])
            }
            unknown_codes = sorted(set(selected) - allowed_codes)
            missing_required_codes = sorted(required_codes - set(selected))
            if unknown_codes:
                errors["selected_categories"] = _(
                    "selected_categories содержит неизвестные категории: %(codes)s."
                ) % {"codes": ", ".join(unknown_codes)}
            if missing_required_codes:
                errors["selected_categories"] = _(
                    "selected_categories должен включать обязательные категории: %(codes)s."
                ) % {"codes": ", ".join(missing_required_codes)}
        self.selected_categories = selected
        extra_meta_error = _validate_audit_json_object(
            field_name="extra_meta",
            value=self.extra_meta,
            reserved_root_keys=_RESERVED_AUDIT_ROOT_KEYS,
        )
        if extra_meta_error:
            errors["extra_meta"] = extra_meta_error

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        subject = self.user_id or self.anonymous_token or "anonymous"  # pyright: ignore[reportAttributeAccessIssue]
        return f"cookie:{self.policy_revision.version}:{subject}"


class CookieBannerState(models.Model):
    "The UI banner state for a subject: dismissed/decided/updated."

    class DecisionAction(models.TextChoices):
        ACCEPT_ALL = "accept_all", _("Принять все")
        REJECT_ALL = "reject_all", _("Отклонить все")
        REQUIRED_ONLY = "required_only", _("Только обязательные")
        SAVE_CUSTOM = "save_custom", _("Сохранить выбранные категории")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cookie_banner_state",
    )
    anonymous_token = models.CharField(
        max_length=128,
        null=True,
        blank=True,
    )
    dismissed_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_action = models.CharField(
        max_length=32,
        choices=DecisionAction.choices,
        blank=True,
        verbose_name=_("Действие выбора"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Состояние cookie-баннера")
        verbose_name_plural = _("Состояния cookie-баннера")
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["updated_at"], name="cookie_banner_updated_idx"),
            models.Index(fields=["created_at"], name="cookie_banner_created_idx"),
        ]
        constraints = [
            # Comment
            # Comment
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False)
                    | models.Q(anonymous_token__isnull=False)
                ),
                name="cookie_banner_state_has_subject",
            ),
            models.UniqueConstraint(
                fields=["anonymous_token"],
                condition=models.Q(anonymous_token__isnull=False),
                name="cookie_banner_state_unique_anonymous_token",
            ),
        ]

    def clean(self) -> None:
        "Validates model invariants before saving."

        super().clean()

        token = str(self.anonymous_token or "").strip()
        self.anonymous_token = token or None
        if not self.user_id and self.anonymous_token is None:  # pyright: ignore[reportAttributeAccessIssue]
            raise ValidationError(
                {
                    "anonymous_token": (
                        _("anonymous_token обязателен, когда пользователь не указан.")
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        subject = self.user_id or self.anonymous_token or "anonymous"  # pyright: ignore[reportAttributeAccessIssue]
        return f"cookie-banner:{subject}"


class CookieAdminSettings(models.Model):
    """Singleton-настройки админ-инструментов cookie-модуля."""

    class CsvDelimiter(models.TextChoices):
        COMMA = ",", _("Запятая (,)")
        SEMICOLON = ";", _("Точка с запятой (;)")
        TAB = "\t", _("Табуляция (TAB)")
        PIPE = "|", _("Вертикальная черта (|)")

    csv_export_delimiter = models.CharField(
        max_length=8,
        choices=CsvDelimiter.choices,
        default=CsvDelimiter.COMMA,
        verbose_name=_("Разделитель CSV-экспорта"),
    )
    show_empty_category_block_override = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Override: show empty category block"),
    )
    show_customize_action_without_optional_override = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Override: show customize action without optional categories"),
    )
    empty_category_block_text_override = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Override: empty category block text"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Настройки админ-инструментов cookie")
        verbose_name_plural = _("Настройки админ-инструментов cookie")
        ordering = ["id"]

    def __str__(self) -> str:
        csv_delimiter_display = self.get_csv_export_delimiter_display()  # pyright: ignore[reportAttributeAccessIssue]
        return _("Настройки админ-инструментов cookie") + f" ({csv_delimiter_display})"  # pyright: ignore[reportAttributeAccessIssue]


class ImmutableCookieEventQuerySet(models.QuerySet):
    "Prevents bulk update/delete on the immutable audit log."

    def update(self, **kwargs):
        raise ValidationError(
            _("CookieConsentEvent неизменяем и не может быть обновлён.")
        )

    def delete(self):
        raise ValidationError(
            _("CookieConsentEvent неизменяем и не может быть удалён.")
        )


class CookieConsentEvent(models.Model):
    "An immutable event in the cookie-consent action audit log."

    class EventType(models.TextChoices):
        ACCEPTED = constants.COOKIE_EVENT_ACCEPTED, _("Принято")
        UPDATED = constants.COOKIE_EVENT_UPDATED, _("Обновлено")
        OUTDATED = constants.COOKIE_EVENT_OUTDATED, _("Устарело")

    objects = ImmutableCookieEventQuerySet.as_manager()

    cookie_consent_record = models.ForeignKey(
        CookieConsentRecord,
        on_delete=models.PROTECT,
        related_name="events",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    source = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    locale = models.CharField(max_length=32, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    session_key_hash = models.CharField(max_length=128, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Событие cookie-согласия")
        verbose_name_plural = _("События cookie-согласий")
        ordering = ["occurred_at", "id"]
        indexes = [
            models.Index(fields=["occurred_at"], name="cookie_evt_occurred_idx"),
            models.Index(
                fields=["event_type", "occurred_at"],
                name="cookie_evt_type_occurred_idx",
            ),
            models.Index(fields=["created_at"], name="cookie_evt_created_idx"),
            models.Index(
                fields=["cookie_consent_record", "occurred_at"],
                name="cookie_evt_record_occurred_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, object] = {}
        payload_error = _validate_audit_json_object(
            field_name="payload",
            value=self.payload,
            reserved_root_keys=_RESERVED_AUDIT_ROOT_KEYS,
        )
        if payload_error:
            errors["payload"] = payload_error
        extra_meta_error = _validate_audit_json_object(
            field_name="extra_meta",
            value=self.extra_meta,
            reserved_root_keys=_RESERVED_AUDIT_ROOT_KEYS,
        )
        if extra_meta_error:
            errors["extra_meta"] = extra_meta_error
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.cookie_consent_record_id}:{self.event_type}"  # pyright: ignore[reportAttributeAccessIssue]


def normalize_categories_snapshot(
    raw_snapshot: Iterable[Mapping[str, object]] | object,
) -> list[dict[str, object]]:
    "Normalizes a categories snapshot to a canonical serializable format."

    if not isinstance(raw_snapshot, list):
        raise ValidationError(_("categories_snapshot должен быть списком."))

    normalized_snapshot: list[dict[str, object]] = []
    known_codes: set[str] = set()
    for index, raw_item in enumerate(raw_snapshot):
        if not isinstance(raw_item, Mapping):
            raise ValidationError(
                _(
                    "Элемент categories_snapshot[%(index)s] должен быть объектом (mapping/dict)."
                )
                % {"index": index}
            )

        code = str(raw_item.get("code") or "").strip()
        if not _COOKIE_CODE_RE.fullmatch(code):
            raise ValidationError(
                _(
                    'categories_snapshot[%(index)s]["code"] должен соответствовать шаблону "[a-z][a-z0-9_]*".'
                )
                % {"index": index}
            )
        if code in known_codes:
            raise ValidationError(
                _('categories_snapshot содержит дублирующийся код "%(code)s".')
                % {"code": code}
            )
        title = str(raw_item.get("title") or "").strip()
        if not title:
            raise ValidationError(
                _('categories_snapshot[%(index)s]["title"] не может быть пустым.')
                % {"index": index}
            )

        description = str(raw_item.get("description") or "").strip()
        is_required = bool(raw_item.get("is_required", False))
        sort_order_raw = raw_item.get("sort_order", index)
        try:
            if isinstance(sort_order_raw, bool):
                raise TypeError("sort_order bool is not supported")
            if isinstance(sort_order_raw, int):
                sort_order = sort_order_raw
            else:
                sort_order = int(str(sort_order_raw))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                _(
                    'categories_snapshot[%(index)s]["sort_order"] должен быть целым числом.'
                )
                % {"index": index}
            ) from exc

        known_codes.add(code)
        normalized_snapshot.append(
            {
                "code": code,
                "title": title,
                "description": description,
                "is_required": is_required,
                "sort_order": sort_order,
            }
        )

    normalized_snapshot.sort(
        key=lambda item: (int(cast(int, item["sort_order"])), str(item["code"]))
    )
    return normalized_snapshot
