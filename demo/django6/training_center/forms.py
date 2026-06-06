from typing import cast

from django import forms
from django.utils.translation import get_language

from django_consent_152fz.forms import ConsentCaptureModeMixin

from .models import CertificateRequest, ContactMessage, Course, CourseSignup


def _t(ru: str, en: str) -> str:
    """Pick RU or EN text for the active language (demo uses inline i18n, no .po)."""
    return en if (get_language() or "").startswith("en") else ru


def _localize_fields(form, *, labels=None, help_texts=None, empty_labels=None) -> None:
    """Apply per-language labels/help_texts at instance time (language is active then)."""
    for name, (ru, en) in (labels or {}).items():
        if name in form.fields:
            form.fields[name].label = _t(ru, en)
    for name, (ru, en) in (help_texts or {}).items():
        if name in form.fields:
            form.fields[name].help_text = _t(ru, en)
    for name, (ru, en) in (empty_labels or {}).items():
        if name in form.fields:
            form.fields[name].empty_label = _t(ru, en)


class ContactForm(ConsentCaptureModeMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("full_name", "email", "message")
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _localize_fields(
            self,
            labels={
                "full_name": ("ФИО", "Full name"),
                "email": ("Электронная почта", "Email"),
                "message": ("Сообщение", "Message"),
            },
            help_texts={
                "full_name": (
                    "Укажите, как к вам обращаться.",
                    "Tell us how to address you.",
                ),
                "email": (
                    "На этот адрес придёт ответ.",
                    "We will send the reply to this address.",
                ),
                "message": (
                    "Опишите вопрос по курсам или расписанию.",
                    "Describe your question about courses or the schedule.",
                ),
            },
        )


class CourseSignupStepOneForm(forms.Form):
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),
        label="Курс",
        empty_label="Выберите курс",
    )
    full_name = forms.CharField(max_length=255, label="ФИО")
    email = forms.EmailField(label="Электронная почта")
    phone = forms.CharField(max_length=32, label="Телефон")
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        course_field = cast(forms.ModelChoiceField, self.fields["course"])
        course_field.queryset = Course.objects.filter(is_active=True).order_by(
            "starts_at",
            "title",
        )
        _localize_fields(
            self,
            labels={
                "course": ("Курс", "Course"),
                "full_name": ("ФИО", "Full name"),
                "email": ("Электронная почта", "Email"),
                "phone": ("Телефон", "Phone"),
                "comment": ("Комментарий", "Comment"),
            },
            empty_labels={
                "course": ("Выберите курс", "Select a course"),
            },
        )


class CourseSignupConfirmForm(ConsentCaptureModeMixin, forms.Form):
    """Second wizard step: consent confirmation and submission."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if (
            "consent_decision" in self.fields
            and not self.fields["consent_decision"].initial
        ):
            self.fields["consent_decision"].initial = "agree"


class VerifiedPaperConsentUploadForm(forms.Form):
    full_name = forms.CharField(max_length=255, label="ФИО")
    email = forms.EmailField(label="Электронная почта")
    paper_file = forms.FileField(
        label="Файл бумажного подтверждения",
        help_text="Допустимые форматы: PDF, PNG, JPG, JPEG, TIF, TIFF.",
        widget=forms.ClearableFileInput(
            attrs={"accept": ".pdf,.png,.jpg,.jpeg,.tif,.tiff"}
        ),
    )
    note = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _localize_fields(
            self,
            labels={
                "full_name": ("ФИО", "Full name"),
                "email": ("Электронная почта", "Email"),
                "paper_file": ("Файл бумажного подтверждения", "Paper consent file"),
                "note": ("Комментарий", "Comment"),
            },
            help_texts={
                "paper_file": (
                    "Допустимые форматы: PDF, PNG, JPG, JPEG, TIF, TIFF.",
                    "Allowed formats: PDF, PNG, JPG, JPEG, TIF, TIFF.",
                ),
            },
        )


class CertificateRequestForm(ConsentCaptureModeMixin, forms.ModelForm):
    course_name = forms.ChoiceField(label="Курс")

    class Meta:
        model = CertificateRequest
        fields = ("full_name", "birth_date", "email", "course_name", "comment")
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = self._build_course_choices(user=user)
        self.fields["course_name"] = forms.ChoiceField(
            label=_t("Курс", "Course"),
            choices=choices,
            required=True,
            help_text=_t(
                "Выберите курс из тех заявок, которые вы уже отправляли на сайте.",
                "Select a course from the signups you have already submitted on the site.",
            ),
        )
        _localize_fields(
            self,
            labels={
                "full_name": ("ФИО", "Full name"),
                "birth_date": ("Дата рождения", "Date of birth"),
                "email": ("Электронная почта", "Email"),
                "comment": ("Комментарий", "Comment"),
            },
            help_texts={
                "full_name": (
                    "Укажите ФИО для сертификата.",
                    "Provide the full name for the certificate.",
                ),
                "birth_date": (
                    "Используется для корректной идентификации.",
                    "Used for correct identification.",
                ),
                "email": (
                    "На этот адрес будет отправлена информация о сертификате.",
                    "Certificate information will be sent to this address.",
                ),
                "comment": (
                    "Необязательно: формат выдачи, уточнения по данным и т. д.",
                    "Optional: delivery format, data clarifications, etc.",
                ),
            },
        )

    @staticmethod
    def _build_course_choices(*, user) -> list[tuple[str, str]]:
        if user is None or not getattr(user, "is_authenticated", False):
            return []

        choices: list[tuple[str, str]] = []
        seen: set[str] = set()
        signups_qs = (
            CourseSignup.objects.filter(user=user)
            .select_related("course")
            .order_by("-created_at", "-id")
        )
        for signup in signups_qs:
            course_title = str(getattr(signup.course, "title", "") or "").strip()
            if not course_title or course_title in seen:
                continue
            seen.add(course_title)
            choices.append((course_title, course_title))
        return choices
