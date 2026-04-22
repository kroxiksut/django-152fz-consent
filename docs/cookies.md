# cookies — текущее состояние cookie-модуля и слоя баннера

**Версия документа:** `0.1`
**Обновлено:** `2026-04-17`
**Статус:** `этапы 7.1–7.7 реализованы, включая дополнительный блок 7.5 (варианты и наборы текстов)`

## Назначение

Документ фиксирует:
- что уже реализовано в cookie-модуле;
- какие инварианты нельзя терять при развитии баннера и runtime-слоя;
- какие точки расширения ещё остаются следующими этапами.

## Что уже есть в коде

На текущем этапе cookie-модуль уже включает:
- категории cookie;
- версии политики cookie;
- рабочие записи реестра `CookieRegistryItem`;
- опубликованные снимки реестра `CookiePolicyRevisionRegistryItem`;
- хранение пользовательских решений и историю cookie-событий;
- отдельное серверное хранилище состояния показа `CookieBannerState`;
- отдельные опубликованные редакции текстов и presentation-настроек `CookieBannerRevision`;
- страницу настройки cookie;
- общий cookie-баннер для всего сайта через шаблонный тег;
- быстрые действия `accept all`, `required only`, `custom selection`, `dismiss`;
- постоянную кнопку `Cookie settings`;
- резервный сценарий без JavaScript через серверную форму баннера и отдельную страницу настроек;
- нижнее размещение баннера по умолчанию на узких экранах;
- изменение ранее выбранного решения;
- политику повторного запроса `ask again after N days/months`;
- отдельный режим `cookies_only`;
- анонимный сценарий через серверный токен и cookie;
- привязку анонимного согласия по cookie и состояния баннера к `user` после логина в шаблонном интерфейсе и API;
- отдельный `runtime`-блок в `get_cookie_requirements()` и cookie API;
- строгое поведение «по умолчанию запрещено» для необязательных скриптов до актуального согласия;
- попытку очистки собственных cookie сайта при отключении ранее разрешённой категории;
- режим предварительного показа с принудительным открытием баннера;
- подключение `custom_css_url` и `custom_js_url` поверх базового слоя;
- скрытие баннера для bot-request по настраиваемым шаблонам user-agent;
- режимы хранения user-agent `off`, `all`, `unique`;
- opt-in режим общих поддоменов через `site_domain` и `cookie_domain`;
- advisory geo signal `ru`, `non_ru`, `unknown` через project hook.

## Что добавлено на этапе 7.7

На этапе `7.7` зафиксированы:
- единый frontend contract DOM-событий для banner/runtime слоя;
- сериализуемый payload contract этих событий;
- backend hook/extension point для внешних интеграций;
- явная граница, что готовые vendor adapters остаются отдельным future TODO.

## Как использовать баннер

Минимальная интеграция:

```django
{% load consent_tags %}
...
{% render_cookie_banner %}
```

Что делает этот тег:
- рендерит панель и кнопку повторного открытия поверх обычного Django template UI;
- использует отдельный маршрут `django_152fz_consent:cookie_banner_action` для быстрых действий;
- не смешивает `dismiss/collapse` с фактом сохранённого согласия;
- хранит `dismissed_at` и `decided_at` в отдельном `CookieBannerState`;
- может повторно показать баннер по политике повторного запроса без искусственного `outdated`;
- сохраняет согласие по cookie через тот же серверный сервисный слой и БД, что и полная страница настроек;
- оставляет страницу `django_152fz_consent:cookie_preferences` как серверный резервный сценарий;
- читает каноническую конфигурацию текстов и presentation через опубликованную `CookieBannerRevision`;
- встраивает JSON-представление `runtime` для клиентского загрузчика;
- при наличии настроек подключает project-specific CSS/JS поверх базовых `cookie_banner.css` и `cookie_banner.js`;
- понимает preview query param и глобальный `force_banner`;
- при настроенном `site_domain` строит каноническую ссылку на страницу настроек cookie;
- по умолчанию скрывает баннер для bot-request, но сохраняет preview и forced-flow для ручной проверки.

## Ключевые инварианты

### Состояние баннера не равно состоянию согласия

Нельзя смешивать:
- факт показа баннера;
- его сворачивание;
- факт сохранённого согласия по cookie.

`dismissed_at` и `decided_at` живут в отдельном состоянии баннера, а `dismiss` не считается согласием.

### Серверная БД — источник истины

Для согласия по cookie источником истины остаётся серверная БД:
- авторизованный пользователь хранится по `user`;
- анонимный сценарий хранится через запись в БД и `anonymous_token`;
- после логина анонимное согласие по cookie и состояние баннера автоматически привязываются к пользователю.

### Повторный запрос не равен `outdated`

Новая редакция политики cookie по-прежнему переводит старое решение в `outdated`.

