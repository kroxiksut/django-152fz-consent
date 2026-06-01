from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Template context objects are framework-dynamic.
from typing import Any

from django import template
from django.conf import settings
from django.template.defaultfilters import linebreaksbr
from django.urls import reverse
from django.utils.html import conditional_escape, format_html, mark_safe

register = template.Library()


def _cookies_deps():
    from django_cookies_152fz.forms import CookiePreferencesForm
    from django_cookies_152fz.integration_contract import (
        get_cookie_runtime_settings,
        get_request_anonymous_token,
        get_request_consent_subject,
    )
    from django_cookies_152fz.models import normalize_categories_snapshot
    from django_cookies_152fz.services import (
        get_active_cookie_policy_revision,
        get_cookie_banner_configuration,
        get_cookie_banner_state,
        get_cookie_empty_categories_display_options,
        get_cookie_requirements,
    )

    return {
        "CookiePreferencesForm": CookiePreferencesForm,
        "get_cookie_runtime_settings": get_cookie_runtime_settings,
        "get_request_anonymous_token": get_request_anonymous_token,
        "get_request_consent_subject": get_request_consent_subject,
        "normalize_categories_snapshot": normalize_categories_snapshot,
        "get_active_cookie_policy_revision": get_active_cookie_policy_revision,
        "get_cookie_banner_configuration": get_cookie_banner_configuration,
        "get_cookie_empty_categories_display_options": (
            get_cookie_empty_categories_display_options
        ),
        "get_cookie_banner_state": get_cookie_banner_state,
        "get_cookie_requirements": get_cookie_requirements,
    }


@register.filter(name="render_cookie_policy")
def render_cookie_policy(policy: Any) -> str:
    if policy is None:
        return ""
    escaped = conditional_escape(getattr(policy, "content_text", "") or "")
    return format_html(
        '<div class="dz152fz-cookie-policy-text">{}</div>',
        mark_safe(linebreaksbr(escaped)),
    )


