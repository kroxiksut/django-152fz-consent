"""РњРёРЅРёРјР°Р»СЊРЅС‹Рµ Django settings РґР»СЏ С‚РµСЃС‚РѕРІРѕРіРѕ РѕРєСЂСѓР¶РµРЅРёСЏ РїР°РєРµС‚Р°.

Р­С‚РѕС‚ РјРѕРґСѓР»СЊ РїРѕРґРґРµСЂР¶РёРІР°РµС‚ РёРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂСѓ РёР· РїСѓРЅРєС‚Р° 3.2: pytest РґРѕР»Р¶РµРЅ СѓРјРµС‚СЊ
РїРѕРґРЅСЏС‚СЊ РёР·РѕР»РёСЂРѕРІР°РЅРЅРѕРµ Django-РѕРєСЂСѓР¶РµРЅРёРµ Р±РµР· Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ РІРЅРµС€РЅРµРіРѕ РїСЂРѕРµРєС‚Р°.
Р—РґРµСЃСЊ РЅР°РјРµСЂРµРЅРЅРѕ РЅРµС‚ РЅРёС‡РµРіРѕ "Р±РѕРµРІРѕРіРѕ" РІСЂРѕРґРµ PostgreSQL, Redis РёР»Рё СЃР»РѕР¶РЅРѕРіРѕ
middleware-СЃС‚РµРєР°, РїРѕС‚РѕРјСѓ С‡С‚Рѕ С†РµР»СЊ С‚РµСЃС‚РѕРІ РїР°РєРµС‚Р° вЂ” РїСЂРѕРІРµСЂСЏС‚СЊ СЃР°Рј РїР°РєРµС‚.
"""

from __future__ import annotations

# РЎРµРєСЂРµС‚ С„РёРєС‚РёРІРЅС‹Р№: РјРѕРґСѓР»СЊ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ С‚РѕР»СЊРєРѕ РІ С‚РµСЃС‚РѕРІРѕРј РѕРєСЂСѓР¶РµРЅРёРё.
SECRET_KEY = "django-consent-152fz-tests"
DEBUG = True
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ALLOWED_HOSTS = ["testserver", "localhost"]
ROOT_URLCONF = "tests.urls"

# РџРѕРґРєР»СЋС‡Р°РµРј РєР°Рє Р±Р°Р·РѕРІРѕРµ РїСЂРёР»РѕР¶РµРЅРёРµ, С‚Р°Рє Рё optional РјРѕРґСѓР»Рё.
# Р­С‚Рѕ РїРѕР·РІРѕР»СЏРµС‚ integration-С‚РµСЃС‚Р°Рј РїРѕРєСЂС‹РІР°С‚СЊ РјР°СЂС€СЂСѓС‚С‹ Рё С€Р°Р±Р»РѕРЅС‹ Р±РµР· РѕС‚РґРµР»СЊРЅРѕР№
# СЃР±РѕСЂРєРё РЅРµСЃРєРѕР»СЊРєРёС… settings-РјРѕРґСѓР»РµР№ РїРѕРґ РєР°Р¶РґС‹Р№ СЃС†РµРЅР°СЂРёР№.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django_consent_152fz",
    "django_consent_152fz.api",
    "django_cookies_152fz",
    "django_consent_152fz.verified_consents",
]

# Middleware РѕСЃС‚Р°РІР»РµРЅ РјРёРЅРёРјР°Р»СЊРЅС‹Рј, РЅРѕ РґРѕСЃС‚Р°С‚РѕС‡РЅС‹Рј РґР»СЏ СЃРµСЃСЃРёР№, auth Рё messages,
# РїРѕС‚РѕРјСѓ С‡С‚Рѕ СЌС‚Рё Р·Р°РІРёСЃРёРјРѕСЃС‚Рё СЂРµР°Р»СЊРЅРѕ РёСЃРїРѕР»СЊР·СѓСЋС‚СЃСЏ UI Рё admin-С‡Р°СЃС‚СЊСЋ РїР°РєРµС‚Р°.
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

# Р”Р»СЏ С‚РµСЃС‚РѕРІ РїРѕРґС…РѕРґРёС‚ in-memory SQLite: РїРѕРґРЅРёРјР°РµС‚СЃСЏ Р±С‹СЃС‚СЂРѕ Рё РЅРµ С‚СЂРµР±СѓРµС‚ РІРЅРµС€РЅРµР№ Р‘Р”.
MEDIA_ROOT = "test_media"
MEDIA_URL = "/media/"
STATIC_URL = "/static/"
LANGUAGE_CODE = "ru"
LANGUAGES = [
    ("ru", "Russian"),
    ("en", "English"),
]
USE_I18N = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# APP_DIRS=True РїРѕР·РІРѕР»СЏРµС‚ С‚РµСЃС‚РёСЂРѕРІР°С‚СЊ С€Р°Р±Р»РѕРЅС‹ РїСЂСЏРјРѕ РёР· РїР°РєРµС‚Р° Р±РµР· РѕС‚РґРµР»СЊРЅРѕР№
# СЂСѓС‡РЅРѕР№ СЂРµРіРёСЃС‚СЂР°С†РёРё template loaders.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
            ]
        },
    }
]
