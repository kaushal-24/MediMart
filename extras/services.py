from django.conf import settings
from django.core.mail import send_mail

from .models import Notification, NotificationDelivery


def create_notification(user, title, message, notification_type=Notification.NotificationType.GENERAL, link=""):
    if not user or not user.is_authenticated:
        return None
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
    )
    deliveries = []
    if getattr(user, "email", ""):
        deliveries.append(
            NotificationDelivery(
                notification=notification,
                channel=NotificationDelivery.Channel.EMAIL,
                destination=user.email,
            )
        )
    NotificationDelivery.objects.bulk_create(deliveries)
    return notification


def send_email_notification(destination, title, message):
    if not destination:
        return False
    return bool(send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [destination], fail_silently=False))


def deliver_notification(delivery):
    notification = delivery.notification
    if delivery.channel == NotificationDelivery.Channel.EMAIL:
        return send_email_notification(delivery.destination, notification.title, notification.message)
    raise ValueError("Only email notification delivery is enabled.")
