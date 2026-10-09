import hashlib
import json
import uuid
from decimal import Decimal
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, models, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from cart.models import Cart
from extras.models import Notification
from extras.services import create_notification
from prescriptions.models import Prescription, PrescriptionItem
from prescriptions.views import user_has_approved_prescription
from vendors.models import VendorProduct

from .forms import CheckoutForm
from .models import (
    Coupon,
    CouponUsage,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PaymentEvent,
    Refund,
)


class CheckoutStockError(Exception):
    pass


def get_user_cart_items(user):
    try:
        cart = user.cart
    except Cart.DoesNotExist:
        return []
    return list(
        cart.items.select_related(
            "vendor_product",
            "vendor_product__product",
            "vendor_product__vendor",
        )
    )


def calculate_cart_totals(items, coupon=None):
    subtotal = sum(item.total_price for item in items)
    discount = Decimal("0.00")
    if coupon:
        discount = coupon.calculate_discount(subtotal)
    delivery_charge = Decimal("0.00") if subtotal == 0 else Decimal("49.00")
    total_amount = subtotal - discount + delivery_charge
    return subtotal, discount, delivery_charge, total_amount


def get_valid_coupon(code, user, subtotal):
    if not code:
        return None, ""

    today = timezone.localdate()
    try:
        coupon = Coupon.objects.get(code=code.upper(), is_active=True)
    except Coupon.DoesNotExist:
        return None, "Coupon code is not valid."

    if coupon.start_date > today or coupon.end_date < today:
        return None, "Coupon is not active today."
    if coupon.usages.count() >= coupon.usage_limit:
        return None, "Coupon usage limit has been reached."
    if subtotal < coupon.minimum_order:
        return None, f"Minimum order for this coupon is ₹{coupon.minimum_order}."
    if CouponUsage.objects.filter(coupon=coupon, user=user).exists():
        return None, "You have already used this coupon."

    return coupon, ""


def get_cart_blocking_message(user, items):
    if not items:
        return "Your cart is empty."

    for item in items:
        offer = item.vendor_product
        if not offer.is_active or not offer.is_approved:
            return f"{offer.product.name} is no longer available from {offer.vendor.business_name}."
        if not offer.vendor.is_active or not offer.vendor.is_approved:
            return f"{offer.vendor.business_name} is no longer an approved seller."
        if item.quantity > offer.stock_quantity:
            return f"Only {offer.stock_quantity} unit(s) are available for {offer.product.name}."
        if offer.product.requires_prescription and not user_has_approved_prescription(
            user,
            offer.product,
            item.quantity,
        ):
            return f"{offer.product.name} requires an approved prescription before checkout."
    return ""


def build_address_snapshot(address):
    parts = [
        address.full_name,
        address.phone,
        address.address_line_1,
        address.address_line_2,
        f"{address.city}, {address.state} - {address.pincode}",
        f"Landmark: {address.landmark}" if address.landmark else "",
    ]
    return "\n".join(part for part in parts if part)


@login_required
def checkout(request):
    items = get_user_cart_items(request.user)
    blocking_message = get_cart_blocking_message(request.user, items)
    if blocking_message:
        messages.error(request, blocking_message)
        if "prescription" in blocking_message.lower():
            return redirect("prescriptions:prescription_upload")
        return redirect("cart:cart_detail")

    if not request.user.addresses.exists():
        messages.info(request, "Add a delivery address before checkout.")
        return redirect("accounts:address_create")

    form = CheckoutForm(request.POST or None, user=request.user)
    coupon = None
    coupon_error = ""
    subtotal, discount, delivery_charge, total_amount = calculate_cart_totals(items)

    if request.method == "POST" and form.is_valid():
        payment_method = form.cleaned_data["payment_method"]
        if payment_method == Order.PaymentMethod.RAZORPAY and not razorpay_is_configured():
            messages.error(
                request,
                "Razorpay is not configured yet. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env.",
            )
            return redirect("orders:checkout")

        coupon, coupon_error = get_valid_coupon(
            form.cleaned_data.get("coupon_code", ""),
            request.user,
            subtotal,
        )
        subtotal, discount, delivery_charge, total_amount = calculate_cart_totals(items, coupon)

        if coupon_error:
            messages.error(request, coupon_error)
        else:
            try:
                with transaction.atomic():
                    order = create_order_from_cart(
                        user=request.user,
                        items=items,
                        address=form.cleaned_data["address"],
                        coupon=coupon,
                        subtotal=subtotal,
                        discount=discount,
                        delivery_charge=delivery_charge,
                        total_amount=total_amount,
                        payment_method=payment_method,
                    )
                    request.user.cart.items.all().delete()
            except CheckoutStockError as exc:
                messages.error(request, str(exc))
                return redirect("cart:cart_detail")
            create_notification(
                request.user,
                "Order placed",
                f"Your order {order.order_number} was placed successfully.",
                Notification.NotificationType.ORDER,
                order.get_absolute_url() if hasattr(order, "get_absolute_url") else "",
            )
            messages.success(request, f"Order {order.order_number} placed successfully.")
            if payment_method == Order.PaymentMethod.RAZORPAY:
                return redirect("orders:payment_start", pk=order.pk)
            return redirect("orders:order_detail", pk=order.pk)

    return render(
        request,
        "orders/checkout.html",
        {
            "form": form,
            "items": items,
            "subtotal": subtotal,
            "discount": discount,
            "delivery_charge": delivery_charge,
            "total_amount": total_amount,
        },
    )


