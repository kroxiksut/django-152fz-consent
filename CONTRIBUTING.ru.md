# Участие в проекте

Спасибо за вклад в `django-consent-152fz`.

## Окружение

- Python: `>=3.10`
- Поддерживаемые версии Django: `5.x`, `6.x`
- Можно использовать любой менеджер окружения (`venv`, `virtualenv`, `conda`, `poetry` и т.д.).

## Подготовка окружения

### Linux/macOS (`venv`)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
```

### Windows PowerShell (`venv`)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
```

### Любая ОС (`conda`)

```bash
conda create -n django152fz-py312 python=3.12 -y
conda activate django152fz-py312
python -m pip install -U pip
python -m pip install -e .[dev]
```

Проверка матрицы:
- Для Django 5: Python `3.10+`
- Для Django 6: Python `3.12+`

Примеры команд (Linux/macOS, `venv`):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
python -m pytest
ruff check src tests
```

Примеры команд (Windows PowerShell, `venv`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
python -m pytest
ruff check src tests
```

Примеры команд (Windows PowerShell, `conda`):

```powershell
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' run -n py312-152fz python -m pytest
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' run -n py312-152fz ruff check src tests
```

## Перед созданием pull request

1. Локально выполнены тесты.
2. Проверены регрессии на границах core/cookies/api.
3. Документация синхронизирована с изменениями.
4. При изменении структуры файлов обновлён `STRUCTURE.md`.
5. При изменении статусов дорожной карты обновлён `TASKS.md`.

## Правила по коду и документации

- Доменные инварианты: `ARCHITECTURE.md`.
- Правила разработки репозитория: `AI_RULES.md`.
- Новая логика сопровождается тестами соответствующего уровня.
- Вклад в переводы приветствуется и рассматривается как полноценный вклад.
- Процедура и требования по переводам: [docs/i18n/README.ru.md](./docs/i18n/README.ru.md).

## Что коммитить из AI/служебных файлов

- Коммитьте репозиторные правила и документы процесса (например, `AGENTS.md`, стабильные архитектурные документы, руководства по участию).
- Не коммитьте локальное состояние инструментов и приватные рабочие файлы ассистентов.
- Ориентируйтесь на `.gitignore` как на источник истины для локальных и автоматически сгенерированных артефактов.

## Проверка границ задачи

Перед крупными изменениями проверьте:

- `README.ru.md` (публичные границы),
- `TASKS.md` (дорожная карта и статусы),
- `AI_CONTEXT.md` (продуктовые границы),
- `AI_RULES.md` (архитектурные и процессные ограничения).

## Сообщения коммитов

Рекомендуемые префиксы:

- `core: ...`
- `cookies: ...`
- `api: ...`
- `docs: ...`
- `tests: ...`

В сообщении должно быть понятно, что изменено и зачем.
