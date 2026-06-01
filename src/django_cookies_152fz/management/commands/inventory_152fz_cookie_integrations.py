"""Build advisory inventory hints for cookie integrations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from django_cookies_152fz.integration_contract import (
    SETTING_COOKIE_CONFIG,
    SETTING_COOKIE_CONFIG_LEGACY,
)
from django_cookies_152fz.inventory import build_inventory_hints_for_registry_items


class Command(BaseCommand):
    help = (
        "Build advisory inventory hints for cookie integrations and print "
        "a manual-review report."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when cookie inventory hints are disabled in settings.",
        )

    def handle(self, *args, **options) -> None:
        del args
        force = bool(options.get("force"))
        inventory_enabled = _is_inventory_hints_enabled()

        if not inventory_enabled and not force:
            self.stdout.write(
                "Cookie integration inventory: disabled by configuration "
                "(cookie_inventory.enable_registry_hints=false)."
            )
            return

        report = build_inventory_hints_for_registry_items()
        self.stdout.write("Cookie integration inventory:")
        self.stdout.write(
            f"- source={report.get('source', 'unknown')} "
            f"total_integrations={int(report.get('total_integrations', 0) or 0)} "
            f"requires_manual_verification="
            f"{bool(report.get('requires_manual_verification', True))}"
        )
        self.stdout.write(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
        )


def _is_inventory_hints_enabled() -> bool:
    cfg = getattr(settings, SETTING_COOKIE_CONFIG, None)
    if cfg is None:
        cfg = getattr(settings, SETTING_COOKIE_CONFIG_LEGACY, None)
    if not isinstance(cfg, Mapping):
        return False
    inventory = cfg.get("cookie_inventory", {})
    if not isinstance(inventory, Mapping):
        return False
    return bool(inventory.get("enable_registry_hints", False))

