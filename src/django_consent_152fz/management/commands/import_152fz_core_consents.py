"""CSV import command for baseline core consent migration."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from django_consent_152fz.core.importers import (
    CoreConsentImportMapping,
    import_core_consents_from_csv,
)
from django_consent_152fz.imports.adapters import run_import_adapter


class Command(BaseCommand):
    help = (
        "Import core consent records from CSV with explicit column mapping. "
        "Supports dry-run preview and final import summary."
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

        parser.add_argument("--col-purpose", default="purpose")
        parser.add_argument("--col-document", default="document_code")
        parser.add_argument("--col-status", default="status")
        parser.add_argument("--col-user", default="user")
        parser.add_argument("--col-anon", default="anonymous_token")
        parser.add_argument("--col-consented-at", default="consented_at")

        parser.add_argument("--col-source", default="source")
        parser.add_argument("--col-ip", default="ip_address")
        parser.add_argument("--col-user-agent", default="user_agent")
        parser.add_argument("--col-locale", default="locale")
        parser.add_argument("--col-request-id", default="request_id")
        parser.add_argument("--col-session-key-hash", default="session_key_hash")
        parser.add_argument("--col-extra-meta-json", default="extra_meta_json")

    def handle(self, *args, **options):
        mapping = CoreConsentImportMapping(
            purpose_code=options["col_purpose"],
            document_code=options["col_document"],
            status=options["col_status"],
            user=options["col_user"],
            anonymous_token=options["col_anon"],
            consented_at=options["col_consented_at"],
            source=options["col_source"],
            ip_address=options["col_ip"],
            user_agent=options["col_user_agent"],
            locale=options["col_locale"],
            request_id=options["col_request_id"],
            session_key_hash=options["col_session_key_hash"],
            extra_meta_json=options["col_extra_meta_json"],
        )
        temp_csv_path: Path | None = None
        try:
            csv_path, temp_csv_path = self._resolve_csv_path(
                options=options, mapping=mapping
            )
            summary = import_core_consents_from_csv(
                csv_path=csv_path,
                mapping=mapping,
                dry_run=bool(options["dry_run"]),
                actor_user=self._resolve_actor_user(options["actor_user"]),
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        finally:
            if temp_csv_path is not None:
                try:
                    temp_csv_path.unlink(missing_ok=True)
                except OSError:
                    pass

        self.stdout.write(
            "Core consent import summary: "
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

    def _resolve_csv_path(
        self, *, options, mapping: CoreConsentImportMapping
    ) -> tuple[str, Path | None]:
        csv_path = str(options.get("csv_path") or "").strip()
        adapter_code = str(options.get("adapter_code") or "").strip()
        if bool(csv_path) == bool(adapter_code):
            raise CommandError(
                "Specify exactly one source: --csv-path or --adapter-code."
            )
        if csv_path:
            return csv_path, None
        payload = json.loads(str(options.get("adapter_payload_json") or "{}"))
        rows = run_import_adapter(code=adapter_code, payload=payload)
        fieldnames = [
            mapping.purpose_code,
            mapping.document_code,
            mapping.status,
            mapping.user,
            mapping.anonymous_token,
            mapping.consented_at,
            mapping.source,
            mapping.ip_address,
            mapping.user_agent,
            mapping.locale,
            mapping.request_id,
            mapping.session_key_hash,
            mapping.extra_meta_json,
        ]
        fd, raw_path = tempfile.mkstemp(prefix="core-consent-import-", suffix=".csv")
        os.close(fd)
        temp_path = Path(raw_path)
        with temp_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
        return str(temp_path), temp_path

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
