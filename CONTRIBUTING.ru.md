# Участие в проекте

Спасибо за вклад в `django-consent-152fz`.

> **Вопросы безопасности:** не сообщайте об уязвимостях через публичные issue или
> pull request. Используйте приватный канал из [политики безопасности](./SECURITY.ru.md).

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
conda create -n py312-152fz python=3.12 -y
conda activate py312-152fz
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
pyright
```

Примеры команд (Windows PowerShell, `venv`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
python -m pytest
ruff check src tests
pyright
```

Примеры команд (Windows PowerShell, `conda`):

```powershell
conda run -n py312-152fz python -m pytest
conda run -n py312-152fz ruff check src tests
conda run -n py312-152fz pyright
```

## Перед созданием pull request

1. Локально выполнены тесты.
2. Проверены регрессии на границах core/cookies/api.
3. Документация синхронизирована с изменениями.
4. При изменении структуры файлов обновлён `STRUCTURE.md`.
5. Локально выполнен `pyright`. Проверка типов обязательна.

## Правила по коду и документации

- Новая логика сопровождается тестами соответствующего уровня.
- Вклад в переводы приветствуется и рассматривается как полноценный вклад.
- Процедура и требования по переводам: [docs/i18n/README.ru.md](./docs/i18n/README.ru.md).

## Проверка границ задачи

Перед крупными изменениями проверьте:

- `README.ru.md` (публичные границы),
- модульную документацию в `docs/`,
- руководства по участию и переводам.

## Сообщения коммитов

Рекомендуемые префиксы:

- `core: ...`
- `cookies: ...`
- `api: ...`
- `docs: ...`
- `tests: ...`

В сообщении должно быть понятно, что изменено и зачем.

## Сборка переводов перед релизом

- Если изменены `.po`, перед сборкой и публикацией пакета обязательно пересоберите `.mo`:
  `python -m django compilemessages --ignore .venv --ignore node_modules --ignore build --ignore dist`.
- PR с изменением `.po` считается неполным без обновлённых `.mo` в том же change set.
