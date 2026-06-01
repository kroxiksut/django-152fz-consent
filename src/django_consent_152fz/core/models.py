"""Canonical domain models of the consent flow.

This file covers almost all of roadmap section 4:
- documents and revisions;
- processing purposes;
- audience scoping;
- the staff role responsible for personal data;
- access policies;
- consent records;
- the immutable event log.

This is where the core domain invariants are fixed; the service layer is
built on top of them.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from django_consent_152fz import constants


class LegalDocument(models.Model):
    """Top-level legal document.

    The document does not store the version text itself. It defines the
    document "stream": a stable `code`, the document type, and human-readable
    metadata. Concrete text revisions live in `DocumentRevision`.
    """

    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=64, default="consent")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Legal Document")
        verbose_name_plural = _("Legal Documents")
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class ConsentSelfServiceSettings(models.Model):
    """Global self-service UI settings for the subject of personal data."""

    class SubjectConsentsOpenMode(models.TextChoices):
        """How to open a document stream from a self-service agreement table."""

        PAGE = constants.SUBJECT_CONSENTS_OPEN_MODE_PAGE, _("Open on page")
        NEW_WINDOW = (
            constants.SUBJECT_CONSENTS_OPEN_MODE_NEW_WINDOW,
            _("Open in new window"),
        )
        MODAL = (
            constants.SUBJECT_CONSENTS_OPEN_MODE_MODAL,
            _("Open in modal dialog"),
        )

    class SubjectConsentsListMode(models.TextChoices):
        ALL = "all", _("Все")
        PENDING_ONLY = "pending_only", _("Только на подпись")
        SIGNED_ONLY = "signed_only", _("Только подписанные")

    class ConsentInputMode(models.TextChoices):
        CHECKBOX = (
            constants.SUBJECT_CONSENTS_INPUT_MODE_CHECKBOX,
            _("Checkbox confirmation"),
        )
        RADIO = (
            constants.SUBJECT_CONSENTS_INPUT_MODE_RADIO,
            _("Radio agree or decline"),
        )

    class ConsentDeclineAction(models.TextChoices):
        BLOCK_SUBMIT = (
            constants.SUBJECT_CONSENTS_DECLINE_ACTION_BLOCK_SUBMIT,
            _("Block submit"),
        )
        ALLOW_SUBMIT = (
            constants.SUBJECT_CONSENTS_DECLINE_ACTION_ALLOW_SUBMIT,
            _("Allow submit"),
        )

    class CsvDelimiter(models.TextChoices):
        COMMA = ",", _("Запятая (,)")
        SEMICOLON = ";", _("Точка с запятой (;)")
        TAB = "\t", _("Табуляция (TAB)")
        PIPE = "|", _("Вертикальная черта (|)")

    class PdfPaperSize(models.TextChoices):
        A4 = "a4", _("A4 (210×297 мм)")
        A5 = "a5", _("A5 (148×210 мм)")
        LETTER = "letter", _("Letter (8,5×11 дюйма)")

    class PdfFontFamily(models.TextChoices):
        TIMES_NEW_ROMAN = "times_new_roman", _("Times New Roman")
        ARIAL = "arial", _("Arial")

    class PdfTextAlign(models.TextChoices):
        LEFT = "left", _("По левому краю")
        CENTER = "center", _("По центру")
        RIGHT = "right", _("По правому краю")
        JUSTIFY = "justify", _("По ширине")

    class PdfSignatureAlign(models.TextChoices):
        LEFT = "left", _("Слева")
        CENTER = "center", _("По центру")
        RIGHT = "right", _("Справа")

    subject_consents_open_mode = models.CharField(
        max_length=32,
        choices=SubjectConsentsOpenMode.choices,
        default=SubjectConsentsOpenMode.PAGE,
        verbose_name=_("Режим открытия документа"),
    )
    subject_consents_list_mode = models.CharField(
        max_length=32,
        choices=SubjectConsentsListMode.choices,
        default=SubjectConsentsListMode.ALL,
        verbose_name=_("Режим списка согласий"),
    )
    consent_input_mode = models.CharField(
        max_length=32,
        choices=ConsentInputMode.choices,
        default=ConsentInputMode.CHECKBOX,
        verbose_name=_("Режим подтверждения согласия"),
    )
    checkbox_required = models.BooleanField(
        default=True,
        verbose_name=_("Обязательный флажок"),
    )
    decline_action = models.CharField(
        max_length=32,
        choices=ConsentDeclineAction.choices,
        default=ConsentDeclineAction.BLOCK_SUBMIT,
        verbose_name=_("Поведение при отказе"),
    )
    decline_warning_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Показывать предупреждение при отказе"),
    )
    decline_warning_text = models.CharField(
        max_length=255,
        default=(
            "Если вы не согласны на обработку персональных данных, "
            "мы не сможем связаться с вами по заявке."
        ),
        verbose_name=_("Текст предупреждения при отказе"),
    )
    csv_export_delimiter = models.CharField(
        max_length=8,
        choices=CsvDelimiter.choices,
        default=CsvDelimiter.COMMA,
        verbose_name=_("Разделитель CSV-экспорта"),
    )
    printable_pdf_paper_size = models.CharField(
        max_length=16,
        choices=PdfPaperSize.choices,
        default=PdfPaperSize.A4,
        verbose_name=_("Формат бумаги для печатного PDF"),
    )
    printable_pdf_font_family = models.CharField(
        max_length=32,
        choices=PdfFontFamily.choices,
        default=PdfFontFamily.TIMES_NEW_ROMAN,
        verbose_name=_("Шрифт печатного PDF"),
    )
    printable_pdf_font_size = models.PositiveSmallIntegerField(
        default=12,
        verbose_name=_("Размер шрифта печатного PDF"),
    )
    printable_pdf_text_align = models.CharField(
        max_length=16,
        choices=PdfTextAlign.choices,
        default=PdfTextAlign.LEFT,
        verbose_name=_("Выравнивание текста печатного PDF"),
    )
    printable_pdf_show_signature_footer = models.BooleanField(
        default=True,
        verbose_name=_("Добавлять блок подписи внизу PDF"),
    )
    printable_pdf_signature_align = models.CharField(
        max_length=16,
        choices=PdfSignatureAlign.choices,
        default=PdfSignatureAlign.CENTER,
        verbose_name=_("Выравнивание подписи (ПОДПИСЬ/ФИО)"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Consent Self-service Settings")
        verbose_name_plural = _("Consent Self-service Settings")
        ordering = ["id"]

    def __str__(self) -> str:
        return (
            f"{_('Настройки самообслуживания согласий')} "
            f"({self.get_subject_consents_open_mode_display()})"  # pyright: ignore[reportAttributeAccessIssue]
        )


class DocumentRevision(models.Model):
    """Concrete revision of a document for the `document + purpose` stream.

    Why `purpose_code` is stored directly on the revision: the same physical
    document container can be used in different scenarios, and the consent-flow
    logic relies specifically on the `purpose + document_code` pairing.
    """

    class ContentFormat(models.TextChoices):
        """Supported formats for presenting legal text."""

        PLAIN_TEXT = "plain_text", _("Plain text")
        MARKDOWN = "markdown", _("Markdown")
        HTML = "html", _("HTML")
        PDF_FILE = "pdf_file", _("PDF file")
        OFFICE_FILE = "office_file", _("Office file (DOC/DOCX/ODT/ODTX)")

    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    purpose_code = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    format = models.CharField(
        max_length=32,
        choices=ContentFormat.choices,
        default=ContentFormat.PLAIN_TEXT,
    )
    content_text = models.TextField(blank=True)
    content_file = models.FileField(
        upload_to="django_consent_152fz/documents/",
        blank=True,
    )
    fields_snapshot = models.JSONField(default=list)
    meta = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    is_box_template = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Document Revision")
        verbose_name_plural = _("Document Revisions")
        ordering = ["document_id", "purpose_code", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=("document", "purpose_code", "version"),
                name="uq_doc_revision_document_purpose_version",
            )
        ]

    def clean(self) -> None:
        """Check the consistency of the C format with the actual content."""
        super().clean()

        text_formats = {
            self.ContentFormat.PLAIN_TEXT,
            self.ContentFormat.MARKDOWN,
            self.ContentFormat.HTML,
        }
        text_value = (self.content_text or "").strip()
        has_file = bool(self.content_file)

        errors: dict[str, str] = {}
        if self.format in text_formats:
            if not text_value:
                errors["content_text"] = "content_text is required for text formats."
            if has_file:
                errors["content_file"] = "content_file must be empty for text formats."

        file_formats = {
            self.ContentFormat.PDF_FILE,
            self.ContentFormat.OFFICE_FILE,
        }
        if self.format in file_formats:
            if not has_file:
                errors["content_file"] = (
                    "content_file is required for selected file format."
                )
            if text_value:
                errors["content_text"] = "content_text must be empty for file formats."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Always validate the revision before writing it to the DB."""
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.document.code}:{self.purpose_code}:v{self.version}"


