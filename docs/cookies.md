# cookies — текущее состояние cookie-модуля и слоя баннера

**Версия документа:** `0.1`
**Обновлено:** `2026-04-23`
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
- постоянную кнопку `Настройки cookie`;
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

Дополнительно для 11.11:
- `CookieBannerState.decision_action` хранит действие принятия решения (`accept_all`, `required_only`, `save_custom`);
- post-consent видимость баннера управляется через поля `CookieBannerRevision.keep_visible_after_*`;
- это влияет только на рендер/видимость баннера и не меняет `CookieConsentRecord.status`.

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

### Тексты баннера не равны редакции политики cookie

Редакция текстов и presentation баннера живёт отдельно от `CookiePolicyRevision`.

Инварианты:
- публикация `CookieBannerRevision` не переводит cookie-consent в `outdated`;
- публикация новой `CookiePolicyRevision` не переписывает тексты баннера;
- banner-layer читает только одну активную published revision текстов и presentation;
- при отсутствии DB-редакции используется встроенный fallback по умолчанию.

В той же revision теперь версионируются и banner controls:
- `show_close_control`;
- `close_control_placement` (`left` или `right`);
- `show_reject_action`;
- `blocking_mode_until_choice`;
- `hide_launcher_after_decision`;
- `close_tooltip_text`;
- `close_aria_label`;
- `reject_label`;
- `keep_visible_after_accept_all`;
- `keep_visible_after_required_only`;
- `keep_visible_after_save_custom`.

Отображение close-control:
- после принятия cookie-решения кнопка `dismiss` рендерится рядом с launcher (а не внутри секции custom choice);
- это действие закрывает banner-panel (`CookieBannerState.dismissed_at`) и не создаёт/не отзывает consent;
- после `dismiss` launcher `Настройки cookie` скрывается до следующего показа по re-ask/re-consent;
- при `hide_launcher_after_decision=True` launcher скрывается после сохранённого решения пользователя (`current`), когда баннер не должен быть показан.
- при `blocking_mode_until_choice=True` баннер становится блокирующим до выбора пользователя:
  `dismiss` недоступен, закрытие по `Esc` и клику по backdrop отключено до явного действия выбора.

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

### Канонические коробочные категории cookie (11.13.4)

Коробочный seed/bootstrap использует канонический набор категорий:
- `Обязательные cookie` (`necessary`);
- `Функциональные cookie` (`functional`);
- `Аналитические cookie` (`analytics`);
- `Рекламные и таргетинговые cookie` (`marketing`).

Правила нормализации:
- термин `Основные файлы cookie` не используется для функциональной категории;
- описание `Обязательных cookie` включает сценарии балансировки нагрузки, входа, отправки форм и базовых privacy/security-настроек;
- описание `Функциональных cookie` акцентирует запоминание выбора пользователя и персонализацию интерфейса;
- описание `Аналитических cookie` акцентирует статистику использования, популярность контента и анализ пользовательских сценариев;
- описание `Рекламных и таргетинговых cookie` акцентирует поведенческую рекламу и рекламных партнёров.

Решение по `third-party session replay`:
- этот сценарий классифицируется как аналитический/исследовательский инструмент и относится к категории `Аналитические cookie`;
- при фактическом использовании такого инструмента оператор должен явно раскрыть его отдельно в реестре и политике cookie (провайдер, назначение, сроки хранения, объём собираемых данных).

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
- `CookieBannerRevision.hide_for_bots_override` позволяет управлять этим
  поведением через admin без обязательной правки `settings.py`:
  `пусто` = использовать `cookie_runtime.hide_for_bots`,
  `включено` = скрывать баннер для bot-like user agents,
  `выключено` = показывать баннер даже ботам;
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
- `outdated` при публикации новой редакции политики cookie остаётся отдельным сценарием и не зависит от этого интервала.

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
- admin override `hide_for_bots_override` имеет приоритет над
  `cookie_runtime.hide_for_bots` и остаётся operational helper, а не legal-engine;
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
- `data-cookie-banner-text-preset`;
- `data-cookie-banner-mobile-text-preset`;
- `data-cookie-banner-mobile-variant`;
- `data-cookie-banner-mobile-consent-ui`;
- `data-cookie-banner-mobile-reconsent-variant`.

