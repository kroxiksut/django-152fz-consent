"""URL routes for the package UI layer.

The HTML and template endpoints from section 5 are always included. The
optional API is added only in a valid configuration where the API app is
installed and DRF is available. This follows the architectural principle of
independent feature flags and optional apps from sections 3 and 4.
"""

from __future__ import annotations

from typing import TypeAlias

from django.urls import include, path, re_path
from django.urls.resolvers import URLPattern, URLResolver

from . import constants, views
from .api.dependencies import is_drf_available
from .api.stub_views import (
    api_consents_root_stub,
    api_consents_v1_stub,
    api_not_found_stub,
    api_root_stub,
)
from .settings import get_api_setting, is_api_app_installed

app_name = "django_consent_152fz"

UrlEntry: TypeAlias = URLPattern | URLResolver

urlpatterns: list[UrlEntry] = [
    # The basic template UI routes work independently of the API.
    path(
        "consent/documents/<str:purpose_code>/<str:document_code>/",
        views.document_detail,
        name="document",
    ),
    path(
        "consent/documents/<str:purpose_code>/<str:document_code>/pdf/",
        views.document_pdf_download,
        name="document_pdf",
    ),
    path(
        "consent/accept/<str:purpose_code>/<str:document_code>/",
        views.accept_consent_view,
        name="accept",
    ),
    path(
        "consent/withdraw/<str:purpose_code>/<str:document_code>/",
        views.withdraw_consent_view,
        name="withdraw",
    ),
    path(
        "consent/self-service/",
        views.subject_consents_view,
        name="subject_consents",
    ),
    path(
        "consent/self-service/withdraw/<str:purpose_code>/<str:document_code>/",
        views.subject_consents_withdraw_view,
        name="subject_consents_withdraw",
    ),
]

if is_api_app_installed() and is_drf_available():
    # Add API routes only for a working configuration so the main package stays
    # suitable for the template-only mode.
    urlpatterns.append(
        path(
            str(get_api_setting(constants.SETTING_API_PREFIX) or "api/consents/v1/"),
            include("django_consent_152fz.api.urls"),
        )
    )
    if get_api_setting(constants.SETTING_PUBLIC_API_ENABLED):
        urlpatterns.append(
            path(
                str(
                    get_api_setting(constants.SETTING_PUBLIC_API_PREFIX)
                    or "api/consents/public/v1/"
                ),
                include("django_consent_152fz.api.public_urls"),
            )
        )

if get_api_setting(constants.SETTING_API_SAFE_ROOT_STUBS_ENABLED):
    has_private_api = is_api_app_installed() and is_drf_available()
    if not has_private_api:
        urlpatterns.append(path("api/consents/v1/", api_consents_v1_stub))
    urlpatterns.extend(
        [
            path("api/", api_root_stub),
            path("api/consents/", api_consents_root_stub),
            re_path(r"^api/(?P<subpath>.*)$", api_not_found_stub),
        ]
    )
