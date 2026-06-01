from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
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
    path("", include(("training_center.urls", "pages"), namespace="pages")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
