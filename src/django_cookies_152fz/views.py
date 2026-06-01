"""HTML views for the cookie module (section 5.3)."""

from __future__ import annotations

import secrets

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from .forms import CookiePreferencesForm
from .integration_contract import (
    ConsentError,
    build_request_audit_context,
    constants,
    get_cookie_banner_settings,
    get_cookie_runtime_allowed_hosts,
    get_request_anonymous_token,
    get_request_consent_subject,
    persist_anonymous_token,
)
from .models import CookiePolicyRevision, normalize_categories_snapshot
from .services import (
    accept_cookie_preferences,
    attach_anonymous_cookie_data_to_user,
    dismiss_cookie_banner,
    get_active_cookie_policy_revision,
    get_cookie_banner_state,
    get_cookie_empty_categories_display_options,
    get_cookie_requirements,
    get_cookie_status,
)

COOKIE_BANNER_ACTION_ACCEPT_ALL = "accept_all"
COOKIE_BANNER_ACTION_REJECT_ALL = "reject_all"
COOKIE_BANNER_ACTION_REQUIRED_ONLY = "required_only"
COOKIE_BANNER_ACTION_SAVE_CUSTOM = "save_custom"
COOKIE_BANNER_ACTION_DISMISS = "dismiss"
COOKIE_BANNER_ACTIONS = frozenset(
    {
        COOKIE_BANNER_ACTION_ACCEPT_ALL,
        COOKIE_BANNER_ACTION_REJECT_ALL,
        COOKIE_BANNER_ACTION_REQUIRED_ONLY,
        COOKIE_BANNER_ACTION_SAVE_CUSTOM,
        COOKIE_BANNER_ACTION_DISMISS,
    }
)


def cookie_preferences_view(request: HttpRequest) -> HttpResponse:
    """Display and save cookie category choices for the current subject."""

    if request.method == "POST":
        _policy_revision, optional_categories = _get_cookie_policy_form_state()
        form = CookiePreferencesForm(
            request.POST,
            optional_categories=optional_categories,
        )
        banner_action = _get_cookie_banner_action(request)
        if banner_action in {None, COOKIE_BANNER_ACTION_DISMISS}:
            banner_action = COOKIE_BANNER_ACTION_SAVE_CUSTOM
        if form.is_valid():
            user, anonymous_token = _resolve_cookie_request_subject(
                request,
                anonymous_token=form.cleaned_data["anonymous_token"],
                ensure_anonymous_token=True,
            )
            try:
                accept_cookie_preferences(
                    selected_categories=_resolve_banner_selected_categories(
                        banner_action=banner_action,
                        optional_categories=optional_categories,
                        selected_categories=form.cleaned_data["selected_categories"],
                    ),
                    decision_action=(banner_action or COOKIE_BANNER_ACTION_SAVE_CUSTOM),
                    user=user,
                    anonymous_token=anonymous_token,
                    audit_context=build_request_audit_context(
                        request,
                        source="template_ui.cookies",
                        anonymous_token=anonymous_token,
                    ),
                )
            except ConsentError as exc:
                form.add_error(None, str(exc))
            else:
                response = redirect(
                    _get_safe_redirect_target(
                        request,
                        next_url=form.cleaned_data["next"],
                        fallback_url=_reverse_cookie_preferences_url(),
                    )
                )
                if anonymous_token:
                    persist_anonymous_token(
                        response,
                        anonymous_token=anonymous_token,
                    )
                return response
        return _render_cookie_preferences_response(
            request,
            form=form,
            anonymous_token_override=form.data.get("anonymous_token", ""),
            status=400,
        )

    return _render_cookie_preferences_response(request)