Mobile-specific overrides (11.17):
- в `CookieBannerRevision` добавлены mobile overrides для text preset, variant preset и visibility/close поведения;
- если mobile override пустой, runtime берёт desktop/default значение;
- на узких экранах (`max-width: 900px`) `cookie_banner.js` применяет `mobile_overrides` для текста, variants и поведения кнопок `dismiss`/`reject`.

Дополнительные режимы позиционирования (11.13.1/11.13.6):
- `desktop_position="center"` — центрирование banner-panel в viewport на desktop;
- `desktop_position="bottom_fullwidth"` — полноширинный нижний режим на desktop;
- `mobile_position="center"` — центрирование banner-panel на mobile;
- `mobile_position="bottom_fullwidth"` — полноширинный нижний режим на mobile.

Blocking-mode contract (11.13.2/11.13.6):
- при `blocking_mode_until_choice=True` рендерится `dz152fz-cookie-banner--blocking-active`;
- в data-атрибутах публикуются `data-cookie-banner-blocking-mode` и
  `data-cookie-banner-blocking-active`;
- до явного выбора недоступны `dismiss`, закрытие по `Esc` и клик по backdrop;
- no-JS сценарий остаётся рабочим для явного выбора через submit формы.

Default choice + post-decision blocking (11.18):
- при первом показе баннера (`initial visit`) активным выбором по умолчанию выставляется `accept_all`;
- это отражается в `data-cookie-choice-initial-state="accept_all"` и в `aria-pressed` / screen-reader status через `cookie_banner.js`;
- `blocking_mode_until_choice` активен только до первого явного выбора;
- после сохранённого выбора при повторном показе (`reopen after saved choice`) блокировка страницы повторно не включается.

Legacy-поля presentation (сохранены для обратной совместимости):
- `layout_variant`: `compact` или `wide`;
- `theme_variant`: `light` или `contrast`;
- `desktop_position`: `bottom_right` | `bottom_left` | `center` | `bottom_fullwidth`;
- `mobile_position`: `bottom` | `top` | `center` | `bottom_fullwidth`.

Visual customization (11.23):
- отдельный `color_preset` с коробочными вариантами `light`, `contrast`,
  `forest`, `sand`;
- custom цветовые override-поля для ключевых элементов баннера;
- настраиваемые spacing-параметры (`panel_padding_px`, `section_gap_px`,
  `button_gap_px`);
- `overlay_opacity` для backdrop-слоя.

## 11.1 contract updates (cookie-only)

- Добавлен отдельный cookie-only router `django_152fz_consent.cookies.urls`.
- В package template `cookie_preferences.html` добавлен блочный контракт для
  template override и i18n (`{% trans %}`) без хардкода UI-строк.
- Entry points banner/preference теперь управляются конфигом:
  `cookie_banner.show_launcher` и `cookie_banner.show_preferences_link`.
- Добавлена настройка `cookie_banner.preferences_page_template`: она позволяет
  отрисовывать страницу cookie preferences внутри проектного шаблона сайта
  (с меню/layout), а при пустом значении или отсутствии указанного шаблона
  оставляет коробочный standalone fallback.
- Для такого встраивания предусмотрен reusable include:
  `django_152fz_consent/includes/cookie_preferences_content.html`.
- Рекомендуемый layout-contract: проектный шаблон расширяет ваш `base.html`,
  а внутри `block content` подключает include
  `django_152fz_consent/includes/cookie_preferences_content.html`.
- No-JS fallback остаётся инвариантом: ссылка на страницу настроек сохраняется в
  `<noscript>` даже при отключённых видимых entry points.
- Добавлен bootstrap default `CookiePolicyRevision` с русскоязычным коробочным
  текстом через management command `bootstrap_152fz_cookie_defaults`.
