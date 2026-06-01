"""Management command for downloading boxed sample documents."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_consent_152fz.box_templates.documents import (
    bootstrap_sample_documents,
    is_sample_documents_bootstrap_allowed,
)
from django_consent_152fz.constants import SAMPLE_DOCUMENTS_LOAD_MODE_DISABLED
from django_consent_152fz.settings import get_sample_documents_load_mode


class Command(BaseCommand):
    """Load curated sample documents into the database."""

    help = (
        "Загружает коробочные образцы LegalDocument, DocumentRevision, "
        "ConsentAccessPolicy и ConsentAudienceRule для типовых сценариев 152-ФЗ. "
        "Все записи создаются как безопасные неактивные шаблоны и требуют "
        "юридической/проектной адаптации."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Игнорировать режим sample_documents.load_mode=disabled и всё равно "
                "выполнить bootstrap."
            ),
        )
        parser.add_argument(
            "--database",
            default="default",
            help="Псевдоним БД, в которую нужно загрузить sample-документы.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        database = options["database"]
        load_mode = get_sample_documents_load_mode()
        if not is_sample_documents_bootstrap_allowed(force=force):
            raise CommandError(
                "Bootstrap sample-документов отключён настройкой "
                f"sample_documents.load_mode={SAMPLE_DOCUMENTS_LOAD_MODE_DISABLED!r}. "
                "Используйте --force, если хотите выполнить команду осознанно."
            )

        summary = bootstrap_sample_documents(using=database)
        self.stdout.write(
            self.style.SUCCESS(
                "Sample-документы обработаны: "
                f"created_purposes={summary['created_purposes']}, "
                f"created_documents={summary['created_documents']}, "
                f"created_revisions={summary['created_revisions']}, "
                f"existing_samples={summary['existing_samples']}, "
                f"skipped_existing_streams={summary['skipped_existing_streams']}, "
                f"created_access_policies={summary['created_access_policies']}, "
                f"created_audience_rules={summary['created_audience_rules']}."
            )
        )
        self.stdout.write(f"Текущий режим bootstrap: {load_mode}")
        for item in summary["items"]:
            self.stdout.write(
                f"- {item['key']} ({item['document_code']}): {item['status']}"
            )