def cookie_banner_action_view(request: HttpRequest) -> HttpResponse:
    """Handle quick cookie banner actions and redirect back."""

    if request.method != "POST":
        return redirect(_reverse_cookie_preferences_url())

    _policy_revision, optional_categories = _get_cookie_policy_form_state()
    form = CookiePreferencesForm(
        request.POST,
        optional_categories=optional_categories,
    )
    banner_action = _get_cookie_banner_action(request)
    if banner_action is None:
        form.add_error(None, _("Неизвестное действие cookie-баннера."))
    if not form.is_valid() or banner_action is None:
        return _render_cookie_preferences_response(
            request,
            form=form,
            anonymous_token_override=form.data.get("anonymous_token", ""),
            status=400,
        )

    user, anonymous_token = _resolve_cookie_request_subject(
        request,
        anonymous_token=form.cleaned_data["anonymous_token"],
        ensure_anonymous_token=True,
    )
    try:
        if banner_action == COOKIE_BANNER_ACTION_DISMISS:
            if _is_cookie_banner_dismiss_blocked(
                user=user,
                anonymous_token=anonymous_token,
            ):
                form.add_error(
                    None,
                    (
                        _("В блокирующем режиме до выбора нельзя закрыть баннер. ")
                        + _("Сначала выберите вариант cookie.")
                    ),
                )
                return _render_cookie_preferences_response(
                    request,
                    form=form,
                    anonymous_token_override=form.data.get("anonymous_token", ""),
                    status=400,
                )
            # Dismiss only updates the banner state and does not record a consent.
            dismiss_cookie_banner(
                user=user,
                anonymous_token=anonymous_token,
                audit_context=build_request_audit_context(
                    request,
                    source="template_ui.cookie_banner.dismiss",
                    anonymous_token=anonymous_token,
                ),
            )
        else:
            # All other actions always go through the unified consent-flow service.
            accept_cookie_preferences(
                selected_categories=_resolve_banner_selected_categories(
                    banner_action=banner_action,
                    optional_categories=optional_categories,
                    selected_categories=form.cleaned_data["selected_categories"],
                ),
                decision_action=banner_action,
                user=user,
                anonymous_token=anonymous_token,
                audit_context=build_request_audit_context(
                    request,
                    source="template_ui.cookie_banner",
                    anonymous_token=anonymous_token,
                ),
            )
    except ConsentError as exc:
        form.add_error(None, str(exc))
        return _render_cookie_preferences_response(
            request,
            form=form,
            anonymous_token_override=form.data.get("anonymous_token", ""),
            status=400,
        )

    response = redirect(
        _get_safe_redirect_target(
            request,
            next_url=form.cleaned_data["next"],
            fallback_url=_reverse_cookie_preferences_url(),
        )
    )
    if anonymous_token:
        persist_anonymous_token(response, anonymous_token=anonymous_token)
    return response


def _is_cookie_banner_dismiss_blocked(
    *,
    user,
    anonymous_token: str | None,
) -> bool:
    banner_state = get_cookie_banner_state(
        user=user,
        anonymous_token=anonymous_token or None,
    )
    return bool(banner_state.get("blocking_mode_active", False))


def _get_active_policy_or_404() -> CookiePolicyRevision:
    """Return the single active cookie policy revision, or raise 404."""

    policy = get_active_cookie_policy_revision()
    if policy is None:
        raise Http404(_("Активная редакция политики cookie не найдена."))
    return policy


def _render_cookie_preferences_response(
    request: HttpRequest,
    *,
    form: CookiePreferencesForm | None = None,
    anonymous_token_override: str = "",
    status: int | None = None,
) -> HttpResponse:
    """Build a unified response for the standalone preferences page and banner fallback."""

    user, anonymous_token = _resolve_cookie_request_subject(
        request,
        anonymous_token=anonymous_token_override,
    )
    requirements = get_cookie_requirements(
        user=user,
        anonymous_token=anonymous_token or None,
        request=request,
    )
    if not requirements["enabled"]:
        raise Http404(_("Cookie-поток отключён."))

    policy = _get_active_policy_or_404()
    categories = normalize_categories_snapshot(policy.categories_snapshot)
    required_categories = [item for item in categories if bool(item["is_required"])]
    optional_categories = [item for item in categories if not bool(item["is_required"])]
    has_optional_categories = bool(optional_categories)
    display_options = get_cookie_empty_categories_display_options()
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
        empty_category_block_text = _("Сейчас нет дополнительных категорий для выбора.")
    required_codes = {str(item["code"]) for item in required_categories}
    status_info = get_cookie_status(user=user, anonymous_token=anonymous_token or None)
    banner_state = get_cookie_banner_state(
        user=user,
        anonymous_token=anonymous_token or None,
    )

    if form is None:
        form = CookiePreferencesForm(
            optional_categories=optional_categories,
            initial_categories=[
                code
                for code in status_info["selected_categories"]
                if code not in required_codes
            ],
            initial={
                "anonymous_token": anonymous_token,
                "next": request.get_full_path(),
            },
        )

    context = {
        "policy": policy,
        "status_info": status_info,
        "banner_state": banner_state,
        "requirements": requirements,
        "required_categories": required_categories,
        "optional_categories": optional_categories,
        "preferences_form": form,
        "preferences_has_optional_categories": has_optional_categories,
        "preferences_show_optional_custom_block": show_optional_custom_block,
        "preferences_show_customize_action": show_customize_action,
        "preferences_empty_category_block_text": empty_category_block_text,
    }
    return render(
        request,
        _get_cookie_preferences_template_names(),
        context,
        status=status if status is not None else (400 if form.errors else 200),
    )


