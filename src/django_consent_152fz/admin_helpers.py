"""Support layer for the admin implementations in section 5.2.

The module keeps permission logic separate from concrete admin classes:
- resolves access for the `PersonalDataManager` role;
- synchronizes the service Django group with the assignment model;
- provides mixins for restricted and read-only admin interfaces.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from django.contrib import admin
from django.contrib.auth.models import Group


def safe_register_admin_models(
    site: admin.sites.AdminSite,
    *,
    registrations: Sequence[tuple[type, type[admin.ModelAdmin]]],
) -> None:
    """Register admin models idempotently for register_admin(site) contract."""

    for model, model_admin in registrations:
        if model in site._registry:
            continue
        site.register(model, model_admin)


PERSONAL_DATA_MANAGER_GROUP_NAME = "PersonalDataManager"
PERSONAL_DATA_MANAGER_GROUP_LABEL = "Ответственный за ПДн"


def normalize_permission_flags(
    permission_flags: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize a single flag or a collection of flags into a tuple."""

    if permission_flags is None:
        return ()
    if isinstance(permission_flags, str):
        return (permission_flags,)
    return tuple(permission_flags)


def get_active_personal_data_manager_assignment(user):
    """Return the active assignment only for the current staff user."""

    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return None
    assignment = getattr(user, "personal_data_manager_assignment", None)
    if assignment is None or not assignment.is_active:
        return None
    return assignment


def has_personal_data_manager_permission(
    user,
    *,
    permission_flags: str | Iterable[str] | None = None,
) -> bool:
    """Check whether the user can perform package admin actions."""

    if not getattr(user, "is_active", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    assignment = get_active_personal_data_manager_assignment(user)
    if assignment is None:
        return False

    normalized_flags = normalize_permission_flags(permission_flags)
    if not normalized_flags:
        return True
    return any(bool(getattr(assignment, flag, False)) for flag in normalized_flags)


def ensure_personal_data_manager_group() -> Group:
    """Ensure the service Django group for the PD role exists."""

    group, _ = Group.objects.get_or_create(name=PERSONAL_DATA_MANAGER_GROUP_NAME)
    return group


def sync_personal_data_manager_group_membership(*, assignment) -> None:
    """Keep the service group membership in sync with the assignment model."""

    group = ensure_personal_data_manager_group()
    if assignment.is_active and assignment.user.is_staff:
        assignment.user.groups.add(group)
        return
    assignment.user.groups.remove(group)


class AssignmentRestrictedAdminMixin(admin.ModelAdmin):
    """Mixin for admin models whose access is controlled by assignment flags."""

    change_permission_flags: str | Iterable[str] | None = None
    view_permission_flags: str | Iterable[str] | None = None
    superuser_only = False

    def _has_admin_access(
        self,
        request,
        *,
        permission_flags: str | Iterable[str] | None,
    ) -> bool:
        if self.superuser_only:
            return bool(
                getattr(request.user, "is_active", False)
                and getattr(request.user, "is_superuser", False)
            )
        return has_personal_data_manager_permission(
            request.user,
            permission_flags=permission_flags,
        )

    def has_module_permission(self, request) -> bool:
        flags = self.view_permission_flags
        if flags is None:
            flags = self.change_permission_flags
        return self._has_admin_access(request, permission_flags=flags)

    def has_view_permission(self, request, obj=None) -> bool:
        flags = self.view_permission_flags
        if flags is None:
            flags = self.change_permission_flags
        return self._has_admin_access(request, permission_flags=flags)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._has_admin_access(
            request,
            permission_flags=self.change_permission_flags,
        )

    def has_add_permission(self, request) -> bool:
        return self.has_change_permission(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self.has_change_permission(request, obj=obj)


class ReadOnlyAdminMixin(admin.ModelAdmin):
    """Mixin for visible but immutable historical entities."""

    def get_readonly_fields(self, request, obj=None):
        return [
            *[field.name for field in self.model._meta.fields],
            *[field.name for field in self.model._meta.many_to_many],
        ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class PublishableRevisionAdminMixin:
    """Shared helpers for versioned and publishable admin entities."""

    version_field_name = "version"
    is_active_field_name = "is_active"
    published_at_field_name = "published_at"

    def assign_next_version(self, obj, *, latest_version: int) -> None:
        setattr(obj, self.version_field_name, latest_version + 1)

    def ensure_published_at(self, obj, *, now_value) -> None:
        is_active = bool(getattr(obj, self.is_active_field_name, False))
        published_at = getattr(obj, self.published_at_field_name, None)
        if is_active and published_at is None:
            setattr(obj, self.published_at_field_name, now_value)
