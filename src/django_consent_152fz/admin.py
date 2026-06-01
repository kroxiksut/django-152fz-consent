"""Django admin for the implementations in section 5.2.

The module connects the admin UI to the package domain logic:
- publishing document revisions;
- managing audience and access rules;
- viewing consent records and immutable audit events;
- assigning the `PersonalDataManager` role.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Django dynamic ORM/admin attributes are not fully inferable by pyright.
# ruff: noqa: E501
import csv
import json
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Exists, OuterRef
from django.http import HttpResponse
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from . import constants
from .admin_helpers import (
    PERSONAL_DATA_MANAGER_GROUP_LABEL,
    AssignmentRestrictedAdminMixin,
    PublishableRevisionAdminMixin,
    ReadOnlyAdminMixin,
    has_personal_data_manager_permission,
    safe_register_admin_models,
    sync_personal_data_manager_group_membership,
)
from .audit import log_module_operation
from .core.models import (
    ConsentAccessPolicy,
    ConsentAudienceRule,
    ConsentEvent,
    ConsentModuleOperationAuditLog,
    ConsentPurpose,
    ConsentRecord,
    ConsentSelfServiceSettings,
    DocumentRevision,
    LegalDocument,
    ModuleOperationAuditLog,
    PersonalDataManagerAssignment,
)
from .core.services import (
    clone_access_policy_as_draft,
    clone_audience_rule_as_draft,
    clone_box_template_revision,
    clone_legal_document_stream_as_draft,
)
from .core.starter_purposes import CORE_152FZ_STARTER_PURPOSE_TEMPLATES
from .exceptions import ConsentError
from .settings import get_document_templates_settings

USER_LOOKUP = get_user_model().USERNAME_FIELD
_VERIFIED_CONSENTS_ADMIN_APP_LABEL = "verified_consents"
_ADMIN_APP_LIST_PATCH_MARKER = "_dz152fz_merge_verified_app_applied"


def _merge_verified_consents_app_into_core(
    app_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    core_label = constants.APP_LABEL
    core_entry: dict[str, Any] | None = None
    verified_models: list[dict[str, Any]] = []
    filtered_apps: list[dict[str, Any]] = []

    for app in app_list:
        app_label = str(app.get("app_label") or "")
        if app_label == core_label and core_entry is None:
            core_entry = app
            filtered_apps.append(app)
            continue
        if app_label == _VERIFIED_CONSENTS_ADMIN_APP_LABEL:
            verified_models.extend(
                list(cast(list[dict[str, Any]], app.get("models") or []))
            )
            continue
        filtered_apps.append(app)

    if core_entry is None or not verified_models:
        return filtered_apps

    existing_models = list(cast(list[dict[str, Any]], core_entry.get("models") or []))
    existing_keys = {
        (
            str(model.get("object_name") or ""),
            str(model.get("admin_url") or ""),
            str(model.get("view_only") or ""),
        )
        for model in existing_models
    }
    for model in verified_models:
        dedupe_key = (
            str(model.get("object_name") or ""),
            str(model.get("admin_url") or ""),
            str(model.get("view_only") or ""),
        )
        if dedupe_key in existing_keys:
            continue
        existing_models.append(model)
        existing_keys.add(dedupe_key)

    existing_models.sort(key=lambda item: str(item.get("name") or "").lower())
    core_entry["models"] = existing_models
    return filtered_apps


def _patch_admin_site_app_list(site: admin.sites.AdminSite) -> None:
    if bool(getattr(site, _ADMIN_APP_LIST_PATCH_MARKER, False)):
        return
    original_get_app_list = site.get_app_list

    def _patched_get_app_list(request, app_label=None):
        app_list = original_get_app_list(request, app_label)
        return _merge_verified_consents_app_into_core(
            list(cast(list[dict[str, Any]], app_list))
        )

    site.get_app_list = _patched_get_app_list  # type: ignore[method-assign]
    setattr(site, _ADMIN_APP_LIST_PATCH_MARKER, True)


def _resolve_csv_delimiter() -> str:
    settings_obj = ConsentSelfServiceSettings.objects.order_by(
        "-updated_at", "-id"
    ).first()
    if not settings_obj:
        return ","
    delimiter = str(getattr(settings_obj, "csv_export_delimiter", ",") or ",")
    return delimiter if delimiter in {",", ";", "\t", "|"} else ","


def _sanitize_csv_cell(value: Any) -> str:
    """Protect CSV export cells against spreadsheet formula execution."""

    raw = "" if value is None else str(value)
    if raw and raw[0] in {"=", "+", "-", "@", "\t", "\r"}:
        return f"'{raw}"
    return raw


def _sanitize_csv_row(values: list[Any]) -> list[str]:
    return [_sanitize_csv_cell(value) for value in values]


def _format_document_type_label(raw_value: str) -> str:
    normalized = str(raw_value or "").strip().lower()
    labels = {
        "consent": _("Согласие"),
        "policy": _("Политика"),
        "privacy_policy": _("Политика обработки персональных данных"),
        "notice": _("Уведомление"),
        "agreement": _("Соглашение"),
        "theme": _("Тема"),
    }
    return str(labels.get(normalized, raw_value))


def _starter_purpose_template_choices() -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [("", str(_("Без шаблона")))]
    for template_key, template in CORE_152FZ_STARTER_PURPOSE_TEMPLATES.items():
        title = str(template["title"])
        code = str(template["code"])
        choices.append((template_key, f"[152-ФЗ] {title} ({code})"))
    return choices


def _set_verbose_names(model, field_labels: dict[str, object]) -> None:
    for field_name, label in field_labels.items():
        model._meta.get_field(field_name).verbose_name = label


def _localize_admin_field_labels() -> None:
    _set_verbose_names(
        ConsentPurpose,
        {
            "code": _("Код"),
            "title": _("Название"),
            "description": _("Описание"),
            "fields_config": _("Конфигурация полей"),
            "withdraw_strategy": _("Стратегия отзыва"),
            "reconsent_mode": _("Режим повторного согласия"),
            "consent_frequency_policy": _("Политика частоты подписания"),
            "subject_availability_policy": _("Доступность для субъектов"),
            "is_experimental": _("Экспериментальный режим"),
            "is_active": _("Активна"),
        },
    )
    _set_verbose_names(
        LegalDocument,
        {
            "code": _("Код"),
            "title": _("Название"),
            "document_type": _("Тип документа"),
            "description": _("Описание"),
            "is_active": _("Активен"),
        },
    )
    _set_verbose_names(
        DocumentRevision,
        {
            "document": _("Документ"),
            "purpose_code": _("Код цели"),
            "version": _("Версия"),
            "format": _("Формат"),
            "content_text": _("Текст редакции"),
            "content_file": _("Файл редакции"),
            "fields_snapshot": _("Снимок полей"),
            "meta": _("Метаданные"),
            "is_active": _("Опубликована"),
            "is_box_template": _("Коробочный шаблон"),
            "published_at": _("Дата публикации"),
            "created_at": _("Создано"),
        },
    )
    _set_verbose_names(
        ConsentAudienceRule,
        {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "scope_mode": _("Охват"),
            "group": _("Django-группа"),
            "is_required": _("Требуется согласие"),
            "is_active": _("Активно"),
            "starts_at": _("Начало действия"),
            "ends_at": _("Окончание действия"),
            "notes": _("Заметки"),
            "created_by": _("Создано пользователем"),
        },
    )
    _set_verbose_names(
        ConsentAccessPolicy,
        {
            "code": _("Код"),
            "title": _("Название"),
            "description": _("Описание"),
            "purpose": _("Цель"),
            "document": _("Документ"),
            "resource_code": _("Код ресурса"),
            "app_label": _("Метка приложения"),
            "model_name": _("Модель"),
            "action": _("Действие"),
            "on_missing_consent": _("При отсутствии согласия"),
            "on_outdated_consent": _("При устаревшем согласии"),
            "is_active": _("Активна"),
            "starts_at": _("Начало действия"),
            "ends_at": _("Окончание действия"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
        },
    )
    _set_verbose_names(
        ConsentRecord,
        {
            "purpose": _("Цель"),
            "document_revision": _("Редакция документа"),
            "status": _("Статус"),
            "confirmation_method": _("Метод подтверждения"),
            "source": _("Источник"),
            "created_at": _("Создано"),
        },
    )
    _set_verbose_names(
        ConsentSelfServiceSettings,
        {
            "subject_consents_open_mode": _(
                "Как открывать «Открыть и подписать» в самообслуживании"
            ),
            "printable_pdf_paper_size": _("Формат бумаги для печатного PDF"),
            "printable_pdf_font_family": _("Шрифт печатного PDF"),
            "printable_pdf_font_size": _("Размер шрифта печатного PDF"),
            "printable_pdf_text_align": _("Выравнивание текста печатного PDF"),
            "printable_pdf_show_signature_footer": _(
                "Добавлять блок подписи внизу PDF"
            ),
            "printable_pdf_signature_align": _("Выравнивание подписи (ПОДПИСЬ/ФИО)"),
        },
    )
    _set_verbose_names(
        ConsentEvent,
        {
            "consent_record": _("Запись согласия"),
            "event_type": _("Тип события"),
            "actor_type": _("Тип актора"),
            "actor_user": _("Пользователь-актор"),
            "source": _("Источник"),
            "occurred_at": _("Время события"),
        },
    )
    _set_verbose_names(
        PersonalDataManagerAssignment,
        {
            "user": _("Пользователь"),
            "scope_mode": _("Охват"),
            "groups": _("Django-группы"),
            "can_manage_purposes": _("Может управлять целями"),
            "can_manage_documents": _("Может управлять документами"),
            "can_publish_revisions": _("Может публиковать редакции"),
            "can_manage_audience_rules": _("Может управлять правилами аудитории"),
            "can_manage_access_policies": _("Может управлять политиками доступа"),
            "can_handle_verified_consents": _(
                "Может обрабатывать подтверждённые согласия"
            ),
            "is_active": _("Активно"),
        },
    )
    _set_verbose_names(
        ModuleOperationAuditLog,
        {
            "operation_code": _("Код операции"),
            "actor_user": _("Пользователь-оператор"),
            "source": _("Источник"),
            "status": _("Статус"),
            "target_model": _("Целевая модель"),
            "target_id": _("Идентификатор цели"),
            "summary": _("Описание"),
            "payload": _("Параметры"),
            "result": _("Результат"),
            "created_at": _("Создано"),
        },
    )


_localize_admin_field_labels()


class DocumentRevisionActionForm(ActionForm):
    """Native ActionForm of admin actions for selecting target Django groups."""

    audience_groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.order_by("name"),
        required=False,
        label=_("Audience groups"),
        help_text=_(
            "Ограничьте публикацию выбранных редакций участниками указанных групп."
        ),
    )


class ConsentPurposeAdminForm(forms.ModelForm):
    starter_template = forms.ChoiceField(
        required=False,
        label=_("Коробочная цель (стартовый набор 152-ФЗ)"),
        choices=(),
        help_text=_(
            "Выберите цель из стартового набора 152-ФЗ, чтобы автоматически "
            "подставить готовые значения кода, названия, описания и "
            "конфигурации полей. После подстановки все значения можно "
            "отредактировать под проект."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["starter_template"].choices = _starter_purpose_template_choices()
        self.fields["code"].required = False
        self.fields["title"].required = False
        self.fields["fields_config"].required = False

    def clean(self):
        cleaned_data = cast(dict[str, Any], super().clean())
        template_key = cleaned_data.get("starter_template")
        template = CORE_152FZ_STARTER_PURPOSE_TEMPLATES.get(str(template_key or ""))
        if template is None:
            return cleaned_data

        code_value = str(cleaned_data.get("code") or "").strip()
        title_value = str(cleaned_data.get("title") or "").strip()
        description_value = str(cleaned_data.get("description") or "").strip()
        fields_value = cleaned_data.get("fields_config")

        if not code_value:
            cleaned_data["code"] = str(template["code"])
        if not title_value:
            cleaned_data["title"] = str(template["title"])
        if not description_value:
            cleaned_data["description"] = str(template["description"])
        if fields_value in (None, "", [], {}):
            cleaned_data["fields_config"] = template["fields_config"]

        return cleaned_data

    class Meta:
        model = ConsentPurpose
        fields = "__all__"
        labels = {
            "code": _("Код"),
            "title": _("Название"),
            "description": _("Описание"),
            "fields_config": _("Конфигурация полей"),
            "withdraw_strategy": _("Стратегия отзыва"),
            "reconsent_mode": _("Режим повторного согласия"),
            "consent_frequency_policy": _("Политика частоты подписания"),
            "subject_availability_policy": _("Доступность для субъектов"),
            "consent_input_mode_override": _("UI подтверждения для этой формы"),
            "checkbox_required_override": _("Обязательный флажок (переопределение)"),
            "decline_action_override": _(
                "Действие при «не согласен» (переопределение)"
            ),
            "decline_warning_enabled_override": _(
                "Показывать предупреждение (переопределение)"
            ),
            "decline_warning_text_override": _(
                "Текст предупреждения (переопределение)"
            ),
            "is_experimental": _("Экспериментальный режим"),
            "is_active": _("Активна"),
        }
        help_texts = {
            "code": _(
                "Стабильный уникальный код цели (например: `newsletter_signup`, "
                "`job_application`, `support_request`). Используется не только в API, "
                "но и во внутренних связях, шаблонах, политиках доступа и маршрутизации "
                "логики согласий."
            ),
            "title": _("Краткое название цели, видимое в админке и UI-сценариях."),
            "description": _(
                "Подробно опишите, для чего собирается и используется согласие."
            ),
            "fields_config": _(
                "JSON-конфигурация полей формы согласия. Минимальная структура: "
                '[{"name": "email", "required": true}]. '
                "Каждый элемент — объект поля как минимум с ключом `name`; "
                "рекомендуется указывать `required`."
            ),
            "withdraw_strategy": _(
                "Поведение системы при отзыве согласия пользователем."
            ),
            "reconsent_mode": _(
                "Когда и при каких условиях повторно запрашивать согласие."
            ),
            "consent_frequency_policy": _(
                "Определяет, требовать ли подтверждение один раз до новой редакции "
                "или при каждом пользовательском действии."
            ),
            "subject_availability_policy": _(
                "Ограничивает, может ли цель применяться только к авторизованным "
                "или также к анонимным субъектам."
            ),
            "consent_input_mode_override": _(
                "Тонкая настройка конкретной формы: наследовать глобальный режим, "
                "флажок или переключатель «согласен/не согласен»."
            ),
            "checkbox_required_override": _(
                "Пусто = наследовать глобальную настройку. "
                "True/False = принудительное поведение для этой формы."
            ),
            "decline_action_override": _(
                "Как обрабатывать выбор «не согласен» для этой формы: наследовать, "
                "блокировать отправку или разрешать отправку."
            ),
            "decline_warning_enabled_override": _(
                "Пусто = наследовать глобальную настройку показа предупреждения."
            ),
            "decline_warning_text_override": _(
                "Если заполнено, заменяет глобальный текст предупреждения для этой формы."
            ),
            "is_experimental": _(
                "Включайте для пилотных сценариев и ограниченного поэтапного "
                "развёртывания."
            ),
            "is_active": _(
                "Отключите цель, чтобы исключить её из активных потоков согласия."
            ),
        }


class LegalDocumentAdminForm(forms.ModelForm):
    _DOCUMENT_TYPE_LABELS = {
        "consent": _("Согласие"),
        "policy": _("Политика"),
        "privacy_policy": _("Политика обработки персональных данных"),
        "notice": _("Уведомление"),
        "agreement": _("Соглашение"),
        "theme": _("Тема"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        document_type_field = self.fields.get("document_type")
        if document_type_field is None:
            return
        current_value = str(
            getattr(self.instance, "document_type", "")
            or self.initial.get("document_type")
            or ""
        ).strip()
        choices = [
            (code, str(label)) for code, label in self._DOCUMENT_TYPE_LABELS.items()
        ]
        if current_value and current_value not in self._DOCUMENT_TYPE_LABELS:
            choices.append((current_value, current_value))
        document_type_field.widget = forms.Select(choices=choices)
        document_type_field.help_text = _(
            "Выберите тип документа. В БД сохраняется технический код."
        )

    class Meta:
        model = LegalDocument
        fields = "__all__"
        labels = {
            "code": _("Код"),
            "title": _("Название"),
            "document_type": _("Тип документа"),
            "description": _("Описание"),
            "is_active": _("Активен"),
        }
        help_texts = {
            "code": _(
                "Уникальный код документа для ссылок из политик и правил доступа."
            ),
            "title": _("Человекочитаемое название документа."),
            "document_type": _("Тип документа для группировки и фильтрации редакций."),
            "description": _(
                "Описание области применения и юридического назначения документа."
            ),
            "is_active": _("Снимите флаг, чтобы скрыть документ из рабочих сценариев."),
        }


class DocumentRevisionAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        document_field = self.fields.get("document")
        if isinstance(document_field, forms.ModelChoiceField):
            document_field.label_from_instance = lambda obj: (
                f"{obj.title} ({obj.code})" if obj.title else obj.code
            )
        templates_settings = get_document_templates_settings()
        default_format = str(
            templates_settings[constants.CONFIG_DOCUMENT_TEMPLATES_DEFAULT_TEXT_FORMAT]
        )
        if not getattr(self.instance, "pk", None):
            self.fields["format"].initial = default_format
        content_file_field = self.fields.get("content_file")
        if content_file_field is not None:
            content_file_field.widget.attrs["accept"] = ".pdf,.doc,.docx,.odt,.odtx"

        editor_mode = str(
            templates_settings[constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_EDITOR_MODE]
        )
        if editor_mode != constants.DOCUMENT_TEMPLATES_EDITOR_MODE_WYSIWYG:
            return

        widget_path = str(
            templates_settings[constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET]
            or ""
        ).strip()
        if not widget_path:
            return

        widget_attrs = dict(
            templates_settings[
                constants.CONFIG_DOCUMENT_TEMPLATES_ADMIN_WYSIWYG_WIDGET_ATTRS
            ]
            or {}
        )
        try:
            widget_class = import_string(widget_path)
        except Exception:
            return

        if not issubclass(widget_class, forms.Widget):
            return
        self.fields["content_text"].widget = widget_class(attrs=widget_attrs)

    class Meta:
        model = DocumentRevision
        fields = "__all__"
        labels = {
            "document": _("Документ"),
            "purpose_code": _("Код цели"),
            "version": _("Версия"),
            "format": _("Формат"),
            "content_text": _("Текст редакции"),
            "content_file": _("Файл редакции"),
            "fields_snapshot": _("Снимок полей"),
            "meta": _("Метаданные"),
            "is_active": _("Опубликована"),
            "is_box_template": _("Коробочный шаблон"),
            "published_at": _("Дата публикации"),
            "created_at": _("Создано"),
        }
        help_texts = {
            "document": _("Документ, к которому относится эта редакция."),
            "purpose_code": _("Код цели, с которой связана публикация редакции."),
            "version": _("Версия редакции в версионируемом потоке документа."),
            "format": _(
                "Формат содержимого: text/markdown/html или file-формат "
                "(PDF/DOC/DOCX/ODT/ODTX). Для новых шаблонов рекомендуем markdown."
            ),
            "content_text": _("Текст редакции, если выбран текстовый формат."),
            "content_file": _(
                "Загрузите файл редакции для сценариев с файлами "
                "(PDF, DOC, DOCX, ODT, ODTX)."
            ),
            "fields_snapshot": _("JSON-снимок бизнес-полей на момент публикации."),
            "meta": _("Дополнительные служебные метаданные в формате JSON."),
            "is_active": _("Активная редакция используется в текущем потоке согласия."),
            "is_box_template": _("Отметка коробочного шаблона, поставляемого пакетом."),
            "published_at": _("Дата и время публикации редакции."),
            "created_at": _("Техническое время создания записи."),
        }


class ConsentAudienceRuleAdminForm(forms.ModelForm):
    class Meta:
        model = ConsentAudienceRule
        fields = "__all__"
        labels = {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "scope_mode": _("Охват"),
            "group": _("Django-группа"),
            "is_required": _("Требуется согласие"),
            "is_active": _("Активно"),
            "starts_at": _("Начало действия"),
            "ends_at": _("Окончание действия"),
            "notes": _("Заметки"),
            "created_by": _("Создано пользователем"),
        }
        help_texts = {
            "purpose": _("Цель согласия, на которую действует правило аудитории."),
            "document": _("Документ/редакция, требуемые для доступа аудитории."),
            "scope_mode": _(
                "Режим охвата: глобально или только для конкретной группы."
            ),
            "group": _("Django-группа, если правило ограничено group-режимом."),
            "is_required": _("Требовать ли согласие по правилу для целевой аудитории."),
            "is_active": _(
                "Отключите правило, чтобы временно исключить его из вычислений."
            ),
            "starts_at": _("Начало действия правила (опционально)."),
            "ends_at": _("Окончание действия правила (опционально)."),
            "notes": _("Внутренние комментарии для сопровождения правила."),
            "created_by": _("Пользователь, создавший правило."),
        }


class ConsentAccessPolicyAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        document_field = self.fields.get("document")
        if isinstance(document_field, forms.ModelChoiceField):
            document_field.label_from_instance = lambda obj: (
                f"{obj.title} ({obj.code})" if obj.title else obj.code
            )

    class Meta:
        model = ConsentAccessPolicy
        fields = "__all__"
        labels = {
            "code": _("Код"),
            "title": _("Название"),
            "description": _("Описание"),
            "purpose": _("Цель"),
            "document": _("Документ"),
            "resource_code": _("Код ресурса"),
            "app_label": _("Метка приложения"),
            "model_name": _("Модель"),
            "action": _("Действие"),
            "on_missing_consent": _("При отсутствии согласия"),
            "on_outdated_consent": _("При устаревшем согласии"),
            "is_active": _("Активна"),
            "starts_at": _("Начало действия"),
            "ends_at": _("Окончание действия"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
        }
        help_texts = {
            "code": _(
                "Стабильный уникальный код политики доступа (например: "
                "`public_profile_view`, `orders_export`, `crm_contact_update`). "
                "Нужен не только для API-интеграций: используется в аудит-логах, "
                "внутренних ссылках и для однозначной идентификации политики в слое "
                "контроля доступа."
            ),
            "title": _("Краткое название политики доступа."),
            "description": _(
                "Опишите, какой ресурс и почему ограничивается согласием."
            ),
            "purpose": _("Цель согласия, проверяемая перед доступом."),
            "document": _(
                "Документ/редакция, подтверждающие требуемое согласие. "
                "В списке отображается формат «Название (код)»."
            ),
            "resource_code": _(
                "Стабильный код защищаемого ресурса или бизнес-операции "
                "(например: `profile_page`, `orders_export_csv`, "
                "`support_ticket_update`, `billing.invoice_export`). "
                "Ресурсом считается страница, действие или конечная точка, доступ к "
                "которым проверяется слоем контроля доступа. Для охвата по "
                "подсистемам используйте модульный префикс "
                "(`crm.contact_update`, `billing.invoice_export`, "
                "`support.ticket_view`)."
            ),
            "app_label": _("Django app_label целевой модели для model-level проверок."),
            "model_name": _("Имя модели (без app_label) для model-level проверок."),
            "action": _(
                "Код действия при проверке доступа (например: "
                "`view` — просмотр, `add` — создание, `change` — изменение, "
                "`delete` — удаление, `export` — выгрузка). "
                "Поле остаётся свободным: можно указывать и проектные коды "
                "действий (`approve`, `publish`, `archive`), если они используются "
                "в вашем контракте политик доступа."
            ),
            "on_missing_consent": _("Реакция системы, если согласие отсутствует."),
            "on_outdated_consent": _("Реакция системы, если согласие устарело."),
            "is_active": _("Включает или отключает политику во время выполнения."),
            "starts_at": _("Начало действия политики (опционально)."),
            "ends_at": _("Окончание действия политики (опционально)."),
            "notes": _("Внутренние пояснения по назначению политики."),
            "extra_meta": _(
                "Дополнительные технические метаданные в JSON. "
                "Для группировки политик по модулю/подсистеме используйте "
                "контракт вида: "
                '{"module_scope": "billing", "subsystem": "invoices"}.'
            ),
        }


class PersonalDataManagerAssignmentAdminForm(forms.ModelForm):
    class Meta:
        model = PersonalDataManagerAssignment
        fields = "__all__"
        labels = {
            "user": _("Пользователь"),
            "scope_mode": _("Охват"),
            "groups": _("Django-группы"),
            "can_manage_purposes": _("Может управлять целями"),
            "can_manage_documents": _("Может управлять документами"),
            "can_publish_revisions": _("Может публиковать редакции"),
            "can_manage_audience_rules": _("Может управлять правилами аудитории"),
            "can_manage_access_policies": _("Может управлять политиками доступа"),
            "can_handle_verified_consents": _(
                "Может обрабатывать подтверждённые/ручные согласия"
            ),
            "is_active": _("Активно"),
        }
        help_texts = {
            "user": _("Пользователь, которому назначаются роли управления согласием."),
            "scope_mode": _("Область действия назначения: глобальная или по группам."),
            "groups": _(
                "Группы, в рамках которых действует назначение (если применимо)."
            ),
            "can_manage_purposes": _("Разрешение управлять целями согласия."),
            "can_manage_documents": _("Разрешение управлять документами и редакциями."),
            "can_publish_revisions": _("Разрешение публиковать новые редакции."),
            "can_manage_audience_rules": _("Разрешение управлять правилами аудитории."),
            "can_manage_access_policies": _(
                "Разрешение управлять правилами политик доступа."
            ),
            "can_handle_verified_consents": _(
                "Разрешение обрабатывать артефакты подтверждённых/ручных согласий."
            ),
            "is_active": _("Отключите назначение, чтобы временно снять полномочия."),
        }


class ConsentSelfServiceSettingsAdminForm(forms.ModelForm):
    class Meta:
        model = ConsentSelfServiceSettings
        fields = "__all__"
        labels = {
            "subject_consents_open_mode": _(
                "Как открывать «Открыть и подписать» в самообслуживании"
            ),
            "subject_consents_list_mode": _("Что показывать в списке самообслуживания"),
            "consent_input_mode": _("Вариант UI подтверждения согласия"),
            "checkbox_required": _("Обязательный флажок в форме согласия"),
            "decline_action": _("Поведение при выборе «не согласен»"),
            "decline_warning_enabled": _("Показывать предупреждение при отказе"),
            "decline_warning_text": _("Текст предупреждения при отказе"),
            "csv_export_delimiter": _("Разделитель CSV-экспорта"),
            "printable_pdf_paper_size": _("Формат бумаги для печатного PDF"),
            "printable_pdf_font_family": _("Шрифт печатного PDF"),
            "printable_pdf_font_size": _("Размер шрифта печатного PDF"),
            "printable_pdf_text_align": _("Выравнивание текста печатного PDF"),
            "printable_pdf_show_signature_footer": _(
                "Добавлять блок подписи внизу PDF"
            ),
            "printable_pdf_signature_align": _("Выравнивание подписи (ПОДПИСЬ/ФИО)"),
        }
        help_texts = {
            "subject_consents_open_mode": _(
                "Определяет, как открывать страницу документа из списка самообслуживания: "
                "в текущей вкладке, в новом окне или в модальном окне."
            ),
            "subject_consents_list_mode": _(
                "Режим списка: все потоки, только требующие подписи или только уже подписанные."
            ),
            "consent_input_mode": _(
                "Выберите тип элемента в блоке подписания: флажок или переключатель."
            ),
            "checkbox_required": _(
                "Если включено, без отметки флажка отправка формы невозможна."
            ),
            "decline_action": _(
                "Определяет, блокировать ли отправку формы при выборе варианта «не согласен»."
            ),
            "decline_warning_enabled": _(
                "Показывать диалог-предупреждение перед отправкой формы при отказе."
            ),
            "decline_warning_text": _(
                "Текст предупреждения в диалоге подтверждения отказа."
            ),
            "csv_export_delimiter": _(
                "Разделитель по умолчанию для CSV-экспорта в административных списках согласий."
            ),
            "printable_pdf_paper_size": _(
                "Формат страницы для автоматически сгенерированного PDF согласия."
            ),
            "printable_pdf_font_family": _(
                "Базовый шрифт для текста в автоматически сгенерированном PDF."
            ),
            "printable_pdf_font_size": _(
                "Размер шрифта в пунктах (pt), используется при генерации печатного PDF."
            ),
            "printable_pdf_text_align": _(
                "Выравнивание текста по умолчанию для печатной PDF-версии согласия."
            ),
            "printable_pdf_show_signature_footer": _(
                "Добавляет внизу страницы поля даты и подписи для печатного подписания."
            ),
            "printable_pdf_signature_align": _(
                "Положение подписи (ПОДПИСЬ/ФИО): слева, по центру или справа."
            ),
        }

    def clean(self):
        cleaned_data = cast(dict[str, Any], super().clean())
        font_size = int(cleaned_data.get("printable_pdf_font_size") or 0)
        if font_size < 8 or font_size > 24:
            self.add_error(
                "printable_pdf_font_size",
                _("Размер шрифта должен быть в диапазоне от 8 до 24 pt."),
            )
        return cleaned_data


class StarterTemplateOriginFilter(admin.SimpleListFilter):
    """A separate filter that splits starter templates from custom revisions."""

    title = _("Revision origin")
    parameter_name = "revision_origin"

    def lookups(self, request, model_admin):
        return (
            ("starter", _("Starter templates")),
            ("custom", _("Custom revisions")),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "starter":
            return queryset.filter(is_box_template=True)
        if value == "custom":
            return queryset.filter(is_box_template=False)
        return queryset


class LegalDocumentTemplateStatusFilter(admin.SimpleListFilter):
    """Separate filter for starter document streams and regular documents."""

    title = _("Document stream")
    parameter_name = "document_stream"

    def lookups(self, request, model_admin):
        return (
            ("starter", _("Starter template stream")),
            ("custom", _("Custom stream")),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "starter":
            return queryset.filter(revisions__is_box_template=True).distinct()
        if value == "custom":
            return queryset.filter(revisions__is_box_template=False).distinct()
        return queryset


class LegalDocumentTypeFilter(admin.SimpleListFilter):
    """Localized document type filter in the admin panel."""

    title = _("Тип документа")
    parameter_name = "document_type"

    def lookups(self, request, model_admin):
        values = (
            model_admin.get_queryset(request)
            .exclude(document_type__isnull=True)
            .exclude(document_type__exact="")
            .order_by()
            .values_list("document_type", flat=True)
            .distinct()
        )
        return [(value, _format_document_type_label(str(value))) for value in values]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(document_type=value)


class ConsentPurposeAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for personal-data processing purposes."""

    form = ConsentPurposeAdminForm
    change_permission_flags = "can_manage_purposes"
    list_display = (
        "code",
        "title",
        "withdraw_strategy",
        "reconsent_mode",
        "consent_frequency_policy",
        "subject_availability_policy",
        "is_active",
        "is_experimental",
    )
    list_display_links = ("code", "title")
    list_filter = (
        "is_active",
        "is_experimental",
        "withdraw_strategy",
        "reconsent_mode",
        "consent_frequency_policy",
        "subject_availability_policy",
    )
    search_fields = ("code", "title", "description")
    fields = (
        "starter_template",
        "code",
        "title",
        "description",
        "fields_config",
        "withdraw_strategy",
        "reconsent_mode",
        "consent_frequency_policy",
        "subject_availability_policy",
        "consent_input_mode_override",
        "checkbox_required_override",
        "decline_action_override",
        "decline_warning_enabled_override",
        "decline_warning_text_override",
        "is_experimental",
        "is_active",
    )


class LegalDocumentAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for the legal documents that revisions are bound to."""

    form = LegalDocumentAdminForm
    change_permission_flags = "can_manage_documents"
    list_display = (
        "code",
        "title",
        "document_type_display",
        "template_status_display",
        "is_active",
        "updated_at",
    )
    list_display_links = ("code", "title")
    list_filter = (
        "is_active",
        LegalDocumentTypeFilter,
        LegalDocumentTemplateStatusFilter,
    )
    search_fields = ("code", "title", "description")
    actions = ("clone_selected_document_streams_as_drafts",)

    @admin.display(description=_("Тип документа"))
    def document_type_display(self, obj) -> str:
        return _format_document_type_label(str(obj.document_type or ""))

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        revisions = DocumentRevision.objects.filter(document_id=OuterRef("pk"))
        return queryset.annotate(
            has_box_templates=Exists(revisions.filter(is_box_template=True)),
            has_custom_revisions=Exists(revisions.filter(is_box_template=False)),
        )

    @admin.display(description=_("Document stream"))
    def template_status_display(self, obj) -> str:
        has_box_templates = bool(getattr(obj, "has_box_templates", False))
        has_custom_revisions = bool(getattr(obj, "has_custom_revisions", False))
        if has_box_templates and has_custom_revisions:
            return str(_("Starter + custom"))
        if has_box_templates:
            return str(_("Starter template stream"))
        if has_custom_revisions:
            return str(_("Custom stream"))
        return str(_("No revisions"))

    @admin.action(description=_("Склонировать выбранные документы в черновые потоки"))
    def clone_selected_document_streams_as_drafts(self, request, queryset) -> None:
        success_count = 0
        total_cloned_revisions = 0
        for document in queryset.order_by("pk"):
            _cloned_document, cloned_revisions = clone_legal_document_stream_as_draft(
                source_document=document
            )
            success_count += 1
            total_cloned_revisions += cloned_revisions

        if success_count:
            self.message_user(
                request,
                ngettext(
                    "Склонирован %(count)d поток документа.",
                    "Склонировано %(count)d потоков документов.",
                    success_count,
                )
                % {"count": success_count},
                level=messages.SUCCESS,
            )
        log_module_operation(
            operation_code="admin.legal_document.clone_document_streams",
            actor_user=request.user,
            source="admin.core.legal_document",
            target_model="django_consent_152fz.LegalDocument",
            summary="Clone legal document streams as draft copies.",
            payload={"selected_count": queryset.count()},
            result={
                "success_count": success_count,
                "cloned_revisions_count": total_cloned_revisions,
            },
        )


class DocumentRevisionAdmin(
    PublishableRevisionAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Admin for document revisions and bulk application of audience rules."""

    form = DocumentRevisionAdminForm
    action_form = DocumentRevisionActionForm
    save_as = True
    change_permission_flags = "can_publish_revisions"
    view_permission_flags = ("can_publish_revisions", "can_manage_documents")
    list_display = (
        "document_title",
        "document_code",
        "purpose_code",
        "revision_origin_display",
        "version",
        "format",
        "is_active",
        "published_at",
    )
    list_display_links = ("document_title", "document_code", "purpose_code", "version")
    list_filter = ("format", "is_active", StarterTemplateOriginFilter, "purpose_code")
    search_fields = (
        "document__code",
        "document__title",
        "purpose_code",
        "content_text",
    )
    list_select_related = ("document",)
    readonly_fields = (
        "version",
        "revision_origin_display",
        "template_source_display",
        "published_at",
        "created_at",
    )
    fields = (
        "document",
        "purpose_code",
        "version",
        "revision_origin_display",
        "template_source_display",
        "format",
        "content_text",
        "content_file",
        "fields_snapshot",
        "meta",
        "is_active",
        "is_box_template",
        "published_at",
        "created_at",
    )
    actions = (
        "clone_starter_templates_as_drafts",
        "apply_revision_to_all_registered_users",
        "apply_revision_to_selected_groups",
    )

    @admin.display(description=_("Document title"))
    def document_title(self, obj) -> str:
        return obj.document.title

    @admin.display(description=_("Код документа"))
    def document_code(self, obj) -> str:
        return obj.document.code

    @admin.display(description=_("Origin"))
    def revision_origin_display(self, obj) -> str:
        if obj.is_box_template:
            return str(_("Starter template"))
        if isinstance(obj.meta, dict) and obj.meta.get("derived_from_box_template"):
            return str(_("Custom draft from starter template"))
        return str(_("Custom revision"))

    @admin.display(description=_("Source template"))
    def template_source_display(self, obj) -> str:
        if obj.is_box_template:
            return str(_("Starter template"))
        if not isinstance(obj.meta, dict):
            return "—"

        source_document_code = obj.meta.get("box_template_source_document_code")
        source_purpose_code = obj.meta.get("box_template_source_purpose_code")
        source_version = obj.meta.get("box_template_source_version")
        if source_document_code and source_purpose_code and source_version:
            return f"{source_document_code} / {source_purpose_code} / v{source_version}"
        return "—"

    @admin.action(
        description=_("Create custom draft copies from selected starter templates")
    )
    def clone_starter_templates_as_drafts(self, request, queryset) -> None:
        """Clone starter templates into ordinary unpublished revisions.

        This supports the typical section 4.3 workflow:
        1. a project loads the box-provided sample documents;
        2. the operator locates them via a dedicated admin filter;
        3. creates a private copy to adapt the text;
        4. later edits and publishes the customized revision.
        """

        success_count = 0
        error_count = 0
        for revision in queryset.select_related("document").order_by("pk"):
            try:
                clone_box_template_revision(template_revision=revision)
                success_count += 1
            except ConsentError:
                error_count += 1

        if success_count:
            self.message_user(
                request,
                ngettext(
                    "Created %(count)d custom draft from starter template.",
                    "Created %(count)d custom drafts from starter templates.",
                    success_count,
                )
                % {"count": success_count},
                level=messages.SUCCESS,
            )
        log_module_operation(
            operation_code="admin.document_revision.clone_starter_templates",
            actor_user=request.user,
            source="admin.core.document_revision",
            target_model="django_consent_152fz.DocumentRevision",
            summary="Clone starter templates as custom drafts.",
            payload={"selected_count": queryset.count()},
            result={
                "success_count": success_count,
                "error_count": error_count,
            },
        )
        if error_count:
            self.message_user(
                request,
                ngettext(
                    "Failed to adapt %(count)d revision. Action is available only for starter templates without file content.",
                    "Failed to adapt %(count)d revisions. Action is available only for starter templates without file content.",
                    error_count,
                )
                % {"count": error_count},
                level=messages.WARNING,
            )

    @admin.action(description=_("Apply revision to all registered users"))
    def apply_revision_to_all_registered_users(self, request, queryset) -> None:
        """Apply the revision to the entire registered-users audience."""

        if not has_personal_data_manager_permission(
            request.user,
            permission_flags="can_manage_audience_rules",
        ):
            self.message_user(
                request,
                _("Insufficient permissions to manage audience rules."),
                level=messages.ERROR,
            )
            return

        affected = self._apply_audience_rules(
            queryset=queryset,
            created_by=request.user,
            scope_mode=ConsentAudienceRule.ScopeMode.ALL_REGISTERED_USERS,
        )
        self.message_user(
            request,
            ngettext(
                "Applied %(count)d rule to all registered users.",
                "Applied %(count)d rules to all registered users.",
                affected,
            )
            % {"count": affected},
            level=messages.SUCCESS,
        )
        log_module_operation(
            operation_code="admin.document_revision.apply_all_registered_users",
            actor_user=request.user,
            source="admin.core.document_revision",
            target_model="django_consent_152fz.DocumentRevision",
            summary="Apply revision to all registered users.",
            payload={"selected_count": queryset.count()},
            result={"created_or_updated_rules": affected},
        )

    @admin.action(description=_("Apply revision to selected Django groups"))
    def apply_revision_to_selected_groups(self, request, queryset) -> None:
        """Creates audience rules only for selected Django groups."""

        if not has_personal_data_manager_permission(
            request.user,
            permission_flags="can_manage_audience_rules",
        ):
            self.message_user(
                request,
                _("Insufficient permissions to manage audience rules."),
                level=messages.ERROR,
            )
            return

        group_ids = request.POST.getlist("audience_groups")
        groups = list(Group.objects.filter(pk__in=group_ids).order_by("pk"))
        if not groups:
            self.message_user(
                request,
                _("Select at least one group for this action."),
                level=messages.ERROR,
            )
            return

        affected = self._apply_audience_rules(
            queryset=queryset,
            created_by=request.user,
            scope_mode=ConsentAudienceRule.ScopeMode.DJANGO_GROUP,
            groups=groups,
        )
        self.message_user(
            request,
            ngettext(
                "Applied %(count)d rule to selected Django groups.",
                "Applied %(count)d rules to selected Django groups.",
                affected,
            )
            % {"count": affected},
            level=messages.SUCCESS,
        )
        log_module_operation(
            operation_code="admin.document_revision.apply_selected_groups",
            actor_user=request.user,
            source="admin.core.document_revision",
            target_model="django_consent_152fz.DocumentRevision",
            summary="Apply revision to selected Django groups.",
            payload={
                "selected_count": queryset.count(),
                "group_ids": [group.pk for group in groups],
            },
            result={"created_or_updated_rules": affected},
        )

    def save_model(self, request, obj, form, change) -> None:
        """Automatically versions the revision and deactivates the previously active one."""

        if not change:
            latest_version = (
                DocumentRevision.objects.filter(
                    document=obj.document,
                    purpose_code=obj.purpose_code,
                )
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            )
            self.assign_next_version(obj, latest_version=latest_version)
        self.ensure_published_at(obj, now_value=timezone.now())

        super().save_model(request, obj, form, change)

        if obj.is_active:
            DocumentRevision.objects.filter(
                document=obj.document,
                purpose_code=obj.purpose_code,
            ).exclude(pk=obj.pk).update(is_active=False)
            log_module_operation(
                operation_code="admin.document_revision.publish",
                actor_user=request.user,
                source="admin.core.document_revision",
                target_model="django_consent_152fz.DocumentRevision",
                target_id=str(obj.pk),
                summary="Published document revision.",
                result={
                    "document_code": obj.document.code,
                    "purpose_code": obj.purpose_code,
                    "version": obj.version,
                },
            )

    def _apply_audience_rules(
        self,
        *,
        queryset,
        created_by,
        scope_mode: str,
        groups: list[Group] | None = None,
    ) -> int:
        """Creates or updates audience rules for selected revision streams."""

        affected = 0
        revisions = queryset.select_related("document").order_by("pk")
        purposes_by_code = {
            purpose.code: purpose
            for purpose in ConsentPurpose.objects.filter(
                code__in={revision.purpose_code for revision in revisions}
            )
        }
        for revision in revisions:
            purpose = purposes_by_code.get(revision.purpose_code)
            if purpose is None:
                continue
            target_groups = groups or [None]
            for group in target_groups:
                ConsentAudienceRule.objects.update_or_create(
                    purpose=purpose,
                    document=revision.document,
                    scope_mode=scope_mode,
                    group=group,
                    defaults={
                        "is_required": True,
                        "is_active": True,
                        "created_by": created_by,
                        "notes": f"Applied from admin for revision {revision.pk}.",
                    },
                )
                affected += 1
        return affected


class ConsentAudienceRuleAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for the audience rules from section 4.9."""

    form = ConsentAudienceRuleAdminForm
    change_permission_flags = "can_manage_audience_rules"
    list_display = (
        "purpose",
        "document",
        "scope_mode",
        "group",
        "is_required",
        "is_active",
    )
    list_display_links = ("purpose", "document")
    list_filter = ("scope_mode", "is_required", "is_active", "purpose", "document")
    search_fields = ("purpose__code", "document__code", "group__name", "notes")
    raw_id_fields = ("group", "created_by")
    actions = ("clone_selected_rules_as_drafts",)

    @admin.action(
        description=_("Склонировать выбранные правила аудитории как черновики")
    )
    def clone_selected_rules_as_drafts(self, request, queryset) -> None:
        success_count = 0
        for rule in queryset.select_related("purpose", "document", "group").order_by(
            "pk"
        ):
            clone_audience_rule_as_draft(
                source_rule=rule,
                created_by=request.user,
            )
            success_count += 1

        if success_count:
            self.message_user(
                request,
                ngettext(
                    "Склонировано %(count)d правило аудитории.",
                    "Склонировано %(count)d правил аудитории.",
                    success_count,
                )
                % {"count": success_count},
                level=messages.SUCCESS,
            )
        log_module_operation(
            operation_code="admin.audience_rule.clone_rules",
            actor_user=request.user,
            source="admin.core.consent_audience_rule",
            target_model="django_consent_152fz.ConsentAudienceRule",
            summary="Clone audience rules as draft copies.",
            payload={"selected_count": queryset.count()},
            result={"success_count": success_count},
        )


class ConsentAccessPolicyAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Admin for access policies and the section 4.11 guard-layer rules."""

    form = ConsentAccessPolicyAdminForm
    change_permission_flags = "can_manage_access_policies"
    list_display = (
        "code",
        "resource_code",
        "action",
        "purpose",
        "document",
        "is_active",
    )
    list_display_links = ("code", "resource_code")
    list_filter = ("is_active", "action", "purpose", "document")
    search_fields = ("code", "resource_code", "title", "description")
    autocomplete_fields = ("purpose", "document")
    actions = ("clone_selected_policies_as_drafts",)

    @admin.action(description=_("Склонировать выбранные access policy как черновики"))
    def clone_selected_policies_as_drafts(self, request, queryset) -> None:
        success_count = 0
        for policy in queryset.select_related("purpose", "document").order_by("pk"):
            clone_access_policy_as_draft(source_policy=policy)
            success_count += 1

        if success_count:
            self.message_user(
                request,
                ngettext(
                    "Склонирована %(count)d access policy.",
                    "Склонировано %(count)d access policy.",
                    success_count,
                )
                % {"count": success_count},
                level=messages.SUCCESS,
            )
        log_module_operation(
            operation_code="admin.access_policy.clone_policies",
            actor_user=request.user,
            source="admin.core.consent_access_policy",
            target_model="django_consent_152fz.ConsentAccessPolicy",
            summary="Clone access policies as draft copies.",
            payload={"selected_count": queryset.count()},
            result={"success_count": success_count},
        )


