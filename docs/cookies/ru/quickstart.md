# Модуль куки: быстрый старт

- [К разделу cookie](./README.md)
- [К общему разделу документации](../README.md)

Это руководство проводит `django-cookies-152fz` от чистой установки до
отрисованного баннера куки, учитывающего согласие. Полный справочник настроек —
в [configuration.md](./configuration.md); тексты и визуальные варианты — в
[presentation.md](./presentation.md).

Пакет намеренно автономен: не импортирует слой согласий и работает без
`django-consent-152fz`.

> Пакет распространяется «как есть». Рабочий баннер сам по себе не делает проект
> соответствующим 152-ФЗ — юридическую корректность текста политики и
> инвентаризации cookie обеспечивает оператор.

## 1. Установка

```bash
pip install django-cookies-152fz
```

Необязательная интеграция с пакетом согласий:

```bash
pip install "django-cookies-152fz[consent]"   # подключает django-consent-152fz
```

Совместимость: Python 3.10–3.14, Django 5.0 / 5.1 / 5.2 / 6.0 (`Django>=5,<7`).
Для Python 3.14 требуется Django 5.2.8+ или Django 6.x.

## 2. Включение приложения

```python
INSTALLED_APPS = [
    # ...
    "django_cookies_152fz",
]
```

## 3. Конфигурация

Настраивается через словарь `DJANGO_COOKIES_152FZ`. Минимальный рабочий профиль:

```python
DJANGO_COOKIES_152FZ = {
    "enable_cookies": True,
    "cookie_banner": {
        "bootstrap_initial_revision": True,
        "banner_variant": "card",        # bar | card | modal
        "consent_ui_variant": "panel",   # inline | panel
        "text_preset": "ru_balanced",    # ru_balanced | ru_formal | ru_compact
    },
}
```

Ключи баннера, представления и runtime (домены, обработка ботов, очистка аудита)
описаны в [configuration.md](./configuration.md). Категории cookie, реестр
интеграций и редакции политики/баннера ведутся в админке Django.

## 4. Подключение URL

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    path(
        "cookies/",
        include(
            ("django_cookies_152fz.urls", "django_cookies_152fz"),
            namespace="django_cookies_152fz",
        ),
    ),
]
```

Это открывает страницу настроек по адресу `/cookies/`.

## 5. Миграции

```bash
python manage.py migrate
```

При `bootstrap_initial_revision: True` начальная редакция баннера заполняется на
`post_migrate`. (Также доступна management-команда
`bootstrap_152fz_cookie_defaults`.)

## 6. Отрисовка баннера

Загрузите библиотеку тегов и один раз отрисуйте баннер в базовом шаблоне, прямо
перед `</body>`:

```django
{% load cookies_tags %}
...
{% render_cookie_banner %}
</body>
```

Runtime запускает необязательные скрипты только при наличии соответствующего
согласия. Контракт DOM-событий и серверного слоя — см.
[contracts.md](./contracts.md).

## Дальше

- [Настройки жизненного цикла и серверного слоя](./configuration.md)
- [Версионируемые тексты и оформление](./presentation.md)
- [Использование, меню админки и настройка](./operations-admin.md)
- [Контракт событий DOM и серверных перехватов](./contracts.md)
- [Рекомендательная инвентаризация и ограничения](./inventory.md)
- [Ключевые инварианты](./invariants.md)
- [Демо-стенды](./demo.md)
