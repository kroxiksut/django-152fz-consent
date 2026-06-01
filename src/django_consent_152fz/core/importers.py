"""CSV import helpers for baseline core consent migration flows."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from django_consent_152fz import constants
from django_consent_152fz.audit import log_module_operation
from django_consent_152fz.core.models import ConsentRecord, ModuleOperationAuditLog
from django_consent_152fz.core.services import (
    accept_consent,
    mark_outdated_consents,
    withdraw_consent,
)
from django_consent_152fz.exceptions import ConsentError

MAX_EXTRA_META_JSON_BYTES = 64 * 1024
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoreConsentImportMapping:
    purpose_code: str
    document_code: str
    status: str
    user: str
    anonymous_token: str
    consented_at: str
    source: str
    ip_address: str
    user_agent: str
    locale: str
    request_id: str
    session_key_hash: str
    extra_meta_json: str


@dataclass(frozen=True, slots=True)
class CoreConsentImportRowResult:
    row_number: int
    status: str
    detail: str


def import_core_consents_from_csv(
    *,
    csv_path: str,
    mapping: CoreConsentImportMapping,
    dry_run: bool = False,
    source: str = "management.import_152fz_core_consents",
    actor_user=None,
) -> dict[str, Any]:
    """Import baseline core consents from CSV with explicit column mapping."""
    path = Path(csv_path)
    if not path.exists() or not path.is_file():
        raise ConsentError(f"CSV file not found: {csv_path}")

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ConsentError("CSV file has no header row.")

        required_columns = {
            mapping.purpose_code,
            mapping.document_code,
            mapping.status,
        }
        missing_columns = sorted(
            column for column in required_columns if column not in reader.fieldnames
        )
        if missing_columns:
            raise ConsentError(
                f"CSV mapping references missing columns: {', '.join(missing_columns)}"
            )

        summary: dict[str, Any] = {
            "dry_run": bool(dry_run),
            "source": source,
            "total_rows": 0,
            "imported": 0,
            "would_import": 0,
            "skipped": 0,
            "errors": 0,
            "rows": [],
        }

        for index, row in enumerate(reader, start=2):
            summary["total_rows"] += 1
            row_result = _process_one_row(
                row_number=index,
                row=row,
                mapping=mapping,
                dry_run=dry_run,
            )
            summary["rows"].append(
                {
                    "row": row_result.row_number,
                    "status": row_result.status,
                    "detail": row_result.detail,
                }
            )
            if row_result.status == "imported":
                summary["imported"] += 1
            elif row_result.status == "would_import":
                summary["would_import"] += 1
            elif row_result.status == "skipped":
                summary["skipped"] += 1
            else:
                summary["errors"] += 1

    audit_status = (
        ModuleOperationAuditLog.Status.DRY_RUN
        if dry_run
        else (
            ModuleOperationAuditLog.Status.ERROR
            if summary["errors"] > 0
            else ModuleOperationAuditLog.Status.SUCCESS
        )
    )
    log_module_operation(
        operation_code="service.core.import_consents_csv",
        source=source,
        status=audit_status,
        target_model="django_consent_152fz.ConsentRecord",
        summary="Import baseline core consents from CSV.",
        actor_user=actor_user,
        payload={
            "csv_path": str(path),
            "mapping": asdict(mapping),
        },
        result={
            "total_rows": summary["total_rows"],
            "imported": summary["imported"],
            "would_import": summary["would_import"],
            "skipped": summary["skipped"],
            "errors": summary["errors"],
        },
    )
    return summary


def _process_one_row(
    *,
    row_number: int,
    row: Mapping[str, str],
    mapping: CoreConsentImportMapping,
    dry_run: bool,
) -> CoreConsentImportRowResult:
    try:
        purpose_code = _read_row_value(row=row, column=mapping.purpose_code)
        document_code = _read_row_value(row=row, column=mapping.document_code)
        target_status = (
            _read_row_value(row=row, column=mapping.status)
            or ConsentRecord.Status.CURRENT
        )
        if target_status not in {
            ConsentRecord.Status.CURRENT,
            ConsentRecord.Status.WITHDRAWN,
            ConsentRecord.Status.OUTDATED,
        }:
            return CoreConsentImportRowResult(
                row_number=row_number,
                status="skipped",
                detail=(
                    f"unsupported status '{target_status}', "
                    "only current/withdrawn/outdated are supported"
                ),
            )

        user = _resolve_user(row=row, mapping=mapping)
        anonymous_token = _read_row_value(row=row, column=mapping.anonymous_token)
        if user is None and not anonymous_token:
            return CoreConsentImportRowResult(
                row_number=row_number,
                status="skipped",
                detail="subject is empty: provide user or anonymous_token",
            )

        raw_consented_at = _read_row_value(row=row, column=mapping.consented_at)
        consented_at, has_explicit_consented_at = _parse_consented_at(raw_consented_at)
        audit_context = _build_audit_context(
            row=row, mapping=mapping, consented_at=consented_at
        )
        row_fingerprint = _build_row_fingerprint(
            purpose_code=purpose_code,
            document_code=document_code,
            target_status=target_status,
            user_id=getattr(user, "pk", None),
            anonymous_token=anonymous_token,
            consented_at=consented_at if has_explicit_consented_at else None,
        )
        if dry_run:
            return CoreConsentImportRowResult(
                row_number=row_number,
                status="would_import",
                detail=f"{purpose_code}/{document_code} as {target_status}",
            )

        with transaction.atomic():
            if _is_duplicate_core_import(
                purpose_code=purpose_code,
                document_code=document_code,
                user_id=getattr(user, "pk", None),
                anonymous_token=anonymous_token,
                row_fingerprint=row_fingerprint,
            ):
                return CoreConsentImportRowResult(
                    row_number=row_number,
                    status="skipped",
                    detail="duplicate row fingerprint already imported",
                )

            record = accept_consent(
                purpose_code=purpose_code,
                document_code=document_code,
                user=user,
                anonymous_token=anonymous_token or None,
                confirmation_method=constants.CONFIRMATION_METHOD_API_ACCEPT,
                source=str(audit_context.get("source") or "csv_import"),
                audit_context=_merge_import_fingerprint(
                    audit_context=audit_context,
                    row_fingerprint=row_fingerprint,
                ),
                confirmed_at=consented_at,
            )
            if target_status == ConsentRecord.Status.WITHDRAWN:
                withdraw_consent(
                    purpose_code=purpose_code,
                    document_code=document_code,
                    user=user,
                    anonymous_token=anonymous_token or None,
                    audit_context=audit_context,
                )
            elif target_status == ConsentRecord.Status.OUTDATED:
                mark_outdated_consents(
                    purpose_code=purpose_code,
                    document_code=document_code,
                    user=user,
                    anonymous_token=anonymous_token or None,
                    audit_context=audit_context,
                )

        return CoreConsentImportRowResult(
            row_number=row_number,
            status="imported",
            detail=f"record_id={record.pk}",
        )
    except (ConsentError, DatabaseError, ValueError, TypeError, RuntimeError) as exc:
        logger.warning(
            "Core consent CSV row import failed: row=%s purpose=%r document=%r error=%s",
            row_number,
            _read_row_value(row=row, column=mapping.purpose_code),
            _read_row_value(row=row, column=mapping.document_code),
            exc,
            exc_info=True,
        )
        return CoreConsentImportRowResult(
            row_number=row_number,
            status="error",
            detail=str(exc),
        )


def _read_row_value(*, row: Mapping[str, str], column: str) -> str:
    if not column:
        return ""
    return str(row.get(column, "") or "").strip()


def _resolve_user(*, row: Mapping[str, str], mapping: CoreConsentImportMapping):
    raw_value = _read_row_value(row=row, column=mapping.user)
    if not raw_value:
        return None
    user_model = get_user_model()
    if raw_value.isdigit():
        return user_model.objects.filter(pk=int(raw_value)).first()
    return user_model.objects.filter(username=raw_value).first()


def _parse_consented_at(raw_value: str):
    if not raw_value:
        return timezone.now(), False
    parsed = parse_datetime(raw_value)
    if parsed is None:
        raise ConsentError(
            "consented_at must be ISO datetime, for example 2026-01-20T10:00:00+03:00"
        )
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone()), True
    return parsed, True


def _build_audit_context(
    *,
    row: Mapping[str, str],
    mapping: CoreConsentImportMapping,
    consented_at,
) -> dict[str, Any]:
    extra_meta_raw = _read_row_value(row=row, column=mapping.extra_meta_json)
    extra_meta: dict[str, Any] = {}
    if extra_meta_raw:
        if len(extra_meta_raw.encode("utf-8")) > MAX_EXTRA_META_JSON_BYTES:
            raise ConsentError("extra_meta_json is too large (max 65536 bytes).")
        parsed_meta = json.loads(extra_meta_raw)
        if not isinstance(parsed_meta, dict):
            raise ConsentError("extra_meta_json must contain a JSON object.")
        extra_meta = parsed_meta

    return {
        "source": _read_row_value(row=row, column=mapping.source) or "csv_import",
        "ip_address": _read_row_value(row=row, column=mapping.ip_address) or None,
        "user_agent": _read_row_value(row=row, column=mapping.user_agent),
        "locale": _read_row_value(row=row, column=mapping.locale),
        "request_id": _read_row_value(row=row, column=mapping.request_id),
        "session_key_hash": _read_row_value(row=row, column=mapping.session_key_hash),
        "extra_meta": extra_meta,
        "occurred_at": consented_at,
    }


def _build_row_fingerprint(
    *,
    purpose_code: str,
    document_code: str,
    target_status: str,
    user_id: int | None,
    anonymous_token: str,
    consented_at,
) -> str:
    parts = [
        purpose_code,
        document_code,
        target_status,
        str(user_id or ""),
        anonymous_token,
    ]
    if consented_at is not None:
        parts.append(consented_at.isoformat())
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _merge_import_fingerprint(
    *, audit_context: dict[str, Any], row_fingerprint: str
) -> dict[str, Any]:
    result = dict(audit_context)
    extra_meta = dict(result.get("extra_meta") or {})
    custom_meta = dict(extra_meta.get("custom") or {})
    import_meta = dict(custom_meta.get("import_meta") or {})
    import_meta["row_fingerprint"] = row_fingerprint
    custom_meta["import_meta"] = import_meta
    extra_meta["custom"] = custom_meta
    result["extra_meta"] = extra_meta
    return result


def _is_duplicate_core_import(
    *,
    purpose_code: str,
    document_code: str,
    user_id: int | None,
    anonymous_token: str,
    row_fingerprint: str,
) -> bool:
    qs = ConsentRecord.objects.select_related(
        "purpose", "document_revision__document"
    ).filter(
        purpose__code=purpose_code,
        document_revision__document__code=document_code,
    )
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    else:
        qs = qs.filter(anonymous_token=anonymous_token)
    return qs.filter(
        Q(extra_meta__import_meta__row_fingerprint=row_fingerprint)
        | Q(extra_meta__custom__import_meta__row_fingerprint=row_fingerprint)
    ).exists()
