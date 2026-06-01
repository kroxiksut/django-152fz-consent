from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_DIR = BASE_DIR.parent
PROJECT_ROOT = DEMO_DIR.parent
COMMON_DIR = DEMO_DIR / "common"

SECRET_KEY = "demo-django5-secret-key"
DEBUG = True
ALLOWED_HOSTS: list[str] = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "rest_framework",
    "allauth",
    "allauth.account",
    "django_consent_152fz",
    "django_consent_152fz.api",
    "django_consent_152fz.verified_consents",
    "django_cookies_152fz",
    "formtools",
    "django_bootstrap5",
    "training_center",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "demo_site.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [COMMON_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "demo_site.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SITE_ID = 1

LOGIN_REDIRECT_URL = "pages:profile"
LOGOUT_REDIRECT_URL = "pages:home"
ACCOUNT_LOGOUT_REDIRECT_URL = "pages:home"
ACCOUNT_EMAIL_VERIFICATION = "none"

DJANGO_CONSENT_152FZ = {
    "enable_core": True,
    "enable_access_policies": False,
    "sample_documents": {
        "load_mode": "command",
    },
    "subject_consents": {
        "open_mode": "page",
        "allow_anonymous_withdraw": True,
        "consent_input_mode": "radio",
        "checkbox_required": True,
        "decline_action": "block_submit",
        "decline_warning_enabled": True,
        "decline_warning_text": (
            "Если вы не согласны на обработку персональных данных, "
            "мы не сможем связаться с вами по заявке."
        ),
    },
}
USE_API_152FZ = True
API_152FZ_AUTHENTICATION_CLASSES = [
    "rest_framework.authentication.SessionAuthentication",
    "rest_framework.authentication.BasicAuthentication",
]
API_152FZ_PERMISSION_CLASSES = [
    "rest_framework.permissions.IsAuthenticated",
]
PUBLIC_API_152FZ_ENABLED = True
PUBLIC_API_152FZ_URL_PREFIX = "api/consents/public/v1/"
PUBLIC_API_152FZ_ALLOWED_PURPOSES = [
    "webform_request",
    "course_enrollment",
    "certificate_issue",
]

DJANGO_COOKIES_152FZ = {
    "enable_cookies": True,
    "cookie_banner": {
        "bootstrap_initial_revision": True,
        "banner_variant": "card",
        "consent_ui_variant": "panel",
        "text_preset": "auto",
        "show_launcher": True,
        "show_preferences_link": False,
        "show_empty_category_block": True,
        "show_customize_action_without_optional": True,
        "empty_category_block_text": "?? ????? ???????????? ?????? ???????????? cookie. ?????????????? ????????? ?????? ?? ?????????.",
    },
    "cookie_runtime": {
        "force_banner": False,
        "preview_param": "cookie_banner_preview",
        "custom_css_url": "",
        "custom_js_url": "",
        "hide_for_bots": True,
        "bot_patterns": [
            "googlebot",
            "yandexbot",
            "bingbot",
            "duckduckbot",
            "crawler",
            "spider",
            "bot",
        ],
        "user_agent_mode": "all",
        "shared_subdomain": False,
        "site_domain": "",
        "cookie_domain": "",
        "geo_signal_hook": "",
    },
}

LANGUAGE_CODE = "ru"
LANGUAGES = [
    ("ru", "Русский"),
    ("en", "English"),
]
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [COMMON_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
LOCALE_PATHS = [COMMON_DIR / "locale"]
FIXTURE_DIRS = [COMMON_DIR / "fixtures"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TRAINING_CENTER_AUTO_BOOTSTRAP = True
