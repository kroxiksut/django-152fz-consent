"""Admin-часть optional verified-consent сценариев.

Несмотря на отдельный контур verified-consents, permission-модель здесь
та же, что и в остальном admin-слое пункта 5.2.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Django dynamic ORM/admin attributes are not fully inferable by pyright.
import os

# ruff: noqa: E501
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from django_consent_152fz.admin_helpers import (
    AssignmentRestrictedAdminMixin,
    safe_register_admin_models,
)
from django_consent_152fz.core.models import ConsentEvent, ConsentRecord
from django_consent_152fz.exceptions import ConsentError

from .models import (
    VerifiedConsentArtifact,
    VerifiedConsentFormPolicy,
    VerifiedConsentPolicy,
    VerifiedConsentSubmission,
)
from .services import confirm_verified_consent, reject_verified_consent


def _set_verbose_names(model, field_labels: dict[str, object]) -> None:
    for field_name, label in field_labels.items():
        model._meta.get_field(field_name).verbose_name = label


def _localize_verified_admin_field_labels() -> None:
    _set_verbose_names(
        VerifiedConsentPolicy,
        {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "verification_mode": _("Режим верификации"),
            "flow_scope": _("Область применения"),
            "legacy_web_consent_policy": _("Поведение для старых веб-согласий"),
            "allow_subject_self_upload": _("Разрешать самозагрузку субъектом"),
            "allow_draft_data_before_upload": _(
                "Разрешать сохранение данных до загрузки согласия"
            ),
            "pre_upload_access_mode": _("Поведение до загрузки бумажного согласия"),
            "notification_mode": _("Канал уведомлений"),
            "notification_templates": _("Шаблоны уведомлений"),
            "notify_on_data_saved": _("Уведомлять при сохранении данных"),
            "notify_on_paper_uploaded": _("Уведомлять при загрузке согласия"),
            "notify_on_verified": _("Уведомлять при подтверждении согласия"),
            "notify_on_rejected": _("Уведомлять при отклонении согласия"),
            "is_active": _("Активна"),
            "starts_at": _("Начало действия"),
            "ends_at": _("Окончание действия"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
        },
    )
    _set_verbose_names(
        VerifiedConsentArtifact,
        {
            "consent_record": _("Запись согласия"),
            "policy": _("Политика"),
            "artifact_type": _("Тип артефакта"),
            "file": _("Файл артефакта"),
            "external_provider": _("Внешний провайдер"),
            "external_ref": _("Внешняя ссылка/идентификатор"),
            "subject_signed_at": _("Время подписи субъектом"),
            "note": _("Заметка"),
            "extra_meta": _("Метаданные"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        },
    )
    _set_verbose_names(
        VerifiedConsentFormPolicy,
        {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "form_code": _("Код формы"),
            "verification_mode_override": _("Режим верификации для формы"),
            "draft_data_policy_override": _("Политика сохранения данных до загрузки"),
            "pre_upload_access_mode_override": _(
                "Поведение до загрузки бумажного согласия"
            ),
            "notification_mode_override": _("Канал уведомлений"),
            "is_active": _("Активна"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        },
    )
    _set_verbose_names(
        VerifiedConsentSubmission,
        {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "user": _("Пользователь"),
            "anonymous_token": _("Анонимный токен"),
            "subject_ref": _("Внешний идентификатор субъекта"),
            "form_code": _("Код формы"),
            "status": _("Статус заявки"),
            "subject_data": _("Данные субъекта"),
            "generated_blank_file": _("Сгенерированный бланк согласия"),
            "blank_generated_at": _("Когда сгенерирован бланк"),
            "consent_record": _("Запись согласия"),
            "latest_artifact": _("Последний артефакт"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
            "completed_at": _("Время завершения"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        },
    )


_localize_verified_admin_field_labels()


class VerifiedArtifactActionForm(ActionForm):
    """Дополнительные поля для массовых admin-action verified-артефактов."""

    confirmation_note = forms.CharField(
        required=False,
        label=_("Комментарий подтверждения"),
        help_text=_(
            "Комментарий, который будет записан при массовом подтверждении артефактов."
        ),
    )
    rejection_note = forms.CharField(
        required=False,
        label=_("Причина отклонения"),
        help_text=_("Причина отклонения, которая будет сохранена в аудите действий."),
    )


class VerifiedConsentPolicyAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        purpose_field = self.fields.get("purpose")
        if purpose_field is not None:
            purpose_field.label_from_instance = lambda obj: (
                f"{obj.title} ({obj.code})" if obj.title else obj.code
            )
        document_field = self.fields.get("document")
        if document_field is not None:
            document_field.label_from_instance = lambda obj: (
                f"{obj.title} ({obj.code})" if obj.title else obj.code
            )

    class Meta:
        model = VerifiedConsentPolicy
        fields = "__all__"
        labels = {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "verification_mode": _("Режим верификации"),
            "flow_scope": _("Область применения"),
            "legacy_web_consent_policy": _("Поведение для старых веб-согласий"),
            "allow_subject_self_upload": _("Разрешать самозагрузку субъектом"),
            "allow_draft_data_before_upload": _(
                "Разрешать сохранение данных до загрузки согласия"
            ),
            "pre_upload_access_mode": _("Поведение до загрузки бумажного согласия"),
            "notification_mode": _("Канал уведомлений"),
            "notification_templates": _("Шаблоны уведомлений"),
            "notify_on_data_saved": _("Уведомлять при сохранении данных"),
            "notify_on_paper_uploaded": _("Уведомлять при загрузке согласия"),
            "notify_on_verified": _("Уведомлять при подтверждении согласия"),
            "notify_on_rejected": _("Уведомлять при отклонении согласия"),
            "is_active": _("Активна"),
            "starts_at": _("Начало действия"),
            "ends_at": _("Окончание действия"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
        }
        help_texts = {
            "purpose": _(
                "Цель согласия, для которой применяется политика подтверждения."
            ),
            "document": _(
                "Документ/редакция, участвующие в сценарии подтверждённого согласия."
            ),
            "verification_mode": _(
                "Режим верификации: кто и как подтверждает согласие."
            ),
            "flow_scope": _(
                "Где применяется проверяемый сценарий согласия: в личном кабинете, в веб-формах или в обоих сценариях."
            ),
            "legacy_web_consent_policy": _(
                "Как трактовать уже выданные веб-согласия после включения более строгого проверяемого режима."
            ),
            "allow_subject_self_upload": _(
                "Разрешить субъекту отправлять бумажный артефакт без участия оператора ПДн."
            ),
            "allow_draft_data_before_upload": _(
                "Разрешить двухэтапный сценарий: сначала сохранить данные, затем загрузить подписанное согласие."
            ),
            "pre_upload_access_mode": _(
                "Как трактовать доступ до момента загрузки бумажного согласия."
            ),
            "notification_mode": _(
                "Куда отправлять уведомления о событиях verified-сценария."
            ),
            "notification_templates": _(
                "JSON-шаблоны текстов уведомлений по ключам: data_saved, paper_uploaded, verified, rejected."
            ),
            "notify_on_data_saved": _(
                "Отправлять уведомление при сохранении данных без файла согласия."
            ),
            "notify_on_paper_uploaded": _(
                "Отправлять уведомление при загрузке бумажного согласия."
            ),
            "notify_on_verified": _(
                "Отправлять уведомление после подтверждения согласия оператором."
            ),
            "notify_on_rejected": _(
                "Отправлять уведомление после отклонения согласия оператором."
            ),
            "is_active": _(
                "Включает или отключает политику подтверждения в рабочем потоке."
            ),
            "starts_at": _("Начало действия политики (опционально)."),
            "ends_at": _("Окончание действия политики (опционально)."),
            "notes": _("Внутренние комментарии по политике верификации."),
            "extra_meta": _("Дополнительные технические метаданные в формате JSON."),
        }


class VerifiedConsentArtifactAdminForm(forms.ModelForm):
    class Meta:
        model = VerifiedConsentArtifact
        fields = "__all__"
        labels = {
            "consent_record": _("Запись согласия"),
            "policy": _("Политика"),
            "artifact_type": _("Тип артефакта"),
            "file": _("Файл артефакта"),
            "external_provider": _("Внешний провайдер"),
            "external_ref": _("Внешняя ссылка/идентификатор"),
            "subject_signed_at": _("Время подписи субъектом"),
            "note": _("Заметка"),
            "extra_meta": _("Метаданные"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        }
        help_texts = {
            "consent_record": _(
                "Связанная запись согласия, подтверждаемая артефактом."
            ),
            "policy": _("Политика подтверждения, по которой обрабатывается артефакт."),
            "artifact_type": _(
                "Тип подтверждающего артефакта (файл, провайдер, ручное подтверждение)."
            ),
            "file": _("Файл артефакта, если используется файловый сценарий."),
            "external_provider": _("Внешний провайдер/сервис, выдавший подтверждение."),
            "external_ref": _("Внешний идентификатор или ссылка на подтверждение."),
            "subject_signed_at": _(
                "Время, когда субъект подписал/подтвердил согласие."
            ),
            "note": _("Комментарий оператора по артефакту."),
            "extra_meta": _("Дополнительные метаданные артефакта в формате JSON."),
            "created_at": _("Техническое время создания записи."),
            "updated_at": _("Техническое время последнего обновления."),
        }


class VerifiedConsentFormPolicyAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        purpose_field = self.fields.get("purpose")
        if purpose_field is not None:
            purpose_field.label_from_instance = lambda obj: (
                f"{obj.title} ({obj.code})" if obj.title else obj.code
            )
        document_field = self.fields.get("document")
        if document_field is not None:
            document_field.label_from_instance = lambda obj: (
                f"{obj.title} ({obj.code})" if obj.title else obj.code
            )

    class Meta:
        model = VerifiedConsentFormPolicy
        fields = "__all__"
        labels = {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "form_code": _("Код формы"),
            "verification_mode_override": _("Режим верификации для формы"),
            "draft_data_policy_override": _("Политика сохранения данных до загрузки"),
            "pre_upload_access_mode_override": _(
                "Поведение до загрузки бумажного согласия"
            ),
            "notification_mode_override": _("Канал уведомлений"),
            "is_active": _("Активна"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
        }
        help_texts = {
            "purpose": _("Цель согласия, к которой относится эта форма."),
            "document": _("Документ потока, для которого настраивается форма."),
            "form_code": _(
                "Стабильный код формы сайта (например: demo.contact, demo.course_signup)."
            ),
            "verification_mode_override": _(
                "Переопределение для формы: только веб, бумажное, Госключ, бумажное/Госключ или наследование из политики потока."
            ),
            "draft_data_policy_override": _(
                "Переопределение для формы: разрешать/запрещать сохранение данных до загрузки согласия."
            ),
            "pre_upload_access_mode_override": _(
                "Переопределение реакции до загрузки бумажного согласия."
            ),
            "notification_mode_override": _(
                "Переопределение канала уведомлений для событий формы."
            ),
            "is_active": _(
                "Отключите запись, чтобы форма снова наследовала базовую политику."
            ),
            "notes": _("Внутренние комментарии по переопределению формы."),
            "extra_meta": _("Дополнительные технические метаданные в формате JSON."),
        }


class VerifiedConsentSubmissionAdminForm(forms.ModelForm):
    class Meta:
        model = VerifiedConsentSubmission
        fields = "__all__"
        labels = {
            "purpose": _("Цель"),
            "document": _("Документ"),
            "user": _("Пользователь"),
            "anonymous_token": _("Анонимный токен"),
            "subject_ref": _("Внешний идентификатор субъекта"),
            "form_code": _("Код формы"),
            "status": _("Статус заявки"),
            "subject_data": _("Данные субъекта"),
            "generated_blank_file": _("Сгенерированный бланк согласия"),
            "blank_generated_at": _("Когда сгенерирован бланк"),
            "consent_record": _("Запись согласия"),
            "latest_artifact": _("Последний артефакт"),
            "notes": _("Заметки"),
            "extra_meta": _("Доп. метаданные"),
            "completed_at": _("Время завершения"),
            "created_at": _("Создано"),
            "updated_at": _("Обновлено"),
        }
        help_texts = {
            "purpose": _(
                "Цель обработки, к которой относится заявка на подтверждённое согласие."
            ),
            "document": _("Документ и его редакция, на которые оформляется согласие."),
            "user": _(
                "Авторизованный пользователь-субъект, если заявка привязана к аккаунту."
            ),
            "anonymous_token": _(
                "Токен анонимного субъекта, если заявка оформлена без авторизации."
            ),
            "subject_ref": _(
                "Внешний идентификатор субъекта для связи с другими системами."
            ),
            "form_code": _("Код формы, из которой инициирована заявка."),
            "status": _("Текущий статус заявки в процессе подтверждённого согласия."),
            "subject_data": _(
                "Данные формы, сохранённые до загрузки бумажного согласия."
            ),
            "generated_blank_file": _("PDF-бланк согласия для печати и подписи."),
            "blank_generated_at": _("Когда был сгенерирован бланк согласия."),
            "consent_record": _(
                "Каноническая запись согласия, созданная после загрузки артефакта."
            ),
            "latest_artifact": _(
                "Последний загруженный бумажный артефакт по этой заявке."
            ),
            "notes": _("Служебные заметки оператора по заявке."),
            "extra_meta": _("Технические метаданные рабочего процесса и уведомлений."),
            "completed_at": _("Когда заявка переведена в завершённое состояние."),
            "created_at": _("Когда заявка была создана."),
            "updated_at": _("Когда заявка последний раз обновлялась."),
        }


class VerifiedConsentPolicyAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Админка политик усиленного/проверяемого подтверждения согласия."""

    form = VerifiedConsentPolicyAdminForm
    change_permission_flags = "can_handle_verified_consents"
    list_display = (
        "purpose",
        "document",
        "verification_mode",
        "flow_scope",
        "legacy_web_consent_policy",
        "allow_subject_self_upload",
        "allow_draft_data_before_upload",
        "pre_upload_access_mode",
        "notification_mode",
        "is_active",
        "starts_at",
        "ends_at",
    )
    list_display_links = ("purpose", "document")
    list_filter = (
        "verification_mode",
        "flow_scope",
        "legacy_web_consent_policy",
        "allow_subject_self_upload",
        "allow_draft_data_before_upload",
        "pre_upload_access_mode",
        "notification_mode",
        "is_active",
        "purpose",
        "document",
    )
    search_fields = ("purpose__code", "document__code", "notes")


class VerifiedConsentArtifactAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Админка артефактов, подтверждающих verified-consent flow."""

    form = VerifiedConsentArtifactAdminForm
    change_form_template = (
        "admin/django_consent_152fz/verifiedconsentartifactproxy/change_form.html"
    )
    action_form = VerifiedArtifactActionForm
    change_permission_flags = "can_handle_verified_consents"
    list_display = (
        "subject_user_display",
        "artifact_type",
        "file_download_link",
        "subject_signed_at",
        "created_at",
        "consent_record",
        "policy",
        "form_code_display",
    )
    list_display_links = ("consent_record", "policy", "artifact_type")
    list_filter = ("artifact_type", "policy__purpose", "policy__document")
    search_fields = (
        "consent_record__purpose__code",
        "policy__document__code",
        "consent_record__verified_submission__form_code",
        "consent_record__subject_ref",
        "consent_record__anonymous_token",
        "external_provider",
        "external_ref",
    )
    raw_id_fields = ("consent_record", "policy")
    readonly_fields = ("file_download_link",)
    actions = (
        "confirm_selected_as_employee",
        "confirm_selected_as_admin",
        "reject_selected_artifacts",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "consent_record__user",
                "consent_record__verified_submission__user",
                "consent_record__verified_submission",
                "policy__purpose",
                "policy__document",
            )
        )

    @admin.display(description=_("Код формы"))
    def form_code_display(self, obj) -> str:
        submission = getattr(obj.consent_record, "verified_submission", None)
        if submission and submission.form_code:
            return str(submission.form_code)
        source = str(getattr(obj.consent_record, "source", "") or "")
        return source or "-"

    @admin.display(description=_("Пользователь"))
    def subject_user_display(self, obj) -> str:
        submission = getattr(obj.consent_record, "verified_submission", None)
        if submission and submission.user:
            return str(submission.user)
        if obj.consent_record.user:
            return str(obj.consent_record.user)
        anonymous_token = str(getattr(obj.consent_record, "anonymous_token", "") or "")
        if anonymous_token:
            return f"anon:{anonymous_token}"
        subject_ref = str(getattr(obj.consent_record, "subject_ref", "") or "")
        return subject_ref or "-"

    @admin.display(description=_("Файл артефакта"))
    def file_download_link(self, obj) -> str:
        file_field = getattr(obj, "file", None)
        if not file_field:
            return "-"
        try:
            url = file_field.url
        except Exception:
            return "-"
        name = os.path.basename(str(file_field.name or "")) or str(_("Скачать файл"))
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>', url, name
        )

    @admin.action(description=_("Подтвердить выбранные как подтверждённые сотрудником"))
    def confirm_selected_as_employee(self, request, queryset) -> None:
        note = str(request.POST.get("confirmation_note", "") or "").strip()
        self._confirm_selected(
            request=request,
            queryset=queryset,
            confirmation_note=note,
            as_admin=False,
        )

    @admin.action(
        description=_("Подтвердить выбранные как подтверждённые администратором")
    )
    def confirm_selected_as_admin(self, request, queryset) -> None:
        if not request.user.is_superuser:
            self.message_user(
                request,
                _(
                    "Подтверждение как admin_confirmed доступно только суперпользователю."
                ),
                level=messages.ERROR,
            )
            return
        note = str(request.POST.get("confirmation_note", "") or "").strip()
        self._confirm_selected(
            request=request,
            queryset=queryset,
            confirmation_note=note,
            as_admin=True,
        )

    @admin.action(description=_("Отклонить выбранные (нужна причина)"))
    def reject_selected_artifacts(self, request, queryset) -> None:
        rejection_note = str(request.POST.get("rejection_note", "") or "").strip()
        if not rejection_note:
            self.message_user(
                request,
                _("Укажите причину отклонения для выбранных артефактов."),
                level=messages.ERROR,
            )
            return

        success_count = 0
        error_count = 0
        for artifact in queryset.select_related("consent_record"):
            try:
                reject_verified_consent(
                    consent_record=artifact.consent_record,
                    rejected_by=request.user,
                    actor_type=(
                        ConsentEvent.ActorType.ADMIN
                        if request.user.is_superuser
                        else ConsentEvent.ActorType.EMPLOYEE
                    ),
                    rejection_note=rejection_note,
                    audit_context={"source": "admin"},
                )
                success_count += 1
            except ConsentError:
                error_count += 1

        self._report_bulk_action_result(
            request=request,
            success_count=success_count,
            error_count=error_count,
            success_action="rejected",
        )

    def _confirm_selected(
        self,
        *,
        request,
        queryset,
        confirmation_note: str,
        as_admin: bool,
    ) -> None:
        success_count = 0
        error_count = 0
        confirmation_method = (
            ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED
            if as_admin
            else ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED
        )
        for artifact in queryset.select_related("consent_record"):
            try:
                confirm_verified_consent(
                    consent_record=artifact.consent_record,
                    confirmed_by=request.user,
                    confirmation_method=confirmation_method,
                    confirmation_note=confirmation_note,
                    audit_context={"source": "admin"},
                )
                success_count += 1
            except ConsentError:
                error_count += 1

        self._report_bulk_action_result(
            request=request,
            success_count=success_count,
            error_count=error_count,
            success_action="confirmed",
        )

    def _report_bulk_action_result(
        self,
        *,
        request,
        success_count: int,
        error_count: int,
        success_action: str,
    ) -> None:
        if success_count:
            if success_action == "confirmed":
                success_message = ngettext(
                    "Confirmed %(count)d verified artifact.",
                    "Confirmed %(count)d verified artifacts.",
                    success_count,
                )
            else:
                success_message = ngettext(
                    "Rejected %(count)d verified artifact.",
                    "Rejected %(count)d verified artifacts.",
                    success_count,
                )
            self.message_user(
                request,
                success_message % {"count": success_count},
                level=messages.SUCCESS,
            )
        if error_count:
            self.message_user(
                request,
                ngettext(
                    "Failed to process %(count)d artifact.",
                    "Failed to process %(count)d artifacts.",
                    error_count,
                )
                % {"count": error_count},
                level=messages.ERROR,
            )

    def response_change(self, request, obj):
        if "_confirm_current_as_employee" in request.POST:
            return self._confirm_current_from_change_form(
                request=request,
                obj=obj,
                as_admin=False,
            )
        if "_confirm_current_as_admin" in request.POST:
            return self._confirm_current_from_change_form(
                request=request,
                obj=obj,
                as_admin=True,
            )
        return super().response_change(request, obj)

    def _confirm_current_from_change_form(self, *, request, obj, as_admin: bool):
        if as_admin and not request.user.is_superuser:
            self.message_user(
                request,
                _(
                    "Подтверждение как admin_confirmed доступно только суперпользователю."
                ),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(".")
        confirmation_method = (
            ConsentRecord.ConfirmationMethod.ADMIN_CONFIRMED
            if as_admin
            else ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED
        )
        confirmation_note = str(request.POST.get("note", "") or "").strip()
        try:
            confirm_verified_consent(
                consent_record=obj.consent_record,
                confirmed_by=request.user,
                confirmation_method=confirmation_method,
                confirmation_note=confirmation_note,
                audit_context={"source": "admin"},
            )
        except ConsentError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
        else:
            self.message_user(
                request, _("Артефакт подтверждён."), level=messages.SUCCESS
            )
        return HttpResponseRedirect(".")


class VerifiedConsentFormPolicyAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Админка per-form override verified-flow."""

    form = VerifiedConsentFormPolicyAdminForm
    change_permission_flags = "can_handle_verified_consents"
    list_display = (
        "form_code",
        "purpose",
        "document",
        "verification_mode_override",
        "draft_data_policy_override",
        "pre_upload_access_mode_override",
        "notification_mode_override",
        "is_active",
    )
    list_display_links = ("form_code", "purpose", "document")
    list_filter = (
        "verification_mode_override",
        "draft_data_policy_override",
        "pre_upload_access_mode_override",
        "notification_mode_override",
        "is_active",
        "purpose",
        "document",
    )
    search_fields = ("form_code", "purpose__code", "document__code", "notes")


