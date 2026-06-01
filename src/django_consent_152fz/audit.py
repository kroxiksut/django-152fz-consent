"""Module-level audit log helpers for admin and service operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.contrib.auth import get_user_model

from django_consent_152fz.core.models import ModuleOperationAuditLog


def log_module_operation(
    *,
    operation_code: str,
    actor_user=None,
    source: str = "",
    status: str = ModuleOperationAuditLog.Status.SUCCESS,
    target_model: str = "",
    target_id: str = "",
    summary: str = "",
    payload: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
) -> ModuleOperationAuditLog:
    """Persist one module operation audit record."""

    normalized_actor_user = _normalize_actor_user(actor_user)
    return ModuleOperationAuditLog.objects.create(
        operation_code=str(operation_code or "").strip()[:128],
        actor_user=normalized_actor_user,
        source=str(source or "").strip()[:128],
        status=str(status or ModuleOperationAuditLog.Status.SUCCESS),
        target_model=str(target_model or "").strip()[:128],
        target_id=str(target_id or "").strip()[:128],
        summary=str(summary or "").strip(),
        payload=dict(payload or {}),
        result=dict(result or {}),
    )


def _normalize_actor_user(actor_user):
    if actor_user is None:
        return None
    user_model = get_user_model()
    if isinstance(actor_user, user_model):
        return actor_user
    return None
