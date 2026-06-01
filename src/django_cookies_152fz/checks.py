"""System checks for cookie app."""

from __future__ import annotations

from django.core.checks import Tags, register


@register(Tags.compatibility)
def check_cookies_base_app(app_configs, **kwargs):  # type: ignore[unused-argument]
    """Cookie app is standalone; no hard dependency on consent app."""

    return []
