"""Cookie-only URL router for standalone integration."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "django_cookies_152fz"

urlpatterns = [
    path(
        "cookies/",
        views.cookie_preferences_view,
        name="cookie_preferences",
    ),
    path(
        "cookies/banner/",
        views.cookie_banner_action_view,
        name="cookie_banner_action",
    ),
]
