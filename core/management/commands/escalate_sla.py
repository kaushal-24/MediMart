from datetime import timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import UserProfile
from core.models import AuditEvent
from extras.models import Notification, SupportTicket
from extras.services import create_notification
from healthcare.models import LabBooking
from orders.models import Shipment


User = get_user_model()
OPERATIONS_ROLES = {
    UserProfile.Role.ADMIN,
    UserProfile.Role.OPERATIONS_MANAGER,
    UserProfile.Role.WAREHOUSE_MANAGER,
    UserProfile.Role.SUPPORT_STAFF,
    UserProfile.Role.PHARMACIST,
    UserProfile.Role.PHLEBOTOMIST,
}


class Command(BaseCommand):
    help = "Find overdue shipment, lab, and support SLAs and notify operations owners."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        now = timezone.now()
        limit = max(1, min(options["limit"], 1000))
        recipients = list(
            User.objects.filter(is_active=True, profile__role__in=OPERATIONS_ROLES)
            .select_related("profile")
            .distinct()
        )
        counts = {
            "shipments": self._escalate_shipments(now, recipients, limit),
            "labs": self._escalate_labs(now, recipients, limit),
            "tickets": self._escalate_tickets(now, recipients, limit),
        }
        self.stdout.write(self.style.SUCCESS(f"SLA escalation complete: {counts}"))

    def _already_escalated(self, target, kind, now):
        return AuditEvent.objects.filter(
            action="sla.escalated",
            target_type=target._meta.label_lower,
            target_id=str(target.pk),
            metadata__kind=kind,
            created_at__gte=now - timedelta(hours=20),
        ).exists()

    def _notify(self, recipients, title, message, link):
        for user in recipients:
            create_notification(user, title, message, Notification.NotificationType.SUPPORT, link)

    def _record(self, target, kind, summary):
        AuditEvent.objects.create(
            action="sla.escalated",
            target_type=target._meta.label_lower,
            target_id=str(target.pk),
            summary=summary[:255],
            metadata={"kind": kind, "automated": True},
        )

    def _escalate_shipments(self, now, recipients, limit):
        overdue = Shipment.objects.select_related("order").filter(
            promised_at__isnull=False,
            promised_at__lt=now,
        ).exclude(status__in=[Shipment.Status.DELIVERED, Shipment.Status.RETURNED, Shipment.Status.RTO])[:limit]
        count = 0
        for shipment in overdue:
            if self._already_escalated(shipment, "shipment", now):
                continue
            self._record(shipment, "shipment", f"Shipment {shipment.order.order_number} exceeded its promised delivery time.")
            self._notify(
                recipients,
                "Delivery SLA escalation",
                f"Shipment for order {shipment.order.order_number} is overdue. Review assignment, ETA, and any NDR/RTO action.",
                shipment.order.get_absolute_url(),
            )
            count += 1
        return count

    def _escalate_labs(self, now, recipients, limit):
        bookings = LabBooking.objects.select_related("lab_test").filter(
            status__in=[LabBooking.Status.SAMPLE_COLLECTED, LabBooking.Status.PROCESSING],
        )[:limit]
        count = 0
        for booking in bookings:
            start = booking.sample_collected_at or booking.scheduled_start or booking.created_at
            due_at = start + timedelta(hours=max(1, booking.lab_test.report_sla_hours, settings.LAB_SLA_ESCALATION_HOURS))
            if due_at >= now or self._already_escalated(booking, "lab", now):
                continue
            self._record(booking, "lab", f"Lab booking #{booking.pk} exceeded its report SLA.")
            self._notify(
                recipients,
                "Lab report SLA escalation",
                f"Lab booking #{booking.pk} for {booking.lab_test.name} is past its report SLA and needs review.",
                f"/admin-dashboard/manage/lab_bookings/?q={booking.accession_number}",
            )
            count += 1
        return count

    def _escalate_tickets(self, now, recipients, limit):
        tickets = SupportTicket.objects.select_related("user").filter(
            status__in=[SupportTicket.Status.OPEN, SupportTicket.Status.IN_PROGRESS],
            updated_at__lt=now - timedelta(hours=settings.SUPPORT_SLA_ESCALATION_HOURS),
        )[:limit]
        count = 0
        for ticket in tickets:
            if self._already_escalated(ticket, "support", now):
                continue
            self._record(ticket, "support", f"Support ticket #{ticket.pk} exceeded its response SLA.")
            self._notify(
                recipients,
                "Support SLA escalation",
                f"Support ticket #{ticket.pk} ({ticket.subject}) has had no update for more than {settings.SUPPORT_SLA_ESCALATION_HOURS} hours.",
                f"/support/{ticket.pk}/",
            )
            count += 1
        return count