Отдельная политика повторного запроса `ask again after N days/months`:
- не меняет статус согласия сама по себе;
- управляет только повторным показом баннера;
- позволяет повторно подтвердить тот же выбор без создания искусственного состояния `outdated`.

### Тексты баннера не равны policy revision

Редакция текстов и presentation баннера живёт отдельно от `CookiePolicyRevision`.

Инварианты:
- публикация `CookieBannerRevision` не переводит cookie-consent в `outdated`;
- публикация новой `CookiePolicyRevision` не переписывает тексты баннера;
- banner-layer читает только одну активную published revision текстов и presentation;
- при отсутствии DB-редакции используется встроенный fallback по умолчанию.

### Реестр cookie и скриптов

Текущая реализация уже добавляет отдельный слой реестра:
- рабочие метаданные хранятся в `CookieRegistryItem`;
- опубликованный снимок раскрываемых данных хранится в `CookiePolicyRevisionRegistryItem`;
- метаданные включают `provider`, `purpose`, `retention`, `cookie_names`, `src_url`, `clear_strategy`;
- записи реестра привязываются к `CookieCategory` и к опубликованной `CookiePolicyRevision`;
- `get_cookie_requirements()` и cookie API возвращают `registry_items` как дополнительную часть ответа;
- тот же payload включает `runtime` с полями `strict_default_deny`, `consent_allows_runtime`, `allowed_categories`, `script_items`, `cleanup_items`, `event_contract`.

Ограничения:
- в БД не хранится произвольный исполняемый JavaScript как основной исполняемый код;
- `src_url` хранит только URL или путь к загрузчику;
- фактический код интеграции вендора должен лежать в static-файлах проекта или в другом контролируемом источнике.

### Необязательные скрипты по умолчанию запрещены

До получения согласия необязательные аналитические, маркетинговые и рекламные скрипты не должны загружаться.

Текущая реализация:
- клиентский загрузчик активирует `runtime.script_items` только при `runtime.consent_allows_runtime=True`;
- состояние `outdated` снова переводит runtime в deny по умолчанию, даже если в прошлом выбор уже был;
- при отключении категории фронтенд пытается очистить перечисленные `cookie_names` и удаляет управляемые `script`-теги, которые сам добавил.

### Bot handling, домены и geo signal — это operational helpers

Текущие правила:
- `hide_for_bots=True` остаётся значением по умолчанию;
- `bot_patterns` применяются как best-effort substring-эвристика по user-agent;
- `user_agent_mode="all"` сохраняет raw user-agent в записи и событиях;
- `user_agent_mode="off"` не сохраняет raw user-agent;
- `user_agent_mode="unique"` не сохраняет raw user-agent и фиксирует только `user_agent_sha256` в `extra_meta.cookie_runtime`;
- отдельная сущность для bot/user-agent статистики не добавляется;
- `shared_subdomain=True` всегда остаётся явным opt-in режимом;
- `site_domain` используется для канонических ссылок и redirect allowlist;
- `cookie_domain` используется для выставления анонимного cookie на общий домен;
- `geo_signal_hook` возвращает только advisory сигнал `ru`, `non_ru` или `unknown`.

## Конфигурация жизненного цикла

Минимальный конфиг жизненного цикла:

```python
DJANGO_152FZ_CONSENT = {
    "cookie_banner": {
        "reask_after_days": 30,
        # или:
        # "reask_after_months": 6,
    },
}
```

Правила:
- можно задать только один из ключей: `reask_after_days` или `reask_after_months`;
- значение `0` отключает периодический повторный запрос;
- `outdated` при публикации новой policy revision остаётся отдельным сценарием и не зависит от этого интервала.

## Конфигурация runtime-слоя

Минимальный конфиг runtime-слоя:

```python
DJANGO_152FZ_CONSENT = {
    "cookie_runtime": {
        "force_banner": False,
        "preview_param": "cookie_banner_preview",
        "custom_css_url": "/static/project/cookies.css",
        "custom_js_url": "/static/project/cookies.js",
        "hide_for_bots": True,
        "bot_patterns": ["googlebot", "yandexbot", "bot"],
        "user_agent_mode": "all",  # "off" | "all" | "unique"
        "shared_subdomain": False,
        "site_domain": "",
        "cookie_domain": "",
        "geo_signal_hook": "",
    },
}
```

Правила:
- `force_banner=True` принудительно открывает баннер независимо от сохранённого решения;
- `preview_param` задаёт query param для ручной проверки banner flow;
- `custom_css_url` и `custom_js_url` подключаются как дополнительные ассеты поверх baseline-слоя;
- `hide_for_bots=True` скрывает баннер в template flow для bot-request;
- `bot_patterns` можно переопределить на стороне проекта;
- `user_agent_mode` принимает только `off`, `all`, `unique`;
- `shared_subdomain=True` требует непустой `cookie_domain`;
- `site_domain` и `cookie_domain` должны быть заданы как host/domain без схемы и пути;
- эти настройки не меняют источник истины для согласия: решение по-прежнему читается из серверной БД и опубликованного снимка policy.