class VerifiedConsentSubmissionAdmin(AssignmentRestrictedAdminMixin, admin.ModelAdmin):
    """Read-only status board for two-step verified submissions."""

    form = VerifiedConsentSubmissionAdminForm
    change_permission_flags = "can_handle_verified_consents"
    list_display = (
        "id",
        "purpose",
        "document",
        "form_code",
        "status",
        "user",
        "anonymous_token",
        "consent_record",
        "blank_generated_at",
        "updated_at",
    )
    list_display_links = ("id", "purpose", "document")
    list_filter = ("status", "purpose", "document")
    search_fields = (
        "purpose__code",
        "document__code",
        "form_code",
        "anonymous_token",
        "subject_ref",
        "notes",
    )
    readonly_fields = (
        "purpose",
        "document",
        "user",
        "anonymous_token",
        "subject_ref",
        "form_code",
        "status",
        "subject_data",
        "generated_blank_file",
        "blank_generated_at",
        "consent_record",
        "latest_artifact",
        "notes",
        "extra_meta",
        "completed_at",
        "created_at",
        "updated_at",
    )


def register_admin(site: admin.sites.AdminSite) -> None:
    """Register verified-consents admin models via explicit app-level contract."""

    safe_register_admin_models(
        site,
        registrations=(
            (VerifiedConsentPolicy, VerifiedConsentPolicyAdmin),
            (VerifiedConsentArtifact, VerifiedConsentArtifactAdmin),
            (VerifiedConsentFormPolicy, VerifiedConsentFormPolicyAdmin),
            (VerifiedConsentSubmission, VerifiedConsentSubmissionAdmin),
        ),
    )


register_admin(admin.site)
