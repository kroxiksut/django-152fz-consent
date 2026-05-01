# API Контракт Для Router-Интеграций

**Версия документа:** `0.1`  
**Обновлено:** `2026-04-07`

## Назначение

Этот документ фиксирует минимальный публичный Python API пакета для внешних
интеграций и будущего router-слоя.  
Каноническая точка входа: `django_152fz_consent.service_api`.

## Provider Contract

- `provider_code` должен быть стабильным: `ru_152fz`;
- код провайдера читается через `service_api.get_provider_code()`;
- `provider_code` также присутствует в payload `get_current_requirements()`.

## Публичный Service API (v1)

Публичная поверхность `service_api` зафиксирована через:
- `PUBLIC_SERVICE_API_V1`;
- `__all__`.

Состав `v1`:
- `register_purposes_from_config`
- `get_current_requirements`
- `accept_consent`
- `withdraw_consent`
- `anonymize_subject_consents`
- `get_consent_status`
- `attach_anonymous_consents_to_user`
- `get_cookie_requirements`
- `accept_cookie_preferences`
- `get_cookie_status`
- `get_provider_code`

## Правила Стабильности

- изменения состава `PUBLIC_SERVICE_API_V1` считаются контрактными;
- изменения сигнатур публичных функций считаются контрактными;
- любые контрактные изменения требуют синхронного обновления:
  - `TASKS.md`
  - `ARCHITECTURE.md`
  - `README.md` (если меняется внешний onboarding/API-использование)
  - `STRUCTURE.md`
  - тестов контрактов публичного API.

## Router Extension Contract

Будущий внешний router должен работать поверх `service_api`, а не через прямые
импорты внутренних модулей (`core.services`, `cookies.services`).

## Import Flow (12.x)

CSV/import migration flow выполняется через management commands:
- `import_152fz_core_consents`;
- `import_152fz_cookie_data`.

Это operational-import слой, он намеренно не включён в `PUBLIC_SERVICE_API_V1`.
Для внешних источников используется adapter extension point
`django_152fz_consent.imports.adapters`.

Границы:
- пакет не реализует выбор юрисдикции;
- в `core` не добавляется логика маршрутизации по правовым режимам;
- router-слой остаётся внешним компонентом, который выбирает provider и вызывает
  публичный service API конкретного провайдера.

## Тестовое Покрытие Контракта

- `tests/test_service_api.py` — экспорты, сигнатуры, делегирование вызовов;
- `tests/test_router_readiness.py` — anti-regression проверка, что в `core` не
  появляется юрисдикционная логика.

