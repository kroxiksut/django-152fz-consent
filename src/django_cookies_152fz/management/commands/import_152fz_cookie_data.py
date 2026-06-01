"""CSV import command for cookie consent and banner state data."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from django_cookies_152fz.importers import (
    CookieImportMapping,
    import_cookie_data_from_csv,
)
from django_cookies_152fz.imports.adapters import run_import_adapter


class Command(BaseCommand):
    help = (
        "Import cookie consent and banner state from CSV using explicit "
        "contract and column mapping."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--csv-path", default="", help="Path to CSV file.")
        parser.add_argument(
            "--adapter-code", default="", help="External import adapter code."
        )
        parser.add_argument(
            "--adapter-payload-json",
            default="{}",
            help="JSON payload passed to external adapter callable.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Preview only.")
        parser.add_argument(
            "--actor-user",
            default="",
            help="Operator user id or username for module audit log.",
        )

        parser.add_argument("--col-kind", default="kind")
        parser.add_argument("--col-contract-version", default="contract_version")
        parser.add_argument(
            "--col-policy-revision-version", default="policy_revision_version"
        )
        parser.add_argument(
            "--col-policy-categories-snapshot-json",
            default="policy_categories_snapshot_json",
        )
        parser.add_argument(
            "--col-selected-categories-json", default="selected_categories_json"
        )
        parser.add_argument("--col-user", default="user")
        parser.add_argument("--col-anon", default="anonymous_token")
        parser.add_argument("--col-source", default="source")
        parser.add_argument("--col-ip", default="ip_address")
        parser.add_argument("--col-user-agent", default="user_agent")
        parser.add_argument("--col-locale", default="locale")
        parser.add_argument("--col-request-id", default="request_id")
        parser.add_argument("--col-session-key-hash", default="session_key_hash")
        parser.add_argument("--col-extra-meta-json", default="extra_meta_json")
        parser.add_argument("--col-consented-at", default="consented_at")
        parser.add_argument("--col-decision-action", default="decision_action")
        parser.add_argument("--col-decided-at", default="decided_at")
        parser.add_argument("--col-dismissed-at", default="dismissed_at")

    def handle(self, *args, **options):
        mapping = CookieImportMapping(
            kind=options["col_kind"],
            contract_version=options["col_contract_version"],
            policy_revision_version=options["col_policy_revision_version"],
            policy_categories_snapshot_json=options[
                "col_policy_categories_snapshot_json"
            ],
            selected_categories_json=options["col_selected_categories_json"],
            user=options["col_user"],
            anonymous_token=options["col_anon"],
            source=options["col_source"],
            ip_address=options["col_ip"],
            user_agent=options["col_user_agent"],
            locale=options["col_locale"],
            request_id=options["col_request_id"],
            session_key_hash=options["col_session_key_hash"],
            extra_meta_json=options["col_extra_meta_json"],
            consented_at=options["col_consented_at"],
            decision_action=options["col_decision_action"],
            decided_at=options["col_decided_at"],
            dismissed_at=options["col_dismissed_at"],
        )
        try:
            csv_path = self._resolve_csv_path(options=options, mapping=mapping)
            summary = import_cookie_data_from_csv(
                csv_path=csv_path,
                mapping=mapping,
                dry_run=bool(options["dry_run"]),
                actor_user=self._resolve_actor_user(options["actor_user"]),
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            "Cookie import summary: "
            f"dry_run={summary['dry_run']}, "
            f"rows={summary['total_rows']}, "
            f"imported={summary['imported']}, "
            f"would_import={summary['would_import']}, "
            f"skipped={summary['skipped']}, "
            f"errors={summary['errors']}"
        )
        for item in summary["rows"]:
            self.stdout.write(
                f"- row={item['row']} status={item['status']} detail={item['detail']}"
            )

    def _resolve_csv_path(self, *, options, mapping: CookieImportMapping) -> str:
        csv_path = str(options.get("csv_path") or "").strip()
        adapter_code = str(options.get("adapter_code") or "").strip()
        if bool(csv_path) == bool(adapter_code):
            raise CommandError(
                "Specify exactly one source: --csv-path or --adapter-code."
            )
        if csv_path:
            return csv_path
        payload = json.loads(str(options.get("adapter_payload_json") or "{}"))
        rows = run_import_adapter(code=adapter_code, payload=payload)
        fieldnames = [
            mapping.kind,
            mapping.contract_version,
            mapping.policy_revision_version,
            mapping.policy_categories_snapshot_json,
            mapping.selected_categories_json,
            mapping.user,
            mapping.anonymous_token,
            mapping.source,
            mapping.ip_address,
            mapping.user_agent,
            mapping.locale,
            mapping.request_id,
            mapping.session_key_hash,
            mapping.extra_meta_json,
            mapping.consented_at,
            mapping.decision_action,
            mapping.decided_at,
            mapping.dismissed_at,
        ]
        temp_path = Path(tempfile.mkstemp(prefix="cookie-import-", suffix=".csv")[1])
        with temp_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
        return str(temp_path)

    def _resolve_actor_user(self, raw_value: str):
        normalized = str(raw_value or "").strip()
        if not normalized:
            return None
        user_model = get_user_model()
        if normalized.isdigit():
            user = user_model.objects.filter(pk=int(normalized)).first()
        else:
            user = user_model.objects.filter(username=normalized).first()
        if user is None:
            raise CommandError(f"Actor user not found: {normalized}")
        return user
