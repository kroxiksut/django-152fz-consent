from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path, re_path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    base = request.build_absolute_uri("/").rstrip("/")
    return Response(
        {
            "consents": f"{base}/api/consents/",
            "consents_v1": f"{base}/api/consents/v1/",
            "consents_public_v1": f"{base}/api/consents/public/v1/",
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def api_consents_root(request):
    base = request.build_absolute_uri("/").rstrip("/")
    return Response(
        {
            "v1": f"{base}/api/consents/v1/",
            "public_v1": f"{base}/api/consents/public/v1/",
            "note": "Публичный контур доступен без авторизации по public_v1.",
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def api_public_root(request):
    base = request.build_absolute_uri("/").rstrip("/")
    return Response(
        {
            "consents_public_v1": f"{base}/api/consents/public/v1/",
        }
    )


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@permission_classes([AllowAny])
def api_not_found_root(request, subpath: str = ""):
    base = request.build_absolute_uri("/").rstrip("/")
    return Response(
        {
            "detail": "Такого API-адреса нет.",
            "requested_path": request.path,
            "allowed": {
                "api_root": f"{base}/api/",
                "consents_root": f"{base}/api/consents/",
                "consents_v1": f"{base}/api/consents/v1/",
                "consents_public_v1": f"{base}/api/consents/public/v1/",
            },
        },
        status=404,
    )


def api_public_v1_no_slash(_request):
    return redirect("/api/consents/public/v1/", permanent=False)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api-auth/", include("rest_framework.urls")),
    path("api/", api_root, name="api_root"),
    path("api/consents/", api_consents_root, name="api_consents_root"),
    path("api/public", api_public_root, name="api_public_root_no_slash"),
    path("api/public/", api_public_root, name="api_public_root"),
    path(
        "api/consents/public/v1", api_public_v1_no_slash, name="api_public_v1_no_slash"
    ),
    path(
        "",
        include(
            ("django_consent_152fz.urls", "django_consent_152fz"),
            namespace="django_consent_152fz",
        ),
    ),
    path(
        "cookies/",
        include(
            ("django_cookies_152fz.urls", "django_cookies_152fz"),
            namespace="django_cookies_152fz",
        ),
    ),
    re_path(r"^api/(?P<subpath>.*)$", api_not_found_root, name="api_not_found_root"),
    path("", include(("training_center.urls", "pages"), namespace="pages")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
