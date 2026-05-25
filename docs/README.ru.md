# Документация проекта `django-152fz`: модули согласий и куки

Это верхнеуровневый индекс русскоязычной документации.

## Основные разделы

- [Модуль согласий](./consent/ru/README.md)
- [Модуль cookie](./cookies/ru/README.md)

## Документы для ИИ

Инструкции для ИИ-агентов поддерживаются отдельно и только на английском:

- [AI-гайды по модулю согласий](./consent/ai/README.md)
- [AI-гайды по модулю cookie](./cookies/ai/README.md)

## Карта установки пакетов

- `pip install django-consent-152fz` - модуль жизненного цикла согласий.
- `pip install django-cookies-152fz` - модуль баннера и исполнения куки.
- `pip install django-consent-152fz django-cookies-152fz` - полная установка.
- `pip install "django-consent-152fz[api]"` - дополнительный набор для API в модуле согласий.

## Тестирование и миграция

- [Тестирование модуля согласий](./consent/ru/testing.md)
- [Миграция модуля согласий](./consent/ru/migration.md)
- [Тестирование модуля cookie](./cookies/ru/testing.md)
- [Миграция модуля cookie](./cookies/ru/migration.md)

## Карта документов по модулю согласий

- [consent/overview.md](./consent/ru/overview.md) - обзор и текущее состояние слоя согласий.
- [consent/invariants.md](./consent/ru/invariants.md) - ключевые доменные инварианты.
- [consent/operations-admin.md](./consent/ru/operations-admin.md) - использование, административные разделы и операционные сценарии.
- [consent/authoring.md](./consent/ru/authoring.md) - создание потоков согласий, работа с текстами и редакциями документов.
- [consent/configuration.md](./consent/ru/configuration.md) - настройки и контракт политик.
- [consent/service-api.md](./consent/ru/service-api.md) - публичный фасад и транспортный контракт.
- [consent/testing.md](./consent/ru/testing.md) - тестирование модуля согласий.
- [consent/migration.md](./consent/ru/migration.md) - миграция модуля согласий.
- [consent/self-service.md](./consent/ru/self-service.md) - сценарии самообслуживания субъекта.
- [consent/access-policies.md](./consent/ru/access-policies.md) - политики доступа и область ресурсов.
- [consent/verified-flow.md](./consent/ru/verified-flow.md) - контур подтверждённых согласий.
- [consent/goskey.md](./consent/ru/goskey.md) - статус и условия будущей интеграции с Госключом.
- [consent/import.md](./consent/ru/import.md) - импорт исторических данных.
- [consent/scope-limits.md](./consent/ru/scope-limits.md) - границы области применения.
- [consent/demo.md](./consent/ru/demo.md) - демо-стенды для сценариев модуля согласий.

## Карта документов по модулю cookie

- [cookies/overview.md](./cookies/ru/overview.md) - обзор текущего состояния cookie-модуля.
- [cookies/invariants.md](./cookies/ru/invariants.md) - ключевые инварианты баннера и серверного слоя.
- [cookies/configuration.md](./cookies/ru/configuration.md) - конфигурация жизненного цикла и серверного слоя.
- [cookies/operations-admin.md](./cookies/ru/operations-admin.md) - использование, административные разделы и операции.
- [cookies/contracts.md](./cookies/ru/contracts.md) - контракт событий и точек интеграции.
- [cookies/presentation.md](./cookies/ru/presentation.md) - тексты, варианты показа и визуальные настройки.
- [cookies/inventory.md](./cookies/ru/inventory.md) - реестр и инвентаризация.
- [cookies/testing.md](./cookies/ru/testing.md) - тестирование модуля cookie.
- [cookies/migration.md](./cookies/ru/migration.md) - миграция модуля cookie.
- [cookies/notes.md](./cookies/ru/notes.md) - дополнительные заметки.
- [cookies/demo.md](./cookies/ru/demo.md) - демо-стенды для сценариев модуля куки.
- [AI-гайд по языкам cookie-модуля](./cookies/ai/languages.md)

## Поддержка

- Поддержка сообщества — GitHub Issues
- Коммерческая поддержка — связь с авторами
- Юридическое и техническое консультирование — по запросу

## Правовое уведомление

Этот проект не связан с государственными органами.

Пользователь самостоятельно определяет применимые правовые требования и при необходимости получает независимую юридическую консультацию.
