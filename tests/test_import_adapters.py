from __future__ import annotations

import pytest
from django.test import override_settings

from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.imports.adapters import (
    get_import_adapter,
    register_import_adapter,
    run_import_adapter,
)


def _settings_adapter(payload):
    return [{"value": payload.get("value", "ok")}]


def test_register_and_run_runtime_import_adapter() -> None:
    register_import_adapter(
        code="runtime_demo",
        adapter=lambda payload: [{"row": payload.get("row", 1)}],
    )
    rows = run_import_adapter(code="runtime_demo", payload={"row": 7})
    assert rows == [{"row": 7}]


@override_settings(
    DJANGO_152FZ_CONSENT={
        "import_adapters": {
            "settings_demo": "tests.test_import_adapters._settings_adapter",
        }
    }
)
def test_get_import_adapter_from_settings_import_path() -> None:
    adapter = get_import_adapter(code="settings_demo")
    assert adapter({"value": "x"}) == [{"value": "x"}]


def test_get_import_adapter_raises_on_unknown_code() -> None:
    with pytest.raises(ConsentError):
        get_import_adapter(code="unknown_adapter")
