import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


PRIVATE_PREFIXES = (
    "prescriptions",
    "vendors/documents",
    "vendors/licenses",
    "support",
    "doctors/credentials",
)


class Command(BaseCommand):
    help = "Copy legacy regulated uploads from MEDIA_ROOT into PRIVATE_MEDIA_ROOT."

    def handle(self, *args, **options):
        if settings.USE_CLOUD_MEDIA:
            raise CommandError(
                "Cloud migration requires provider-specific transfer tooling. Keep the bucket private and upload these prefixes to private/."
            )
        source_root = Path(settings.MEDIA_ROOT).resolve()
        target_root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        copied = 0
        skipped = 0
        for prefix in PRIVATE_PREFIXES:
            source_dir = (source_root / prefix).resolve()
            if not source_dir.is_relative_to(source_root) or not source_dir.exists():
                continue
            for source in source_dir.rglob("*"):
                if not source.is_file():
                    continue
                relative = source.relative_to(source_root)
                target = (target_root / relative).resolve()
                if not target.is_relative_to(target_root):
                    raise CommandError(f"Unsafe target path: {target}")
                if target.exists():
                    skipped += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied += 1
        self.stdout.write(
            self.style.SUCCESS(f"Private media migration complete: {copied} copied, {skipped} already present.")
        )
