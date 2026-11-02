import hashlib
import hmac
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from extras.models import Notification
from extras.services import create_notification
from core.checkout import get_checkout_config

from .models import Consultation, ConsultationFollowUp, ConsultationPayment


def consultation_room_url(consultation):
    """Return a stable room URL; use a configured provider when available."""
    room_id = consultation.room_id or f"mm-consultation-{consultation.pk}-{uuid.uuid4().hex[:10]}"
    if not consultation.room_id:
        consultation.room_id = room_id
        provider_base = str(getattr(settings, "CONSULTATION_ROOM_BASE_URL", "")).rstrip("/")
        consultation.room_url = f"{provider_base}/{room_id}" if provider_base else ""
        consultation.save(update_fields=["room_id", "room_url", "updated_at"])
    return consultation.room_url or reverse("healthcare:consultation_room", args=[consultation.pk])


def consultation_payment_is_configured():
    configured = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)
    if configured and get_checkout_config().finance_test_mode:
        return str(settings.RAZORPAY_KEY_ID).startswith("rzp_test_")
    return configured


def _razorpay_client():
    import razorpay

    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_consultation_payment_order(consultation):
    payment, _ = ConsultationPayment.objects.get_or_create(
        consultation=consultation,
        defaults={"amount": consultation.fee},
    )
    if payment.status == ConsultationPayment.Status.PAID:
        return payment, {"id": payment.provider_order_id}
    if not consultation_payment_is_configured():
        raise RuntimeError("Razorpay is not configured for consultation payments.")
    if payment.provider_order_id:
        return payment, {"id": payment.provider_order_id}
    gateway_order = _razorpay_client().order.create(
        {
            "amount": int(Decimal(payment.amount) * 100),
            "currency": getattr(settings, "RAZORPAY_CURRENCY", "INR"),
            "receipt": f"consultation-{consultation.pk}",
            "notes": {"consultation_id": str(consultation.pk)},
        }
    )
    payment.provider_order_id = gateway_order["id"]
    payment.save(update_fields=["provider_order_id", "updated_at"])
    return payment, gateway_order


@transaction.atomic
def verify_consultation_payment(consultation, payment_id, signature):
    payment = ConsultationPayment.objects.select_for_update().get(consultation=consultation)
    if payment.status == ConsultationPayment.Status.PAID:
        return payment
    if not payment.provider_order_id or not payment_id or not signature:
        raise ValueError("Incomplete consultation payment details.")
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{payment.provider_order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Consultation payment signature verification failed.")
    client = _razorpay_client()
    client.utility.verify_payment_signature(
        {
            "razorpay_order_id": payment.provider_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }
    )
    gateway_payment = client.payment.fetch(payment_id)
    if gateway_payment.get("status") != "captured":
        raise ValueError("Consultation payment has not been captured.")
    payment.status = ConsultationPayment.Status.PAID
    payment.provider_payment_id = payment_id
    payment.paid_at = timezone.now()
    payment.failure_reason = ""
    payment.save(update_fields=["status", "provider_payment_id", "paid_at", "failure_reason", "updated_at"])
    consultation.status = Consultation.Status.CONFIRMED
    consultation.save(update_fields=["status", "updated_at"])
    consultation_room_url(consultation)
    create_notification(
        consultation.user,
        "Consultation payment confirmed",
        f"Your consultation with Dr. {consultation.doctor.full_name} is confirmed.",
        Notification.NotificationType.GENERAL,
        reverse("healthcare:consultation_detail", args=[consultation.pk]),
    )
    create_notification(
        consultation.doctor.user,
        "Consultation confirmed",
        f"Payment is confirmed for consultation #{consultation.pk}. Review the consultation workspace.",
        Notification.NotificationType.GENERAL,
        reverse("healthcare:consultation_detail", args=[consultation.pk]),
    )
    return payment


def schedule_consultation_followup(consultation, actor, scheduled_at, notes=""):
    if consultation.status != Consultation.Status.COMPLETED:
        raise ValueError("Follow-ups can be scheduled after the consultation is completed.")
    if scheduled_at <= timezone.now():
        raise ValueError("Choose a future follow-up time.")
    followup = ConsultationFollowUp.objects.create(
        consultation=consultation,
        scheduled_at=scheduled_at,
        notes=notes[:4000],
        created_by=actor,
    )
    create_notification(
        consultation.user,
        "Consultation follow-up scheduled",
        f"A follow-up with Dr. {consultation.doctor.full_name} was scheduled for {scheduled_at:%d %b %Y, %I:%M %p}.",
        Notification.NotificationType.GENERAL,
        reverse("healthcare:consultation_detail", args=[consultation.pk]),
    )
    return followup


@transaction.atomic
def refund_consultation_payment(consultation):
    payment = ConsultationPayment.objects.select_for_update().get(consultation=consultation)
    if payment.status == ConsultationPayment.Status.REFUNDED:
        return payment
    if payment.status != ConsultationPayment.Status.REFUND_PENDING or not payment.provider_payment_id:
        raise ValueError("A captured consultation payment is required before a refund can be processed.")
    if not consultation_payment_is_configured():
        raise RuntimeError("Razorpay is not configured for consultation refunds.")
    refund = _razorpay_client().payment.refund(payment.provider_payment_id, {"amount": int(Decimal(payment.amount) * 100), "notes": {"consultation_id": str(consultation.pk)}})
    payment.provider_refund_id = refund.get("id", "")
    payment.refunded_amount = payment.amount
    payment.status = ConsultationPayment.Status.REFUNDED
    payment.save(update_fields=["provider_refund_id", "refunded_amount", "status", "updated_at"])
    consultation.status = Consultation.Status.CANCELLED
    consultation.save(update_fields=["status", "updated_at"])
    create_notification(
        consultation.user,
        "Consultation refund completed",
        f"The refund for consultation #{consultation.pk} has been submitted successfully.",
        Notification.NotificationType.GENERAL,
        reverse("healthcare:consultation_detail", args=[consultation.pk]),
    )
    return payment