- Bootstrap policy теперь загружает два коробочных варианта текста:
  короткий (`short`) и полный (`full`), оба как обычные versioned-редакции.
- Повторный bootstrap не создаёт дубли ни активной редакции, ни коробочных
  policy-вариантов.
- В admin добавлены действия для выбора и публикации нужного коробочного
  варианта, а также для создания пользовательского черновика на его основе.
- Правило сопровождения переводов: новые коробочные UI-тексты, preset-лейблы и
  default labels добавляются вместе с русским переводом в том же change set.

## 11.7 Визуальное состояние выбора (banner + preferences)

- Для banner и страницы `cookie_preferences` добавлен единый UI-контракт выбора:
  `data-cookie-choice-root`, `data-cookie-choice-mode`,
  `data-cookie-choice-state`, `data-cookie-choice-action`.
- JS-синхронизация переводит состояние в:
  `required_only` при пустом выборе optional категорий,
  `accept_all` при полном выборе optional категорий,
  `custom` при частичном выборе.
- После клика `Только необходимые` кнопка `Принять все` больше не остаётся
  визуально активной.
- При ручном изменении checkbox optional категорий интерфейс автоматически
  переключается в состояние `custom` (выбранные категории).
- Для accessibility добавлены:
  `aria-pressed` на action-кнопках, видимый индикатор текущего состояния
  (`data-cookie-choice-indicator`) и screen-reader live region
  (`data-cookie-choice-status`, `role="status"`, `aria-live="polite"`).
- No-JS fallback сохраняется: итоговый выбор по-прежнему читается из состояния
  form controls и может быть сохранён серверной формой без JavaScript.

## 11.8 Retention, cleanup и объём аудита

- Добавлен runtime-модуль `cookies/retention.py` с batch-cleanup для:
  `CookieConsentEvent`, `CookieConsentRecord`, `CookieBannerState`.
- Поддержаны сценарии age-based очистки и max-count прореживания oldest-first.
- Для больших таблиц очистка идёт порциями (batch) и не держит одну длинную
  транзакцию на весь объём.
- Для защиты юридически значимых данных поддерживается
  `protect_current_records=True`: записи `current` и связанные события не
  удаляются.
- Для private/incognito best-effort сигналов поддержаны отдельные короткие
  сроки хранения (`private_records_older_than_days`,
  `private_events_older_than_days`) и настраиваемые JSON-пути
  (`private_signal_paths`).
- Перед удалением батча вызывается optional archive/export hook:
  `set_cookie_audit_archive_hook(...)` c payload
  `cookie_audit.archive_requested`.
- Добавлена management command:
  `cleanup_152fz_cookie_audit` (`dry-run`, `report-only`, `batch-size`,
  `older-than-days`, `database`).
- Для производительности добавлены индексы на поля времени, статуса,
  субъектов и связей policy/revision; в admin включён `list_select_related`
  для `CookieConsentRecord`, `CookieConsentEvent`, `CookieBannerState`.

Рекомендуемые baseline-профили retention:
- Малый сайт: 180–365 дней, `batch_size` 500–1000, без max-count лимита.
- Средний проект: 90–180 дней, `batch_size` 1000–5000, max-count по events.
- Крупный проект с высоким трафиком: 30–90 дней для banner/event аудита,
  отдельные лимиты max-count и регулярный архивный hook до удаления.

## 14. Audit действий модуля и администраторов

Реализован отдельный журнал операций `ModuleOperationAuditLog`:
- хранит код операции, источник, статус, исполнителя, цель, payload/result и время;
- покрывает admin-публикации/массовые действия и service-операции bootstrap/cleanup;
- поддерживает экспорт выбранных записей в CSV из Django admin.

