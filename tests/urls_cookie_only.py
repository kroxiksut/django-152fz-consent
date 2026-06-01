from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path(
        "consent/",
        include(
            ("django_cookies_152fz.urls", "django_cookies_152fz"),
            namespace="django_cookies_152fz",
        ),
    ),
]
