"""Retention and cleanup helpers for cookie audit data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models import Q, QuerySet
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.translation import gettext as _

from .integration_contract import (
    ConsentError,
    constants,
    get_cookie_retention_settings,
    log_module_operation,
    trigger_cookie_audit_archive,
)
from .models import CookieBannerState, CookieConsentEvent, CookieConsentRecord

COOKIE_AUDIT_ARCHIVE_CONTRACT_VERSION = "1.0"
TRUSTED_RETENTION_PRIVATE_NAMESPACE = "retention_private"
_TRUSTED_RETENTION_PRIVATE_PATH_PREFIX = f"{TRUSTED_RETENTION_PRIVATE_NAMESPACE}."
_PRIVATE_SIGNAL_SEGMENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class CookieRetentionModelSpec:
    code: str
    model: type
    datetime_field: str
    default_ordering: tuple[str, str]
    older_than_days_setting: str
    max_count_setting: str
    private_older_than_days_setting: str | None = None


@dataclass(frozen=True)
class CookieRetentionSpecSettings:
    older_than_days: int
    private_older_than_days: int
    max_count: int


COOKIE_RETENTION_MODEL_SPECS: tuple[CookieRetentionModelSpec, ...] = (
    CookieRetentionModelSpec(
        code="events",
        model=CookieConsentEvent,
        datetime_field="occurred_at",
        default_ordering=("occurred_at", "pk"),
        older_than_days_setting=constants.CONFIG_COOKIE_RETENTION_EVENTS_OLDER_THAN_DAYS,
        max_count_setting=constants.CONFIG_COOKIE_RETENTION_EVENTS_MAX_COUNT,
        private_older_than_days_setting=(
            constants.CONFIG_COOKIE_RETENTION_PRIVATE_EVENTS_OLDER_THAN_DAYS
        ),
    ),
    CookieRetentionModelSpec(
        code="records",
        model=CookieConsentRecord,
        datetime_field="created_at",
        default_ordering=("created_at", "pk"),
        older_than_days_setting=(
            constants.CONFIG_COOKIE_RETENTION_RECORDS_OLDER_THAN_DAYS
        ),
        max_count_setting=constants.CONFIG_COOKIE_RETENTION_RECORDS_MAX_COUNT,
        private_older_than_days_setting=(
            constants.CONFIG_COOKIE_RETENTION_PRIVATE_RECORDS_OLDER_THAN_DAYS
        ),
    ),
    CookieRetentionModelSpec(
        code="banner_states",
        model=CookieBannerState,
        datetime_field="updated_at",
        default_ordering=("updated_at", "pk"),
        older_than_days_setting=(
            constants.CONFIG_COOKIE_RETENTION_BANNER_STATES_OLDER_THAN_DAYS
        ),
        max_count_setting=constants.CONFIG_COOKIE_RETENTION_BANNER_STATES_MAX_COUNT,
    ),
)


def cleanup_cookie_audit(
    *,
    dry_run: bool = False,
    report_only: bool = False,
    batch_size: int | None = None,
    older_than_days: int | None = None,
    actor_user=None,
    source: str = "cookies.retention.cleanup",
    using: str = DEFAULT_DB_ALIAS,
    now=None,
) -> dict[str, Any]:
    """Cleanup cookie audit data using retention settings."""

    if isinstance(older_than_days, bool) or (
        older_than_days is not None and older_than_days < 0
    ):
        raise ValueError(
            _("older_than_days должен быть неотрицательным целым числом или None.")
        )

    retention_settings = get_cookie_retention_settings()
    effective_batch_size = (
        _parse_non_negative_int(
            setting_name=constants.CONFIG_COOKIE_RETENTION_BATCH_SIZE,
            value=retention_settings[constants.CONFIG_COOKIE_RETENTION_BATCH_SIZE],
        )
        if batch_size is None
        else _parse_non_negative_int(
            setting_name="batch_size",
            value=batch_size,
        )
    )
    if isinstance(effective_batch_size, bool) or effective_batch_size <= 0:
        raise ValueError(_("batch_size должен быть положительным целым числом."))

    model_settings = _build_cookie_retention_model_settings(
        retention_settings=retention_settings,
        older_than_days_override=older_than_days,
    )

    timestamp = now or timezone.now()
    model_reports: list[dict[str, Any]] = []
    total_deleted = 0

    for spec in COOKIE_RETENTION_MODEL_SPECS:
        report = _cleanup_cookie_audit_model(
            spec=spec,
            retention_settings=retention_settings,
            spec_settings=model_settings[spec.code],
            dry_run=dry_run,
            report_only=report_only,
            batch_size=effective_batch_size,
            using=using,
            now_value=timestamp,
        )
        total_deleted += int(report["deleted_total"])
        model_reports.append(report)

    summary = {
        "dry_run": bool(dry_run),
        "report_only": bool(report_only),
        "batch_size": effective_batch_size,
        "older_than_days_override": older_than_days,
        "total_deleted": total_deleted,
        "models": model_reports,
    }
    log_module_operation(
        operation_code="service.cookies.cleanup_cookie_audit",
        actor_user=actor_user,
        source=source,
        status=("dry_run" if (dry_run or report_only) else "success"),
        target_model="django_cookies_152fz.CookieAudit",
        summary=_("Очистка cookie-аудита по политике хранения."),
        payload={
            "dry_run": bool(dry_run),
            "report_only": bool(report_only),
            "batch_size": effective_batch_size,
            "older_than_days_override": older_than_days,
            "database": using,
        },
        result={"total_deleted": total_deleted, "models": model_reports},
    )
    return summary


def _cleanup_cookie_audit_model(
    *,
    spec: CookieRetentionModelSpec,
    retention_settings: dict[str, object],
    spec_settings: CookieRetentionSpecSettings,
    dry_run: bool,
    report_only: bool,
    batch_size: int,
    using: str,
    now_value,
) -> dict[str, Any]:
    queryset = spec.model.objects.using(using).all()
    before_count = queryset.count()
    deletable_queryset = _build_deletable_queryset(
        queryset=queryset,
        spec=spec,
        retention_settings=retention_settings,
    )
    protected_current_count = max(before_count - deletable_queryset.count(), 0)

    older_than_days_value = spec_settings.older_than_days
    private_older_than_days_value = spec_settings.private_older_than_days
    max_count_value = spec_settings.max_count

    age_queryset = _build_age_cleanup_queryset(
        queryset=deletable_queryset,
        spec=spec,
        retention_settings=retention_settings,
        older_than_days=older_than_days_value,
        private_older_than_days=private_older_than_days_value,
        now_value=now_value,
    )
    age_candidates = age_queryset.count()

    deleted_age_count = 0
    age_candidate_ids: list[int] = []
    if not dry_run and not report_only and age_candidates:
        deleted_age_count = _delete_queryset_in_batches(
            spec=spec,
            queryset=age_queryset,
            batch_size=batch_size,
            reason="older_than_days",
            using=using,
            dry_run=dry_run,
            report_only=report_only,
            now_value=now_value,
        )
    elif dry_run or report_only:
        age_candidate_ids = list(age_queryset.values_list("pk", flat=True))

    deletable_after_age_queryset = (
        _build_deletable_queryset(
            queryset=spec.model.objects.using(using).all(),
            spec=spec,
            retention_settings=retention_settings,
        )
        if not (dry_run or report_only)
        else (
            deletable_queryset.exclude(pk__in=age_candidate_ids)
            if age_candidate_ids
            else deletable_queryset
        )
    )
    max_candidate_ids = _select_max_count_candidate_ids(
        spec=spec,
        queryset=deletable_after_age_queryset,
        max_count=max_count_value,
    )
    max_candidates = len(max_candidate_ids)

    deleted_max_count = 0
    if not dry_run and not report_only and max_candidate_ids:
        deleted_max_count = _delete_ids_in_batches(
            spec=spec,
            ids=max_candidate_ids,
            batch_size=batch_size,
            reason="max_count",
            using=using,
            dry_run=dry_run,
            report_only=report_only,
            now_value=now_value,
        )

    deleted_total = deleted_age_count + deleted_max_count
    remaining_count = (
        before_count - age_candidates - max_candidates
        if dry_run or report_only
        else spec.model.objects.using(using).count()
    )

    return {
        "model": spec.model._meta.label,
        "model_code": spec.code,
        "before_count": before_count,
        "remaining_count": max(remaining_count, 0),
        "protected_current_count": protected_current_count,
        "older_than_days": older_than_days_value,
        "private_older_than_days": private_older_than_days_value,
        "max_count": max_count_value,
        "age_candidates": age_candidates,
        "max_count_candidates": max_candidates,
        "deleted_age_count": deleted_age_count,
        "deleted_max_count": deleted_max_count,
        "deleted_total": deleted_total,
    }


def _build_deletable_queryset(
    *,
    queryset: QuerySet,
    spec: CookieRetentionModelSpec,
    retention_settings: dict[str, object],
) -> QuerySet:
    protect_current_records = bool(
        retention_settings[constants.CONFIG_COOKIE_RETENTION_PROTECT_CURRENT_RECORDS]
    )
    if not protect_current_records:
        return queryset

    if spec.code == "records":
        return queryset.exclude(status=CookieConsentRecord.Status.CURRENT)
    if spec.code == "events":
        return queryset.exclude(
            cookie_consent_record__status=CookieConsentRecord.Status.CURRENT
        )
    return queryset


def _build_age_cleanup_queryset(
    *,
    queryset: QuerySet,
    spec: CookieRetentionModelSpec,
    retention_settings: dict[str, object],
    older_than_days: int,
    private_older_than_days: int,
    now_value,
) -> QuerySet:
    if older_than_days <= 0 and private_older_than_days <= 0:
        return queryset.none()

    cleanup_q = Q()
    if older_than_days > 0:
        cleanup_q |= Q(
            **{
                f"{spec.datetime_field}__lt": (
                    now_value - timedelta(days=older_than_days)
                )
            }
        )

    if private_older_than_days > 0 and spec.private_older_than_days_setting:
        cleanup_q |= _build_private_mode_query(
            spec=spec,
            retention_settings=retention_settings,
            threshold=now_value - timedelta(days=private_older_than_days),
        )

    return queryset.filter(cleanup_q)


def _build_private_mode_query(
    *,
    spec: CookieRetentionModelSpec,
    retention_settings: dict[str, object],
    threshold,
) -> Q:
    if spec.code not in {"records", "events"}:
        return Q(pk__in=[])

    raw_private_signal_paths = retention_settings[
        constants.CONFIG_COOKIE_RETENTION_PRIVATE_SIGNAL_PATHS
    ]
    if not isinstance(raw_private_signal_paths, (list, tuple)):
        return Q(pk__in=[])
    private_signal_paths = list(raw_private_signal_paths)
    private_flags_q = Q(pk__in=[])
    true_like_values = (True, 1, "1", "true", "True", "yes", "on")
    for path in private_signal_paths:
        lookup_path = _normalize_trusted_private_lookup_path(path)
        if not lookup_path:
            continue
        for value in true_like_values:
            private_flags_q |= Q(**{f"extra_meta__{lookup_path}": value})
            if spec.code == "events":
                private_flags_q |= Q(
                    **{(f"cookie_consent_record__extra_meta__{lookup_path}"): value}
                )

    if private_flags_q == Q(pk__in=[]):
        return Q(pk__in=[])
    return private_flags_q & Q(**{f"{spec.datetime_field}__lt": threshold})


def _normalize_trusted_private_lookup_path(path: object) -> str | None:
    raw_path = str(path or "").strip()
    if not raw_path.startswith(_TRUSTED_RETENTION_PRIVATE_PATH_PREFIX):
        return None
    segments = [segment for segment in raw_path.split(".") if segment]
    if not segments:
        return None
    if segments[0] != TRUSTED_RETENTION_PRIVATE_NAMESPACE:
        return None
    if not all(_PRIVATE_SIGNAL_SEGMENT_RE.fullmatch(segment) for segment in segments):
        return None
    if len(segments) <= 1:
        return None
    return "__".join(segments)


def _delete_queryset_in_batches(
    *,
    spec: CookieRetentionModelSpec,
    queryset: QuerySet,
    batch_size: int,
    reason: str,
    using: str,
    dry_run: bool,
    report_only: bool,
    now_value,
) -> int:
    deleted_total = 0
    batch_number = 0
    attempted_ids: set[int] = set()
    stalled_batches = 0

    while True:
        batch_queryset = queryset
        if attempted_ids:
            batch_queryset = batch_queryset.exclude(pk__in=attempted_ids)
        ids = list(
            batch_queryset.order_by(*spec.default_ordering).values_list(
                "pk", flat=True
            )[:batch_size]
        )
        if not ids:
            break

        batch_number += 1
        archive_accepted = _trigger_cookie_archive_hook(
            spec=spec,
            batch_ids=ids,
            reason=reason,
            batch_number=batch_number,
            using=using,
            dry_run=dry_run,
            report_only=report_only,
            now_value=now_value,
        )
        _ensure_cookie_archive_available_for_batch(
            spec=spec,
            archive_accepted=archive_accepted,
        )

        with transaction.atomic(using=using):
            deleted_count = _delete_ids_resilient(
                model=spec.model,
                ids=ids,
                using=using,
            )
        attempted_ids.update(ids)
        if deleted_count == 0:
            stalled_batches += 1
            if stalled_batches >= 3:
                break
        else:
            stalled_batches = 0
        deleted_total += int(deleted_count)

    return deleted_total


def _delete_ids_in_batches(
    *,
    spec: CookieRetentionModelSpec,
    ids: list[int],
    batch_size: int,
    reason: str,
    using: str,
    dry_run: bool,
    report_only: bool,
    now_value,
) -> int:
    deleted_total = 0
    batch_number = 0
    ordered_ids = list(
        spec.model.objects.using(using)
        .filter(pk__in=ids)
        .order_by(*spec.default_ordering)
        .values_list("pk", flat=True)
    )
    for index in range(0, len(ordered_ids), batch_size):
        batch_ids = ordered_ids[index : index + batch_size]
        if not batch_ids:
            continue
        batch_number += 1
        archive_accepted = _trigger_cookie_archive_hook(
            spec=spec,
            batch_ids=batch_ids,
            reason=reason,
            batch_number=batch_number,
            using=using,
            dry_run=dry_run,
            report_only=report_only,
            now_value=now_value,
        )
        _ensure_cookie_archive_available_for_batch(
            spec=spec,
            archive_accepted=archive_accepted,
        )

        with transaction.atomic(using=using):
            deleted_count = _delete_ids_resilient(
                model=spec.model,
                ids=batch_ids,
                using=using,
            )
        deleted_total += int(deleted_count)

    return deleted_total


def _trigger_cookie_archive_hook(
    *,
    spec: CookieRetentionModelSpec,
    batch_ids: list[int],
    reason: str,
    batch_number: int,
    using: str,
    dry_run: bool,
    report_only: bool,
    now_value,
) -> bool:
    archive_ack = trigger_cookie_audit_archive(
        {
            "contract_version": COOKIE_AUDIT_ARCHIVE_CONTRACT_VERSION,
            "event_name": "cookie_audit.archive_requested",
            "model": spec.model._meta.label,
            "model_code": spec.code,
            "reason": reason,
            "batch_number": batch_number,
            "batch_size": len(batch_ids),
            "batch_ids": list(batch_ids),
            "database": using,
            "dry_run": bool(dry_run),
            "report_only": bool(report_only),
            "requested_at": now_value.isoformat(),
        }
    )
    return bool(archive_ack)


def _delete_ids_resilient(*, model, ids: list[int], using: str) -> int:
    """Delete rows by ids and skip protected objects without raising."""

    # Use _base_manager to bypass immutable custom managers (for audit events).
    queryset = model._base_manager.using(using).filter(pk__in=ids)
    try:
        deleted_count, _ = queryset.delete()
        return int(deleted_count)
    except ProtectedError:
        deleted_total = 0
        for object_id in ids:
            try:
                deleted_count, _ = (
                    model._base_manager.using(using).filter(pk=object_id).delete()
                )
            except ProtectedError:
                continue
            deleted_total += int(deleted_count)
        return deleted_total


def _build_cookie_retention_model_settings(
    *,
    retention_settings: dict[str, object],
    older_than_days_override: int | None,
) -> dict[str, CookieRetentionSpecSettings]:
    settings_by_model: dict[str, CookieRetentionSpecSettings] = {}
    for spec in COOKIE_RETENTION_MODEL_SPECS:
        older_than_days = (
            older_than_days_override
            if older_than_days_override is not None
            else _parse_non_negative_int(
                setting_name=spec.older_than_days_setting,
                value=retention_settings[spec.older_than_days_setting],
            )
        )
        private_older_than_days = 0
        if older_than_days_override is None and spec.private_older_than_days_setting:
            private_older_than_days = _parse_non_negative_int(
                setting_name=spec.private_older_than_days_setting,
                value=retention_settings[spec.private_older_than_days_setting],
            )
        max_count = _parse_non_negative_int(
            setting_name=spec.max_count_setting,
            value=retention_settings[spec.max_count_setting],
        )
        settings_by_model[spec.code] = CookieRetentionSpecSettings(
            older_than_days=older_than_days,
            private_older_than_days=private_older_than_days,
            max_count=max_count,
        )
    return settings_by_model


def _parse_non_negative_int(*, setting_name: str, value: object) -> int:
    if value in {None, ""}:
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{setting_name} must be a non-negative integer.")
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"{setting_name} must be a non-negative integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{setting_name} must be a non-negative integer.") from exc
    if parsed < 0:
        raise ValueError(f"{setting_name} must be a non-negative integer.")
    return parsed


def _select_max_count_candidate_ids(
    *,
    spec: CookieRetentionModelSpec,
    queryset: QuerySet,
    max_count: int,
) -> list[int]:
    if max_count <= 0:
        return []
    deletable_count = queryset.count()
    if deletable_count <= max_count:
        return []
    delete_count = min(deletable_count - max_count, deletable_count)
    return list(
        queryset.order_by(*spec.default_ordering).values_list("pk", flat=True)[
            :delete_count
        ]
    )


def _ensure_cookie_archive_available_for_batch(
    *,
    spec: CookieRetentionModelSpec,
    archive_accepted: bool,
) -> None:
    if spec.code == "events" and not archive_accepted:
        raise ConsentError(
            "CookieConsentEvent retention delete requires an archive sink acknowledgement."
        )
