# Модуль согласий: настройки и контракт политик

- [К разделу согласий](./README.md)
- [К общему разделу документации](../README.md)

## Базовая конфигурация

Основная конфигурация задаётся в `DJANGO_CONSENT_152FZ`:
- `fields_mode` и `fields` для реестра полей ПД;
- `purposes` для целей обработки;
- `subject_consents` для поведения самообслуживания;
- флаги возможностей для включения дополнительных контуров.

## Флаги возможностей

- `enable_core` — основной жизненный цикл согласий;
- `enable_access_policies` — ресурсные ограничения доступа;
- `enable_verified_consents` — флаг совместимости для экспериментального контура подтверждённых согласий.

## Контракт политик

- `ConsentPurpose.consent_frequency_policy`: `once_until_outdated` | `every_time`;
- `ConsentPurpose.subject_availability_policy`: `authenticated_only` | `authenticated_and_anonymous`;
- `subject_consents.allow_anonymous_withdraw` включает или отключает анонимный отзыв в самообслуживании;
- в транспортном слое и API используется `consent_required_reason`:
  `not_required`, `every_time`, `outdated`, `missing_or_other`, `not_applicable`.

## Практика сопровождения

- изменения логики политик и флагов возможностей должны сопровождаться обновлением
  [./service-api.md](./service-api.md) и тестов;
- изменения сценариев привязки документов к формам и бумажного подтверждения
  синхронизируются с [./operations-admin.md](./operations-admin.md);
- при добавлении новых пользовательских строк обновляются `.po/.mo`.

## Контекст аудита запроса: страна и сведения о клиенте

`build_request_audit_context(...)` для потока согласий дополнительно заполняет:
- `extra_meta.client.country_code` (по возможности код ISO alpha-2);
- `extra_meta.client.country_source` (`header:<name>` или `locale`);
- `extra_meta.client.browser_name`, `extra_meta.client.browser_version_major`;
- `extra_meta.client.os_family`, `extra_meta.client.os_version_major`.

Важно:
- заполнение выполняется по возможности, без гарантии каждого поля;
- структура остаётся обратно совместимой: новые данные пишутся в `extra_meta.client`.

## Навигация по разделу

- Предыдущий: [Создание и наполнение согласий](./authoring.md)
- Следующий: [Публичный сервисный API](./service-api.md)
