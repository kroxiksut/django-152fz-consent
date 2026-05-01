# configuration — настройки banner-layer и интеграции

**Версия документа:** `0.1`
**Обновлено:** `2026-04-23`
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
- у коробочных редакций заполняется `published_at`, чтобы демо и admin могли показывать дату публикации стартовой редакции;
- тексты всегда помечаются как стартовые образцы, требующие юридической проверки и адаптации.

В коробочный core-набор входят:
- `sample_personal_data_processing_policy` — политика обработки персональных данных;
- `sample_generic_webform_consent` — согласие для обычной web-формы;
- `sample_feedback_contact_consent` — согласие для обратной связи и обработки обращения;
- `sample_account_registration_consent` — согласие для регистрации и личного кабинета;
- `sample_newsletter_subscription_consent` — отдельное добровольное согласие для рассылок.

Cookie policy относится к cookie-модулю и не загружается этим core-bootstrap.
Оператор должен заменить реквизиты, адреса, ссылки, цели, состав ПДн, сроки
хранения, каналы связи и фактических получателей данных перед публикацией
пользовательской редакции.

Admin flow:
- `LegalDocument` и `DocumentRevision` показывают отдельный признак starter/custom потока;
- в `DocumentRevision` есть фильтр происхождения ревизии;
- коробочную ревизию можно отредактировать напрямую или создать пользовательскую
  копию через admin action и через `Save as new`;
- пользовательская копия создаётся как `is_box_template=False`,
  `is_active=False` и не публикуется автоматически.

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
- `outdated` при публикации новой редакции политики cookie остаётся отдельным сценарием;
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
- `CookieBannerRevision.hide_for_bots_override` позволяет управлять
  suppression через admin: `None` = брать значение из settings,
  `True` = скрывать баннер для bot-like user agents,
  `False` = показывать баннер даже для bot-like user agents;
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
- `desktop_position`: `bottom_right` | `bottom_left` | `center` | `bottom_fullwidth`;
- `mobile_position`: `bottom` | `top` | `center` | `bottom_fullwidth`.

Зафиксированный template/CSS контракт слоя вариантов:
- `data-cookie-banner-contract-version`;
- `data-cookie-banner-variant`;
- `data-cookie-banner-consent-ui`;
- `data-cookie-banner-reconsent-variant`;
- `data-cookie-banner-text-preset`;
- `data-cookie-banner-mobile-text-preset`;
- `data-cookie-banner-mobile-variant`;
- `data-cookie-banner-mobile-consent-ui`;
- `data-cookie-banner-mobile-reconsent-variant`.

Mobile overrides (11.17):
- `CookieBannerRevision.mobile_text_preset_code`;
- `CookieBannerRevision.mobile_banner_variant`;
- `CookieBannerRevision.mobile_consent_ui_variant`;
- `CookieBannerRevision.mobile_reconsent_notice_variant`;
- `CookieBannerRevision.mobile_show_close_control`;
- `CookieBannerRevision.mobile_close_control_placement`;
- `CookieBannerRevision.mobile_show_reject_action`;
- `CookieBannerRevision.mobile_blocking_mode_until_choice`;
- `CookieBannerRevision.mobile_hide_launcher_after_decision`;
- `CookieBannerRevision.mobile_keep_visible_after_accept_all`;
- `CookieBannerRevision.mobile_keep_visible_after_required_only`;
- `CookieBannerRevision.mobile_keep_visible_after_save_custom`.

Fallback contract:
- пустой/`None` mobile override не перезаписывает desktop значение;
- effective mobile значения публикуются в `cookie_banner_config.mobile_overrides`.

Banner lifecycle behavior (11.18):
- при первом показе без сохранённого выбора lifecycle возвращает `default_choice_action="accept_all"`;
- runtime state явно разделяется флагами `initial_visit` и `reopen_after_saved_choice`;
- `blocking_mode_active=True` только до первого осмысленного выбора (`accept_all` / `reject_all` / `required_only` / `save_custom`).

## Что уже доступно без отдельного settings API

