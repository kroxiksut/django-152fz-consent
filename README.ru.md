<p align="center">
  <img src="docs/assets/logo/dj-152fz-logo.png" alt="django-152fz" width="220">
</p>

<h1 align="center">django-152fz</h1>

<p align="center">
  <img alt="Пакет consent" src="https://img.shields.io/badge/django--152fz--consent-0.1.0-blue">
  <img alt="Пакет cookies" src="https://img.shields.io/badge/django--152fz--cookies-0.1.0-blue">
  <img alt="Статус проекта" src="https://img.shields.io/badge/status-alpha-orange">
  <img alt="Версии Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="Версии Django" src="https://img.shields.io/badge/django-5.x%20%7C%206.x-0C4B33">
  <img alt="Тесты" src="https://img.shields.io/badge/tests-pytest-0A9EDC">
  <img alt="Лицензия" src="https://img.shields.io/badge/license-MIT-green">
</p>

`django-152fz` - набор Django-пакетов для проектов, которым нужен серверный контур согласий в контексте 152-ФЗ и отдельный cookie-слой с баннером, реестром и runtime-логикой, завязанной на согласие.

Репозиторий разделён на два устанавливаемых пакета:

- `django-consent-152fz` - жизненный цикл согласий, документы, аудит, self-service субъекта, политики доступа, service API;
- `django-cookies-152fz` - cookie-баннер, категории cookie, редакции политик, реестр runtime-элементов, аудит cookie и сценарии `cookies-only`.

Основные ссылки:

- [Документация на английском](./docs/README.md)
- [Документация на русском](./docs/README.ru.md)
- [English README](./README.md)
- [AI-friendly гайды по интеграции (только на английском)](./docs/consent/ai/README.md)

## Область пакетов

### `django-consent-152fz`

Пакет согласий покрывает:

- `ConsentPurpose`, `LegalDocument`, `DocumentRevision`, `ConsentRecord`, `ConsentEvent`;
- выдачу, отзыв, проверку статуса и re-consent по цепочке `purpose + document`;
- неизменяемый аудит событий;
- анонимные и авторизованные сценарии;
- self-service субъекта;
- опциональный контракт `verified_consents`;
- опциональные политики доступа;
- публичный Python-фасад `django_consent_152fz.service_api`.

### `django-cookies-152fz`

Cookie-пакет покрывает:

- `CookieCategory`, `CookiePolicyRevision`, `CookieBannerRevision`;
- отдельный cookie-баннер и страницу пользовательских настроек;
- сценарий `cookies-only` без обязательной установки consent-пакета;
- хранение cookie-решений и cookie-аудит;
- реестр cookie и script-интеграций;
- строгий запрет по умолчанию для необязательных скриптов;
- правила очистки и хранения;
- анонимный и авторизованный сценарии.

### Как они работают вместе

В полном сценарии:

- consent-пакет владеет жизненным циклом согласий;
- cookie-пакет владеет cookie-доменом, UI баннера и runtime-слоем;
- `django_consent_152fz.urls` подключает UI согласий и маршруты cookie-пакета под общим префиксом `consent/`;
- внешние интеграции должны использовать cookie-функции через service layer, а не напрямую через внутренние модели.

## Поддерживаемые сценарии

Текущая схема поставки поддерживает три режима:

1. `consent-only`
   Установлен только `django-consent-152fz`.
2. `cookies-only`
   Установлен только `django-cookies-152fz`.
3. `full`
   Установлены оба пакета, и они работают совместно.

Это соответствует новой структуре документации в `docs/consent/*` и `docs/cookies/*`.

## Установка

### Только consent

```bash
pip install django-consent-152fz
```

### Только cookies

```bash
pip install django-cookies-152fz
```

### Полный сценарий

```bash
pip install django-consent-152fz django-cookies-152fz
```

### Если нужен API

```bash
pip install "django-consent-152fz[api]"
```

### Дополнительный extra

```bash
pip install "django-consent-152fz[cookies]"
```

Этот extra подтягивает cookie-пакет как зависимость для consent-first проектов.

## Быстрый старт

### Только consent

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",
]

DJANGO_152FZ_CONSENT = {
    "enable_core": True,
    "enable_access_policies": False,
    "enable_verified_consents": False,
}

USE_API_152FZ = False
```

```python
from django.urls import include, path

urlpatterns = [
    path("", include("django_consent_152fz.urls")),
]
```

### Только cookies

```python
INSTALLED_APPS = [
    # ...
    "django_cookies_152fz",
]

DJANGO_152FZ_COOKIES = {
    "enable_cookies": True,
}
```

```python
from django.urls import include, path

urlpatterns = [
    path("", include("django_cookies_152fz.urls")),
]
```

### Полный сценарий: consent + cookies

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",
    "django_cookies_152fz",
]

DJANGO_152FZ_CONSENT = {
    "enable_core": True,
    "enable_access_policies": False,
    "enable_verified_consents": False,
}

DJANGO_152FZ_COOKIES = {
    "enable_cookies": True,
}

USE_API_152FZ = False
```

```python
from django.urls import include, path

urlpatterns = [
    path("", include("django_consent_152fz.urls")),
]
```

## Примечания

- Проект ориентирован на российский правовой контекст, но не заменяет юридическую проверку.
- Тексты, категории и шаблоны - стартовые образцы, их нужно адаптировать под конкретную установку.
- Актуальная документация разделена по языкам:
  - [English docs](./docs/README.md)
  - [Русская документация](./docs/README.ru.md)
