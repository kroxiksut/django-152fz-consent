"""Cleanup command for cookie audit retention."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_cookies_152fz.retention import cleanup_cookie_audit


class Command(BaseCommand):
    help = (
        "Batch cleanup for CookieConsentRecord/CookieConsentEvent/CookieBannerState "
        "based on configured retention policy."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show cleanup report without deleting rows.",
        )
        parser.add_argument(
            "--report-only",
            action="store_true",
            help="Alias for dry report mode; rows are not deleted.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=0,
            help="Override batch size for delete operations.",
        )
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=None,
            help="Global age threshold override for all cookie audit models.",
        )
        parser.add_argument(
            "--database",
            default="default",
            help="Nominates a database to clean up. Defaults to 'default'.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        report_only = bool(options["report_only"])
        batch_size = int(options["batch_size"] or 0)
        older_than_days = options["older_than_days"]
        database = str(options["database"] or "default")

        if older_than_days is not None and older_than_days < 0:
            raise CommandError("--older-than-days must be >= 0.")
        if batch_size < 0:
            raise CommandError("--batch-size must be >= 0.")

        summary = cleanup_cookie_audit(
            dry_run=dry_run,
            report_only=report_only,
            batch_size=batch_size or None,
            older_than_days=older_than_days,
            source="management.cleanup_152fz_cookie_audit",
            using=database,
        )

        self.stdout.write(
            "Cookie audit cleanup summary: "
            f"dry_run={summary['dry_run']}, "
            f"report_only={summary['report_only']}, "
            f"batch_size={summary['batch_size']}, "
            f"older_than_days_override={summary['older_than_days_override']}"
        )
        for model_report in summary["models"]:
            self.stdout.write(
                f"- {model_report['model']}: "
                f"before={model_report['before_count']}, "
                f"remaining={model_report['remaining_count']}, "
                f"age_candidates={model_report['age_candidates']}, "
                f"max_candidates={model_report['max_count_candidates']}, "
                f"deleted={model_report['deleted_total']}, "
                f"protected={model_report['protected_current_count']}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Total deleted cookie audit rows: {summary['total_deleted']}"
            )
        )
