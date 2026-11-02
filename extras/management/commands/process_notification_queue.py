from django.core.management.base import BaseCommand
from extras.queue import process_pending_notification_deliveries


class Command(BaseCommand):
    help = "Deliver queued MediMart WhatsApp notifications with retries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--max-attempts", type=int, default=None)

    def handle(self, *args, **options):
        sent, failed = process_pending_notification_deliveries(
            limit=options["limit"],
            max_attempts=options["max_attempts"],
        )
        self.stdout.write(self.style.SUCCESS(f"Notification queue processed: {sent} sent, {failed} failed."))
