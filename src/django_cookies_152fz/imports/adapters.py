"""Adapter registry for external cookie import sources."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from django.conf import settings
from django.utils.module_loading import import_string

from django_cookies_152fz.integration_contract import (
    SETTING_COOKIE_CONFIG,
    SETTING_COOKIE_CONFIG_LEGACY,
    ConsentError,
)

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
        raise ConsentError(
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
    config = getattr(settings, SETTING_COOKIE_CONFIG, None)
    if config is None:
        config = getattr(settings, SETTING_COOKIE_CONFIG_LEGACY, {})
    config = config or {}
    if not isinstance(config, Mapping):
        raise ConsentError(f"{SETTING_COOKIE_CONFIG} must be a mapping.")
    adapters = config.get("import_adapters", {})
    if adapters in (None, {}):
        return None
    if not isinstance(adapters, Mapping):
        raise ConsentError("import_adapters must be a mapping.")
    value = adapters.get(code)
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ConsentError(
            f"import_adapters[{code!r}] must be non-empty import path."
        )
    return normalized

