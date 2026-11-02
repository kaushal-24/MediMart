import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restore a MySQL SQL dump after an explicit confirmation."

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        parser.add_argument("--confirm-restore", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_restore"]:
            raise CommandError("This operation is destructive. Add --confirm-restore to continue.")
        dump_path = Path(options["input"]).expanduser().resolve()
        if not dump_path.is_file():
            raise CommandError(f"SQL backup was not found: {dump_path}")

        database = settings.DATABASES["default"]
        command = [
            "mysql",
            "--host", str(database.get("HOST") or "127.0.0.1"),
            "--port", str(database.get("PORT") or "3306"),
            "--user", str(database.get("USER") or ""),
            str(database.get("NAME") or ""),
        ]
        env = os.environ.copy()
        password = str(database.get("PASSWORD") or "")
        if password:
            env["MYSQL_PWD"] = password
        try:
            with dump_path.open("rb") as dump:
                result = subprocess.run(command, stdin=dump, env=env, capture_output=True, check=False)
        except OSError as exc:
            raise CommandError("mysql was not found on PATH or could not be started.") from exc
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace")[-1000:]
            raise CommandError(f"Database restore failed: {detail}")
        self.stdout.write(self.style.SUCCESS(f"Database restored from {dump_path}"))
