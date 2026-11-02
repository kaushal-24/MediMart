from datetime import datetime
from pathlib import Path
import os
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a consistent SQL backup of the configured MySQL database."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Output .sql path; defaults to backups/medimart-<timestamp>.sql")

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if database.get("ENGINE") != "django.db.backends.mysql":
            raise CommandError("This command only supports the configured MySQL database.")
        output = Path(options.get("output") or Path(settings.BASE_DIR) / "backups" / f"medimart-{datetime.now():%Y%m%d-%H%M%S}.sql")
        output.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        password = database.get("PASSWORD") or ""
        if password:
            env["MYSQL_PWD"] = password
        command = [
            "mysqldump", "--single-transaction", "--routines", "--events", "--triggers",
            "--default-character-set=utf8mb4", "--host", str(database.get("HOST") or "127.0.0.1"),
            "--port", str(database.get("PORT") or "3306"), "--user", str(database.get("USER") or "root"),
            str(database.get("NAME")),
        ]
        try:
            with output.open("wb") as backup_file:
                result = subprocess.run(command, env=env, stdout=backup_file, stderr=subprocess.PIPE, check=False)
        except FileNotFoundError as exc:
            raise CommandError("mysqldump was not found on PATH. Add the MySQL bin directory to PATH.") from exc
        if result.returncode:
            output.unlink(missing_ok=True)
            raise CommandError(result.stderr.decode(errors="replace").strip() or "mysqldump failed.")
        self.stdout.write(self.style.SUCCESS(f"Database backup created: {output}"))
