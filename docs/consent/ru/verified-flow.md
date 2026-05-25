# Модуль согласий: экспериментальный контур подтверждённых согласий

- [К разделу согласий](./README.md)
- [К общему разделу документации](../README.md)

## Статус

`verified_consents` — экспериментальный необязательный модуль для сценариев усиленного подтверждения отдельных потоков согласий.

## Базовый контракт

- единый `verification_mode`:
  `web_only | paper_required | goskey_required | paper_or_goskey`;
- `flow_scope`:
  `both | self_service_only | forms_only`;
- поведение для ранее выданных веб-согласий:
  `keep_web_current | mark_web_outdated | withdraw_web_now | withdraw_after_paper_confirmed`;
- переопределение для конкретной формы через `VerifiedConsentFormPolicy`.

## Практика постепенного включения

Рекомендуемое постепенное включение `web_only -> paper_required`:
1. `dry-run` без `--apply`;
2. ограниченный `apply` с `--batch-size`;
3. мониторинг `ModuleOperationAuditLog`.

Команда перехода:

```bash
python manage.py transition_152fz_verified_legacy_web \
  --purpose-code <purpose_code> \
  --document-code <document_code> \
  --channel form \
  --form-code <form_code> \
  --dry-run
```

## Границы

- контур подтверждения не заменяет основной жизненный цикл согласий;
- контур подтверждения не добавляет отдельный домен согласий;
- контур подтверждения не обещает готовые производственные интеграции со сторонними провайдерами подписи.

Отдельно по Госключу:
- режимы `goskey_required` и `paper_or_goskey` зарезервированы как направление
  расширения;
- рабочая интеграция с внешним сервисом пока не реализована;
- подробная позиция проекта вынесена в [./goskey.md](./goskey.md).

Подробная эксплуатация и пошаговые сценарии:
- [./operations-admin.md](./operations-admin.md);
- [./README.md](./README.md).
