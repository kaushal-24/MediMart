import json
from urllib import request as urlrequest

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
    profile = getattr(user, "profile", None)
    phone_number = getattr(profile, "phone_number", "")
    if phone_number:
        deliveries.append(
            NotificationDelivery(
                notification=notification,
                channel=NotificationDelivery.Channel.SMS,
                destination=phone_number,
            )
        )
    NotificationDelivery.objects.bulk_create(deliveries)
    return notification


def send_email_notification(destination, title, message):
    if not destination:
        return False
    return bool(send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [destination], fail_silently=False))


def send_sms_notification(phone_number, message):
    if not phone_number:
        return False
    if settings.SMS_BACKEND == "console":
        print(f"MediMart SMS to {phone_number}: {message}")
        return True
    if settings.SMS_BACKEND != "http" or not settings.SMS_API_URL or not settings.SMS_API_KEY:
        return False

    payload = json.dumps(
        {
            "to": phone_number,
            "message": message,
            "sender": settings.SMS_SENDER_ID,
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        settings.SMS_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.SMS_API_KEY}",
        },
        method="POST",
    )
    try:
        urlrequest.urlopen(req, timeout=5)
    except Exception as exc:
        raise RuntimeError("SMS provider request failed.") from exc
    return True


def deliver_notification(delivery):
    notification = delivery.notification
    if delivery.channel == NotificationDelivery.Channel.EMAIL:
        return send_email_notification(delivery.destination, notification.title, notification.message)
    if delivery.channel == NotificationDelivery.Channel.SMS:
        return send_sms_notification(delivery.destination, notification.message)
    raise ValueError("Unsupported notification channel.")
