"""API permission helpers for privileged consent operations."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import BasePermission

from django_consent_152fz import constants


def get_active_verified_pdm_assignment(user):
    """Return the active PDM assignment allowed for verified consent operations."""

    if not user or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return None

    assignment = getattr(user, "personal_data_manager_assignment", None)
    if assignment is None:
        return None
    if not bool(getattr(assignment, "is_active", False)):
        return None
    if not bool(getattr(assignment, "can_handle_verified_consents", False)):
        return None
    return assignment


def can_access_verified_consent_record(*, user, consent_record) -> bool:
    """Object-level access rule for verified artifact endpoints."""

    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    assignment = get_active_verified_pdm_assignment(user)
    if assignment is None:
        return False
    if assignment.scope_mode == constants.PDM_SCOPE_GLOBAL:
        return True
    if assignment.scope_mode != constants.PDM_SCOPE_DJANGO_GROUPS:
        return False

    subject_user = getattr(consent_record, "user", None)
    if subject_user is None or not getattr(subject_user, "pk", None):
        return False
    group_ids = list(assignment.groups.values_list("id", flat=True))
    if not group_ids:
        return False
    return subject_user.groups.filter(pk__in=group_ids).exists()


class IsStaffOrPersonalDataManager(BasePermission):
    """Allow access only to staff users or active PDM assignees."""

    message = _("Insufficient permissions to manage audience rules.")

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True

        return get_active_verified_pdm_assignment(user) is not None

    def has_object_permission(self, request, view, obj) -> bool:
        return can_access_verified_consent_record(user=request.user, consent_record=obj)