@register.inclusion_tag(
    "django_cookies_152fz/includes/cookie_banner.html",
    takes_context=True,
)
def render_cookie_banner(
    context: template.Context,
    next_url: str = "",
) -> dict[str, Any]:
    if "django_cookies_152fz" not in getattr(settings, "INSTALLED_APPS", []):
        return {"cookie_banner_enabled": False}
    deps = _cookies_deps()
    request = context.get("request")
    if request is None:
        return {"cookie_banner_enabled": False}

    user, anonymous_token = _resolve_cookie_subject(request)
    requirements = deps["get_cookie_requirements"](
        user=user,
        anonymous_token=anonymous_token or None,
        request=request,
    )
    banner_state = deps["get_cookie_banner_state"](
        user=user,
        anonymous_token=anonymous_token or None,
    )
    banner_config = deps["get_cookie_banner_configuration"]()
    runtime_settings = deps["get_cookie_runtime_settings"]()
    policy = deps["get_active_cookie_policy_revision"]()
    if not requirements["enabled"] or policy is None:
        return {"cookie_banner_enabled": False}

    categories = deps["normalize_categories_snapshot"](policy.categories_snapshot)
    required_categories = [item for item in categories if bool(item["is_required"])]
    optional_categories = [item for item in categories if not bool(item["is_required"])]
    optional_codes = {str(item["code"]) for item in optional_categories}
    has_optional_categories = bool(optional_categories)
    display_options = deps["get_cookie_empty_categories_display_options"]()
    show_empty_category_block = bool(
        display_options.get("show_empty_category_block", False)
    )
    show_customize_action_without_optional = bool(
        display_options.get("show_customize_action_without_optional", False)
    )
    show_optional_custom_block = has_optional_categories or show_empty_category_block
    show_customize_action = (
        has_optional_categories or show_customize_action_without_optional
    )
    empty_category_block_text = str(
        display_options.get("empty_category_block_text", "") or ""
    ).strip()
    if not empty_category_block_text:
        empty_category_block_text = str(
            banner_config.get("optional_section_empty_text") or ""
        )
    if not next_url:
        next_url = request.get_full_path()

    resolver_match = getattr(request, "resolver_match", None)
    is_preferences_page = (
        bool(resolver_match)
        and resolver_match.view_name == "django_cookies_152fz:cookie_preferences"
    )
    preview_mode = _is_preview_mode(
        request,
        str(runtime_settings.get("preview_param") or "cookie_banner_preview"),
    )
    bot_hidden = (
        bool(requirements["runtime"].get("hide_for_bots"))
        and bool(requirements["runtime"].get("is_bot_request"))
        and not preview_mode
    )
    if bot_hidden:
        return {"cookie_banner_enabled": False}

    banner_should_show = bool(
        banner_state["has_policy"]
        and (preview_mode or (not is_preferences_page and banner_state["should_show"]))
    )
    hide_launcher_after_decision = bool(
        banner_config.get("hide_launcher_after_decision", False)
    )
    hide_launcher_due_to_decision = bool(
        banner_state["has_decision"]
        and hide_launcher_after_decision
        and not banner_should_show
    )
    hide_launcher_due_to_dismiss = bool(banner_state["is_dismissed"])
    blocking_mode_active = bool(banner_state["blocking_mode_active"])

    banner_form = deps["CookiePreferencesForm"](
        optional_categories=optional_categories,
        initial_categories=[
            code
            for code in requirements["selected_categories"]
            if code in optional_codes
        ],
        initial={
            "anonymous_token": anonymous_token,
            "next": next_url,
        },
    )

    cookie_root = getattr(settings, "DJANGO_COOKIES_152FZ", None)
    if cookie_root is None:
        cookie_root = getattr(settings, "DJANGO_152FZ_COOKIES", {})
    banner_cfg = dict((cookie_root or {}).get("cookie_banner", {}))
    show_launcher = bool(banner_cfg.get("show_launcher", True))
    show_preferences_link = bool(banner_cfg.get("show_preferences_link", False))
    preferences_url = reverse("django_cookies_152fz:cookie_preferences")

    return {
        "cookie_banner_enabled": True,
        "request": request,
        "cookie_policy": policy,
        "cookie_requirements": requirements,
        "cookie_required_categories": required_categories,
        "cookie_optional_categories": optional_categories,
        "cookie_banner_form": banner_form,
        "cookie_banner_config": banner_config,
        "cookie_banner_state": banner_state,
        "cookie_banner_should_show": banner_should_show,
        "cookie_banner_has_decision": banner_state["has_decision"],
        "cookie_banner_requires_reconsent": banner_state["requires_reconsent"],
        "cookie_banner_is_reask_due": banner_state["is_reask_due"],
        "cookie_banner_reask_reason": banner_state["reask_reason"],
        "cookie_banner_launcher_visible": requirements["has_policy"]
        and not is_preferences_page
        and show_launcher
        and not hide_launcher_due_to_dismiss
        and not hide_launcher_due_to_decision
        and not blocking_mode_active,
        "cookie_preferences_link_visible": show_preferences_link,
        "cookie_banner_action_url": reverse(
            "django_cookies_152fz:cookie_banner_action"
        ),
        "cookie_preferences_url": preferences_url,
        "cookie_banner_preview_mode": preview_mode,
        "cookie_banner_blocking_mode_enabled": bool(
            banner_state["blocking_mode_enabled"]
        ),
        "cookie_banner_blocking_mode_active": blocking_mode_active,
        "cookie_banner_blocking_gate_open": bool(banner_state["blocking_gate_open"]),
        "cookie_banner_initial_visit": bool(banner_state["initial_visit"]),
        "cookie_banner_reopen_after_saved_choice": bool(
            banner_state["reopen_after_saved_choice"]
        ),
        "cookie_banner_custom_css_url": str(
            runtime_settings.get("custom_css_url") or ""
        ),
        "cookie_banner_custom_js_url": str(runtime_settings.get("custom_js_url") or ""),
        "cookie_banner_runtime_payload": requirements["runtime"],
        "cookie_banner_has_optional_categories": has_optional_categories,
        "cookie_banner_show_optional_custom_block": show_optional_custom_block,
        "cookie_banner_show_customize_action": show_customize_action,
        "cookie_banner_empty_category_block_text": empty_category_block_text,
    }


def _resolve_cookie_subject(request):
    deps = _cookies_deps()
    user = getattr(request, "user", None)
    token = deps["get_request_anonymous_token"](
        request,
        ensure_anonymous_token=(not getattr(user, "is_authenticated", False)),
    )
    if getattr(user, "is_authenticated", False):
        return user, token
    return deps["get_request_consent_subject"](
        request,
        anonymous_token=token,
        ensure_anonymous_token=False,
    )


def _is_preview_mode(request, preview_param: str) -> bool:
    raw = str(request.GET.get(preview_param, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}
