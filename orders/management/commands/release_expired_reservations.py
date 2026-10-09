from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orders.models import Order
from orders.views import release_order_inventory


class Command(BaseCommand):
    help = "Release inventory held by expired unpaid online-payment orders."

    def handle(self, *args, **options):
        expired_ids = list(
            Order.objects.filter(
                payment_method=Order.PaymentMethod.RAZORPAY,
                payment_status=Order.PaymentStatus.PENDING,
                inventory_released_at__isnull=True,
                stock_reserved_until__lte=timezone.now(),
            ).values_list("pk", flat=True)
        )
        released = 0
        for order_id in expired_ids:
            with transaction.atomic():
                release_order_inventory(
                    order_id,
                    reason="Online payment reservation expired automatically.",
                )
            released += 1
        self.stdout.write(self.style.SUCCESS(f"Released {released} expired reservation(s)."))
