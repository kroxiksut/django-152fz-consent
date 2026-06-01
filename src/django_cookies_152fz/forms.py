"""Forms for the cookie module HTML UI."""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Django form field wiring is dynamic at runtime.
from collections.abc import Sequence

from django import forms
from django.utils.translation import gettext_lazy as _

from .integration_contract import ConsentAuditContextForm


class CookiePreferencesForm(ConsentAuditContextForm):
    """Form for selecting optional cookie categories."""

    selected_categories = forms.MultipleChoiceField(
        required=False,
        label=_("Необязательные категории cookie"),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(
        self,
        *args,
        optional_categories: Sequence[dict[str, object]] | None = None,
        initial_categories: Sequence[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["selected_categories"].choices = [
            (str(item["code"]), str(item["title"]))
            for item in list(optional_categories or [])
        ]
        self.fields["selected_categories"].help_text = _(
            "Обязательные категории включены всегда и не требуют выбора."
        )
        if initial_categories is not None:
            self.initial.setdefault("selected_categories", list(initial_categories))
