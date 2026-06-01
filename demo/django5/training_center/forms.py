from typing import cast

from django import forms

from django_consent_152fz.forms import ConsentCaptureModeMixin

from .models import CertificateRequest, ContactMessage, Course, CourseSignup


class ContactForm(ConsentCaptureModeMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("full_name", "email", "message")
        labels = {
            "full_name": "ФИО",
            "email": "Email",
            "message": "Сообщение",
        }
        help_texts = {
            "full_name": "Укажите, как к вам обращаться.",
            "email": "Мы отправим ответ на этот адрес.",
            "message": "Опишите вопрос по обучению или расписанию.",
        }
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
        }


class CourseSignupStepOneForm(forms.Form):
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),
        label="Курс",
        empty_label="Выберите курс",
    )
    full_name = forms.CharField(max_length=255, label="ФИО")
    email = forms.EmailField(label="Email")
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


class CourseSignupConfirmForm(ConsentCaptureModeMixin, forms.Form):
    """Второй шаг wizard: подтверждение и отправка."""

    pass


class VerifiedPaperConsentUploadForm(forms.Form):
    full_name = forms.CharField(max_length=255, label="ФИО")
    email = forms.EmailField(label="Email")
    paper_file = forms.FileField(
        label="Файл бумажного согласия",
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


class CertificateRequestForm(ConsentCaptureModeMixin, forms.ModelForm):
    course_name = forms.ChoiceField(label="Курс")

    class Meta:
        model = CertificateRequest
        fields = ("full_name", "birth_date", "email", "course_name", "comment")
        labels = {
            "full_name": "ФИО",
            "birth_date": "Дата рождения",
            "email": "Email",
            "course_name": "Курс",
            "comment": "Комментарий",
        }
        help_texts = {
            "full_name": "Укажите ФИО для сертификата.",
            "birth_date": "Используется для корректной идентификации.",
            "email": "На этот адрес придёт информация по сертификату.",
            "course_name": "Название курса, по которому нужен сертификат.",
            "comment": "Дополнительно: формат выдачи, уточнения по данным и т.д.",
        }
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = self._build_course_choices(user=user)
        self.fields["course_name"] = forms.ChoiceField(
            label="Курс",
            choices=choices,
            required=True,
            help_text=("Выберите курс из заявок, которые вы уже отправляли на сайте."),
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
