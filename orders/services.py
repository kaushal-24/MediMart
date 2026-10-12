from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from extras.models import Notification
from extras.services import create_notification

from .models import (
    InventoryBatch,
    InventoryMovement,
    Order,
    OrderStatusHistory,
    OrderItem,
    Payment,
    RecallNotice,
    Refund,
    ReturnRequest,
)


@transaction.atomic
def activate_recall_notice(recall, actor=None):
    """Quarantine the affected stock and notify customers with traceable order lines."""
    recall = RecallNotice.objects.select_for_update().select_related("product", "batch").get(pk=recall.pk)
    recall.status = RecallNotice.Status.ACTIVE
    if actor:
        recall.initiated_by = actor
    recall.save(update_fields=["status", "initiated_by", "updated_at"])

    affected_batches = InventoryBatch.objects.filter(vendor_product__product=recall.product)
    if recall.batch_id:
        affected_batches = affected_batches.filter(pk=recall.batch_id)
    affected_batches.update(
        is_quarantined=True,
        quarantine_reason=recall.reason[:255],
        recall_reference=recall.reference,
        excursion_status="normal",
    )
    recall.product.recall_status = recall.product.RecallStatus.RECALLED
    recall.product.recall_reference = recall.reference
    recall.product.recall_reason = recall.reason[:255]
    recall.product.is_active = False
    recall.product.save(update_fields=["recall_status", "recall_reference", "recall_reason", "is_active", "updated_at"])

    lines = OrderItem.objects.select_related("order__customer").filter(product=recall.product)
    if recall.batch_id:
        lines = lines.filter(dispensed_batch_id=recall.batch_id)
    customer_ids = set()
    for line in lines:
        if line.order.customer_id in customer_ids:
            continue
        customer_ids.add(line.order.customer_id)
        create_notification(
            line.order.customer,
            "Important product recall notice",
            f"Please stop using {recall.product.name} from recall {recall.reference}. Support will help with the next step.",
            Notification.NotificationType.ORDER,
            reverse("orders:order_detail", args=[line.order.pk]),
        )
    recall.affected_customers_notified_at = timezone.now()
    recall.save(update_fields=["affected_customers_notified_at", "updated_at"])
    return recall


@transaction.atomic
def create_return_refund(return_request, requested_by=None):
    """Create one refund queue entry after a returned item is received and inspected."""
    return_request = (
        ReturnRequest.objects.select_for_update()
        .select_related("order_item__order__payment", "user")
        .get(pk=return_request.pk)
    )
    if return_request.status != ReturnRequest.Status.RECEIVED:
        raise ValueError("A refund can be created only after the returned item is received.")
    if return_request.inspection_decision not in {
        ReturnRequest.InspectionDecision.ACCEPTED,
        ReturnRequest.InspectionDecision.RESTOCKED,
    }:
        raise ValueError("Inspect and accept the returned item before queueing its refund.")

    order = return_request.order_item.order
    payment, _ = Payment.objects.get_or_create(
        order=order,
        defaults={
            "payment_method": order.payment_method,
            "amount": order.total_amount,
            "status": order.payment_status,
        },
    )
    refund, created = Refund.objects.get_or_create(
        return_request=return_request,
        defaults={
            "payment": payment,
            "amount": return_request.refund_amount,
            "reason": f"Return request #{return_request.pk}: {return_request.get_reason_display()}",
            "requested_by": requested_by,
        },
    )
    if not created and refund.payment_id != payment.pk:
        raise ValueError("This return is linked to a different payment record.")

    return_request.status = ReturnRequest.Status.REFUND_PENDING
    return_request.save(update_fields=["status", "updated_at"])
    create_notification(
        return_request.user,
        "Return received; refund queued",
        f"Your returned {return_request.order_item.product_name} was received. Refund processing has started.",
        Notification.NotificationType.ORDER,
        reverse("orders:return_list"),
    )
    return refund


@transaction.atomic
def restock_return_inventory(return_request, actor=None):
    """Return accepted units to their traced batch and seller stock once."""
    return_request = (
        ReturnRequest.objects.select_for_update()
        .select_related("order_item__dispensed_batch")
        .get(pk=return_request.pk)
    )
    batch = return_request.order_item.dispensed_batch
    if not batch:
        return False
    reference = f"return:{return_request.pk}"
    if InventoryMovement.objects.filter(
        batch=batch,
        movement_type=InventoryMovement.MovementType.RETURN,
        reference=reference,
    ).exists():
        return True
    batch.quantity += return_request.quantity
    batch.save(update_fields=["quantity", "updated_at"])
    from vendors.models import VendorProduct

    VendorProduct.objects.filter(pk=batch.vendor_product_id).update(
        stock_quantity=F("stock_quantity") + return_request.quantity,
        updated_at=timezone.now(),
    )
    InventoryMovement.objects.create(
        batch=batch,
        movement_type=InventoryMovement.MovementType.RETURN,
        quantity=return_request.quantity,
        reference=reference,
        actor=actor,
    )
    return True


@transaction.atomic
def complete_refund(refund, resolution_note="Refund completed by the payment provider."):
    """Apply one successful refund exactly once and close a linked return request."""
    refund = (
        Refund.objects.select_for_update()
        .select_related("payment__order")
        .get(pk=refund.pk)
    )
    if refund.status == Refund.Status.COMPLETED:
        return refund

    try:
        return_request = refund.return_request
    except ReturnRequest.DoesNotExist:
        return_request = None

    refund.status = Refund.Status.COMPLETED
    refund.save(update_fields=["status", "updated_at"])
    payment = refund.payment
    payment.refunded_amount = min(payment.amount, payment.refunded_amount + refund.amount)
    payment.status = (
        Order.PaymentStatus.REFUNDED
        if payment.refunded_amount >= payment.amount
        else Order.PaymentStatus.PARTIALLY_REFUNDED
    )
    payment.save(update_fields=["refunded_amount", "status", "updated_at"])
    payment.order.payment_status = payment.status
    order_update_fields = ["payment_status", "updated_at"]
    if return_request:
        payment.order.order_status = (
            Order.OrderStatus.REFUNDED
            if payment.status == Order.PaymentStatus.REFUNDED
            else Order.OrderStatus.RETURNED
        )
        order_update_fields.append("order_status")
    payment.order.save(update_fields=order_update_fields)
    if return_request and return_request.status == ReturnRequest.Status.REFUND_PENDING:
        return_request.status = ReturnRequest.Status.COMPLETED
        return_request.resolution_note = resolution_note[:500]
        return_request.save(update_fields=["status", "resolution_note", "updated_at"])
        OrderStatusHistory.objects.create(
            order=payment.order,
            status=payment.order.order_status,
            note="Return refund completed.",
            actor=refund.requested_by,
        )
        create_notification(
            return_request.user,
            "Return refund completed",
            f"Your refund of ₹{refund.amount} for {return_request.order_item.product_name} has been completed.",
            Notification.NotificationType.ORDER,
            reverse("orders:return_list"),
        )
    return refund