## DOM event contract

Клиентский слой `cookie_banner.js` публикует следующие события:
- `dz152fz:cookie-runtime:applied`;
- `dz152fz:cookie-runtime:cleanup-applied`;
- `dz152fz:cookie-banner:opened`;
- `dz152fz:cookie-banner:closed`;
- `dz152fz:cookie-banner:custom-opened`;
- `dz152fz:cookie-banner:action-submitted`.

Общий payload каждого события:
- `contract_version`, `contract_namespace`, `event_key`, `event_name`, `timestamp`;
- event-specific поля (`allowed_categories`, `removed_categories`, `action`, `selected_optional_categories` и т.д.).

Источником имён событий теперь является `runtime.event_contract`:
- `version`;
- `namespace`;
- `events`.

## Backend hooks для интеграций

Сервисный слой cookie runtime публикует backend extension point:
- `set_cookie_runtime_event_hook(...)` — регистрация callback;
- `trigger_cookie_runtime_event(payload)` — вызов callback из runtime-потока;
- `reset_hooks()` — сброс hook-состояния для тестов и изоляции.

Payload backend hook:
- `contract_version`, `event_name`, `occurred_at`, `source`;
- `subject` (`kind`, `user_id`, `anonymous_token_present`);
- `consent` (если применимо);
- `banner` (если применимо);
- `event_payload`, `audit`, `extra_meta`.

Готовые адаптеры под GTM / Google Consent Mode / Яндекс Метрику в core-контракт не входят и остаются future TODO на стороне проекта.

## Версионируемые тексты и presentation

Текущая реализация добавляет отдельную модель:
- `CookieBannerRevision` хранит plain-text тексты, подписи кнопок и presentation-параметры баннера;
- редакции публикуются отдельно от `CookiePolicyRevision`;
- в Django admin можно редактировать тексты и поля вариантов без хранения произвольного HTML или JavaScript;
- шаблонный слой читает только активную published revision и отдаёт data-атрибуты контракта вариантов;
- project-specific кастомизация по-прежнему остаётся на стороне template override и project CSS/JS override assets.

Канонические поля вариантов:
- `banner_variant`: `bar` | `card` | `modal`;
- `consent_ui_variant`: `inline` | `panel`;
- `reconsent_notice_variant`: `inline` | `alert`;
- `text_preset_code`: `ru_balanced` | `ru_formal` | `ru_compact`.

Наборы текстов и контракт:
- визуальный вариант и набор текстов выбираются независимо;
- пакет включает три коробочных набора текстов (`ru_balanced`, `ru_formal`, `ru_compact`);
- `CookieBannerRevision.is_box_template=True` используется для стартовой DB-backed редакции из bootstrap;
- защищённые юридические поля (`title_text`, `description_text`, `reconsent_notice_text`, `reask_notice_text`) выделены отдельно от безопасно редактируемых подписей/лейблов.

Зафиксированные data-атрибуты контракта вариантов:
- `data-cookie-banner-contract-version`;
- `data-cookie-banner-variant`;
- `data-cookie-banner-consent-ui`;
- `data-cookie-banner-reconsent-variant`;
- `data-cookie-banner-text-preset`.

Legacy-поля presentation (сохранены для обратной совместимости):
- `layout_variant`: `compact` или `wide`;
- `theme_variant`: `light` или `contrast`;
- `desktop_position`: `bottom_right` или `bottom_left`;
- `mobile_position`: `bottom` или `top`.

## 11.1 contract updates (cookie-only)

- Добавлен отдельный cookie-only router `django_152fz_consent.cookies.urls`.
- В package template `cookie_preferences.html` добавлен блочный контракт для
  template override и i18n (`{% trans %}`) без хардкода UI-строк.
- Entry points banner/preference теперь управляются конфигом:
  `cookie_banner.show_launcher` и `cookie_banner.show_preferences_link`.
- Добавлена настройка `cookie_banner.preferences_page_template`: она позволяет
  отрисовывать страницу cookie preferences внутри проектного шаблона сайта
  (с меню/layout), а при пустом значении оставляет коробочный standalone fallback.
- Для такого встраивания предусмотрен reusable include:
  `django_152fz_consent/includes/cookie_preferences_content.html`.
- No-JS fallback остаётся инвариантом: ссылка на страницу настроек сохраняется в
  `<noscript>` даже при отключённых видимых entry points.
- Добавлен bootstrap default `CookiePolicyRevision` с русскоязычным коробочным
  текстом через management command `bootstrap_152fz_cookie_defaults`.
