"""Dry-run and batch apply command for verified legacy web-consent transition."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from django_consent_152fz.exceptions import ConsentError
from django_consent_152fz.verified_consents.services import (
    apply_verified_legacy_transition,
    preview_verified_legacy_transition,
)


class Command(BaseCommand):
    help = (
        "Preview and apply legacy web-consent transition for verified policies "
        "(keep_web_current/mark_web_outdated/withdraw_web_now/"
        "withdraw_after_paper_confirmed)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--purpose-code",
            required=True,
            help="Purpose code for verified flow.",
        )
        parser.add_argument(
            "--document-code",
            default="",
            help="Optional document code (required when purpose has multiple documents).",
        )
        parser.add_argument(
            "--form-code",
            default="",
            help="Optional form code for per-form override resolution.",
        )
        parser.add_argument(
            "--channel",
            default="runtime",
            choices=("runtime", "self_service", "form"),
            help="Resolution channel for verified policy.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Batch size for apply mode.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Force dry-run mode (preview only).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply immediate transition to matching records.",
        )
        parser.add_argument(
            "--actor-user",
            default="",
            help="Operator user id or username for module audit log.",
        )

    def handle(self, *args, **options):
        purpose_code = str(options["purpose_code"] or "").strip()
        document_code = str(options["document_code"] or "").strip() or None
        form_code = str(options["form_code"] or "").strip() or None
        channel = str(options["channel"] or "runtime").strip() or "runtime"
        batch_size = int(options["batch_size"] or 0)
        dry_run_flag = bool(options["dry_run"])
        apply_flag = bool(options["apply"])
        actor_user = self._resolve_actor_user(str(options["actor_user"] or ""))

        if batch_size <= 0:
            raise CommandError("--batch-size must be a positive integer.")
        if dry_run_flag and apply_flag:
            raise CommandError("Use either --dry-run or --apply, not both.")

        try:
            preview = preview_verified_legacy_transition(
                purpose_code=purpose_code,
                document_code=document_code,
                form_code=form_code,
                channel=channel,
            )
        except ConsentError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            "Verified legacy transition preview: "
            f"purpose={preview['purpose_code']}, "
            f"document={preview['document_code']}, "
            f"channel={preview['channel']}, "
            f"form_code={preview['form_code'] or '-'}, "
            f"verification_mode={preview['verification_mode']}, "
            f"transition_mode={preview['transition_mode']}, "
            f"candidates={preview['affected_candidates']}, "
            f"immediate={preview['would_change_immediately']}, "
            f"deferred={preview['would_defer_until_confirmation']}."
        )

        if not apply_flag:
            self.stdout.write(self.style.SUCCESS("Dry-run completed."))
            return

        try:
            result = apply_verified_legacy_transition(
                purpose_code=purpose_code,
                document_code=document_code,
                form_code=form_code,
                channel=channel,
                batch_size=batch_size,
                dry_run=False,
                actor_user=actor_user,
                source="management.transition_152fz_verified_legacy_web",
            )
        except ConsentError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Apply completed: "
                f"changed_records={result['changed_records']}, "
                f"batches={result['batches_processed']}, "
                f"transition_mode={result['transition_mode']}."
            )
        )

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