class ConsentPurpose(models.Model):
    """Processing purpose for personal data.

    This is one of the central domain entities. It defines:
    - what the data is collected for;
    - which fields are usually expected;
    - how to behave on withdrawal;
    - whether a soft or hard reconsent mode is required.
    """

    class WithdrawStrategy(models.TextChoices):
        """System response strategies for consent withdrawal."""

        BLOCK = constants.WITHDRAW_STRATEGY_BLOCK, _("Block")
        DELETE = constants.WITHDRAW_STRATEGY_DELETE, _("Delete")

    class ReconsentMode(models.TextChoices):
        """Reaction modes for an outdated consent."""

        SOFT = constants.RECONSENT_MODE_SOFT, _("Мягкое повторное согласие")
        HARD = constants.RECONSENT_MODE_HARD, _("Жёсткое повторное согласие")

    class ConsentFrequencyPolicy(models.TextChoices):
        """Frequency of signing within the purpose + document flow."""

        ONCE_UNTIL_OUTDATED = (
            constants.CONSENT_FREQUENCY_ONCE_UNTIL_OUTDATED,
            _("Один раз до новой редакции"),
        )
        EVERY_TIME = (
            constants.CONSENT_FREQUENCY_EVERY_TIME,
            _("Подписывать при каждом действии"),
        )

    class SubjectAvailabilityPolicy(models.TextChoices):
        """Target availability for auth/anon subjects."""

        AUTHENTICATED_ONLY = (
            constants.SUBJECT_AVAILABILITY_AUTHENTICATED_ONLY,
            _("Только авторизованные пользователи"),
        )
        AUTHENTICATED_AND_ANONYMOUS = (
            constants.SUBJECT_AVAILABILITY_AUTHENTICATED_AND_ANONYMOUS,
            _("Авторизованные и анонимные пользователи"),
        )

    class ConsentInputModeOverride(models.TextChoices):
        INHERIT = "inherit", _("Наследовать глобальную настройку")
        CHECKBOX = (
            constants.SUBJECT_CONSENTS_INPUT_MODE_CHECKBOX,
            _("Подтверждение флажком"),
        )
        RADIO = (
            constants.SUBJECT_CONSENTS_INPUT_MODE_RADIO,
            _("Выбор «согласен/не согласен»"),
        )

    class ConsentDeclineActionOverride(models.TextChoices):
        INHERIT = "inherit", _("Наследовать глобальную настройку")
        BLOCK_SUBMIT = (
            constants.SUBJECT_CONSENTS_DECLINE_ACTION_BLOCK_SUBMIT,
            _("Блокировать отправку"),
        )
        ALLOW_SUBMIT = (
            constants.SUBJECT_CONSENTS_DECLINE_ACTION_ALLOW_SUBMIT,
            _("Разрешать отправку"),
        )

    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    fields_config = models.JSONField(default=list)
    withdraw_strategy = models.CharField(
        max_length=32,
        choices=WithdrawStrategy.choices,
        default=WithdrawStrategy.BLOCK,
    )
    reconsent_mode = models.CharField(
        max_length=32,
        choices=ReconsentMode.choices,
        default=ReconsentMode.SOFT,
    )
    consent_frequency_policy = models.CharField(
        max_length=32,
        choices=ConsentFrequencyPolicy.choices,
        default=ConsentFrequencyPolicy.ONCE_UNTIL_OUTDATED,
    )
    subject_availability_policy = models.CharField(
        max_length=48,
        choices=SubjectAvailabilityPolicy.choices,
        default=SubjectAvailabilityPolicy.AUTHENTICATED_AND_ANONYMOUS,
    )
    consent_input_mode_override = models.CharField(
        max_length=32,
        choices=ConsentInputModeOverride.choices,
        default=ConsentInputModeOverride.INHERIT,
    )
    checkbox_required_override = models.BooleanField(null=True, blank=True)
    decline_action_override = models.CharField(
        max_length=32,
        choices=ConsentDeclineActionOverride.choices,
        default=ConsentDeclineActionOverride.INHERIT,
    )
    decline_warning_enabled_override = models.BooleanField(null=True, blank=True)
    decline_warning_text_override = models.CharField(max_length=255, blank=True)
    is_experimental = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Consent Purpose")
        verbose_name_plural = _("Consent Purposes")
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class ConsentAudienceRule(models.Model):
    """Rule that applies the consent-flow to a specific audience.

    This model is responsible not for the fact of consent, but for the question
    of "for whom is this consent stream required at all". That is why it is kept
    separate instead of being built into `ConsentPurpose` or `DocumentRevision`.
    """

    class ScopeMode(models.TextChoices):
        """Supported ways to describe an audience."""

        ALL_REGISTERED_USERS = (
            constants.AUDIENCE_SCOPE_ALL_REGISTERED_USERS,
            _("All registered users"),
        )
        DJANGO_GROUP = constants.AUDIENCE_SCOPE_DJANGO_GROUP, _("Django group")
        ANONYMOUS_SUBJECTS = (
            constants.AUDIENCE_SCOPE_ANONYMOUS_SUBJECTS,
            _("Anonymous subjects"),
        )

    purpose = models.ForeignKey(
        ConsentPurpose,
        on_delete=models.CASCADE,
        related_name="audience_rules",
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.CASCADE,
        related_name="audience_rules",
    )
    scope_mode = models.CharField(
        max_length=32,
        choices=ScopeMode.choices,
    )
    group = models.ForeignKey(
        "auth.Group",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="consent_audience_rules",
    )
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_consent_audience_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Consent Audience Rule")
        verbose_name_plural = _("Consent Audience Rules")
        ordering = ["purpose__code", "document__code", "scope_mode", "id"]

    def clean(self) -> None:
        """Check that the audience definition does not contradict itself."""
        super().clean()

        if self.scope_mode == self.ScopeMode.DJANGO_GROUP:
            if not self.group_id:  # pyright: ignore[reportAttributeAccessIssue]
                raise ValidationError(
                    {"group": "group is required for django_group scope_mode."}
                )
        elif self.group_id:  # pyright: ignore[reportAttributeAccessIssue]
            raise ValidationError(
                {"group": "group must be empty unless scope_mode is django_group."}
            )

        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValidationError(
                {"ends_at": "ends_at must be greater than or equal to starts_at."}
            )

    def save(self, *args, **kwargs):
        """Write the rule only after validation."""
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.purpose.code}:{self.document.code}:{self.scope_mode}:{self.pk}"


