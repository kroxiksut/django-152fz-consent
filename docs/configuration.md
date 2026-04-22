# configuration — настройки banner-layer и интеграции

**Версия документа:** `0.1`
**Обновлено:** `2026-04-17`
**Статус:** `settings contract для этапов 7.1–7.7 и дополнительного блока 7.5 (варианты и наборы текстов) реализован`

## Назначение

Документ фиксирует:
- какой settings contract уже реализован для cookie banner lifecycle и runtime-слоя;
- какой DB-backed contract уже реализован для текстов и presentation баннера;
- какие части конфигурации ещё остаются следующими этапами;
- какие инварианты нужно сохранять при дальнейшем развитии конфигурации.

## Принципы

- banner-layer должен быть пригоден для обычного Django template-проекта;
- обязательная внешняя JavaScript-библиотека не добавляется;
- shared-subdomain режим не включается автоматически;
- скрытие баннера для ботов остаётся явной настраиваемой опцией;
- bot-detection считается best-effort эвристикой, а не security-гарантией;
- advisory geo signal не считается legal-engine;
- исполняемый JavaScript не хранится в БД как основной способ конфигурации;
- вендорные адаптеры не считаются частью минимального обязательного объёма.

## Что уже зафиксировано в коде

### 0. Bootstrap коробочных sample-документов

```python
DJANGO_152FZ_CONSENT = {
    "sample_documents": {
        "load_mode": "command",  # "command" | "auto" | "disabled"
    },
}
```

Поведение:
- `command` является консервативным режимом по умолчанию и не пишет в БД ничего сам;
- `auto` включает post-migrate bootstrap curated starter templates;
- `disabled` отключает bootstrap как штатный режим, а management command без `--force` отдаёт понятную ошибку;
- sample-документы создаются как неактивные `LegalDocument` / `DocumentRevision` с `is_box_template=True`;
- sample-документы не публикуются через live flow и не переводят существующие consent records в `outdated`;
- тексты всегда помечаются как стартовые образцы, требующие юридической проверки и адаптации.

### 1. Жизненный цикл баннера

```python
DJANGO_152FZ_CONSENT = {
    "cookie_banner": {
        "reask_after_days": 30,
        # или:
        # "reask_after_months": 6,
        "banner_variant": "card",  # "bar" | "card" | "modal"
        "consent_ui_variant": "panel",  # "inline" | "panel"
        "reconsent_notice_variant": "inline",  # "inline" | "alert"
        "text_preset": "ru_balanced",  # "ru_balanced" | "ru_formal" | "ru_compact"
        "bootstrap_initial_revision": True,
    },
}
```

Поведение:
- можно задать только один из ключей: `reask_after_days` или `reask_after_months`;
- `0` отключает периодический повторный запрос;
- re-ask влияет только на повторный показ banner-layer;
- `outdated` при публикации новой policy revision остаётся отдельным сценарием;
- `dismissed_at` и `decided_at` хранятся в отдельном `CookieBannerState`, а не внутри cookie-consent record;
- визуальные варианты и наборы текстов выбираются независимо;
- при `bootstrap_initial_revision=True` post-migrate bootstrap может создать стартовую `CookieBannerRevision` как `is_box_template=True`.

### 2. Runtime-слой баннера

```python
DJANGO_152FZ_CONSENT = {
    "cookie_runtime": {
        "force_banner": False,
        "preview_param": "cookie_banner_preview",
        "custom_css_url": "/static/project/cookies.css",
        "custom_js_url": "/static/project/cookies.js",
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
        "user_agent_mode": "all",  # "off" | "all" | "unique"
        "shared_subdomain": False,
        "site_domain": "",
        "cookie_domain": "",
        "geo_signal_hook": "",
    },
}
```

Поведение:
- `force_banner=True` принудительно открывает баннер независимо от текущего сохранённого решения;
- `preview_param` задаёт query param для ручной проверки banner flow;
- `custom_css_url` и `custom_js_url` подключаются как дополнительные ассеты поверх baseline-слоя;
- `hide_for_bots=True` скрывает баннер в template flow для bot-request;
- `bot_patterns` задают project-specific подписи bot user-agent;
- `user_agent_mode` принимает только `off`, `all`, `unique`;
- `shared_subdomain=True` требует непустой `cookie_domain`;
- `site_domain` и `cookie_domain` валидируются как host/domain без схемы, пути и порта;
- `geo_signal_hook` принимает importable callable или сам callable;
- эти настройки не меняют источник истины для согласия: решение по-прежнему читается из серверной БД.

### 3. Поведение режимов `user_agent_mode`

- `all` сохраняет raw user-agent в записи согласия и в событии.
- `off` очищает raw user-agent перед записью в согласие и событие.
- `unique` очищает raw user-agent и вместо него пишет в `extra_meta.cookie_runtime` только `user_agent_sha256`.

Отдельная статистическая сущность для user-agent и bot-метрик не добавляется. Канонический контекст остаётся внутри существующих consent records и events.

### 4. Domain и shared-subdomain contract

Реализованный contract:
- `site_domain` используется для канонической генерации ссылки на страницу настроек cookie;
- `get_cookie_runtime_allowed_hosts()` добавляет `site_domain` в allowlist безопасных redirect;
- `cookie_domain` используется при выставлении анонимного cookie, чтобы состояние могло жить на общем домене поддоменов;
- shared-subdomain режим остаётся opt-in и не обещает синхронизацию между разными сайтами или инсталляциями.

