from __future__ import annotations

from django.http import JsonResponse
from django.urls import include, path


def custom_api_root(_request):
    return JsonResponse({"source": "project_custom_api"})


urlpatterns = [
    path("api/", custom_api_root, name="custom_api_root"),
    path("", include("django_consent_152fz.urls")),
    path("", include("django_cookies_152fz.urls")),
]