class PersonalDataManagerAssignment(models.Model):
    """Assignment of the "Personal Data Manager" role to a specific staff user.

    This is not a full ACL system, but a compact permission set for a staff
    user who must be able to manage the package's domain entities.
    """

    class ScopeMode(models.TextChoices):
        """The scope of management is given to the employee."""

        GLOBAL = constants.PDM_SCOPE_GLOBAL, _("Глобально")
        DJANGO_GROUPS = constants.PDM_SCOPE_DJANGO_GROUPS, _("По Django-группам")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_data_manager_assignment",
    )
    scope_mode = models.CharField(
        max_length=32,
        choices=ScopeMode.choices,
        default=ScopeMode.GLOBAL,
    )
    groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="personal_data_manager_assignments",
    )
    can_manage_purposes = models.BooleanField(default=False)
    can_manage_documents = models.BooleanField(default=False)
    can_publish_revisions = models.BooleanField(default=False)
    can_manage_audience_rules = models.BooleanField(default=False)
    can_manage_access_policies = models.BooleanField(default=False)
    can_handle_verified_consents = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Personal Data Manager Assignment")
        verbose_name_plural = _("Personal Data Manager Assignments")
        ordering = ["user_id"]

    def clean(self) -> None:
        """Limit role assignments to staff users only."""
        super().clean()

        if self.user_id and not self.user.is_staff:  # pyright: ignore[reportAttributeAccessIssue]
            raise ValidationError(
                {"user": _("Назначение доступно только пользователю-сотруднику.")}
            )

    def save(self, *args, **kwargs):
        """Do not allow saving an invalid staff assignment."""
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        user_label = getattr(self.user, "get_username", lambda: str(self.user_id))()  # pyright: ignore[reportAttributeAccessIssue]
        return f"{user_label} ({self.get_scope_mode_display()})"  # pyright: ignore[reportAttributeAccessIssue]


