"""Clear local MediMart data while preserving approved role accounts.

This command is intentionally explicit and local-only. It keeps only the
users listed in ROLE_ACCOUNT_CREDENTIALS.md, plus Django's schema metadata.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Delete MediMart records while preserving accounts from ROLE_ACCOUNT_CREDENTIALS.md."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm-reset",
            action="store_true",
            help="Confirm deletion of all non-account application data.",
        )

    def approved_usernames(self):
        credentials_path = Path(settings.BASE_DIR) / "ROLE_ACCOUNT_CREDENTIALS.md"
        if not credentials_path.exists():
            raise CommandError(f"Missing approved account file: {credentials_path}")
        usernames = set(re.findall(r"\|[^|]+\|\s*`([^`]+)`\s*\|", credentials_path.read_text(encoding="utf-8")))
        if not usernames:
            raise CommandError("No approved usernames were found in ROLE_ACCOUNT_CREDENTIALS.md")
        return usernames

    @staticmethod
    def quote_table(table_name):
        return "`" + table_name.replace("`", "``") + "`"

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Role-data reset is disabled when DEBUG=False.")
        if not options["confirm_reset"]:
            raise CommandError("This deletes existing data. Re-run with --confirm-reset to continue.")

        approved = self.approved_usernames()
        preserved_tables = {
            "auth_user",
            "accounts_userprofile",
            "django_migrations",
            "django_content_type",
            "auth_permission",
        }
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            try:
                deleted_tables = 0
                for table in tables:
                    if table in preserved_tables:
                        continue
                    cursor.execute(f"DELETE FROM {self.quote_table(table)}")
                    deleted_tables += 1

                placeholders = ", ".join(["%s"] * len(approved))
                cursor.execute(
                    f"DELETE FROM `auth_user` WHERE username NOT IN ({placeholders})",
                    tuple(sorted(approved)),
                )
                removed_users = cursor.rowcount

                cursor.execute(
                    "DELETE FROM `accounts_userprofile` "
                    "WHERE user_id NOT IN (SELECT id FROM `auth_user`)"
                )
                removed_profiles = cursor.rowcount
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared {deleted_tables} data tables; removed {removed_users} unapproved users "
                f"and {removed_profiles} orphaned profiles. Preserved {len(approved)} approved usernames."
            )
        )
