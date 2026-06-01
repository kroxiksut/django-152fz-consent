"""Optional admin navigation customization for django-152fz modules."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Any, cast

from django.contrib.admin import AdminSite

from django_consent_152fz import admin as core_admin_module
from django_consent_152fz import constants
from django_consent_152fz.settings import (
    get_admin_navigation_settings,
    is_verified_consents_app_installed,
)

_VERIFIED_CONSENTS_ADMIN_APP_LABEL = "verified_consents"


class ConsentNavigationAdminSite(AdminSite):
    """Optional AdminSite with configurable ordering and collapse behavior."""

    index_template = "admin/django_consent_152fz/custom_index.html"

    def each_context(self, request):
        context = super().each_context(request)
        navigation_settings = get_admin_navigation_settings()
        context["dz152fz_admin_navigation_enabled"] = bool(
            navigation_settings[constants.CONFIG_ADMIN_NAVIGATION_ENABLED]
        )
        context["dz152fz_admin_navigation_section_title"] = str(
            navigation_settings[constants.CONFIG_ADMIN_NAVIGATION_SECTION_TITLE]
        )
        return context

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        app_list = _merge_verified_consents_app_into_core(list(app_list))
        navigation_settings = get_admin_navigation_settings()
        return _apply_navigation_settings(
            app_list=app_list,
            navigation_settings=navigation_settings,
        )


def _merge_verified_consents_app_into_core(app_list: list[dict]) -> list[dict]:
    core_label = constants.APP_LABEL
    core_entry: dict[str, Any] | None = None
    verified_models: list[dict[str, Any]] = []
    filtered_apps: list[dict] = []

    for app in app_list:
        app_label = str(app.get("app_label") or "")
        if app_label == core_label and core_entry is None:
            core_entry = app
            filtered_apps.append(app)
            continue
        if app_label == _VERIFIED_CONSENTS_ADMIN_APP_LABEL:
            verified_models.extend(list(app.get("models") or []))
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


def _apply_navigation_settings(
    *,
    app_list: list[dict],
    navigation_settings: dict[str, object],
) -> list[dict]:
    ordered_apps = list(app_list)
    consent_apps = {
        str(value)
        for value in cast(
            Iterable[Any],
            navigation_settings[constants.CONFIG_ADMIN_NAVIGATION_CONSENT_APPS],
        )
    }
    collapsed_apps = {
        str(value)
        for value in cast(
            Iterable[Any],
            navigation_settings[constants.CONFIG_ADMIN_NAVIGATION_COLLAPSED_APPS],
        )
    }
    app_order = [
        str(value)
        for value in cast(
            Iterable[Any],
            navigation_settings[constants.CONFIG_ADMIN_NAVIGATION_APP_ORDER],
        )
    ]
    enabled = bool(navigation_settings[constants.CONFIG_ADMIN_NAVIGATION_ENABLED])

    if app_order:
        explicit_order = {label: index for index, label in enumerate(app_order)}
        ordered_apps.sort(
            key=lambda app: (
                explicit_order.get(str(app["app_label"]), len(explicit_order)),
                str(app["name"]).lower(),
            )
        )
    elif enabled:
        ordered_apps = _move_apps_to_bottom(
            app_list=ordered_apps,
            app_labels_to_bottom=consent_apps,
        )

    first_consent_marked = False
    for app in ordered_apps:
        app_label_value = str(app["app_label"])
        is_consent_app = app_label_value in consent_apps
        app["dz152fz_is_consent"] = is_consent_app
        app["dz152fz_collapsed"] = app_label_value in collapsed_apps
        app["dz152fz_is_first_consent"] = False
        if is_consent_app and not first_consent_marked:
            app["dz152fz_is_first_consent"] = True
            first_consent_marked = True

    return ordered_apps


def _move_apps_to_bottom(
    *,
    app_list: list[dict],
    app_labels_to_bottom: Iterable[str],
) -> list[dict]:
    labels = set(app_labels_to_bottom)
    top_apps: list[dict] = []
    bottom_apps: list[dict] = []
    for app in app_list:
        if str(app["app_label"]) in labels:
            bottom_apps.append(app)
        else:
            top_apps.append(app)
    return top_apps + bottom_apps


def register_optional_admin(site: AdminSite) -> None:
    """Register package admin models in the provided optional AdminSite."""

    core_admin_module.register_admin(site)

    if is_verified_consents_app_installed():
        from django_consent_152fz.verified_consents import (
            admin as verified_admin_module,
        )

        verified_admin_module.register_admin(site)


@lru_cache(maxsize=1)
def get_optional_admin_site() -> ConsentNavigationAdminSite:
    """Return the singleton optional admin site for custom navigation mode."""

    site = ConsentNavigationAdminSite(name="dz152fz_admin")
    register_optional_admin(site)
    return site
