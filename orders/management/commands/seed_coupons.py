from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Coupon


class Command(BaseCommand):
    help = "Create demo coupons for MediMart checkout testing."

    def handle(self, *args, **options):
        today = timezone.localdate()
        Coupon.objects.update_or_create(
            code="MEDI10",
            defaults={
                "discount_type": Coupon.DiscountType.PERCENTAGE,
                "discount_value": Decimal("10.00"),
                "minimum_order": Decimal("500.00"),
                "maximum_discount": Decimal("250.00"),
                "start_date": today,
                "end_date": today.replace(year=today.year + 1),
                "usage_limit": 100,
                "is_active": True,
            },
        )
        Coupon.objects.update_or_create(
            code="FIRST50",
            defaults={
                "discount_type": Coupon.DiscountType.FIXED,
                "discount_value": Decimal("50.00"),
                "minimum_order": Decimal("250.00"),
                "maximum_discount": Decimal("50.00"),
                "start_date": today,
                "end_date": today.replace(year=today.year + 1),
                "usage_limit": 100,
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS("MediMart demo coupons created."))
