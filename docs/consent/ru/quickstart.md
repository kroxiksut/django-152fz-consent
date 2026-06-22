# Модуль согласий: быстрый старт

- [К разделу модуля согласий](./README.md)
- [К общему разделу документации](../README.md)

Это руководство проводит `django-consent-152fz` от чистой установки до рабочего
потока согласий с самообслуживанием субъекта. Полный контракт настроек — в
[configuration.md](./configuration.md); создание документов и текстов — в
[authoring.md](./authoring.md).

> Пакет распространяется «как есть». Рабочая установка сама по себе не делает
> проект соответствующим 152-ФЗ — юридическую корректность текстов, документов и
> процессов обработки обеспечивает оператор.

## 1. Установка

```bash
pip install django-consent-152fz
```

Необязательные extra (ставьте только нужное):

```bash
pip install "django-consent-152fz[api]"   # эндпойнты DRF API
pip install "django-consent-152fz[pdf]"   # PDF для контура бумажных согласий (ReportLab)
```

Ядро зависит только от Django (`Django>=5,<7`, Python 3.10–3.14). DRF и ReportLab
подключаются только через extra выше.
Для Python 3.14 требуется Django 5.2.8+ или Django 6.x.

## 2. Включение приложений

Необязательные возможности включаются **добавлением их Django-приложения** в
`INSTALLED_APPS`, а не просто флагом:

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",                      # ядро (всегда)
    "django_consent_152fz.api",                  # опционально: DRF API
    "django_consent_152fz.verified_consents",    # опционально: контур подтверждённых/бумажных согласий
]
```

Для минимальной установки достаточно одного `"django_consent_152fz"`.

## 3. Конфигурация

Всё поведение настраивается через единый проверяемый контракт. Некорректная
конфигурация рано вызывает `ConsentConfigurationError`.

```python
DJANGO_CONSENT_152FZ = {
    "enable_core": True,
    "sample_documents": {
        # "command" -> загрузить примеры документов management-командой (ниже);
        # "auto"    -> заполнить их на post_migrate.
        "load_mode": "command",
    },
    "subject_consents": {
        "open_mode": "page",
        "allow_anonymous_withdraw": True,
    },
}

# API монтируется, только если установлено приложение api и импортируется DRF.
USE_API_152FZ = True
```

Коды (целей / документов / полей) должны соответствовать `^[a-z][a-z0-9_]*$`.
Цели, реестр полей ПДн, контракты политик и контекст аудита — см.
[configuration.md](./configuration.md).

## 4. Подключение URL

Шаблонный UI монтируется независимо от API; API подмешивается только когда
приложение API установлено **и** импортируется DRF.

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    path(
        "",
        include(
            ("django_consent_152fz.urls", "django_consent_152fz"),
            namespace="django_consent_152fz",
        ),
    ),
]
```

Это открывает, среди прочего:

- `consent/documents/<purpose_code>/<document_code>/` — карточка документа
- `consent/accept/<purpose_code>/<document_code>/` — выдача согласия
- `consent/withdraw/<purpose_code>/<document_code>/` — отзыв
- `consent/self-service/` — самообслуживание субъекта

## 5. Миграции и стартовые данные

```bash
python manage.py migrate
python manage.py bootstrap_152fz_sample_documents   # только при load_mode = "command"
```

При `load_mode: "auto"` примеры документов и стартовые цели заполняются на
`post_migrate`, и команду можно пропустить.

## 6. Сервисный фасад

Внешние интеграции должны вызывать стабильный фасад, а не импортировать
`core.services` напрямую:

```python
from django_consent_152fz import service_api
```

Изменение его сигнатур — это изменение контракта, см.
[service-api.md](./service-api.md).

## Дальше

- [Конфигурация и контракт политик](./configuration.md)
- [Создание и наполнение согласий](./authoring.md)
- [Сценарии самообслуживания субъекта](./self-service.md)
- [Публичный сервисный API и транспортный контракт](./service-api.md)
- [Контур подтверждённых / бумажных согласий](./verified-flow.md)
- [Ключевые инварианты жизненного цикла согласий](./invariants.md)
- [Демо-стенды](./demo.md)