Текущие ключевые коды операций:
- `admin.document_revision.publish`
- `admin.document_revision.clone_starter_templates`
- `admin.document_revision.apply_all_registered_users`
- `admin.document_revision.apply_selected_groups`
- `admin.cookies.publish_policy_revision`
- `admin.cookies.publish_banner_revision`
- `admin.cookies.publish_box_policy_variant`
- `admin.cookies.create_custom_draft_policy_variant`
- `service.cookies.cleanup_cookie_audit`
- `service.cookies.publish_policy_revision`
- `service.cookies.publish_banner_revision`
- `service.cookies.sync_policy_registry_snapshot`

## 15.1 Best-effort инвентаризация и подсказки

Реализован минимальный advisory-сценарий инвентаризации без crawler-платформы:
- анализ уже известных интеграций (`CookieRegistryItem`) и/или входного списка;
- best-effort подсказка категории: `necessary` / `functional` / `analytics` / `marketing`;
- обязательный флаг ручной верификации для каждого результата.

Технические entry points:
- `django_152fz_consent.cookies.inventory.build_best_effort_inventory_hints(...)`;
- `django_152fz_consent.cookies.inventory.build_inventory_hints_for_registry_items()`;
- management command `inventory_152fz_cookie_integrations`.

Важно:
- это heuristics-only слой подсказок;
- пакет не обещает автоматическое юридическое определение категории.

## 15.2 Scope и ограничения inventory-layer

- Полноценный crawler/scanner страниц не является обязательной частью alpha-core.
- Автоматический анализ всех таблиц БД и внешних CRM на наличие ПД в этот блок не входит.
- Settings `cookie_inventory` по умолчанию отключает запуск инвентаризации:
  `enable_registry_hints=False`.
- Команда `inventory_152fz_cookie_integrations` выполняется только при явном включении
  `enable_registry_hints=True` или с флагом `--force` для разового ручного запуска.
- Параметры `enable_external_scanners` и `enable_db_auto_discovery` в alpha-core
  не поддерживаются и валидируются как конфигурационная ошибка.

## 15.3 Интеграция с cookie registry

Best-effort подсказки интегрированы с реестром `CookieRegistryItem` в формате
advisory review queue:
- `build_inventory_hints_for_registry_items()` дополнительно возвращает
  `registry_mapping_review_queue`;
- для каждой интеграции фиксируются:
  `current_category_code`, `suggested_category`, `mapping_status`,
  `confidence`, `reasons`;
- `mapping_status="requires_manual_review"` означает только рекомендацию, без
  изменения БД.

Границы и инварианты:
- auto-apply в базовом пакете отсутствует (`auto_apply_allowed=False`);
- ручная верификация оператора обязательна для любого несоответствия категории;
- если функционал инвентаризации отключён, базовый cookie-flow работает
  без изменений.

## 15.4 Тесты и документация (advisory inventory)

- Добавлены тестовые fixture-сценарии для advisory categorization и integration hints.
- Покрыты кейсы:
  `aligned mapping`, `requires_manual_review`, `missing suggested category`,
  а также optional-режим запуска management command (`disabled by default` и `--force`).
- Документация фиксирует границы: inventory-layer не выполняет auto-apply и
  не заменяет ручную юридическую/операторскую верификацию.
- `service.cookies.bootstrap_default_policy_revision`
- `service.core.bootstrap_sample_documents`

## 11.15 Clone/copy для cookie revisions

Реализован единый clone/copy flow в Django admin:
- `CookiePolicyRevision`: action `Clone selected policy revisions as custom drafts`;
- `CookieBannerRevision`: action `Clone selected banner revisions as custom drafts` + `Save as new`.

Поведение:
- копия создаётся как отдельная draft-ревизия (`is_active=False`, `is_box_template=False`);
- исходная published/box ревизия не изменяется;
- связь хранится в поле `cloned_from` и показывается в admin как `Source revision`.

## 11.16 Editable text presets

Добавлены DB-backed пресеты:
- `CookieBannerTextPreset`;
- `CookiePolicyTextPreset`.