Текущая реализация уже даёт:
- reusable template tag `{% render_cookie_banner %}`;
- launcher `Настройки cookie`;
- quick actions `accept all`, `required only`, `custom selection`, `dismiss`;
- внешние static assets `cookie_banner.css` и `cookie_banner.js`;
- runtime JSON-представление для client-side loader;
- re-ask lifecycle поверх server-side `CookieBannerState`;
- attach anonymous cookie-consent и banner-state к `user` после логина;
- DB-backed `CookieRegistryItem` и published snapshot `CookiePolicyRevisionRegistryItem` для disclosure и runtime metadata;
- DB-backed `CookieBannerRevision` для versioned plain-text текстов и presentation баннера.

Коробочные коды категорий по умолчанию (`COOKIE_152FZ_DEFAULT_CATEGORIES`):
- `necessary`;
- `functional`;
- `analytics`;
- `marketing`.

Классификация по умолчанию:
- `necessary` всегда помечается как `is_required=True`;
- `functional`, `analytics`, `marketing` управляются через consent choice как
  необязательные категории.

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

Важно:
- bot suppression и bot-detection считаются operational best-effort эвристикой;
- эти признаки не являются юридическим источником истины и не предназначены для compliance-решений.

## Импорт: ядро и внешние адаптеры (12.3)

В alpha-ядро входят только два штатных import-потока:
- `import_152fz_core_consents` — baseline CSV import для `core`-согласий;
- `import_152fz_cookie_data` — отдельный CSV import для cookie consent/banner state.

Bitrix-специфичный или иной vendor-specific импорт в ядро не встроен как обязательный путь.

Для внешних источников оставлен extension point:
- settings: `DJANGO_152FZ_CONSENT["import_adapters"] = {"adapter_code": "python.path.to.callable"}`;
- runtime API: `django_152fz_consent.imports.adapters.register_import_adapter(...)`;
- management commands поддерживают `--adapter-code` и `--adapter-payload-json`.

Контракт adapter callable:
- вход: `payload: dict`;
- выход: iterable из dict-строк, которые будут преобразованы во временный CSV по выбранному mapping.

Таким образом, в ядре остаётся единый импортный контракт, а интеграции с Bitrix/web-form/CRM реализуются снаружи через adapter layer.

### Безопасность и аудит import-flow (12.4)

- каждый запуск `import_152fz_core_consents` и `import_152fz_cookie_data` пишет запись в `ModuleOperationAuditLog`;
- команда принимает `--actor-user` (id или username) и сохраняет оператора запуска;
- в audit также пишутся источник (`source`), mapping, итоговый счётчик `imported/skipped/errors`;
- для защиты от повторного неидемпотентного импорта применяется row fingerprint:
  - `core`: fingerprint на связке `purpose/document/status/subject/consented_at`;
  - `cookies`: fingerprint на связке `policy_revision/subject/selected_categories`.
- при повторе уже импортированной строки запись помечается как `skipped` и не создаёт новый consent record.

## Self-service alpha scope (13.3)

Текущий self-service слой intentionally ограничен:
- просмотром согласий субъекта;
- отзывом согласия через существующий service layer.

Внутрь этого блока не включены:
- произвольные юридические workflow полноценного «личного кабинета»;
- end-to-end процесс «право на забвение» с SLA, актами удаления и юридическим документооборотом.

Эти сценарии считаются внешним расширением и не являются частью alpha-контракта.

### Локализация self-service (13.4)

- self-service UI использует стандартный Django i18n contract (`{% trans %}` в шаблонах);
- ru-каталог: `src/django_152fz_consent/locale/ru/LC_MESSAGES/django.po`;
- после изменения текстов self-service необходимо пересобрать `django.mo`.

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
  (с основным меню/шапкой и т.д.); при пустом значении или если указанный
  шаблон отсутствует, используется коробочный standalone template.
- Для переиспользования стандартного содержимого страницы в проектном шаблоне
  можно подключить include:
  `django_152fz_consent/includes/cookie_preferences_content.html`.
- Рекомендуемый layout-contract проектного шаблона:
  создать страницу, которая расширяет ваш `base.html` и в `block content`
  подключает `django_152fz_consent/includes/cookie_preferences_content.html`.
- Конфликтная комбинация `False/False` валидируется Django system check
  (`django_152fz_consent.E020`).
- Для визуального состояния выбора в banner/preferences используется DOM-контракт:
  `data-cookie-choice-root`, `data-cookie-choice-state`,
  `data-cookie-choice-action` и accessibility-хуки
  `data-cookie-choice-indicator` + `data-cookie-choice-status`.

