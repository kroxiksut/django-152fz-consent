"""Bootstrap command for default cookie-only data."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from django_cookies_152fz.services import (
    bootstrap_cookie_banner_revision,
    bootstrap_default_cookie_policy_revision,
    ensure_default_cookie_categories,
    ensure_default_cookie_registry_items,
)


class Command(BaseCommand):
    """Create default cookie categories, registry items, and initial revisions."""

    help = (
        "Initializes the cookie-only demo contour: creates default cookie categories, "
        "demo registry items, a starter cookie policy revision, and a starter "
        "cookie banner revision. The command is idempotent and does not create "
        "duplicate active revisions."
    )

    def handle(self, *args, **options):
        categories = ensure_default_cookie_categories()
        registry_items = ensure_default_cookie_registry_items()
        policy = bootstrap_default_cookie_policy_revision()
        banner = bootstrap_cookie_banner_revision()

        self.stdout.write(
            self.style.SUCCESS(
                "Cookie defaults processed: "
                f"categories={len(categories)}, "
                f"registry_items={len(registry_items)}, "
                f"policy_created={policy.get('created', False)}, "
                f"banner_created={banner.get('created', False)}."
            )
        )
        self.stdout.write(f"Cookie registry items result: {registry_items}")
        self.stdout.write(f"Cookie policy result: {policy}")
        self.stdout.write(f"Cookie banner result: {banner}")