Контракт:
- коробочные preset-коды остаются совместимыми (`ru_balanced`, `ru_formal`, `ru_compact`, `short`, `full`);
- DB-пресет с тем же кодом переопределяет коробочный текст;
- в admin доступны редактирование и clone-action для создания пользовательской копии пресета;
- banner/policy revision-flow использует те же коды пресетов и сохраняет обратную совместимость.

## 11.2 Локализация admin (cookies/core/verified)

- Для admin-форм и changelist-экранов модулей `core`, `cookies`, `verified_consents`
  добавлены/уточнены русские labels, choice labels, actions и help texts.
- Коробочная поставка ориентирована на русскую локаль; translation contract остаётся
  стандартным Django i18n (`msgid` + `.po/.mo`).

## 11.3 Удобные переходы в changelist

- Для ключевых admin-моделей заданы человекочитаемые `list_display_links`
  (не только технические `id`/`version`), чтобы переход к записи выполнялся по
  полезным бизнес-полям.
- Для журналов/read-only списков акцент сделан на кликабельные поля события,
  записи согласия и источника.

## 11.4 Коробочные policy-тексты cookie

- Bootstrap загружает два DB-backed варианта policy-текста: `short` и `full`.
- Варианты участвуют в обычном revision-flow и публикуются через admin.
- Повторный bootstrap не создаёт дублей активной редакции/коробочных вариантов.

## 11.5 Дорусификация публичного cookie UI

- Launcher и публичные cookie-страницы используют русские коробочные тексты по
  умолчанию.
- Русифицированы presets/default labels и связанные fallback-строки banner/no-JS.

## 11.6 Preferences page из коробки

- Страница настроек cookie доступна из коробки без ручного создания view/template
  в проекте.
- Для интеграции в layout сайта поддержан override через
  `cookie_banner.preferences_page_template` с fallback на package-template.

## 11.10 Коробочные тексты core-согласий

- В core-bootstrap добавлен набор стартовых русскоязычных документов согласия
  (web-form, обратная связь, регистрация, рассылка) как обычные `LegalDocument` /
  `DocumentRevision`.
- Тексты помечены как стартовые шаблоны и требуют юридической адаптации оператором.

## 11.12 Ретроспектива замечаний после 11.11

- Зафиксированы правки для корректного `reject_all`, разделения `dismiss` и consent,
  а также lifecycle-логики launcher после принятого решения.
- Поведение задокументировано как часть runtime/template contract, без изменения
  юридического источника истины для consent.

## 11.14 Ручная очистка cookie runtime-данных через admin

- Для cookie-моделей поддержан admin cleanup-flow, согласованный с retention contract
  из 11.8.
- Очистка распространяется только на cookie-слой (`CookieConsentRecord`,
  `CookieConsentEvent`, `CookieBannerState`) и не применяется к core consent-слою.

## 11.20 Labels/help texts для visibility settings

- Уточнены формулировки и help texts для post-decision visibility флагов
  (`keep_visible_after_*`), чтобы явно описывать: баннер не закрывается автоматически
  после соответствующего действия.
- Пояснения согласованы с blocking mode, dismiss и launcher lifecycle.

## 11.22 Bot suppression

- Поддержан best-effort suppress banner для bot-like user-agent с admin override
  (`hide_for_bots_override`), не как legal-engine, а как operational UX-helper.
- Зафиксирована граница: bot detection не является юридическим источником истины.

### 11.24 Optional media/icon slot
- Добавлен optional media/icon slot в banner header через CookieBannerRevision.
- Contract ограничен лёгкими сценариями: media_slot_type (icon/image), media_icon_emoji, media_image_url, media_image_alt.
- Arbitrary HTML/content не добавляется; если slot выключен, баннер работает в штатном fallback-режиме без изменений.


### 11.25 Refusal UX (отказ от необязательных cookie)
- В banner и preferences добавлен явный сценарий eject_all с отдельной формулировкой отказа от необязательных cookie.
- Визуальное состояние выбора для eject_all сохраняется и отображается при повторном открытии страницы настроек.
- Runtime-поведение остаётся deny-by-default для optional категорий после отказа.

