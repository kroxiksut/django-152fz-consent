# Модуль cookie: конфигурация

- [К разделу cookie](./README.md)
- [К общему разделу документации](../README.md)

## Где задаётся конфигурация

Конфигурация cookie-модуля задаётся в `settings.py` в словаре `DJANGO_152FZ_COOKIES`.

```python
DJANGO_152FZ_COOKIES = {
    "enable_cookies": True,
    "default_cookie_category_codes": ["necessary"],
    "cookie_banner": {...},
    "cookie_runtime": {...},
    "cookie_retention": {...},
}
```

## Корневые ключи

### `enable_cookies`

- Тип: `bool`
- Назначение: глобальное включение cookie-потока.
- По умолчанию: `True`

### `default_cookie_category_codes`

- Тип: `list[str]`
- Назначение: коды обязательных категорий по умолчанию.
- По умолчанию: `["necessary"]`

## Раздел `cookie_banner`

Раздел определяет базовые параметры баннера и страницы настроек.

```python
"cookie_banner": {
    "bootstrap_initial_revision": True,
    "preferences_page_template": "django_cookies_152fz/cookie_preferences.html",
    "banner_variant": "card",
    "consent_ui_variant": "panel",
    "reconsent_notice_variant": "inline",
    "text_preset": "ru_balanced",
}
```

Ключи:
- `bootstrap_initial_revision`: автоматически создавать стартовую редакцию баннера.
- `preferences_page_template`: путь к шаблону страницы `/cookies/`.
- `banner_variant`: вариант баннера (`bar`, `card`, `modal`).
- `consent_ui_variant`: вариант интерфейса выбора (`inline`, `panel`).
- `reconsent_notice_variant`: вариант уведомления о повторном согласии (`inline`, `alert`).
- `text_preset`: код текстового пресета (`ru_balanced`, `ru_formal`, `ru_compact`).

## Раздел `cookie_runtime`

Раздел определяет поведение баннера в запросе и окружении.

```python
"cookie_runtime": {
    "force_banner": False,
    "preview_param": "cookie_banner_preview",
    "custom_css_url": "",
    "custom_js_url": "",
    "hide_for_bots": True,
    "bot_patterns": [],
    "user_agent_mode": "all",
    "shared_subdomain": False,
    "site_domain": "",
    "cookie_domain": "",
    "geo_signal_hook": "",
}
```

Ключи:
- `force_banner`: принудительно показывать баннер.
- `preview_param`: имя параметра URL для режима предпросмотра.
- `custom_css_url`: дополнительный путь к пользовательским стилям.
- `custom_js_url`: дополнительный путь к пользовательскому сценарию.
- `hide_for_bots`: скрывать баннер для роботов.
- `bot_patterns`: пользовательские шаблоны распознавания роботов.
- `user_agent_mode`: режим обработки пользовательского агента (`off`, `all`, `unique`).
- `shared_subdomain`: включить общий режим для поддоменов.
- `site_domain`: домен сайта для проверок безопасного возврата.
- `cookie_domain`: домен установки cookie анонимного токена.
- `geo_signal_hook`: путь к вызываемому объекту геосигнала.

## Раздел `cookie_retention`

Раздел определяет правила очистки аудита и ограничений объёма.

```python
"cookie_retention": {
    "batch_size": 500,
    "records_older_than_days": None,
    "events_older_than_days": None,
    "banner_states_older_than_days": None,
    "records_max_count": None,
    "events_max_count": None,
    "banner_states_max_count": None,
    "private_records_older_than_days": None,
    "private_events_older_than_days": None,
    "private_signal_paths": [],
    "protect_current_records": True,
}
```

Ключи:
- `batch_size`: размер порции удаления.
- `records_older_than_days`: срок хранения для записей согласий.
- `events_older_than_days`: срок хранения для событий согласий.
- `banner_states_older_than_days`: срок хранения для состояний баннера.
- `records_max_count`: предельное число записей согласий.
- `events_max_count`: предельное число событий согласий.
- `banner_states_max_count`: предельное число состояний баннера.
- `private_records_older_than_days`: отдельный срок для приватных записей.
- `private_events_older_than_days`: отдельный срок для приватных событий.
- `private_signal_paths`: пути приватных источников событий.
- `protect_current_records`: защита актуальных записей от удаления.

## Что настраивается в административной панели, а что в `settings.py`

В административной панели:
- категории cookie;
- реестр интеграций;
- редакции политики cookie;
- редакции баннера cookie;
- текстовые пресеты;
- разделитель CSV-экспорта.

В `settings.py`:
- техническое поведение показа;
- доменные параметры и режимы обработки;
- правила очистки аудита;
- подключение пользовательских файлов стилей и сценариев.

## Профиль конфигурации из демо-сайта

В демо-сайте для публичного контура использовался следующий рабочий профиль:

```python
DJANGO_152FZ_COOKIES = {
    "enable_cookies": True,
    "cookie_banner": {
        "bootstrap_initial_revision": True,
        "banner_variant": "card",
        "consent_ui_variant": "panel",
        "text_preset": "ru_balanced",
        "show_launcher": True,
        "show_preferences_link": False,
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
```

Этот профиль показал предсказуемое поведение:
- баннер доступен на всех страницах через кнопку повторного открытия;
- интерфейс не перегружен отдельной ссылкой в верхнем меню;
- роботам не показывается визуальный слой баннера;
- есть ручной параметр предпросмотра для проверки отображения.

Подробнее по разделам административной панели: [Использование, меню админки и настройка](./operations-admin.md).

### CSV delimiter for event export

`csv_export_delimiter` in `CookieAdminSettings` controls the separator for `CookieConsentEvent` admin CSV export.

Allowed values: `,`, `;`, `\t`, `|`.
Invalid values fall back to `,`.

