from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import UserProfile
from orders.models import Order, OrderStatusHistory
from vendors.models import Vendor


DEMO_PASSWORD = "MediMart@2026"


class Command(BaseCommand):
    help = "Add missing MediMart demo role accounts without deleting existing data."

    def handle(self, *args, **options):
        User = get_user_model()
        manufacturer, created = User.objects.get_or_create(
            username="manufacturer",
            defaults={
                "email": "manufacturer@gmail.com",
                "first_name": "Dev",
                "last_name": "Iyer",
            },
        )
        if created:
            manufacturer.set_password(DEMO_PASSWORD)
            manufacturer.save(update_fields=["password"])
        UserProfile.objects.update_or_create(
            user=manufacturer,
            defaults={
                "role": UserProfile.Role.MANUFACTURER,
                "phone_number": "9999999999",
            },
        )
        Vendor.objects.update_or_create(
            user=manufacturer,
            defaults={
                "business_name": "PulseCare Manufacturing",
                "owner_name": "Dev Iyer",
                "email": "manufacturer@gmail.com",
                "phone": "9876512340",
                "address": "88 Biomedical Park, Hyderabad, Telangana",
                "gst_number": "36ABCDE1234F1Z7",
                "license_number": "MFG-LIC-2026",
                "business_type": Vendor.BusinessType.MANUFACTURER,
                "bank_name": "Demo Bank",
                "bank_account_number": "3234567890",
                "ifsc_code": "DEMO0003234",
                "is_approved": True,
                "is_active": True,
            },
        )

        delivery = User.objects.filter(username="delivery").first()
        if delivery:
            order = (
                Order.objects.filter(
                    delivery_staff__isnull=True,
                    order_status__in=[
                        Order.OrderStatus.SHIPPED,
                        Order.OrderStatus.OUT_FOR_DELIVERY,
                    ],
                )
                .order_by("-created_at")
                .first()
            )
            if order:
                order.delivery_staff = delivery
                order.save(update_fields=["delivery_staff", "updated_at"])
                OrderStatusHistory.objects.create(
                    order=order,
                    status=order.order_status,
                    note="Assigned to demo delivery staff.",
                )

        self.stdout.write(self.style.SUCCESS("Demo role data ensured without flushing."))
