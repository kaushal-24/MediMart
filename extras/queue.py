from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import NotificationDelivery
from .services import deliver_notification


def process_pending_notification_deliveries(limit=100, max_attempts=None):
    """Process due WhatsApp deliveries once and return sent/failed counts."""
    max_attempts = max_attempts or settings.WHATSAPP_NOTIFICATION_MAX_ATTEMPTS
    now = timezone.now()
    ids = list(
        NotificationDelivery.objects.filter(
            channel=NotificationDelivery.Channel.WHATSAPP,
            status__in=[NotificationDelivery.Status.PENDING, NotificationDelivery.Status.FAILED],
            next_attempt_at__lte=now,
            attempts__lt=max_attempts,
        ).order_by("next_attempt_at", "pk").values_list("pk", flat=True)[:limit]
    )
    sent = failed = 0
    for delivery_id in ids:
        with transaction.atomic():
            delivery = (
                NotificationDelivery.objects.select_for_update()
                .select_related("notification")
                .get(pk=delivery_id)
            )
            if delivery.status not in {NotificationDelivery.Status.PENDING, NotificationDelivery.Status.FAILED}:
                continue
            delivery.status = NotificationDelivery.Status.PROCESSING
            delivery.attempts += 1
            delivery.save(update_fields=["status", "attempts", "updated_at"])
        try:
            if not deliver_notification(delivery):
                raise RuntimeError("WhatsApp provider did not accept the message.")
        except Exception as exc:
            failed += 1
            delay_minutes = min(60, 2 ** delivery.attempts)
            delivery.status = (
                NotificationDelivery.Status.DEAD_LETTER
                if delivery.attempts >= max_attempts
                else NotificationDelivery.Status.FAILED
            )
            delivery.last_error = str(exc)[:500]
            delivery.next_attempt_at = timezone.now() + timedelta(minutes=delay_minutes)
            delivery.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])
        else:
            sent += 1
            delivery.status = NotificationDelivery.Status.SENT
            delivery.sent_at = timezone.now()
            delivery.last_error = ""
            delivery.save(update_fields=["status", "sent_at", "last_error", "updated_at"])
    return sent, failed


def notification_worker_loop(stop_event, interval_seconds=15):
    """Run the queue in a single process for local development or a service host."""
    while not stop_event.is_set():
        try:
            close_old_connections()
            process_pending_notification_deliveries()
        except Exception:
            # The next interval retries after transient database/provider failures.
            import logging
            logging.getLogger(__name__).exception("Notification worker iteration failed")
        finally:
            close_old_connections()
        stop_event.wait(interval_seconds)
