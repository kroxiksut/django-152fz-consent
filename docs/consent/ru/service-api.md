# Модуль согласий: публичный сервисный API и транспортный контракт

- [К разделу согласий](./README.md)
- [К общему разделу документации](../README.md)

## Публичная точка входа

Для внешних интеграций используется:

```python
from django_consent_152fz import service_api
```

Стабильная поверхность фиксируется через `PUBLIC_SERVICE_API_V1` и `__all__`.

## Ключевые операции ядра согласий

- `register_purposes_from_config`
- `get_current_requirements`
- `accept_consent`
- `withdraw_consent`
- `anonymize_subject_consents`
- `get_consent_status`
- `attach_anonymous_consents_to_user`

## Граница ответственности

- Для cookie доступны отдельные операции (`get_cookie_requirements`, `accept_cookie_preferences`, `get_cookie_status`), но ядро согласий остаётся самостоятельным доменом.
- Прямой импорт внутренних `core.services` и `cookies.services` во внешних интеграциях не рекомендуется.

## Маршрутизация и транспортный контракт

- Расширение маршрутов и API-контракты фиксируются в [../README.md](../README.md).
- Веб- и API-адаптеры должны оставаться тонкими и не дублировать доменную логику сервисного слоя.
- Практические сценарии интеграции форм и бумажного подтверждения описаны в [./operations-admin.md](./operations-admin.md).