def create_order_from_cart(
    user,
    items,
    address,
    coupon,
    subtotal,
    discount,
    delivery_charge,
    total_amount,
    payment_method,
):
    if payment_method not in {Order.PaymentMethod.COD, Order.PaymentMethod.RAZORPAY}:
        raise CheckoutStockError("This payment method is no longer supported.")
    locked_offers = {}
    locked_lines = []
    for item in items:
        offer = (
            VendorProduct.objects.select_for_update()
            .select_related("vendor", "product")
            .get(pk=item.vendor_product_id)
        )
        if not offer.is_active or not offer.is_approved or not offer.vendor.is_approved:
            raise CheckoutStockError(f"{offer.product.name} is no longer available from this seller.")
        if item.quantity > offer.stock_quantity:
            raise CheckoutStockError(
                f"Only {offer.stock_quantity} unit(s) remain for {offer.product.name}. Your cart was not changed."
            )
        locked_offers[item.pk] = offer
        locked_lines.append((item, offer, offer.price * item.quantity))

    subtotal = sum((line_total for _, _, line_total in locked_lines), Decimal("0.00"))
    if coupon:
        coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
        today = timezone.localdate()
        if not coupon.is_active or coupon.start_date > today or coupon.end_date < today:
            raise CheckoutStockError("The selected coupon is no longer active.")
        if coupon.usages.count() >= coupon.usage_limit:
            raise CheckoutStockError("The selected coupon usage limit has been reached.")
        if CouponUsage.objects.filter(coupon=coupon, user=user).exists():
            raise CheckoutStockError("You have already used this coupon.")
        if subtotal < coupon.minimum_order:
            raise CheckoutStockError(f"Minimum order for this coupon is ₹{coupon.minimum_order}.")
    discount = coupon.calculate_discount(subtotal) if coupon else Decimal("0.00")
    delivery_charge = Decimal("0.00") if subtotal == 0 else Decimal("49.00")
    total_amount = subtotal - discount + delivery_charge

    payment_status = Order.PaymentStatus.PENDING
    order_status = (
        Order.OrderStatus.CONFIRMED
        if payment_method == Order.PaymentMethod.COD
        else Order.OrderStatus.PENDING
    )
    order = Order.objects.create(
        customer=user,
        address=address,
        address_snapshot=build_address_snapshot(address),
        subtotal=subtotal,
        discount=discount,
        delivery_charge=delivery_charge,
        total_amount=total_amount,
        coupon=coupon,
        payment_method=payment_method,
        payment_status=payment_status,
        order_status=order_status,
        stock_reserved_until=(
            timezone.now() + timedelta(minutes=settings.PAYMENT_RESERVATION_MINUTES)
            if payment_method == Order.PaymentMethod.RAZORPAY
            else None
        ),
    )

    used_prescription_ids = set()
    for item, offer, line_total in locked_lines:
        prescription_item = None
        if offer.product.requires_prescription:
            prescription_item = _lock_authorizing_prescription_item(
                user,
                offer.product,
                item.quantity,
            )
            if not prescription_item:
                raise CheckoutStockError(
                    f"The approved prescription for {offer.product.name} is no longer valid or has insufficient quantity."
                )
            prescription_item.fulfilled_quantity += item.quantity
            prescription_item.save(update_fields=["fulfilled_quantity"])
            used_prescription_ids.add(prescription_item.prescription_id)
        OrderItem.objects.create(
            order=order,
            vendor_product=offer,
            vendor=offer.vendor,
            product=offer.product,
            prescription_item=prescription_item,
            product_name=offer.product.name,
            seller_name=offer.vendor.business_name,
            sku=offer.product.sku,
            quantity=item.quantity,
            unit_price=offer.price,
            total_price=line_total,
        )
        offer.stock_quantity -= item.quantity
        offer.save(update_fields=["stock_quantity", "updated_at"])

    if used_prescription_ids:
        Prescription.objects.filter(pk__in=used_prescription_ids).update(
            fulfillment_count=models.F("fulfillment_count") + 1,
            updated_at=timezone.now(),
        )

    OrderStatusHistory.objects.create(
        order=order,
        status=order.order_status,
        note="Order placed by customer.",
        actor=user,
    )
    Payment.objects.create(
        order=order,
        payment_method=payment_method,
        amount=total_amount,
        status=payment_status,
        transaction_id="",
    )
    if coupon:
        CouponUsage.objects.create(coupon=coupon, user=user, order=order)

    return order


