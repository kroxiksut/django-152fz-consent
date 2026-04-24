# Quickstart

**Версия документа:** `0.1`
**Обновлено:** `2026-04-17`

## 1. Установка

Только ядро:

```bash
pip install django-152fz-consent
```

Ядро + API:

```bash
pip install django-152fz-consent[api]
```

## 2. Минимальное подключение

```python
INSTALLED_APPS = [
    # ...
    "django_152fz_consent",
    "django_152fz_consent.cookies",
]

USE_API_152FZ = False
```

## 3. Миграции

```bash
python manage.py migrate
```

## 4. (Опционально) Стартовые sample-документы

```bash
python manage.py bootstrap_152fz_sample_documents
```

Bootstrap создаёт неактивные редактируемые шаблоны: политику обработки
персональных данных, согласие для web-формы, согласие для обратной связи,
согласие для регистрации и согласие для рассылок. Дата публикации коробочной
редакции заполняется сразу, но live-публикацию и юридическую адаптацию текста
оператор выполняет самостоятельно.

## 5. Подключение URL

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("", include("django_152fz_consent.urls")),
]
```

## 6. Базовый cookie banner в шаблоне

```django
{% load consent_tags %}
...
{% render_cookie_banner %}
```

## 7. Включение optional API

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "django_152fz_consent",
    "django_152fz_consent.cookies",
    "django_152fz_consent.api",
]

USE_API_152FZ = True
```

Если `USE_API_152FZ=True` без установленного DRF, пакет должен выдавать понятную конфигурационную ошибку.

## 8. Куда идти дальше

- Подробные настройки: `docs/configuration.md`
- Cookie-модуль и banner-layer: `docs/cookies.md`
- Публичный service API и router contract: `docs/api.md`
- Experimental verified-flow: `docs/experimental.md`
