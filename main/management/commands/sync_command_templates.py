from __future__ import annotations

from django.core.cache import cache
from django.core.management.base import BaseCommand

from main.domain.command_catalog import CommandCatalog
from main.models import CommandTemplate


class Command(BaseCommand):
    help = "Synchronize built-in YAML command catalog templates into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created or updated without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created = 0
        updated = 0
        unchanged = 0

        for template in CommandCatalog.file_templates():
            lookup = {
                "name": template.name,
                "vendor": template.vendor,
                "platform": template.platform,
                "operation_type": template.operation_type,
            }
            defaults = {
                "command_body": template.command_body,
                "is_active": template.is_active,
                "revision": template.revision,
            }

            existing = CommandTemplate.objects.filter(**lookup).first()
            if existing is None:
                created += 1
                if not dry_run:
                    CommandTemplate.objects.create(**lookup, **defaults)
                continue

            changed = any(getattr(existing, field) != value for field, value in defaults.items())
            if not changed:
                unchanged += 1
                continue

            updated += 1
            if not dry_run:
                for field, value in defaults.items():
                    setattr(existing, field, value)
                existing.save(update_fields=(*defaults.keys(), "last_updated"))

        if not dry_run:
            cache.delete("cw:templates:active")

        action = "Would sync" if dry_run else "Synced"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} command templates: created={created}, updated={updated}, unchanged={unchanged}"
            )
        )
