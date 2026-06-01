# Демо-сайт: Учебный центр

[English version](./README.md)

Этот каталог содержит демо-проект и материалы для проверки интеграции:

- `django-cookies-152fz` (cookie-модуль),
- `django-consent-152fz` (слой согласий, адаптированный под сценарии 152-ФЗ).

## Что демонстрирует сайт

- Публичные страницы сайта учебного центра.
- Каталог курсов.
- Двухшаговый сценарий записи на курс (`django-formtools`).
- Форму обратной связи.
- Регистрацию, вход, выход и профиль (`django-allauth`).
- UI на Bootstrap (`django-bootstrap5`).
- Локализацию RU/EN.
- Подключение модулей после готовности базового сайта.
- Фиксацию согласий в записи на курс, обратной связи и аккаунт-сценариях.
- Проверку записей через Django admin.

## Порядок реализации (важно)

Работа делится на три фазы для каждой версии Django.

### Фаза A. Базовый сайт (без модулей согласий и cookie)

На этом этапе подключаются только:

- Django,
- `django-allauth`,
- `django-formtools`,
- `django-bootstrap5`.

На этом этапе не добавляются приложения пакета, URL пакета и логика согласий/cookie.
Формы и аккаунт-сценарии должны работать автономно.

### Фаза B. Интеграция cookie-слоя

Только после smoke-проверки базового сайта добавляется интеграция:

- editable-зависимость `-e ../..`,
- `django_cookies_152fz` в `INSTALLED_APPS`,
- настройки `DJANGO_COOKIES_152FZ`,
- URL пакета,
- миграции пакета,
- cookie banner и cookie preferences UI,
- проверка, что базовый сайт не сломался.

Документация:

- Cookies (RU): [../docs/cookies/ru/README.md](../docs/cookies/ru/README.md)
- AI-гайды cookies: [../docs/cookies/ai/README.md](../docs/cookies/ai/README.md)

На этом этапе фиксация согласий в бизнес-формах может оставаться отключенной.

### Фаза C. Интеграция consent-слоя

Только после валидации cookie-слоя включаются consent-сценарии:

- блоки согласий в формах и аккаунт-сценариях,
- связка demo-заявок с записями согласий,
- проверка записей согласий в админке.

Документация:

- Consent (RU): [../docs/consent/ru/README.md](../docs/consent/ru/README.md)
- AI-гайды consent: [../docs/consent/ai/README.md](../docs/consent/ai/README.md)

## Структура каталога

```text
demo/
  README.md
  README.ru.md
  common/
    templates/
    static/
    fixtures/
    texts/
    locale/
  django5/
    manage.py
    requirements.txt
    demo_site/
    training_center/
  django6/
    manage.py
    requirements.txt
    demo_site/
    training_center/
  notes/
```

## Назначение основных папок

- `common/`: общие шаблоны, статика, фикстуры, тексты, локали.
- `django5/`: отдельный стенд на Django 5.x.
- `django6/`: отдельный стенд на Django 6.x.
- `notes/`: smoke-checklist и заметки по различиям версий.

## Политика общего слоя

Django 5.x и 6.x должны проверять один и тот же общий сценарий сайта.
Общие UI/тексты/фикстуры переиспользуются из `common/`.
Версионные настройки и Python-код остаются в `django5/` и `django6/`.

## Политика локализации

- Короткие UI-строки: Django i18n (`{% trans %}`, `.po/.mo`).
- Длинные юридические/демо-тексты: `common/texts/ru/` и `common/texts/en/`.

## Быстрый старт

### Django 5 (Linux/macOS)

```bash
cd demo/django5
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Django 5 (Windows PowerShell)

```powershell
cd demo\django5
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Django 6 (Linux/macOS)

```bash
cd demo/django6
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Django 6 (Windows PowerShell)

```powershell
cd demo\django6
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Дополнительно: сценарий conda

Если используется conda, выполните те же шаги внутри выбранного conda-окружения.
