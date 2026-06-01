from __future__ import annotations

import pytest
from django.test import RequestFactory, override_settings

from django_cookies_152fz.services import get_cookie_requirements


@override_settings(
    DJANGO_COOKIES_152FZ={
        "enable_cookies": True,
        "cookie_runtime": {
            "geo_signal_hook": "tests.missing.module.geo_hook",
        },
    }
)
@pytest.mark.django_db
def test_invalid_geo_signal_hook_string_falls_back_to_unknown() -> None:
    request = RequestFactory().get("/cookie-requirements/")

    requirements = get_cookie_requirements(request=request)

    assert requirements["runtime"]["geo_signal"] == "unknown"
