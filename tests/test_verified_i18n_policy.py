from __future__ import annotations

import gettext as gettext_lib
from pathlib import Path


def test_verified_check_messages_are_present_in_po_and_translated_in_mo() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    po_path = (
        repo_root
        / "src"
        / "django_consent_152fz"
        / "locale"
        / "ru"
        / "LC_MESSAGES"
        / "django.po"
    )
    mo_path = (
        repo_root
        / "src"
        / "django_consent_152fz"
        / "locale"
        / "ru"
        / "LC_MESSAGES"
        / "django.mo"
    )

    po_text = po_path.read_text(encoding="utf-8")
    assert "no active Verified Consent Policy is configured for this" in po_text
    assert "base policy flow_scope '%(flow_scope)s'" in po_text
    assert "include forms." in po_text

    msgid_missing_base = (
        "Form policy '%(form_code)s' for flow '%(purpose_code)s/%(document_code)s' "
        "uses '%(mode)s' but no active Verified Consent Policy is configured for this "
        "flow."
    )
    msgid_scope = (
        "Form policy '%(form_code)s' for flow '%(purpose_code)s/%(document_code)s' "
        "uses '%(mode)s', but base policy flow_scope '%(flow_scope)s' does not "
        "include forms."
    )

    with mo_path.open("rb") as fh:
        ru_catalog = gettext_lib.GNUTranslations(fh)

    translated_missing_base = ru_catalog.gettext(msgid_missing_base)
    translated_scope = ru_catalog.gettext(msgid_scope)

    assert translated_missing_base != msgid_missing_base
    assert translated_scope != msgid_scope
    assert "политики формы" in translated_missing_base.lower()
    assert "не включает формы" in translated_scope.lower()


def test_verified_transition_html_messages_are_wrapped_in_i18n_tags() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    consent_block = (
        repo_root
        / "src"
        / "django_consent_152fz"
        / "templates"
        / "django_consent_152fz"
        / "includes"
        / "consent_form_block.html"
    ).read_text(encoding="utf-8")
    contact_hook = (
        repo_root
        / "src"
        / "django_consent_152fz"
        / "templates"
        / "django_consent_152fz"
        / "includes"
        / "contact_consent_hook.html"
    ).read_text(encoding="utf-8")

    assert (
        'status_info.verified_transition.status_code == "paper_required"'
        in consent_block
    )
    assert (
        '{% trans "Для этого потока требуется бумажное или иное проверяемое '
        'подтверждение. Подписание через web-форму недоступно." %}' in consent_block
    )
    assert (
        '{% trans "Подписание через web-форму недоступно: требуется бумажное '
        'подтверждение согласия." %}' in contact_hook
    )
