from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from extras.models import Notification
from extras.services import create_notification
from vendors.models import VendorProduct

from .models import PriceAlert, Product, StockAlert


@receiver(pre_save, sender=Product)
def capture_previous_product_price(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_selling_price = None
        return
    instance._previous_selling_price = sender.objects.filter(pk=instance.pk).values_list("selling_price", flat=True).first()


@receiver(post_save, sender=Product)
def notify_price_alerts(sender, instance, **kwargs):
    previous_price = getattr(instance, "_previous_selling_price", None)
    if previous_price is None or instance.selling_price >= previous_price:
        return
    alerts = PriceAlert.objects.filter(
        product=instance,
        is_active=True,
        target_price__gte=instance.selling_price,
    ).select_related("user", "product")
    for alert in alerts:
        updated = PriceAlert.objects.filter(pk=alert.pk, is_active=True).update(
            is_active=False,
            notified_at=timezone.now(),
        )
        if not updated:
            continue
        create_notification(
            alert.user,
            "Price drop alert",
            f"{alert.product.name} is now available at ₹{instance.selling_price}, at or below your target price.",
            Notification.NotificationType.OFFER,
            reverse("products:product_detail", kwargs={"slug": alert.product.slug}),
        )


@receiver(post_save, sender=VendorProduct)
def notify_back_in_stock_alerts(sender, instance, **kwargs):
    if not (
        instance.stock_quantity > 0
        and instance.is_active
        and instance.is_approved
        and instance.vendor.is_active
        and instance.vendor.is_approved
    ):
        return

    alerts = StockAlert.objects.filter(
        product=instance.product,
        is_active=True,
        notified_at__isnull=True,
    ).select_related("user", "product")
    for alert in alerts:
        now = timezone.now()
        updated = StockAlert.objects.filter(
            pk=alert.pk,
            is_active=True,
            notified_at__isnull=True,
        ).update(is_active=False, notified_at=now)
        if not updated:
            continue
        create_notification(
            alert.user,
            "Back in stock",
            f"{alert.product.name} is back in stock. You can shop it now on MediMart.",
            Notification.NotificationType.OFFER,
            reverse("products:product_detail", kwargs={"slug": alert.product.slug}),
        )