class ConsentAccessPolicy(models.Model):
    """Resource access rule enforced via the consent-aware guard layer.

    This model does not duplicate Django's permission system and does not
    replace RBAC. Its job is narrower: to bind a specific `resource_code/action`
    to the required consent stream and describe the reaction when consent is
    missing or outdated.
    """

    class MissingConsentAction(models.TextChoices):
        """What to do if there is no agreement at all."""

        DENY = constants.ACCESS_POLICY_ACTION_DENY, _("Deny")
        READ_ONLY = constants.ACCESS_POLICY_ACTION_READ_ONLY, _("Read only")
        REDIRECT_TO_CONSENT = (
            constants.ACCESS_POLICY_ACTION_REDIRECT_TO_CONSENT,
            _("Redirect to consent"),
        )

    class OutdatedConsentAction(models.TextChoices):
        """What to do when consent exists but is outdated."""

        RESPECT_RECONSENT_MODE = (
            constants.ACCESS_POLICY_ACTION_RESPECT_RECONSENT_MODE,
            _("Учитывать режим повторного согласия"),
        )
        DENY = constants.ACCESS_POLICY_ACTION_DENY, _("Deny")
        READ_ONLY = constants.ACCESS_POLICY_ACTION_READ_ONLY, _("Read only")
        REDIRECT_TO_CONSENT = (
            constants.ACCESS_POLICY_ACTION_REDIRECT_TO_CONSENT,
            _("Redirect to consent"),
        )

    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    purpose = models.ForeignKey(
        ConsentPurpose,
        on_delete=models.CASCADE,
        related_name="access_policies",
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.CASCADE,
        related_name="access_policies",
    )
    resource_code = models.CharField(max_length=128)
    app_label = models.CharField(max_length=64, blank=True)
    model_name = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=64)
    on_missing_consent = models.CharField(
        max_length=32,
        choices=MissingConsentAction.choices,
        default=MissingConsentAction.DENY,
    )
    on_outdated_consent = models.CharField(
        max_length=32,
        choices=OutdatedConsentAction.choices,
        default=OutdatedConsentAction.RESPECT_RECONSENT_MODE,
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Consent Access Policy")
        verbose_name_plural = _("Consent Access Policies")
        ordering = ["resource_code", "action", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=("resource_code", "action"),
                name="uq_access_policy_resource_action",
            )
        ]

    def clean(self) -> None:
        """Check the integrity of the model reference fields temporarily in the window."""
        super().clean()

        errors: dict[str, str] = {}
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            errors["ends_at"] = "ends_at must be greater than or equal to starts_at."

        app_label_present = bool(self.app_label.strip())
        model_name_present = bool(self.model_name.strip())
        if app_label_present != model_name_present:
            if not app_label_present:
                errors["app_label"] = (
                    "app_label is required when model_name is provided."
                )
            if not model_name_present:
                errors["model_name"] = (
                    "model_name is required when app_label is provided."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Write an access policy only after validation."""
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.resource_code}:{self.action}:{self.code}"


class ConsentRecord(models.Model):
    """Canonical record of the fact of consent.

    This is the main source of truth for the consent state of a specific
    subject for a specific `purpose + document_revision` stream.

    Important:
    - the record stores a snapshot of the fields and a technical audit context;
    - the transition history is not overwritten here; it goes into `ConsentEvent`;
    - method-specific verified artifacts do not live in `core`; they reside in
      the optional `verified_consents` app.
    """

    class Status(models.TextChoices):
        """Canonical statuses of a consent record."""

        CURRENT = constants.CONSENT_STATUS_CURRENT, _("Current")
        OUTDATED = constants.CONSENT_STATUS_OUTDATED, _("Outdated")
        WITHDRAWN = constants.CONSENT_STATUS_WITHDRAWN, _("Withdrawn")
        PENDING_CONFIRMATION = (
            constants.CONSENT_STATUS_PENDING_CONFIRMATION,
            _("Pending confirmation"),
        )
        REJECTED = constants.CONSENT_STATUS_REJECTED, _("Rejected")
        DELETED = constants.CONSENT_STATUS_DELETED, _("Deleted")

    class ConfirmationMethod(models.TextChoices):
        """How the system received or confirmed the consent."""

        WEB_CHECKBOX = constants.CONFIRMATION_METHOD_WEB_CHECKBOX, _("Web checkbox")
        WEB_BUTTON = constants.CONFIRMATION_METHOD_WEB_BUTTON, _("Web button")
        API_ACCEPT = constants.CONFIRMATION_METHOD_API_ACCEPT, _("API accept")
        UPLOADED_PAPER = (
            constants.CONFIRMATION_METHOD_UPLOADED_PAPER,
            _("Uploaded paper"),
        )
        ADMIN_CONFIRMED = (
            constants.CONFIRMATION_METHOD_ADMIN_CONFIRMED,
            _("Admin confirmed"),
        )
        EMPLOYEE_CONFIRMED = (
            constants.CONFIRMATION_METHOD_EMPLOYEE_CONFIRMED,
            _("Employee confirmed"),
        )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_records",
    )
    subject_ref = models.CharField(max_length=128, blank=True)
    anonymous_token = models.CharField(max_length=128, blank=True)
    purpose = models.ForeignKey(
        ConsentPurpose,
        on_delete=models.PROTECT,
        related_name="consent_records",
    )
    document_revision = models.ForeignKey(
        DocumentRevision,
        on_delete=models.PROTECT,
        related_name="consent_records",
    )
    fields_snapshot = models.JSONField(default=list)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.CURRENT,
    )
    confirmation_method = models.CharField(
        max_length=32,
        choices=ConfirmationMethod.choices,
        default=ConfirmationMethod.WEB_CHECKBOX,
    )
    source = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    locale = models.CharField(max_length=32, blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_consent_records",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmation_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Consent Record")
        verbose_name_plural = _("Consent Records")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | ~models.Q(anonymous_token=""),
                name="ck_consent_record_subject_present",
            ),
            models.UniqueConstraint(
                fields=("user", "purpose", "document_revision"),
                condition=models.Q(
                    status=constants.CONSENT_STATUS_CURRENT, user__isnull=False
                ),
                name="uq_consent_record_current_auth_subject_stream",
            ),
            models.UniqueConstraint(
                fields=("anonymous_token", "purpose", "document_revision"),
                condition=models.Q(
                    status=constants.CONSENT_STATUS_CURRENT,
                    user__isnull=True,
                )
                & ~models.Q(anonymous_token=""),
                name="uq_consent_record_current_anon_subject_stream",
            ),
        ]

    def clean(self) -> None:
        """Check the basic domain invariants of the consent record."""
        super().clean()

        anonymous_token = self.anonymous_token.strip()
        if not self.user_id and not anonymous_token:  # pyright: ignore[reportAttributeAccessIssue]
            raise ValidationError("Either user or anonymous_token must be provided.")

        if (
            self.confirmation_method
            in {
                self.ConfirmationMethod.ADMIN_CONFIRMED,
                self.ConfirmationMethod.EMPLOYEE_CONFIRMED,
            }
            and not self.confirmed_by_id
        ):  # pyright: ignore[reportAttributeAccessIssue]
            raise ValidationError(
                {"confirmed_by": "confirmed_by is required for admin/employee flow."}
            )

        if (
            self.purpose_id  # pyright: ignore[reportAttributeAccessIssue]
            and self.document_revision_id  # pyright: ignore[reportAttributeAccessIssue]
            and self.purpose.code != self.document_revision.purpose_code
        ):
            raise ValidationError(
                {
                    "document_revision": (
                        "document_revision purpose_code must match purpose.code."
                    )
                }
            )

    def save(self, *args, **kwargs):
        """Normalize the subject token and validate the record before saving."""
        if self.anonymous_token:
            self.anonymous_token = self.anonymous_token.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.purpose.code}:{self.status}:{self.pk}"


class ImmutableEventQuerySet(models.QuerySet):
    """QuerySet that forbids bulk modification of audit events.

    This is needed because a restriction only at the `ConsentEvent.save()` level
    does not cover `QuerySet.update()` and `QuerySet.delete()`.
    """

    def update(self, **kwargs):
        raise ValidationError("ConsentEvent is immutable and cannot be updated.")

    def delete(self):
        raise ValidationError("ConsentEvent is immutable and cannot be deleted.")


class ConsentEvent(models.Model):
    """Immutable event in the consent-flow log.

    If `ConsentRecord` answers the question "what is the current state", then
    `ConsentEvent` answers "by what path the system arrived at it". That is why
    events must not be updated or deleted after the fact.
    """

    class ActorType(models.TextChoices):
        """Who initiated the event: subject, collaborator, manager or system."""

        SUBJECT = constants.CONSENT_ACTOR_SUBJECT, _("Subject")
        EMPLOYEE = constants.CONSENT_ACTOR_EMPLOYEE, _("Employee")
        ADMIN = constants.CONSENT_ACTOR_ADMIN, _("Admin")
        SYSTEM = constants.CONSENT_ACTOR_SYSTEM, _("System")

    class EventType(models.TextChoices):
        """Canonical types of audit events."""

        GIVEN = constants.CONSENT_EVENT_GIVEN, _("Given")
        WITHDRAWN = constants.CONSENT_EVENT_WITHDRAWN, _("Withdrawn")
        OUTDATED = constants.CONSENT_EVENT_OUTDATED, _("Outdated")
        RECONFIRMED = constants.CONSENT_EVENT_RECONFIRMED, _("Reconfirmed")
        ADMIN_CONFIRMED = constants.CONSENT_EVENT_ADMIN_CONFIRMED, _("Admin confirmed")
        EMPLOYEE_CONFIRMED = (
            constants.CONSENT_EVENT_EMPLOYEE_CONFIRMED,
            _("Employee confirmed"),
        )
        PAPER_UPLOADED = constants.CONSENT_EVENT_PAPER_UPLOADED, _("Paper uploaded")
        REJECTED = constants.CONSENT_EVENT_REJECTED, _("Rejected")
        BLOCKED = constants.CONSENT_EVENT_BLOCKED, _("Blocked")
        DELETE_REQUESTED = (
            constants.CONSENT_EVENT_DELETE_REQUESTED,
            _("Delete requested"),
        )
        ANONYMIZED = constants.CONSENT_EVENT_ANONYMIZED, _("Anonymized")

    objects = ImmutableEventQuerySet.as_manager()

    consent_record = models.ForeignKey(
        ConsentRecord,
        on_delete=models.PROTECT,
        related_name="events",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_events_actor",
    )
    actor_type = models.CharField(
        max_length=32,
        choices=ActorType.choices,
        default=ActorType.SYSTEM,
    )
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
        app_label = constants.APP_LABEL
        verbose_name = _("Consent Event")
        verbose_name_plural = _("Consent Events")
        ordering = ["occurred_at", "id"]

    def clean(self) -> None:
        """Check the consistency of the actor fields."""
        super().clean()

        if self.actor_type == self.ActorType.SYSTEM and self.actor_user_id:  # pyright: ignore[reportAttributeAccessIssue]
            raise ValidationError(
                {"actor_user": "actor_user must be empty for system events."}
            )

        if self.actor_type in {self.ActorType.ADMIN, self.ActorType.EMPLOYEE}:
            if not self.actor_user_id:  # pyright: ignore[reportAttributeAccessIssue]
                raise ValidationError(
                    {
                        "actor_user": (
                            "actor_user is required for admin/employee events."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        """Allow only new events; existing ones must not be updated."""
        if not self._state.adding:
            raise ValidationError("ConsentEvent is immutable and cannot be updated.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deleting events at the instance level."""
        raise ValidationError("ConsentEvent is immutable and cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.consent_record_id}:{self.event_type}"  # pyright: ignore[reportAttributeAccessIssue]


class ModuleOperationAuditLog(models.Model):
    """Audit log for administrative and service-level module operations."""

    class Status(models.TextChoices):
        SUCCESS = "success", _("Success")
        DRY_RUN = "dry_run", _("Dry run")
        ERROR = "error", _("Error")

    operation_code = models.CharField(max_length=128)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="module_operation_audit_logs",
    )
    source = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUCCESS,
    )
    target_model = models.CharField(max_length=128, blank=True)
    target_id = models.CharField(max_length=128, blank=True)
    summary = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = constants.APP_LABEL
        verbose_name = _("Журнал операций модуля")
        verbose_name_plural = _("Журналы операций модуля")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["operation_code", "created_at"]),
            models.Index(fields=["source", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.operation_code}:{self.status}:{self.pk}"


class RevokedAnonymousToken(models.Model):
    """Durable registry of revoked anonymous tokens."""

    token_hash = models.CharField(max_length=64, unique=True)
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = constants.APP_LABEL
        ordering = ["-revoked_at", "-id"]

    def __str__(self) -> str:
        return f"{self.token_hash}:{self.pk}"


class ConsentModuleOperationAuditLog(ModuleOperationAuditLog):
    """Proxy log of operations of the main module of consents 152-FZ."""

    class Meta:
        proxy = True
        app_label = constants.APP_LABEL
        verbose_name = _("Журнал операций согласий 152-ФЗ")
        verbose_name_plural = _("Журналы операций согласий 152-ФЗ")
