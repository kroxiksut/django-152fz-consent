"""CSV import helpers for cookie consent and banner state migration."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from .integration_contract import (
    ConsentError,
    ModuleOperationAuditLog,
    log_module_operation,
)
from .models import (
    CookieBannerState,
    CookieConsentRecord,
    CookiePolicyRevision,
    normalize_categories_snapshot,
)
from .services import accept_cookie_preferences

COOKIE_IMPORT_CONTRACT_VERSION = "cookie_csv_import_v1"
COOKIE_IMPORT_KIND_CONSENT = "consent"
COOKIE_IMPORT_KIND_BANNER_STATE = "banner_state"
_MAX_JSON_CELL_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class CookieImportMapping:
    kind: str
    contract_version: str
    policy_revision_version: str
    policy_categories_snapshot_json: str
    selected_categories_json: str
    user: str
    anonymous_token: str
    source: str
    ip_address: str
    user_agent: str
    locale: str
    request_id: str
    session_key_hash: str
    extra_meta_json: str
    consented_at: str
    decision_action: str
    decided_at: str
    dismissed_at: str


def import_cookie_data_from_csv(
    *,
    csv_path: str,
    mapping: CookieImportMapping,
    dry_run: bool = False,
    source: str = "management.import_152fz_cookie_data",
    actor_user=None,
) -> dict[str, Any]:
    path = Path(csv_path)
    if not path.exists() or not path.is_file():
        raise ConsentError(_("CSV-файл не найден: %(path)s.") % {"path": csv_path})

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ConsentError(_("CSV-файл не содержит строку заголовков."))
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
            try:
                result = _process_row(
                    row=row,
                    row_number=index,
                    mapping=mapping,
                    dry_run=dry_run,
                )
            except Exception as exc:  # pragma: no cover
                result = {"row": index, "status": "error", "detail": str(exc)}
            summary["rows"].append(result)
            if result["status"] == "imported":
                summary["imported"] += 1
            elif result["status"] == "would_import":
                summary["would_import"] += 1
            elif result["status"] == "skipped":
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
        operation_code="service.cookies.import_cookie_data_csv",
        source=source,
        status=audit_status,
        target_model="django_cookies_152fz.CookieConsentRecord",
        summary=_("Импорт записей cookie-согласий и состояния баннера из CSV."),
        actor_user=actor_user,
        payload={"csv_path": str(path), "mapping": asdict(mapping)},
        result={
            "total_rows": summary["total_rows"],
            "imported": summary["imported"],
            "would_import": summary["would_import"],
            "skipped": summary["skipped"],
            "errors": summary["errors"],
        },
    )
    return summary


def _process_row(
    *,
    row: Mapping[str, str],
    row_number: int,
    mapping: CookieImportMapping,
    dry_run: bool,
) -> dict[str, Any]:
    kind = _read(row, mapping.kind) or COOKIE_IMPORT_KIND_CONSENT
    if kind not in {COOKIE_IMPORT_KIND_CONSENT, COOKIE_IMPORT_KIND_BANNER_STATE}:
        return {
            "row": row_number,
            "status": "skipped",
            "detail": _("Неподдерживаемый kind '%(kind)s'.") % {"kind": kind},
        }
    contract_version = _read(row, mapping.contract_version)
    if contract_version != COOKIE_IMPORT_CONTRACT_VERSION:
        return {
            "row": row_number,
            "status": "skipped",
            "detail": (
                _(
                    "Неподдерживаемый contract_version '%(actual)s', ожидается '%(expected)s'."
                )
                % {
                    "actual": contract_version,
                    "expected": COOKIE_IMPORT_CONTRACT_VERSION,
                }
            ),
        }
    user = _resolve_user(_read(row, mapping.user))
    token = _read(row, mapping.anonymous_token)
    if user is None and not token:
        return {
            "row": row_number,
            "status": "skipped",
            "detail": _("Субъект не задан: укажите user или anonymous_token."),
        }
    if kind == COOKIE_IMPORT_KIND_CONSENT:
        return _import_consent_row(
            row=row,
            row_number=row_number,
            mapping=mapping,
            dry_run=dry_run,
            user=user,
            token=token,
        )
    return _import_banner_state_row(
        row=row,
        row_number=row_number,
        mapping=mapping,
        dry_run=dry_run,
        user=user,
        token=token,
    )


def _import_consent_row(
    *,
    row: Mapping[str, str],
    row_number: int,
    mapping: CookieImportMapping,
    dry_run: bool,
    user,
    token: str,
) -> dict[str, Any]:
    revision_version_raw = _read(row, mapping.policy_revision_version)
    if not revision_version_raw.isdigit():
        return {
            "row": row_number,
            "status": "error",
            "detail": _(
                "policy_revision_version должен быть положительным целым числом."
            ),
        }
    revision = CookiePolicyRevision.objects.filter(
        version=int(revision_version_raw)
    ).first()
    if revision is None:
        return {
            "row": row_number,
            "status": "error",
            "detail": _("Редакция политики cookie v%(version)s не найдена.")
            % {"version": revision_version_raw},
        }

    csv_snapshot_raw = _read(row, mapping.policy_categories_snapshot_json)
    if csv_snapshot_raw:
        parsed_snapshot = _load_json_cell(
            csv_snapshot_raw,
            field_name=(
                mapping.policy_categories_snapshot_json
                or "policy_categories_snapshot_json"
            ),
        )
        normalized_csv_snapshot = normalize_categories_snapshot(parsed_snapshot)
        normalized_revision_snapshot = normalize_categories_snapshot(
            revision.categories_snapshot
        )
        if normalized_csv_snapshot != normalized_revision_snapshot:
            return {
                "row": row_number,
                "status": "error",
                "detail": (
                    _(
                        "policy_categories_snapshot_json не совпадает с редакцией политики v%(version)s."
                    )
                    % {"version": revision.version}
                ),
            }

    selected_raw = _read(row, mapping.selected_categories_json)
    selected_categories = _load_json_cell(
        selected_raw or "[]",
        field_name=(mapping.selected_categories_json or "selected_categories_json"),
    )
    if not isinstance(selected_categories, list):
        return {
            "row": row_number,
            "status": "error",
            "detail": _("selected_categories_json должен быть JSON-списком."),
        }

    row_fingerprint = _build_cookie_row_fingerprint(
        policy_revision_version=revision.version,
        user_id=getattr(user, "pk", None),
        anonymous_token=token,
        selected_categories=selected_categories,
    )
    if dry_run:
        if _is_duplicate_cookie_import(
            policy_revision_id=revision.pk,
            user_id=getattr(user, "pk", None),
            anonymous_token=token,
            row_fingerprint=row_fingerprint,
        ):
            return {
                "row": row_number,
                "status": "skipped",
                "detail": _("Дубликат: fingerprint строки уже был импортирован."),
            }
        return {
            "row": row_number,
            "status": "would_import",
            "detail": (
                _(
                    "consent для policy_revision_version=%(version)s, категорий=%(count)s."
                )
                % {"version": revision.version, "count": len(selected_categories)}
            ),
        }

    with transaction.atomic():
        if _is_duplicate_cookie_import(
            policy_revision_id=revision.pk,
            user_id=getattr(user, "pk", None),
            anonymous_token=token,
            row_fingerprint=row_fingerprint,
        ):
            return {
                "row": row_number,
                "status": "skipped",
                "detail": _("Дубликат: fingerprint строки уже был импортирован."),
            }

        audit_context = _build_audit_context(row=row, mapping=mapping)
        record = accept_cookie_preferences(
            selected_categories=selected_categories,
            policy_revision=revision,
            user=user,
            anonymous_token=token or None,
            audit_context=audit_context,
        )
        # import_meta is a reserved system namespace: user-supplied extra_meta
        # cannot set it (see _RESERVED_AUDIT_ROOT_KEYS). Therefore we write the
        # import fingerprint via a trusted update(), bypassing
        # user-level clean()/full_clean() validation.
        trusted_extra_meta = _merge_import_fingerprint(
            extra_meta=record.extra_meta,
            row_fingerprint=row_fingerprint,
        )
        CookieConsentRecord.objects.filter(pk=record.pk).update(
            extra_meta=trusted_extra_meta,
            updated_at=timezone.now(),
        )
        record.extra_meta = trusted_extra_meta

    if getattr(record, "policy_revision_id", None) != revision.pk:
        return {
            "row": row_number,
            "status": "error",
            "detail": (
                _(
                    "Активная редакция политики не совпадает с импортируемой версией v%(version)s."
                )
                % {"version": revision.version}
            ),
        }

    return {
        "row": row_number,
        "status": "imported",
        "detail": _("record_id=%(id)s") % {"id": record.pk},
    }


def _import_banner_state_row(
    *,
    row: Mapping[str, str],
    row_number: int,
    mapping: CookieImportMapping,
    dry_run: bool,
    user,
    token: str,
) -> dict[str, Any]:
    decision_action = _read(row, mapping.decision_action)
    if decision_action and decision_action not in set(
        CookieBannerState.DecisionAction.values
    ):
        return {
            "row": row_number,
            "status": "error",
            "detail": _("Неподдерживаемый decision_action '%(action)s'.")
            % {"action": decision_action},
        }
    decided_at = _parse_dt(_read(row, mapping.decided_at))
    dismissed_at = _parse_dt(_read(row, mapping.dismissed_at))
    if dry_run:
        return {
            "row": row_number,
            "status": "would_import",
            "detail": _("banner_state"),
        }

    state, _created = CookieBannerState.objects.get_or_create(
        user=user if getattr(user, "pk", None) is not None else None,
        anonymous_token=None
        if getattr(user, "pk", None) is not None
        else (token or None),
        defaults={
            "decision_action": decision_action,
            "decided_at": decided_at,
            "dismissed_at": dismissed_at,
        },
    )
    state.decision_action = decision_action
    state.decided_at = decided_at
    state.dismissed_at = dismissed_at
    state.save(
        update_fields=["decision_action", "decided_at", "dismissed_at", "updated_at"]
    )
    return {
        "row": row_number,
        "status": "imported",
        "detail": _("banner_state_id=%(id)s") % {"id": state.pk},
    }


def _read(row: Mapping[str, str], column: str) -> str:
    if not column:
        return ""
    return str(row.get(column, "") or "").strip()


def _resolve_user(raw_value: str):
    if not raw_value:
        return None
    user_model = get_user_model()
    if raw_value.isdigit():
        return user_model.objects.filter(pk=int(raw_value)).first()
    return user_model.objects.filter(username=raw_value).first()


def _parse_dt(raw_value: str):
    if not raw_value:
        return None
    parsed = parse_datetime(raw_value)
    if parsed is None:
        raise ConsentError(_("datetime должен быть в формате ISO."))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _build_audit_context(
    *, row: Mapping[str, str], mapping: CookieImportMapping
) -> dict[str, Any]:
    extra_meta_raw = _read(row, mapping.extra_meta_json)
    extra_meta = (
        _load_json_cell(
            extra_meta_raw,
            field_name=(mapping.extra_meta_json or "extra_meta_json"),
        )
        if extra_meta_raw
        else {}
    )
    if not isinstance(extra_meta, dict):
        raise ConsentError(_("extra_meta_json должен содержать JSON-объект."))
    extra_meta = dict(extra_meta)
    extra_meta.pop("import_meta", None)
    consented_at = _parse_dt(_read(row, mapping.consented_at))
    return {
        "source": _read(row, mapping.source) or "csv_import",
        "ip_address": _read(row, mapping.ip_address) or None,
        "user_agent": _read(row, mapping.user_agent),
        "locale": _read(row, mapping.locale),
        "request_id": _read(row, mapping.request_id),
        "session_key_hash": _read(row, mapping.session_key_hash),
        "extra_meta": extra_meta,
        "occurred_at": consented_at,
    }


def _build_cookie_row_fingerprint(
    *,
    policy_revision_version: int,
    user_id: int | None,
    anonymous_token: str,
    selected_categories: list[str],
) -> str:
    raw = "|".join(
        [
            str(policy_revision_version),
            str(user_id or ""),
            anonymous_token,
            ",".join(sorted(str(item) for item in selected_categories)),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_duplicate_cookie_import(
    *,
    policy_revision_id: int,
    user_id: int | None,
    anonymous_token: str,
    row_fingerprint: str,
) -> bool:
    qs = CookieConsentRecord.objects.filter(
        policy_revision_id=policy_revision_id,
        extra_meta__import_meta__row_fingerprint=row_fingerprint,
    )
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    else:
        qs = qs.filter(user__isnull=True, anonymous_token=anonymous_token)
    return qs.exists()


def _merge_import_fingerprint(
    *,
    extra_meta: Mapping[str, Any] | None,
    row_fingerprint: str,
) -> dict[str, Any]:
    result = dict(extra_meta or {})
    import_meta = dict(result.get("import_meta") or {})
    import_meta["row_fingerprint"] = row_fingerprint
    result["import_meta"] = import_meta
    return result


def _load_json_cell(raw_value: str, *, field_name: str) -> Any:
    payload = str(raw_value or "")
    if len(payload.encode("utf-8")) > _MAX_JSON_CELL_BYTES:
        raise ConsentError(
            f"{field_name} exceeds max JSON size {_MAX_JSON_CELL_BYTES} bytes."
        )
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ConsentError(f"{field_name} contains invalid JSON.") from exc