def _lock_authorizing_prescription_item(user, product, quantity):
    candidates = (
        PrescriptionItem.objects.select_for_update()
        .select_related("prescription")
        .filter(
            prescription__user=user,
            prescription__status=Prescription.Status.APPROVED,
            prescription__valid_until__gte=timezone.localdate(),
            product=product,
        )
        .order_by("prescription__valid_until", "prescription__created_at")
    )
    for candidate in candidates:
        if candidate.prescription.is_current and candidate.remaining_quantity >= quantity:
            return candidate
    return None


def release_order_inventory(order_pk, *, reason, actor=None):
    order = (
        Order.objects.select_for_update()
        .prefetch_related("items__prescription_item__prescription")
        .get(pk=order_pk)
    )
    if order.inventory_released_at:
        return order

    prescription_ids = set()
    for item in order.items.all():
        offer = VendorProduct.objects.select_for_update().get(pk=item.vendor_product_id)
        offer.stock_quantity = models.F("stock_quantity") + item.quantity
        offer.save(update_fields=["stock_quantity", "updated_at"])
        if item.prescription_item_id:
            prescription_item = PrescriptionItem.objects.select_for_update().get(
                pk=item.prescription_item_id
            )
            prescription_item.fulfilled_quantity = max(
                0,
                prescription_item.fulfilled_quantity - item.quantity,
            )
            prescription_item.save(update_fields=["fulfilled_quantity"])
            prescription_ids.add(prescription_item.prescription_id)

    for prescription in Prescription.objects.select_for_update().filter(pk__in=prescription_ids):
        prescription.fulfillment_count = max(0, prescription.fulfillment_count - 1)
        prescription.save(update_fields=["fulfillment_count", "updated_at"])

    order.inventory_released_at = timezone.now()
    order.stock_reserved_until = None
    if order.order_status in {Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED}:
        order.order_status = Order.OrderStatus.CANCELLED
        order.cancelled_at = timezone.now()
        order.cancellation_reason = reason[:255]
    order.save(
        update_fields=[
            "inventory_released_at",
            "stock_reserved_until",
            "order_status",
            "cancelled_at",
            "cancellation_reason",
            "updated_at",
        ]
    )
    OrderStatusHistory.objects.create(
        order=order,
        status=order.order_status,
        note=reason[:255],
        actor=actor,
    )
    return order


@login_required
def order_list(request):
    orders = request.user.orders.all()
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "status_history"),
        pk=pk,
        customer=request.user,
    )
    can_cancel = order.order_status in {Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED}
    return render(
        request,
        "orders/order_detail.html",
        {"order": order, "can_cancel": can_cancel},
    )


@login_required
@require_POST
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if order.order_status not in {Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED}:
        messages.error(request, "This order can no longer be cancelled online.")
        return redirect("orders:order_detail", pk=order.pk)
    reason = request.POST.get("reason", "Cancelled by customer.").strip() or "Cancelled by customer."
    with transaction.atomic():
        order = release_order_inventory(order.pk, reason=reason, actor=request.user)
        if order.payment_status == Order.PaymentStatus.PAID:
            Refund.objects.get_or_create(
                payment=order.payment,
                status=Refund.Status.REQUESTED,
                defaults={
                    "amount": order.total_amount,
                    "reason": reason[:255],
                    "requested_by": request.user,
                },
            )
    messages.success(
        request,
        "Order cancelled. A refund request was created." if order.payment_status == Order.PaymentStatus.PAID else "Order cancelled.",
    )
    return redirect("orders:order_detail", pk=order.pk)


