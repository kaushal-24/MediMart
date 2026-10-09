from django.core.management.base import BaseCommand
from django.db import transaction

from orders.models import Order, Payment, Refund
from orders.views import get_razorpay_client, razorpay_is_configured


class Command(BaseCommand):
    help = "Submit queued paid-order refunds to Razorpay."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        if not razorpay_is_configured():
            self.stderr.write(self.style.ERROR("Razorpay credentials are not configured."))
            return
        ids = list(
            Refund.objects.filter(status=Refund.Status.REQUESTED)
            .order_by("created_at")
            .values_list("pk", flat=True)[: options["limit"]]
        )
        submitted = 0
        failed = 0
        client = get_razorpay_client()
        for refund_id in ids:
            with transaction.atomic():
                refund = Refund.objects.select_for_update().select_related("payment__order").get(pk=refund_id)
                if refund.status != Refund.Status.REQUESTED:
                    continue
                payment = refund.payment
                if not payment.gateway_payment_id:
                    refund.status = Refund.Status.FAILED
                    refund.save(update_fields=["status", "updated_at"])
                    failed += 1
                    continue
                refund.status = Refund.Status.PROCESSING
                refund.save(update_fields=["status", "updated_at"])
            try:
                response = client.payment.refund(
                    payment.gateway_payment_id,
                    {
                        "amount": int(refund.amount * 100),
                        "speed": "normal",
                        "notes": {"order_number": payment.order.order_number, "reason": refund.reason[:200]},
                    },
                )
            except Exception:
                refund.status = Refund.Status.FAILED
                refund.save(update_fields=["status", "updated_at"])
                failed += 1
                continue
            refund.gateway_refund_id = response.get("id", "")
            refund.status = (
                Refund.Status.COMPLETED
                if response.get("status") == "processed"
                else Refund.Status.PROCESSING
            )
            refund.save(update_fields=["gateway_refund_id", "status", "updated_at"])
            if refund.status == Refund.Status.COMPLETED:
                self._mark_payment_refunded(refund)
            submitted += 1
        self.stdout.write(self.style.SUCCESS(f"Refund queue processed: {submitted} submitted, {failed} failed."))

    @staticmethod
    def _mark_payment_refunded(refund):
        payment = refund.payment
        payment.refunded_amount = min(payment.amount, payment.refunded_amount + refund.amount)
        payment.status = (
            Order.PaymentStatus.REFUNDED
            if payment.refunded_amount >= payment.amount
            else Order.PaymentStatus.PARTIALLY_REFUNDED
        )
        payment.save(update_fields=["refunded_amount", "status", "updated_at"])
        payment.order.payment_status = payment.status
        payment.order.save(update_fields=["payment_status", "updated_at"])