def _get_cookie_preferences_template_names() -> list[str]:
    """Return template candidates for cookie preferences page.

    If a project-level override is configured, Django will try it first and
    transparently fall back to the package template when the override is
    missing.
    """

    banner_settings = get_cookie_banner_settings()
    configured_template = str(
        banner_settings.get(
            constants.CONFIG_COOKIE_BANNER_PREFERENCES_PAGE_TEMPLATE, ""
        )
    ).strip()
    if configured_template:
        return [
            configured_template,
            "django_cookies_152fz/cookie_preferences.html",
        ]
    return ["django_cookies_152fz/cookie_preferences.html"]


def _get_cookie_policy_form_state() -> tuple[
    CookiePolicyRevision, list[dict[str, object]]
]:
    """Return the active policy and the list of optional categories for the form."""

    policy = _get_active_policy_or_404()
    categories = normalize_categories_snapshot(policy.categories_snapshot)
    optional_categories = [item for item in categories if not bool(item["is_required"])]
    return policy, optional_categories


def _get_cookie_banner_action(request: HttpRequest) -> str | None:
    action = str(request.POST.get("banner_action", "")).strip()
    if action in COOKIE_BANNER_ACTIONS:
        return action
    return None


def _resolve_banner_selected_categories(
    *,
    banner_action: str | None,
    optional_categories: list[dict[str, object]],
    selected_categories: list[str],
) -> list[str]:
    # `accept_all`/`required_only` — server-side shortcuts for banner buttons.
    if banner_action == COOKIE_BANNER_ACTION_ACCEPT_ALL:
        return [str(item["code"]) for item in optional_categories]
    if banner_action in {
        COOKIE_BANNER_ACTION_REQUIRED_ONLY,
        COOKIE_BANNER_ACTION_REJECT_ALL,
    }:
        return []
    return list(selected_categories)


def _resolve_cookie_request_subject(
    request: HttpRequest,
    *,
    anonymous_token: str = "",
    ensure_anonymous_token: bool = False,
):
    user = getattr(request, "user", None)
    token = get_request_anonymous_token(
        request,
        anonymous_token=anonymous_token,
        ensure_anonymous_token=(
            ensure_anonymous_token and not getattr(user, "is_authenticated", False)
        ),
    )
    if getattr(user, "is_authenticated", False):
        cookie_token = get_request_anonymous_token(request)
        explicit_token = str(anonymous_token or "").strip()
        if request.method != "POST":
            return user, cookie_token
        if (
            explicit_token
            and cookie_token
            and secrets.compare_digest(explicit_token, cookie_token)
        ):
            attach_anonymous_cookie_data_to_user(
                user=user,
                anonymous_token=cookie_token,
            )
            return user, cookie_token
        return user, ""
    return get_request_consent_subject(
        request,
        anonymous_token=token,
        ensure_anonymous_token=False,
    )


def _get_safe_redirect_target(
    request: HttpRequest,
    *,
    next_url: str,
    fallback_url: str,
) -> str:
    """Accept only a safe local redirect after saving the user's choice."""

    candidate = (next_url or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts=get_cookie_runtime_allowed_hosts(request),
    ):
        return candidate
    return fallback_url


def _reverse_cookie_preferences_url() -> str:
    for route_name in (
        "django_cookies_152fz:cookie_preferences",
        "cookie_preferences",
    ):
        try:
            return reverse(route_name)
        except NoReverseMatch:
            continue
    return "/cookies/"
