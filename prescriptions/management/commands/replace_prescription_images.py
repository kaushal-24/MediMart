from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from prescriptions.models import Prescription


class Command(BaseCommand):
    help = "Store supplied private images and assign them to existing prescriptions in round-robin order."

    def add_arguments(self, parser):
        parser.add_argument(
            "images",
            nargs="+",
            help="Source image paths. The images are copied into private prescription storage.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        source_paths = [Path(path).expanduser() for path in options["images"]]
        missing = [str(path) for path in source_paths if not path.is_file()]
        if missing:
            raise CommandError("Prescription image not found: " + ", ".join(missing))

        stored_names = []
        for index, path in enumerate(source_paths, start=1):
            extension = path.suffix.lower() or ".jpg"
            target_name = f"prescriptions/supplied/prescription-reference-{index}{extension}"
            prescription = Prescription(file=target_name)
            if not prescription.file.storage.exists(target_name):
                with path.open("rb") as source:
                    target_name = prescription.file.storage.save(target_name, File(source))
            stored_names.append(target_name)

        prescriptions = list(Prescription.objects.order_by("pk"))
        for index, prescription in enumerate(prescriptions):
            prescription.file.name = stored_names[index % len(stored_names)]
            prescription.save(update_fields=["file", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Stored {len(stored_names)} private prescription image(s) and updated {len(prescriptions)} prescription record(s)."
            )
        )
