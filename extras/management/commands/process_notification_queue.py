from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from extras.models import NotificationDelivery
from extras.services import deliver_notification


class Command(BaseCommand):
    help = "Deliver queued MediMart email and SMS notifications with retries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--max-attempts", type=int, default=5)

    def handle(self, *args, **options):
        now = timezone.now()
        ids = list(
            NotificationDelivery.objects.filter(
                status__in=[
                    NotificationDelivery.Status.PENDING,
                    NotificationDelivery.Status.FAILED,
                ],
                next_attempt_at__lte=now,
                attempts__lt=options["max_attempts"],
            )
            .order_by("next_attempt_at", "pk")
            .values_list("pk", flat=True)[: options["limit"]]
        )
        sent = 0
        failed = 0
        for delivery_id in ids:
            with transaction.atomic():
                delivery = (
                    NotificationDelivery.objects.select_for_update()
                    .select_related("notification")
                    .get(pk=delivery_id)
                )
                delivery.status = NotificationDelivery.Status.PROCESSING
                delivery.attempts += 1
                delivery.save(update_fields=["status", "attempts", "updated_at"])
            try:
                deliver_notification(delivery)
            except Exception as exc:
                failed += 1
                delay_minutes = min(60, 2 ** delivery.attempts)
                delivery.status = NotificationDelivery.Status.FAILED
                delivery.last_error = str(exc)[:500]
                delivery.next_attempt_at = timezone.now() + timedelta(minutes=delay_minutes)
                delivery.save(
                    update_fields=["status", "last_error", "next_attempt_at", "updated_at"]
                )
            else:
                sent += 1
                delivery.status = NotificationDelivery.Status.SENT
                delivery.sent_at = timezone.now()
                delivery.last_error = ""
                delivery.save(update_fields=["status", "sent_at", "last_error", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Notification queue processed: {sent} sent, {failed} failed."))
