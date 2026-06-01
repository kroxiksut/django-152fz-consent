"""URL routes for the public API app."""

from __future__ import annotations

from django.urls import path

from django_consent_152fz import constants
from django_consent_152fz.settings import get_public_api_settings

from .views import (
    PublicApiRootView,
    PublicFormConsentAcceptApiView,
    PublicFormConsentStatusApiView,
    PublicFormDocumentApiView,
)

app_name = "django_consent_152fz_public_api"

_public_api_settings = get_public_api_settings()

urlpatterns = []
if _public_api_settings[constants.SETTING_PUBLIC_API_SHOW_ROOT]:
    urlpatterns.append(path("", PublicApiRootView.as_view(), name="root"))

urlpatterns.extend(
    [
        path(
            "forms/<str:purpose_code>/accept/",
            PublicFormConsentAcceptApiView.as_view(),
            name="form_accept",
        ),
        path(
            "forms/<str:purpose_code>/status/",
            PublicFormConsentStatusApiView.as_view(),
            name="form_status",
        ),
        path(
            "forms/<str:purpose_code>/documents/<str:document_code>/",
            PublicFormDocumentApiView.as_view(),
            name="form_document",
        ),
    ]
)