class ConsentRecordSubjectTypeFilter(admin.SimpleListFilter):
    """Subject type filter for consent-records."""

    title = _("Тип субъекта")
    parameter_name = "subject_type"

    def lookups(self, request, model_admin):
        return (
            ("registered", _("Зарегистрированный")),
            ("anonymous", _("Анонимный")),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "registered":
            return queryset.filter(user__isnull=False)
        if value == "anonymous":
            return queryset.filter(user__isnull=True)
        return queryset


class ConsentRecordAdmin(
    ReadOnlyAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Read-only admin for consent records with CSV export."""

    change_permission_flags = None
    list_display = (
        "id",
        "purpose",
        "document_code",
        "status",
        "confirmation_method",
        "subject_display",
        "source",
        "created_at",
    )
    list_display_links = ("subject_display", "purpose", "document_code", "created_at")
    list_filter = (
        "status",
        "confirmation_method",
        ConsentRecordSubjectTypeFilter,
        "purpose",
        "purpose__consent_frequency_policy",
        "purpose__subject_availability_policy",
        "source",
    )
    search_fields = (
        "subject_ref",
        "anonymous_token",
        f"user__{USER_LOOKUP}",
        "purpose__code",
        "document_revision__document__code",
    )
    raw_id_fields = ("user", "confirmed_by", "document_revision")
    actions = ("export_selected_records",)

    @admin.display(description=_("Document"))
    def document_code(self, obj) -> str:
        return obj.document_revision.document.code

    @admin.display(description=_("Subject"))
    def subject_display(self, obj) -> str:
        if obj.user_id:
            return str(obj.user)
        if obj.anonymous_token:
            return str(_("Анонимный субъект"))
        return obj.subject_ref or str(_("Не указан"))

    @admin.action(
        description=_("Export selected records to CSV"),
        permissions=["view"],
    )
    def export_selected_records(self, request, queryset) -> HttpResponse:
        """Export writes records to CSV without losing the structured `extra_meta`."""

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="consent-records.csv"'
        writer = csv.writer(response, delimiter=_resolve_csv_delimiter())
        writer.writerow(
            [
                "id",
                "purpose_code",
                "document_code",
                "status",
                "confirmation_method",
                "user_id",
                "anonymous_token",
                "subject_ref",
                "source",
                "locale",
                "created_at",
                "extra_meta",
            ]
        )
        for record in queryset.select_related("purpose", "document_revision__document"):
            writer.writerow(
                _sanitize_csv_row(
                    [
                        record.pk,
                        record.purpose.code,
                        record.document_revision.document.code,
                        record.status,
                        record.confirmation_method,
                        record.user_id or "",
                        record.anonymous_token,
                        record.subject_ref,
                        record.source,
                        record.locale,
                        record.created_at.isoformat(),
                        json.dumps(
                            record.extra_meta, ensure_ascii=False, sort_keys=True
                        ),
                    ]
                )
            )
        return response


class ConsentEventAdmin(
    ReadOnlyAdminMixin,
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Read-only admin for immutable audit events."""

    change_permission_flags = None
    list_display = (
        "id",
        "consent_record",
        "event_type",
        "actor_type",
        "actor_user",
        "source",
        "occurred_at",
    )
    list_display_links = ("consent_record", "event_type", "source", "occurred_at")
    list_filter = ("event_type", "actor_type", "source")
    search_fields = (
        "consent_record__purpose__code",
        "consent_record__document_revision__document__code",
        "request_id",
    )
    raw_id_fields = ("consent_record", "actor_user")


class PersonalDataManagerAssignmentAdmin(
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Admin for the Personal-Data-Manager role assignment model."""

    form = PersonalDataManagerAssignmentAdminForm
    superuser_only = True
    list_display = (
        "user",
        "scope_mode",
        "is_active",
        "can_manage_purposes",
        "can_manage_documents",
        "can_publish_revisions",
        "can_manage_audience_rules",
        "can_manage_access_policies",
        "can_handle_verified_consents",
    )
    list_display_links = ("user",)
    list_filter = ("scope_mode", "is_active")
    search_fields = (f"user__{USER_LOOKUP}", "groups__name")
    filter_horizontal = ("groups",)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("user",)

    def save_model(self, request, obj, form, change) -> None:
        """Make the user a staff member and sync their service group membership."""

        if not obj.user.is_staff:
            obj.user.is_staff = True
            obj.user.save(update_fields=["is_staff"])
        super().save_model(request, obj, form, change)
        sync_personal_data_manager_group_membership(assignment=obj)

    def save_related(self, request, form, formsets, change) -> None:
        """Re-sync membership after the M2M groups change."""

        super().save_related(request, form, formsets, change)
        sync_personal_data_manager_group_membership(assignment=form.instance)

    def delete_model(self, request, obj) -> None:
        """When deleted, the group membership is removed first."""

        obj.is_active = False
        sync_personal_data_manager_group_membership(assignment=obj)
        super().delete_model(request, obj)

    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        extra_context["personal_data_manager_group_label"] = (
            PERSONAL_DATA_MANAGER_GROUP_LABEL
        )
        return super().changelist_view(request, extra_context=extra_context)


class ConsentSelfServiceSettingsAdmin(
    AssignmentRestrictedAdminMixin,
    admin.ModelAdmin,
):
    """Administrator of singleton self-service UI settings."""

    form = ConsentSelfServiceSettingsAdminForm
    superuser_only = True
    list_display = ("subject_consents_open_mode", "consent_input_mode", "updated_at")
    list_display_links = ("subject_consents_open_mode",)
    fields = (
        "subject_consents_open_mode",
        "subject_consents_list_mode",
        "consent_input_mode",
        "checkbox_required",
        "decline_action",
        "decline_warning_enabled",
        "decline_warning_text",
        "csv_export_delimiter",
        "printable_pdf_paper_size",
        "printable_pdf_font_family",
        "printable_pdf_font_size",
        "printable_pdf_text_align",
        "printable_pdf_show_signature_footer",
        "printable_pdf_signature_align",
    )

    def has_add_permission(self, request) -> bool:
        if not super().has_add_permission(request):
            return False
        return not ConsentSelfServiceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ModuleOperationAuditLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only admin of the operation log of the main module 152-FZ."""

    change_permission_flags = None
    list_display = (
        "id",
        "created_at",
        "operation_code",
        "status_display",
        "summary_display",
        "source",
        "actor_user",
        "target_model",
        "target_id",
    )
    list_display_links = ("created_at", "operation_code")
    list_filter = ("status", "source", "operation_code")
    search_fields = (
        "operation_code",
        "source",
        "target_model",
        "target_id",
        "summary",
    )
    raw_id_fields = ("actor_user",)
    actions = ("export_selected_records",)
    summary_translation_map = {
        "Clone legal document streams as draft copies.": _(
            "Клонирование потоков юридических документов в черновики."
        ),
        "Clone starter templates as custom drafts.": _(
            "Клонирование starter-шаблонов в пользовательские черновики."
        ),
        "Apply revision to all registered users.": _(
            "Применение редакции ко всем зарегистрированным пользователям."
        ),
        "Apply revision to selected Django groups.": _(
            "Применение редакции к выбранным Django-группам."
        ),
        "Published document revision.": _("Опубликована редакция документа."),
        "Clone audience rules as draft copies.": _(
            "Клонирование правил аудитории в черновики."
        ),
        "Clone access policies as draft copies.": _(
            "Клонирование политик доступа в черновики."
        ),
        "Bootstrap sample consent templates, policies and audience rules.": _(
            "Инициализация sample-шаблонов согласий, политик и правил аудитории."
        ),
        "Import baseline core consents from CSV.": _(
            "Импорт базовых consent-записей core из CSV."
        ),
    }

    def get_queryset(self, request):
        # The audit table is shared with the standalone cookies package. The
        # consent operation log shows consent-side operations only; cookie
        # operations (admin.cookies.*, service.cookies.*, cookies.*) belong to
        # the cookies admin and are excluded here.
        queryset = super().get_queryset(request)
        return (
            queryset.exclude(operation_code__startswith="admin.cookies.")
            .exclude(operation_code__startswith="service.cookies.")
            .exclude(operation_code__startswith="cookies.")
            .exclude(source__startswith="admin.cookies.")
            .exclude(source__startswith="cookies.")
        )

    @admin.display(description=_("Статус"), ordering="status")
    def status_display(self, obj) -> str:
        return str(obj.get_status_display() or obj.status)

    @admin.display(description=_("Описание"), ordering="summary")
    def summary_display(self, obj) -> str:
        summary = str(obj.summary or "").strip()
        if not summary:
            return ""
        return str(self.summary_translation_map.get(summary, summary))

    @admin.action(description=_("Экспортировать выбранные записи журнала в CSV"))
    def export_selected_records(self, request, queryset) -> HttpResponse:
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            'attachment; filename="consent-module-operation-audit.csv"'
        )
        writer = csv.writer(response, delimiter=_resolve_csv_delimiter())
        writer.writerow(
            [
                "id",
                "created_at",
                "operation_code",
                "status",
                "source",
                "actor_user_id",
                "target_model",
                "target_id",
                "summary",
                "payload",
                "result",
            ]
        )
        for item in queryset.order_by("id"):
            writer.writerow(
                _sanitize_csv_row(
                    [
                        item.pk,
                        item.created_at.isoformat(),
                        item.operation_code,
                        item.status,
                        item.source,
                        item.actor_user_id or "",
                        item.target_model,
                        item.target_id,
                        item.summary,
                        json.dumps(item.payload, ensure_ascii=False, sort_keys=True),
                        json.dumps(item.result, ensure_ascii=False, sort_keys=True),
                    ]
                )
            )
        return response


def register_admin(site: admin.sites.AdminSite) -> None:
    """Register core admin models via explicit app-level contract."""

    _patch_admin_site_app_list(site)
    safe_register_admin_models(
        site,
        registrations=(
            (ConsentPurpose, ConsentPurposeAdmin),
            (LegalDocument, LegalDocumentAdmin),
            (DocumentRevision, DocumentRevisionAdmin),
            (ConsentAudienceRule, ConsentAudienceRuleAdmin),
            (ConsentAccessPolicy, ConsentAccessPolicyAdmin),
            (ConsentRecord, ConsentRecordAdmin),
            (ConsentEvent, ConsentEventAdmin),
            (PersonalDataManagerAssignment, PersonalDataManagerAssignmentAdmin),
            (ConsentSelfServiceSettings, ConsentSelfServiceSettingsAdmin),
            (ConsentModuleOperationAuditLog, ModuleOperationAuditLogAdmin),
        ),
    )


register_admin(admin.site)
