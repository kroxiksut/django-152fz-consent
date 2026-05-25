# Модуль cookie: контракт событий и перехватов

- [К разделу cookie](./README.md)
- [К общему разделу документации](../README.md)

## Контракт событий DOM

Клиентский слой `cookie_banner.js` публикует события:
- `dz152fz:cookie-runtime:applied`;
- `dz152fz:cookie-runtime:cleanup-applied`;
- `dz152fz:cookie-banner:opened`;
- `dz152fz:cookie-banner:closed`;
- `dz152fz:cookie-banner:custom-opened`;
- `dz152fz:cookie-banner:action-submitted`.

Общая полезная нагрузка:
- `contract_version`, `contract_namespace`, `event_key`, `event_name`, `timestamp`;
- поля конкретного события (`allowed_categories`, `removed_categories`, `action`, `selected_optional_categories` и другие).

## Серверные перехваты для интеграций

Сервисный слой cookie публикует точку расширения:
- `set_cookie_runtime_event_hook(...)` — регистрация обратного вызова;
- `trigger_cookie_runtime_event(payload)` — вызов обратного вызова из потока исполнения.

Ответственность за конкретные проектные адаптеры остаётся на стороне проекта.

## Request audit-context: страна, браузер и ОС

`build_request_audit_context(...)` в cookie-пакете добавляет best-effort enrichment в `extra_meta.client`:
- `country_code` (ISO alpha-2);
- `country_source` (`header:<name>` или `locale`);
- `browser_name`, `browser_version_major`;
- `os_family`, `os_version_major`.

Данные не являются обязательными и заполняются только когда их удалось корректно определить.
