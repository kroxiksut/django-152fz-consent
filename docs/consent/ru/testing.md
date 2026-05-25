# Модуль согласий: тестирование

- [К разделу согласий](./README.md)
- [К общему индексу документации](../README.md)

## Область проверок

- доменная модель согласий (`LegalDocument`, `DocumentRevision`, `ConsentRecord`, `ConsentEvent`);
- сервисный слой ядра (`core.services`);
- публичный фасад `service_api` в части операций согласий;
- политики доступа и самообслуживание субъекта.
- сценарии привязки документа к форме и переключения на бумажное подтверждение.

## Минимальный набор

- `tests/test_document_models.py`
- `tests/test_consent_record_model.py`
- `tests/test_consent_event_model.py`
- `tests/test_core_services.py`
- `tests/test_service_api.py`
- `tests/test_feature_flags_config.py`

## Сквозные проверки

- интеграционный набор из каталога `tests`;
- сценарии миграции описаны в [./migration.md](./migration.md).
- практические сценарии эксплуатации описаны в [./operations-admin.md](./operations-admin.md).

## Проверки перед выпуском

Для выпуска модуля согласий обязательны:
- `consent-standalone`;
- `integration`;
- сборка пакетов и проверка метаданных и содержимого артефактов.
