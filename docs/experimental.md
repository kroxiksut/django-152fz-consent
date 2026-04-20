# Experimental

**Версия документа:** `0.1`
**Обновлено:** `2026-04-17`

## 1. Назначение

Этот документ фиксирует experimental-контур пакета: `verified_consents`.

`verified_consents`:
- не заменяет `core`;
- не создаёт отдельный consent-domain;
- усиливает подтверждение выбранных потоков `purpose + document`.

## 2. Включение

```python
INSTALLED_APPS = [
    # ...
    "django_152fz_consent",
    "django_152fz_consent.verified_consents",
]

DJANGO_152FZ_CONSENT = {
    "enable_core": True,
    "enable_verified_consents": True,
}
```

Ограничения:
- `enable_verified_consents=True` допустим только при `enable_core=True`;
- optional app `django_152fz_consent.verified_consents` должен быть подключён в `INSTALLED_APPS`.

## 3. Что входит в experimental-flow

- `VerifiedConsentPolicy` для настройки stricter confirmation по потоку `purpose + document`.
- `VerifiedConsentArtifact` для method-specific данных (файл, hash/meta, `subject_signed_at`).
- Сервисы:
  - `submit_verified_consent()`
  - `confirm_verified_consent()`
  - `reject_verified_consent()`

## 4. Что не обещается

- Готовая production-интеграция с внешними провайдерами подписания.
- Юридическая достаточность сценария без проверки оператором ПДн.
- Автоматическое закрытие всех special-category кейсов.

## 5. Переход и совместимость

Поддерживаются:
- позднее включение `verified_consents` поверх уже работающего `core`;
- migration/backfill legacy `paper_file` в `VerifiedConsentArtifact` без потери исторического audit trail.

## 6. Роль доступа

Операции verified-flow должны выполняться ролью `Ответственный за ПДн`
(`PersonalDataManagerAssignment.can_handle_verified_consents=True`) или пользователем с более высоким staff-доступом.