## 11.9 Optional admin navigation customization

По умолчанию пакет **не меняет** стандартный `admin.site` и не перехватывает
маршрут `/admin/`.

Для optional-режима с управляемым порядком приложений и сворачиванием блоков
можно добавить отдельный маршрут:

```python
from django.contrib import admin
from django.urls import path

from django_152fz_consent.admin_navigation import get_optional_admin_site

urlpatterns = [
    path("admin/", admin.site.urls),                  # стандартный Django admin
    path("admin-152fz/", get_optional_admin_site().urls),  # optional admin
]
```

Настройки:

```python
DJANGO_152FZ_CONSENT = {
    "admin_navigation": {
        "enabled": True,
        "app_order": [
            "auth",
            "django_152fz_consent",
            "django_152fz_consent_cookies",
            "verified_consents",
        ],
        "collapsed_apps": [
            "django_152fz_consent",
        ],
        "consent_apps": [
            "django_152fz_consent",
            "django_152fz_consent_cookies",
            "verified_consents",
        ],
        "section_title": "Согласия 152-ФЗ",
    },
}
```

- `enabled=True` включает логику переноса consent/cookies apps вниз списка, если
  явный `app_order` не задан.
- `app_order` задаёт приоритет сортировки по `app_label`.
- `collapsed_apps` включает свернутый `<details>`-режим для выбранных приложений.
- `consent_apps` определяет список приложений, которые считаются consent-блоком.
- `section_title` задаёт локализуемый заголовок этого блока.
- Ошибки типа/формата валидируются через Django check
  `django_152fz_consent.E023`.

## Cookie-only bootstrap

```bash
python manage.py bootstrap_152fz_cookie_defaults
```

Команда выполняет первичную инициализацию cookie-only контура:
- коробочные cookie categories;
- коробочные policy-варианты `short` и `full` как обычные
  `CookiePolicyRevision` в versioned-flow (idempotent, без дублей);
- стартовую active `CookiePolicyRevision` (по умолчанию `short`, если до этого
  не было активной редакции);
- стартовую active `CookieBannerRevision` (idempotent).

Для выбора policy-варианта в admin добавлены действия:
- публикация выбранного коробочного варианта (`short`/`full`) через обычный
  versioned-flow;
- создание пользовательского черновика на основе выбранного коробочного текста.

## 11.8 Retention и очистка cookie-аудита

```python
DJANGO_152FZ_CONSENT = {
    "cookie_retention": {
        "records_older_than_days": 365,
        "events_older_than_days": 365,
        "banner_states_older_than_days": 365,
        "records_max_count": 0,
        "events_max_count": 0,
        "banner_states_max_count": 0,
        "batch_size": 1000,
        "protect_current_records": True,
        "private_signal_paths": [
            "cookie_runtime.is_private_mode",
            "client_hints.is_private_mode",
        ],
        "private_records_older_than_days": 30,
        "private_events_older_than_days": 30,
    },
}
```

- `records_older_than_days`, `events_older_than_days`,
  `banner_states_older_than_days` задают порог age-based очистки по моделям.
- `records_max_count`, `events_max_count`, `banner_states_max_count` включают
  прореживание oldest-first при превышении лимита (`0` — без лимита).
- `batch_size` обязателен и должен быть положительным целым; некорректное
  значение валидируется через system check `django_152fz_consent.E022`.
- `protect_current_records=True` запрещает cleanup записей со статусом
  `current` и связанных с ними событий.
- `private_*_older_than_days` задают более короткое best-effort хранение для
  private/incognito сигналов (не юридический источник истины).
- `private_signal_paths` задаёт JSON-пути внутри `extra_meta`, по которым
  runtime ищет признаки private/incognito режима.

Команда очистки:

```bash
python manage.py cleanup_152fz_cookie_audit --dry-run --report-only
python manage.py cleanup_152fz_cookie_audit --batch-size=500 --older-than-days=90
```

- Поддерживаются флаги: `--dry-run`, `--report-only`, `--batch-size`,
  `--older-than-days`, `--database`.