### 5. Advisory geo signal

Реализованный contract:
- `geo_signal_hook` вызывается как hook проекта и получает `request=...`;
- результат нормализуется к `ru`, `non_ru` или `unknown`;
- при ошибке hook возвращается `unknown`;
- startup check валидирует import string и отдаёт понятную конфигурационную ошибку.

### 6. DB-backed тексты и presentation баннера

Отдельный settings API для текстов не добавлялся.

Канонический источник этих данных:
- `CookieBannerRevision` хранит тексты, подписи кнопок и presentation-параметры баннера;
- активной считается только одна опубликованная revision;
- публикация `CookieBannerRevision` не помечает cookie-consent как `outdated`;
- публикация новой `CookiePolicyRevision` не переписывает banner texts/settings;
- при отсутствии DB-backed revision шаблон использует встроенный fallback с baseline-значениями.

Канонические поля вариантов:
- `banner_variant`: `bar` | `card` | `modal`;
- `consent_ui_variant`: `inline` | `panel`;
- `reconsent_notice_variant`: `inline` | `alert`;
- `text_preset_code`: `ru_balanced` | `ru_formal` | `ru_compact`.

Текущие legacy-поля presentation (для обратной совместимости):
- `layout_variant`: `compact` или `wide`;
- `theme_variant`: `light` или `contrast`;
- `desktop_position`: `bottom_right` или `bottom_left`;
- `mobile_position`: `bottom` или `top`.

Зафиксированный template/CSS контракт слоя вариантов:
- `data-cookie-banner-contract-version`;
- `data-cookie-banner-variant`;
- `data-cookie-banner-consent-ui`;
- `data-cookie-banner-reconsent-variant`;
- `data-cookie-banner-text-preset`.

## Что уже доступно без отдельного settings API

Текущая реализация уже даёт:
- reusable template tag `{% render_cookie_banner %}`;
- launcher `Cookie settings`;
- quick actions `accept all`, `required only`, `custom selection`, `dismiss`;
- внешние static assets `cookie_banner.css` и `cookie_banner.js`;
- runtime JSON-представление для client-side loader;
- re-ask lifecycle поверх server-side `CookieBannerState`;
- attach anonymous cookie-consent и banner-state к `user` после логина;
- DB-backed `CookieRegistryItem` и published snapshot `CookiePolicyRevisionRegistryItem` для disclosure и runtime metadata;
- DB-backed `CookieBannerRevision` для versioned plain-text текстов и presentation баннера.

## Что уже реализовано в runtime contract

Для cookie runtime уже доступны:
- отдельная live-модель registry items, не смешанная с `CookieCategory`;
- published snapshot registry items на уровне `CookiePolicyRevision`;
- metadata поля `provider`, `purpose`, `retention`, `cookie_names`, `src_url`, `clear_strategy`;
- `runtime`-блок в `get_cookie_requirements()` и cookie API;
- `runtime.event_contract` как канонический JSON-контракт DOM-событий;
- `runtime.consent_allows_runtime=True` только при статусе `current`;
- strict default-deny до принятия решения и повторный deny при статусе `outdated`;
- best-effort cleanup first-party cookies и удаление управляемых loader script tags;
- запрет на хранение raw executable JS в `src_url` и в canonical runtime contract;
- поля request-контекста `hide_for_bots`, `is_bot_request`, `bot_pattern`, `user_agent_collection_mode`, `shared_subdomain`, `site_domain`, `cookie_domain`, `geo_signal`;
- backend hook API `set_cookie_runtime_event_hook(...)` / `trigger_cookie_runtime_event(payload)` для внешних интеграций.

## Что зафиксировано на этапе 7.7

На стороне конфигурационного контракта закреплено:
- имена frontend DOM-событий публикуются сервером в `runtime.event_contract.events`;
- payload этих событий версионируется через `runtime.event_contract.version`;
- backend hook payload имеет версию `contract_version = "1.0"` и стабильные блоки `subject`, `consent`, `banner`, `audit`.

Готовые vendor adapters под GTM / Google Consent Mode / Яндекс Метрику по-прежнему остаются за пределами базового пакета и относятся к future TODO.


## Дополнительные cookie-banner настройки entry points

```python
DJANGO_152FZ_CONSENT = {
    "cookie_banner": {
        "show_launcher": True,
        "show_preferences_link": True,
        "preferences_page_template": "",
    },
}
```

- `show_launcher` управляет постоянной кнопкой повторного открытия banner.
- `show_preferences_link` управляет дополнительной ссылкой в footer banner.
- `preferences_page_template` позволяет рендерить страницу
  `django_152fz_consent:cookie_preferences` в проектном шаблоне сайта
  (с основным меню/шапкой и т.д.); при пустом значении используется
  коробочный standalone template.
- Для переиспользования стандартного содержимого страницы в проектном шаблоне
  можно подключить include:
  `django_152fz_consent/includes/cookie_preferences_content.html`.
- Конфликтная комбинация `False/False` валидируется Django system check
  (`django_152fz_consent.E020`).

## Cookie-only bootstrap

```bash
python manage.py bootstrap_152fz_cookie_defaults
```

Команда выполняет первичную инициализацию cookie-only контура:
- коробочные cookie categories;
- стартовую active `CookiePolicyRevision` (idempotent);
- стартовую active `CookieBannerRevision` (idempotent).
