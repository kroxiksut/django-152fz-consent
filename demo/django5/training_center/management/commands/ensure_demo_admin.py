from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update demo admin user (admin/admin)."

    def handle(self, *args, **options):
        user_model = get_user_model()
        username = "admin"
        password = "admin"

        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "email": "admin@example.local",
            },
        )

        user_obj = cast(Any, user)
        user_obj.is_staff = True
        user_obj.is_superuser = True
        user_obj.is_active = True
        if hasattr(user_obj, "email") and not user_obj.email:
            user_obj.email = "admin@example.local"
        user_obj.set_password(password)
        user_obj.save()

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{action} demo admin: {username}/{password}")
        )