- Очистка выполняется batch-based, без длинной транзакции на всю таблицу.
- Перед удалением вызывается optional archive hook
  `set_cookie_audit_archive_hook(...)` / `trigger_cookie_audit_archive(payload)`.

## 11.11 Управление видимостью и закрытием cookie banner

Поля `CookieBannerRevision` для banner controls:

- `show_close_control` — показывать кнопку/иконку закрытия баннера.
- `close_control_placement` — позиция close-control рядом с launcher: `left` или `right`.
- `show_reject_action` — показывать отдельное действие `reject_all` в quick actions.
- `blocking_mode_until_choice` — включить блокирующий режим до явного выбора пользователя.
- `hide_launcher_after_decision` — скрывать launcher `Настройки cookie` после
  сохранённого выбора пользователя (`current`).
- `close_tooltip_text` — текст `title` для close-control.
- `close_aria_label` — `aria-label` для close-control.
- `reject_label` — подпись кнопки `reject_all`.
- `keep_visible_after_accept_all` — если включено, после `accept_all` баннер не
  закрывается и не сворачивается автоматически.
- `keep_visible_after_required_only` — если включено, после `required_only`
  баннер не закрывается и не сворачивается автоматически.
- `keep_visible_after_save_custom` — если включено, после `save_custom` баннер
  не закрывается и не сворачивается автоматически.

Поведение:
- по умолчанию все `keep_visible_after_* = False` (безопасный коробочный режим);
- по умолчанию `blocking_mode_until_choice=False` (информирующий, неблокирующий режим);
- `dismiss` записывается только в `CookieBannerState.dismissed_at` и не создаёт consent;
- `decision_action` хранится отдельно в `CookieBannerState` и используется только для post-consent visibility логики;
- close-control рендерится рядом с launcher после принятия решения (`has_decision=True`) и отправляет `banner_action=dismiss`;
- `dismiss` скрывает не только панель, но и launcher-ряд (`Настройки cookie`) до
  следующего показа по re-ask/re-consent логике;
- при `hide_launcher_after_decision=True` launcher скрывается после сохранённого
  выбора пользователя, если баннер сейчас не должен быть показан;
- три флага `keep_visible_after_*` различают поведение по конкретному действию
  (`accept_all`, `required_only`, `save_custom`) и не меняют само состояние consent;
- launcher/reopen и no-JS submit через `banner_action=dismiss` остаются рабочими.
- при `blocking_mode_until_choice=True` баннер работает как блокирующий слой:
  пользователь не может закрыть его через `dismiss`, `Esc` или клик по backdrop,
  пока не отправит одно из явных действий выбора (`accept_all`, `reject_all`,
  `required_only`, `save_custom`).
- все эти режимы (`desktop_position`, `mobile_position`, `blocking_mode_until_choice`)
  настраиваются через `Cookie Banner Revision` в Django admin и версионируются вместе
  с остальными настройками баннера, без ручного редактирования template/JS/settings.

## 14. Конфигурация audit-слоя операций

Отдельных settings для включения/выключения журнала операций сейчас не требуется:
- операции пишутся в `ModuleOperationAuditLog` всегда;
- для dry-run cleanup используется статус `dry_run`;
- просмотр и CSV-экспорт доступны из Django admin (`Module Operation Audit Logs`).

Ограничения текущего этапа:
- экспорт реализован в CSV;
- DOC/XLS-форматы намеренно не добавлены в базовый пакет.

## 11.15 Clone/copy revisions в admin

Для ревизий cookie-политики и banner добавлен стандартный clone/copy сценарий:
- создаёт новую draft-запись с новой `version`;
- сохраняет ссылку на исходник в `cloned_from`;
- не требует отдельного settings-флага и доступен через admin actions.

## 11.19 Help texts для admin-полей

- Для core consent admin, cookie admin и verified/admin extensions добавлены
  русскоязычные `help_text` для всех редактируемых полей форм.
- Для action-форм (`audience_groups`, `policy_text_variant`,
  `confirmation_note`, `rejection_note`) также добавлены пояснения.
- Добавлен smoke-тест, который проверяет, что у editable полей admin-форм
  `help_text` не пустой.

## 11.21 Точечная дорусификация cookie/admin строк