@login_required
def invoice_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        pk=pk,
        customer=request.user,
    )
    return render(request, "orders/invoice.html", {"order": order})


@login_required
def invoice_pdf(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        pk=pk,
        customer=request.user,
    )
    buffer = BytesIO()
    build_invoice_pdf(order, buffer)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice-{order.order_number}.pdf"'
    return response


@login_required
def payment_start(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if order.payment_method != Order.PaymentMethod.RAZORPAY:
        return redirect("orders:order_detail", pk=order.pk)
    if not razorpay_is_configured():
        messages.error(request, "Razorpay keys are missing.")
        return redirect("orders:order_detail", pk=order.pk)
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:order_detail", pk=order.pk)
    if order.inventory_released_at or (
        order.stock_reserved_until and order.stock_reserved_until <= timezone.now()
    ):
        with transaction.atomic():
            release_order_inventory(order.pk, reason="Online payment reservation expired.")
        messages.error(request, "This payment reservation expired. Please place the order again.")
        return redirect("orders:order_detail", pk=order.pk)
    if not getattr(order, "payment", None) or not order.payment.gateway_order_id:
        try:
            gateway_order = create_razorpay_order(order)
        except Exception:
            messages.error(request, "The payment gateway is temporarily unavailable. Please try again.")
            return redirect("orders:order_detail", pk=order.pk)
        order.payment.gateway_order_id = gateway_order["id"]
        order.payment.transaction_id = gateway_order["id"]
        order.payment.save(update_fields=["gateway_order_id", "transaction_id", "updated_at"])
        record_payment_event(
            order.payment,
            "gateway_order_created",
            {"gateway_order_id": gateway_order["id"], "amount": gateway_order.get("amount")},
        )

    return render(
        request,
        "orders/payment_start.html",
        {
            "order": order,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "gateway_order_id": order.payment.gateway_order_id,
            "amount_paise": int(order.total_amount * 100),
            "currency": settings.RAZORPAY_CURRENCY,
        },
    )


@login_required
@require_POST
def payment_verify(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    payload = {
        "razorpay_order_id": request.POST.get("razorpay_order_id"),
        "razorpay_payment_id": request.POST.get("razorpay_payment_id"),
        "razorpay_signature": request.POST.get("razorpay_signature"),
    }
    payment = getattr(order, "payment", None)
    if not payment or not all(payload.values()):
        messages.error(request, "Payment verification data is incomplete.")
        return redirect("orders:payment_start", pk=order.pk)
    if payload["razorpay_order_id"] != payment.gateway_order_id:
        record_payment_event(payment, "verification_rejected", {"reason": "gateway_order_mismatch"})
        messages.error(request, "Payment verification failed.")
        return redirect("orders:payment_start", pk=order.pk)
    try:
        client = get_razorpay_client()
        client.utility.verify_payment_signature(payload)
        gateway_payment = client.payment.fetch(payload["razorpay_payment_id"])
        _validate_gateway_payment(order, payment, gateway_payment)
    except Exception:
        record_payment_event(
            payment,
            "verification_rejected",
            {"reason": "signature_or_gateway_validation_failed"},
        )
        messages.error(request, "Payment verification failed.")
        return redirect("orders:payment_start", pk=order.pk)
    with transaction.atomic():
        settle_payment(
            order.pk,
            gateway_payment_id=payload["razorpay_payment_id"],
            gateway_signature=payload["razorpay_signature"],
            event_type="browser_payment_verified",
            event_payload={"gateway_order_id": payload["razorpay_order_id"]},
            actor=request.user,
        )
    messages.success(request, "Payment completed successfully.")
    return redirect("orders:order_detail", pk=order.pk)


def _validate_gateway_payment(order, payment, gateway_payment):
    if gateway_payment.get("order_id") != payment.gateway_order_id:
        raise ValueError("Gateway order does not match.")
    if int(gateway_payment.get("amount", -1)) != int(order.total_amount * 100):
        raise ValueError("Gateway amount does not match.")
    if gateway_payment.get("currency") != settings.RAZORPAY_CURRENCY:
        raise ValueError("Gateway currency does not match.")
    if gateway_payment.get("status") != "captured":
        raise ValueError("Payment has not been captured.")


def settle_payment(
    order_pk,
    *,
    gateway_payment_id,
    gateway_signature="",
    event_type,
    event_payload=None,
    provider_event_id=None,
    actor=None,
):
    order = Order.objects.select_for_update().get(pk=order_pk)
    payment = Payment.objects.select_for_update().get(order=order)
    if payment.status == Order.PaymentStatus.PAID:
        if payment.gateway_payment_id and payment.gateway_payment_id != gateway_payment_id:
            raise ValueError("Order is already linked to another payment.")
        return order
    if order.inventory_released_at:
        raise ValueError("Inventory reservation has already been released.")
    payment.status = Order.PaymentStatus.PAID
    payment.transaction_id = gateway_payment_id
    payment.gateway_payment_id = gateway_payment_id
    payment.gateway_signature = gateway_signature
    payment.verified_at = timezone.now()
    payment.failure_description = ""
    payment.save(
        update_fields=[
            "status",
            "transaction_id",
            "gateway_payment_id",
            "gateway_signature",
            "verified_at",
            "failure_description",
            "updated_at",
        ]
    )
    order.payment_status = Order.PaymentStatus.PAID
    order.order_status = Order.OrderStatus.CONFIRMED
    order.stock_reserved_until = None
    order.save(update_fields=["payment_status", "order_status", "stock_reserved_until", "updated_at"])
    record_payment_event(
        payment,
        event_type,
        event_payload or {},
        provider_event_id=provider_event_id,
    )
    OrderStatusHistory.objects.create(
        order=order,
        status=order.order_status,
        note="Razorpay payment verified.",
        actor=actor,
    )
    return order


@csrf_exempt
@require_POST
def payment_webhook(request):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return JsonResponse({"ok": False, "error": "Webhook is not configured."}, status=503)
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
        body = request.body.decode("utf-8")
        get_razorpay_client().utility.verify_webhook_signature(
            body,
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET,
        )
        payload = json.loads(body)
    except Exception:
        return JsonResponse({"ok": False}, status=400)

    event_type = payload.get("event", "")
    if event_type in {"refund.processed", "refund.failed"}:
        refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        refund_record = Refund.objects.filter(
            gateway_refund_id=refund_entity.get("id", "")
        ).select_related("payment__order").first()
        if not refund_record:
            return JsonResponse({"ok": True, "ignored": True})
        provider_event_id = request.headers.get("X-Razorpay-Event-Id") or None
        if provider_event_id and PaymentEvent.objects.filter(event_id=provider_event_id).exists():
            return JsonResponse({"ok": True, "duplicate": True})
        with transaction.atomic():
            refund_record = Refund.objects.select_for_update().select_related("payment__order").get(
                pk=refund_record.pk
            )
            was_completed = refund_record.status == Refund.Status.COMPLETED
            refund_record.status = (
                Refund.Status.COMPLETED
                if event_type == "refund.processed"
                else Refund.Status.FAILED
            )
            refund_record.save(update_fields=["status", "updated_at"])
            if refund_record.status == Refund.Status.COMPLETED and not was_completed:
                payment = refund_record.payment
                payment.refunded_amount = min(
                    payment.amount,
                    payment.refunded_amount + refund_record.amount,
                )
                payment.status = (
                    Order.PaymentStatus.REFUNDED
                    if payment.refunded_amount >= payment.amount
                    else Order.PaymentStatus.PARTIALLY_REFUNDED
                )
                payment.save(update_fields=["refunded_amount", "status", "updated_at"])
                payment.order.payment_status = payment.status
                payment.order.save(update_fields=["payment_status", "updated_at"])
            record_payment_event(
                refund_record.payment,
                event_type,
                {"refund_id": refund_record.gateway_refund_id, "status": refund_entity.get("status")},
                provider_event_id=provider_event_id,
            )
        return JsonResponse({"ok": True})

    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    gateway_order_id = entity.get("order_id", "")
    provider_event_id = request.headers.get("X-Razorpay-Event-Id") or None
    if provider_event_id and PaymentEvent.objects.filter(event_id=provider_event_id).exists():
        return JsonResponse({"ok": True, "duplicate": True})
    payment = Payment.objects.filter(gateway_order_id=gateway_order_id).select_related("order").first()
    if not payment:
        return JsonResponse({"ok": True, "ignored": True})

    if event_type == "payment.captured":
        try:
            _validate_gateway_payment(payment.order, payment, entity)
            with transaction.atomic():
                settle_payment(
                    payment.order_id,
                    gateway_payment_id=entity.get("id", ""),
                    event_type=event_type,
                    event_payload={
                        "gateway_order_id": gateway_order_id,
                        "amount": entity.get("amount"),
                        "currency": entity.get("currency"),
                    },
                    provider_event_id=provider_event_id,
                )
        except (ValueError, IntegrityError):
            return JsonResponse({"ok": False}, status=409)
    else:
        record_payment_event(
            payment,
            event_type or "unknown_webhook",
            {"gateway_order_id": gateway_order_id, "payment_id": entity.get("id", "")},
            provider_event_id=provider_event_id,
        )
    return JsonResponse({"ok": True})


def record_payment_event(payment, event_type, payload=None, provider_event_id=None):
    payload = payload or {}
    event_id = provider_event_id or uuid.uuid4().hex
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload_hash = hashlib.sha256(f"{event_id}:{canonical}".encode("utf-8")).hexdigest()
    return PaymentEvent.objects.create(
        payment=payment,
        event_id=event_id,
        event_type=event_type,
        payload_hash=payload_hash,
        gateway_order_id=payment.gateway_order_id or "",
        gateway_payment_id=payment.gateway_payment_id or "",
        processed=True,
        processed_at=timezone.now(),
        payload=payload,
    )


def razorpay_is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def get_razorpay_client():
    import razorpay

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    client.set_app_details({"title": "MediMart", "version": "1.0"})
    return client


def create_razorpay_order(order):
    client = get_razorpay_client()
    return client.order.create(
        {
            "amount": int(order.total_amount * 100),
            "currency": settings.RAZORPAY_CURRENCY,
            "receipt": order.order_number,
            "payment_capture": 1,
            "notes": {"order_number": order.order_number, "customer": order.customer.username},
        }
    )


def build_invoice_pdf(order, stream):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(stream, pagesize=A4)
    width, height = A4
    x = 20 * mm
    y = height - 20 * mm

    pdf.setTitle(f"MediMart Invoice {order.order_number}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(x, y, "MediMart Invoice")
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(width - x, y, f"Invoice #INV-{order.order_number}")
    y -= 8 * mm
    pdf.drawString(x, y, f"Order: {order.order_number}")
    pdf.drawRightString(width - x, y, f"Date: {order.created_at:%d %b %Y}")
    y -= 10 * mm

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(x, y, "Customer")
    pdf.drawString(width / 2, y, "Delivery Address")
    pdf.setFont("Helvetica", 9)
    y -= 5 * mm
    pdf.drawString(x, y, order.customer.get_full_name() or order.customer.username)
    address_y = y
    for line in order.address_snapshot.splitlines()[:6]:
        pdf.drawString(width / 2, address_y, line[:55])
        address_y -= 4.5 * mm
    y = min(y - 8 * mm, address_y - 4 * mm)

    pdf.setStrokeColor(colors.HexColor("#d0d5dd"))
    pdf.line(x, y, width - x, y)
    y -= 8 * mm

    pdf.setFont("Helvetica-Bold", 9)
    columns = [x, x + 70 * mm, x + 112 * mm, x + 132 * mm, width - x]
    pdf.drawString(columns[0], y, "Product")
    pdf.drawString(columns[1], y, "Seller")
    pdf.drawRightString(columns[2], y, "Qty")
    pdf.drawRightString(columns[3], y, "Price")
    pdf.drawRightString(columns[4], y, "Total")
    y -= 5 * mm
    pdf.setFont("Helvetica", 9)
    for item in order.items.all():
        if y < 35 * mm:
            pdf.showPage()
            y = height - 20 * mm
            pdf.setFont("Helvetica", 9)
        pdf.drawString(columns[0], y, item.product_name[:38])
        pdf.drawString(columns[1], y, item.seller_name[:24])
        pdf.drawRightString(columns[2], y, str(item.quantity))
        pdf.drawRightString(columns[3], y, f"Rs. {item.unit_price}")
        pdf.drawRightString(columns[4], y, f"Rs. {item.total_price}")
        y -= 6 * mm

    y -= 4 * mm
    pdf.line(width - 80 * mm, y, width - x, y)
    y -= 7 * mm
    totals = [
        ("Subtotal", order.subtotal),
        ("Discount", order.discount),
        ("Delivery", order.delivery_charge),
        ("Total", order.total_amount),
    ]
    for label, amount in totals:
        pdf.setFont("Helvetica-Bold" if label == "Total" else "Helvetica", 10)
        pdf.drawString(width - 80 * mm, y, label)
        pdf.drawRightString(width - x, y, f"Rs. {amount}")
        y -= 6 * mm

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.HexColor("#667085"))
    pdf.drawString(x, 18 * mm, "Generated by MediMart.")
    pdf.save()
