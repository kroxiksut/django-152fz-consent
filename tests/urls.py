"""РўРµСЃС‚РѕРІС‹Р№ URLConf РґР»СЏ РїР°РєРµС‚Р°.

РћРЅ РЅСѓР¶РµРЅ РЅРµ С‚РѕР»СЊРєРѕ РґР»СЏ view-С‚РµСЃС‚РѕРІ. Р”Р°Р¶Рµ smoke/integration-РїСЂРѕРІРµСЂРєРё СѓРїР°РєРѕРІРєРё
Рё optional API РѕРїРёСЂР°СЋС‚СЃСЏ РЅР° С‚Рѕ, С‡С‚Рѕ Django РјРѕР¶РµС‚ РєРѕСЂСЂРµРєС‚РЅРѕ СЃРѕР±СЂР°С‚СЊ URL-РіСЂР°С„.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from django_consent_152fz.admin_navigation import get_optional_admin_site

urlpatterns = [
    # Admin РЅСѓР¶РµРЅ РґР»СЏ С‚РµСЃС‚РѕРІ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РёРІРЅРѕРіРѕ РёРЅС‚РµСЂС„РµР№СЃР° Рё РїСЂРѕРІРµСЂРєРё, С‡С‚Рѕ
    # РїР°РєРµС‚ РЅРµ РєРѕРЅС„Р»РёРєС‚СѓРµС‚ СЃ С‚РёРїРѕРІС‹Рј Django-РїСЂРѕРµРєС‚РѕРј.
    path("admin/", admin.site.urls),
    path("admin-152fz/", get_optional_admin_site().urls),
    # РљРѕСЂРЅРµРІРѕР№ include РѕС‚РґР°С‘С‚ СѓРїСЂР°РІР»РµРЅРёРµ СЃР°РјРѕРјСѓ РїР°РєРµС‚Сѓ.
    path("", include("django_consent_152fz.urls")),
    path("", include("django_cookies_152fz.urls")),
]