- В `CookieBannerRevision` дорусифицированы labels:
  `Текст уведомления о повторном согласии`, `Заголовок блока выбора категорий`,
  `Скрытый текст кнопки закрытия`, `Подсказка кнопки закрытия`,
  `ARIA-метка кнопки закрытия`, `Вариант интерфейса согласия`,
  `Вариант уведомления о повторном согласии`, `Устаревший layout-режим`,
  `Устаревший theme-режим`.
- Для выбора позиции `bottom_fullwidth` обновлено русское название:
  `Нижний полноэкранный`.
- Обновлены каталоги переводов `django.po` / `django.mo` и тесты admin UI.

## 11.23 Расширенная визуальная кастомизация banner

В `CookieBannerRevision` добавлены DB-backed настройки визуального слоя:
- `color_preset`: `light` | `contrast` | `forest` | `sand`;
- custom HEX-цвета (`#RRGGBB`) для фона, текста, primary-кнопки, текста primary,
  border, surface и overlay;
- spacing-поля `panel_padding_px`, `section_gap_px`, `button_gap_px`;
- `overlay_opacity` в процентах.

Контракт безопасности:
- custom colors принимаются только в формате `#RRGGBB`;
- для пары `background/text` проверяется базовая контрастность;
- spacing/opacity нормализуются в безопасные диапазоны (`8..48`, `4..32`,
  `4..24`, `0..85`).

## 11.16 DB-backed presets

Preset-слой теперь поддерживает редактирование через БД:
- `CookieBannerTextPreset` управляет текстами banner-предустановок;
- `CookiePolicyTextPreset` управляет текстами policy-вариантов `short/full`.

Если DB-пресет активен и совпадает по `code`, он имеет приоритет над коробочным preset-значением.

## 11.24 Optional media/icon slot

В CookieBannerRevision добавлены поля:
- show_media_slot (вкл/выкл slot),
- media_slot_type (icon или image),
- media_icon_emoji, media_image_url, media_image_alt.

Правила:
- slot остаётся optional и не влияет на consent/runtime логику;
- image-режим требует URL и alt-текст;
- небезопасные javascript: URL отбрасываются.


## 11.25 Refusal UX
- Для preferences-страницы поддержаны submit-действия ccept_all, eject_all, equired_only, save_custom.
- eject_all фиксируется как отдельный decision_action и не маскируется как equired_only в UI state-label.


## Дополнение по блоку 11 (реализованное)

- `11.2`/`11.5`: коробочные русские labels/help texts для cookie/admin UI поставляются вместе с i18n-каталогами и остаются переводимыми.
- `11.3`: changelist навигация в admin настроена на человекочитаемые `list_display_links` для ключевых моделей.
- `11.4`: bootstrap cookie policy поддерживает два box-варианта (`short`/`full`) в обычном revision-flow.
- `11.6`: `cookie_banner.preferences_page_template` позволяет встраивать страницу настроек в проектный layout с fallback на package-template.
- `11.10`: core sample-документы согласий загружаются как обычные `LegalDocument`/`DocumentRevision` и помечаются как стартовые шаблоны.
- `11.12`/`11.20`: lifecycle/presentation contract уточнён для `reject_all`, `dismiss`, launcher и post-decision visibility.
- `11.14`: ручная admin-очистка cookie runtime-данных использует тот же cleanup contract, что retention-слой `11.8`.
- `11.22`: `hide_for_bots_override` задаёт admin-priority для bot suppression поверх settings runtime-флага.

## 15.2 Scope и ограничения best-effort инвентаризации

Добавлен отдельный settings-блок:

```python
DJANGO_152FZ_CONSENT = {
    "cookie_inventory": {
        "enable_registry_hints": False,
        "enable_external_scanners": False,
        "enable_db_auto_discovery": False,
    },
}
```

Правила alpha-этапа:
- `enable_registry_hints=False` по умолчанию: инвентаризация не является обязательной частью ядра и запускается только явно.
- `enable_external_scanners=True` не поддерживается в alpha core и валидируется как конфигурационная ошибка.
- `enable_db_auto_discovery=True` не поддерживается в alpha core и валидируется как конфигурационная ошибка.
- `inventory_152fz_cookie_integrations` при выключенном `enable_registry_hints` выполняется только с `--force` для разового ручного запуска.
- startup-валидация этих ограничений выполняется через Django system check
  `django_152fz_consent.E024`.
