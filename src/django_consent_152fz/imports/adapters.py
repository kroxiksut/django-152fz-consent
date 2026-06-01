"""Adapter registry for external import sources.

Core package keeps CSV import as canonical path.
External systems (Bitrix, CRM exports, web-form dumps) can be plugged through
this adapter contract without adding vendor-specific code into core modules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from django.utils.module_loading import import_string

from django_consent_152fz.constants import SETTING_CONFIG, SETTING_CONFIG_LEGACY
from django_consent_152fz.exceptions import ConsentConfigurationError, ConsentError
from django_consent_152fz.settings import django_settings

ImportAdapterCallable = Callable[[Mapping[str, Any]], Iterable[Mapping[str, Any]]]
_RUNTIME_ADAPTER_REGISTRY: dict[str, ImportAdapterCallable] = {}


def register_import_adapter(*, code: str, adapter: ImportAdapterCallable) -> None:
    normalized_code = str(code or "").strip()
    if not normalized_code:
        raise ConsentError("Import adapter code must be non-empty.")
    _RUNTIME_ADAPTER_REGISTRY[normalized_code] = adapter


def get_import_adapter(*, code: str) -> ImportAdapterCallable:
    normalized_code = str(code or "").strip()
    if not normalized_code:
        raise ConsentError("Import adapter code must be non-empty.")
    runtime_adapter = _RUNTIME_ADAPTER_REGISTRY.get(normalized_code)
    if runtime_adapter is not None:
        return runtime_adapter

    configured = _get_configured_adapter_import_path(normalized_code)
    if configured is None:
        raise ConsentError(
            f"Unknown import adapter {normalized_code!r}. "
            "Register it in runtime or via settings import_adapters."
        )
    adapter = import_string(configured)
    if not callable(adapter):
        raise ConsentConfigurationError(
            f"Configured import adapter {normalized_code!r} must be callable."
        )
    return cast(ImportAdapterCallable, adapter)


def run_import_adapter(
    *,
    code: str,
    payload: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    adapter = get_import_adapter(code=code)
    rows = adapter(dict(payload or {}))
    normalized: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, Mapping):
            raise ConsentError(
                f"Import adapter {code!r} returned non-mapping row {item!r}."
            )
        normalized.append(dict(item))
    return normalized


def _get_configured_adapter_import_path(code: str) -> str | None:
    config = getattr(django_settings, SETTING_CONFIG, None)
    if config is None:
        config = getattr(django_settings, SETTING_CONFIG_LEGACY, {})
    config = config or {}
    if not isinstance(config, Mapping):
        raise ConsentConfigurationError(f"{SETTING_CONFIG} must be a mapping.")
    adapters = config.get("import_adapters", {})
    if adapters in (None, {}):
        return None
    if not isinstance(adapters, Mapping):
        raise ConsentConfigurationError("import_adapters must be a mapping.")
    value = adapters.get(code)
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ConsentConfigurationError(
            f"import_adapters[{code!r}] must be non-empty import path."
        )
    return normalized
