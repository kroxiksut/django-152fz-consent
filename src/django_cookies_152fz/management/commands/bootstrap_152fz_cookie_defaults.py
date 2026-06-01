"""Bootstrap command for default cookie-only data."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from django_cookies_152fz.services import (
    bootstrap_cookie_banner_revision,
    bootstrap_default_cookie_policy_revision,
    ensure_default_cookie_categories,
)


class Command(BaseCommand):
    """Create default cookie categories and initial policy/banner revisions."""

    help = (
        "Инициализирует cookie-only контур: создаёт коробочные категории cookie, "
        "стартовую редакцию политики cookie и стартовую редакцию cookie-баннера. "
        "Команда идемпотентна и не создаёт дубли активных ревизий."
    )

    def handle(self, *args, **options):
        categories = ensure_default_cookie_categories()
        policy = bootstrap_default_cookie_policy_revision()
        banner = bootstrap_cookie_banner_revision()

        self.stdout.write(
            self.style.SUCCESS(
                "Cookie defaults обработаны: "
                f"categories={len(categories)}, "
                f"policy_created={policy.get('created', False)}, "
                f"banner_created={banner.get('created', False)}."
            )
        )
        self.stdout.write(f"Результат политики cookie: {policy}")
        self.stdout.write(f"Результат cookie-баннера: {banner}")
