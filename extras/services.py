import json
import logging
import re
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Notification, NotificationDelivery


logger = logging.getLogger(__name__)

_OTP_DETAILS_PATTERN = re.compile(
    r"(?i)(?P<label>\b(?:otp|verification code|password reset code)\b[^0-9]{0,30})"
    r"(?P<code>(?<![\w*])\d{4,8}(?![\w*]))"
)
_ORDER_NUMBER_PATTERN = re.compile(r"(?<![\w*])MM[A-Z0-9]{4,}(?![\w*])")
_REFERENCE_NUMBER_PATTERN = re.compile(
    r"(?i)(?<![\w*])"
    r"((?:prescription|ticket|return|consultation|booking|invoice|shipment|batch)\s*#\s*[A-Z0-9_-]+)"
    r"(?![\w*])"
)


def _whatsapp_chat_id(phone):
    """Return an Indian WhatsApp chat id from a profile or address phone value."""
    value = str(phone or "").strip()
    if "@" in value:
        value = value.split("@", 1)[0]
    digits = "".join(character for character in value if character.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        digits = f"91{digits}"
    if len(digits) != 12 or not digits.startswith("91") or digits[2] not in "6789":
        return ""
    return f"{digits}@c.us"


def whatsapp_destination(user):
    """Return the first valid WhatsApp chat id stored for an account."""
    profile = getattr(user, "profile", None)
    candidates = [
        getattr(user, "phone_number", ""),
        getattr(profile, "phone_number", ""),
    ]
    addresses = getattr(user, "addresses", None)
    if addresses is not None:
        candidates.extend(
            addresses.order_by("-is_default", "-updated_at").values_list("phone", flat=True)
        )
    for phone in candidates:
        chat_id = _whatsapp_chat_id(phone)
        if chat_id:
            return chat_id
    return ""


def notification_target_url(link):
    """Turn the stored in-app path into the same clickable destination for WhatsApp."""
    link = str(link or "").strip()
    if not link:
        return ""
    if link.startswith(("http://", "https://")):
        return link
    return urljoin(f"{settings.PUBLIC_SITE_URL.rstrip('/')}/", link.lstrip("/"))


def format_whatsapp_notification(title, message, link=""):
    """Format notification details so important references are easy to scan in WhatsApp."""
    text = f"*{str(title or '').strip()}*\n\n{str(message or '').strip()}"
    text = _OTP_DETAILS_PATTERN.sub(
        lambda match: f"{match.group('label')}*{match.group('code')}*",
        text,
    )
    text = _ORDER_NUMBER_PATTERN.sub(lambda match: f"*{match.group(0)}*", text)
    text = _REFERENCE_NUMBER_PATTERN.sub(lambda match: f"*{match.group(1)}*", text)
    target_url = notification_target_url(link)
    if target_url:
        text += f"\n\n*Click Here To Open Website:*\n{target_url}"
    return text


def _openwa_session_state():
    """Return the configured OpenWA session payload and a safe failure reason."""
    if (
        settings.WHATSAPP_PROVIDER != "openwa"
        or not settings.WHATSAPP_API_URL
        or not settings.WHATSAPP_API_KEY
        or not settings.WHATSAPP_SESSION_ID
    ):
        return {}, "OpenWA is not configured."
    endpoint = (
        f"{settings.WHATSAPP_API_URL.rstrip('/')}/sessions/"
        f"{settings.WHATSAPP_SESSION_ID}"
    )
    request = Request(
        endpoint,
        headers={"Accept": "application/json", "X-API-Key": settings.WHATSAPP_API_KEY},
        method="GET",
    )
    try:
        with urlopen(request, timeout=settings.WHATSAPP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except HTTPError as exc:
        logger.warning("OpenWA session health check was rejected with HTTP %s", exc.code)
        return {}, f"OpenWA session health check returned HTTP {exc.code}."
    except (URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        logger.warning("OpenWA session health check failed: %s", exc.__class__.__name__)
        return {}, "OpenWA session health check failed."


def create_notification(user, title, message, notification_type=Notification.NotificationType.GENERAL, link=""):
    """Create the in-app notification and one durable WhatsApp delivery job."""
    if not user or not user.is_authenticated:
        return None
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
    )
    destination = whatsapp_destination(user)
    profile = getattr(user, "profile", None)
    if destination and getattr(profile, "whatsapp_notifications_enabled", True):
        delivery = NotificationDelivery.objects.create(
            notification=notification,
            channel=NotificationDelivery.Channel.WHATSAPP,
            destination=destination,
        )
        transaction.on_commit(
            lambda delivery_id=delivery.pk: deliver_notification_now(delivery_id)
        )
    return notification


def send_whatsapp_message(destination, text):
    if (
        not destination
        or not str(text or "").strip()
        or settings.WHATSAPP_PROVIDER != "openwa"
        or not settings.WHATSAPP_API_URL
        or not settings.WHATSAPP_API_KEY
        or not settings.WHATSAPP_SESSION_ID
    ):
        return False
    session, state_error = _openwa_session_state()
    if state_error:
        return False
    session_status = str(session.get("status", "")).strip().casefold()
    if session_status != "ready":
        logger.warning(
            "OpenWA session is not ready for delivery: session=%s status=%s phone_linked=%s",
            settings.WHATSAPP_SESSION_ID,
            session_status or "unknown",
            bool(session.get("phone")),
        )
        return False

    endpoint = (
        f"{settings.WHATSAPP_API_URL.rstrip('/')}/sessions/"
        f"{settings.WHATSAPP_SESSION_ID}/messages/send-text"
    )
    request = Request(
        endpoint,
        data=json.dumps({"chatId": destination, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "X-API-Key": settings.WHATSAPP_API_KEY},
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.WHATSAPP_TIMEOUT_SECONDS) as response:
            response_body = response.read()
            if 200 <= response.status < 300:
                return True
            logger.warning("OpenWA returned an unsuccessful status: %s", response.status)
            return False
    except HTTPError as exc:
        # Keep provider response bodies out of user-facing errors and logs.
        logger.warning("OpenWA rejected a message with HTTP %s", exc.code)
        return False
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("OpenWA message delivery failed: %s", exc.__class__.__name__)
        return False


def send_whatsapp_notification(destination, title, message, link=""):
    return send_whatsapp_message(destination, format_whatsapp_notification(title, message, link))


def deliver_notification(delivery):
    notification = delivery.notification
    if delivery.channel == NotificationDelivery.Channel.WHATSAPP:
        delivered = send_whatsapp_notification(
            delivery.destination,
            notification.title,
            notification.message,
            notification.link,
        )
        if delivered:
            return True
        session, state_error = _openwa_session_state()
        if state_error:
            raise RuntimeError(state_error)
        status = str(session.get("status", "")).strip().casefold() or "unknown"
        if status != "ready":
            raise RuntimeError(
                f"OpenWA session is {status}; scan its QR code and link WhatsApp before retrying."
            )
        raise RuntimeError("OpenWA did not accept the WhatsApp message.")
    raise ValueError("Only WhatsApp notification delivery is enabled.")


def deliver_notification_now(delivery_id):
    """Attempt one WhatsApp delivery immediately after its notification commits."""
    with transaction.atomic():
        try:
            delivery = (
                NotificationDelivery.objects.select_for_update()
                .select_related("notification")
                .get(pk=delivery_id)
            )
        except NotificationDelivery.DoesNotExist:
            return False
        if delivery.status != NotificationDelivery.Status.PENDING:
            return delivery.status == NotificationDelivery.Status.SENT
        delivery.status = NotificationDelivery.Status.PROCESSING
        delivery.attempts += 1
        delivery.save(update_fields=["status", "attempts", "updated_at"])

    try:
        delivered = deliver_notification(delivery)
        if not delivered:
            raise RuntimeError("WhatsApp provider did not accept the message.")
    except Exception as exc:
        max_attempts = settings.WHATSAPP_NOTIFICATION_MAX_ATTEMPTS
        delivery.status = (
            NotificationDelivery.Status.DEAD_LETTER
            if delivery.attempts >= max_attempts
            else NotificationDelivery.Status.FAILED
        )
        delivery.last_error = str(exc)[:500]
        delivery.next_attempt_at = timezone.now() + timedelta(minutes=2)
        delivery.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])
        logger.warning("Immediate WhatsApp notification delivery failed: %s", exc.__class__.__name__)
        return False

    delivery.status = NotificationDelivery.Status.SENT
    delivery.sent_at = timezone.now()
    delivery.last_error = ""
    delivery.save(update_fields=["status", "sent_at", "last_error", "updated_at"])
    return True
