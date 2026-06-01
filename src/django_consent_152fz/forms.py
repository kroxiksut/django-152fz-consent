"""Template UI forms and embedded-hook scripts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from django_consent_152fz import constants
from django_consent_152fz.settings import get_subject_consents_capture_settings

ANONYMOUS_CONSENT_SCENARIO_CONTACT = "contact"
ANONYMOUS_CONSENT_SCENARIO_PREORDER = "preorder"
ANONYMOUS_CONSENT_SCENARIOS = (
    ANONYMOUS_CONSENT_SCENARIO_CONTACT,
    ANONYMOUS_CONSENT_SCENARIO_PREORDER,
)


class ConsentAuditContextForm(forms.Form):
    anonymous_token = forms.CharField(required=False, widget=forms.HiddenInput)
    next = forms.CharField(required=False, widget=forms.HiddenInput)
    client_timezone = forms.CharField(required=False, widget=forms.HiddenInput)
    client_languages = forms.CharField(required=False, widget=forms.HiddenInput)
    client_os_locale = forms.CharField(required=False, widget=forms.HiddenInput)
    client_screen_width = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.HiddenInput,
    )
    client_screen_height = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.HiddenInput,
    )
    verification_channel = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
    )
    verification_form_code = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
    )


class ConsentCaptureModeMixin(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label=_("Я даю согласие на обработку персональных данных"),
    )
    consent_decision = forms.ChoiceField(
        required=True,
        label=_("Согласие на обработку персональных данных"),
        choices=(
            ("agree", _("Согласен(а)")),
            ("decline", _("Не согласен(а)")),
        ),
        widget=forms.RadioSelect,
    )

    def __init__(
        self,
        *args,
        consent_capture_options: Mapping[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        defaults = get_subject_consents_capture_settings()
        override = dict(consent_capture_options or {})
        self.consent_capture_options: dict[str, Any] = {**defaults, **override}

        mode = str(self.consent_capture_options.get("input_mode") or "").strip()
        if mode == constants.SUBJECT_CONSENTS_INPUT_MODE_RADIO:
            self.fields.pop("confirm", None)
        else:
            self.fields.pop("consent_decision", None)
            checkbox_required = bool(
                self.consent_capture_options.get("checkbox_required", True)
            )
            if "confirm" in self.fields:
                self.fields["confirm"].required = checkbox_required

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data is None:
            cleaned_data = {}
        mode = str(self.consent_capture_options.get("input_mode") or "").strip()
        decline_action = str(
            self.consent_capture_options.get("decline_action") or ""
        ).strip()
        if (
            mode == constants.SUBJECT_CONSENTS_INPUT_MODE_RADIO
            and cleaned_data.get("consent_decision") == "decline"
            and decline_action == constants.SUBJECT_CONSENTS_DECLINE_ACTION_BLOCK_SUBMIT
        ):
            raise forms.ValidationError(
                _(
                    "Без согласия на обработку персональных данных мы не сможем обработать заявку."
                )
            )
        return cleaned_data


class ConsentAcceptanceForm(ConsentCaptureModeMixin, ConsentAuditContextForm):
    pass


class ConsentWithdrawForm(ConsentAuditContextForm):
    confirm = forms.BooleanField(
        required=True,
        label=_("Подтверждаю отзыв согласия"),
    )


class AnonymousContactConsentHookForm(ConsentCaptureModeMixin, ConsentAuditContextForm):
    scenario = forms.ChoiceField(
        choices=[
            (ANONYMOUS_CONSENT_SCENARIO_CONTACT, "Contact"),
            (ANONYMOUS_CONSENT_SCENARIO_PREORDER, "Preorder"),
        ],
        widget=forms.HiddenInput,
    )
    subject_ref = forms.CharField(required=False, widget=forms.HiddenInput)
    contact_name = forms.CharField(required=False, widget=forms.HiddenInput)
    contact_email = forms.CharField(required=False, widget=forms.HiddenInput)
    contact_phone = forms.CharField(required=False, widget=forms.HiddenInput)
    contact_contacts = forms.CharField(required=False, widget=forms.HiddenInput)
    contact_address = forms.CharField(required=False, widget=forms.HiddenInput)
    contact_message = forms.CharField(required=False, widget=forms.HiddenInput)
    preorder_id = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, scenario: str = "contact", **kwargs):
        super().__init__(*args, **kwargs)
        normalized_scenario = scenario.strip() or ANONYMOUS_CONSENT_SCENARIO_CONTACT
        self.initial.setdefault("scenario", normalized_scenario)
        if "confirm" in self.fields:
            if normalized_scenario == ANONYMOUS_CONSENT_SCENARIO_PREORDER:
                self.fields["confirm"].label = _(
                    "Я даю согласие на обработку ПДн для предзаказа"
                )
            else:
                self.fields["confirm"].label = _(
                    "Я даю согласие на обработку ПДн для обратной связи"
                )


def build_verification_context_from_cleaned_data(
    cleaned_data: Mapping[str, Any],
    *,
    default_channel: str = "",
    default_form_code: str = "",
) -> dict[str, str] | None:
    """Собрать verification-context из скрытых полей формы.

    Нужен для случаев, когда переключение verified-policy выполняется в admin,
    а код страницы-хоста не меняется: форма передаёт стабильный `form_code`,
    и service-layer применяет per-form override автоматически.
    """

    channel = str(
        cleaned_data.get("verification_channel") or default_channel or ""
    ).strip()
    form_code = str(
        cleaned_data.get("verification_form_code") or default_form_code or ""
    ).strip()
    if not channel and form_code:
        channel = "form"
    if not channel and not form_code:
        return None

    context: dict[str, str] = {"channel": channel}
    if form_code:
        context["form_code"] = form_code
    return context
