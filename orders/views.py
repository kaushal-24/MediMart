import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, models, transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from cart.models import Cart, CartItem
from cart.views import get_or_create_cart
from extras.models import Notification
from extras.services import create_notification
from prescriptions.models import Prescription, PrescriptionItem
from prescriptions.views import user_has_approved_prescription
from vendors.models import BusinessLicense, VendorProduct
from core.throttling import rate_limit

from .forms import CheckoutForm, PaymentContactForm, ReturnRequestForm
from .models import (
    Coupon,
    CouponUsage,
    InventoryBatch,
    InventoryMovement,
    Order,
    OrderChargeBreakdown,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PaymentEvent,
    PaymentReconciliation,
    Refund,
    ReturnRequest,
)
from .services import complete_refund


class CheckoutStockError(Exception):
    pass


RETURN_TERMINAL_STATUSES = {
    ReturnRequest.Status.REJECTED,
    ReturnRequest.Status.CANCELLED,
    ReturnRequest.Status.COMPLETED,
}


def return_remaining_quantity(item):
    returned_quantity = sum(
        request.quantity
        for request in item.return_requests.all()
        if request.status not in {ReturnRequest.Status.REJECTED, ReturnRequest.Status.CANCELLED}
    )
    return max(0, item.quantity - returned_quantity)


@login_required
def return_request_create(request, item_pk):
    item = get_object_or_404(
        OrderItem.objects.select_related("order", "product"),
        pk=item_pk,
        order__customer=request.user,
    )
    if item.order.order_status != Order.OrderStatus.DELIVERED:
        messages.error(request, "Returns can be requested after delivery.")
        return redirect("orders:order_detail", pk=item.order.pk)

    delivered_history = item.order.status_history.filter(
        status=Order.OrderStatus.DELIVERED,
    ).order_by("-created_at").first()
    delivered_at = delivered_history.created_at if delivered_history else item.order.updated_at
    if delivered_at < timezone.now() - timedelta(days=7):
        messages.error(request, "The seven-day return window for this order has closed.")
        return redirect("orders:order_detail", pk=item.order.pk)

    remaining_quantity = return_remaining_quantity(item)
    if remaining_quantity <= 0:
        messages.info(request, "All units from this order line already have a return request.")
        return redirect("orders:order_detail", pk=item.order.pk)

    form = ReturnRequestForm(request.POST or None, request.FILES or None)
    form.fields["quantity"].widget.attrs["max"] = remaining_quantity
    if request.method == "POST" and form.is_valid():
        requested_quantity = form.cleaned_data["quantity"]
        if requested_quantity > remaining_quantity:
            form.add_error("quantity", f"Only {remaining_quantity} unit(s) remain eligible for return.")
        else:
            return_request = form.save(commit=False)
            return_request.order_item = item
            return_request.user = request.user
            return_request.refund_amount = item.unit_price * requested_quantity
            return_request.quantity = requested_quantity
            return_request.save()
            create_notification(
                request.user,
                "Return request received",
                f"MediMart received your return request for {item.product_name}.",
                Notification.NotificationType.ORDER,
                reverse("orders:return_list"),
            )
            messages.success(request, "Return request submitted for review.")
            return redirect("orders:return_list")
    return render(
        request,
        "orders/return_form.html",
        {"form": form, "item": item, "remaining_quantity": remaining_quantity},
    )


@login_required
def return_request_list(request):
    returns = request.user.return_requests.select_related(
        "order_item__order",
        "order_item__product",
        "refund",
        "refund__payment",
    )
    return render(request, "orders/return_list.html", {"returns": returns})


@login_required
@require_POST
def return_request_cancel(request, pk):
    return_request = get_object_or_404(ReturnRequest, pk=pk, user=request.user)
    if return_request.status not in {
        ReturnRequest.Status.REQUESTED,
        ReturnRequest.Status.UNDER_REVIEW,
        ReturnRequest.Status.APPROVED,
    }:
        messages.error(request, "This return can no longer be cancelled online.")
        return redirect("orders:return_list")
    return_request.status = ReturnRequest.Status.CANCELLED
    return_request.resolution_note = "Cancelled by customer."
    return_request.save(update_fields=["status", "resolution_note", "updated_at"])
    create_notification(
        request.user,
        "Return request cancelled",
        f"Your return request for {return_request.order_item.product_name} was cancelled.",
        Notification.NotificationType.ORDER,
        reverse("orders:return_list"),
    )
    messages.success(request, "Return request cancelled.")
    return redirect("orders:return_list")


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
    if subtotal == 0 or settings.FREE_DELIVERY:
        delivery_charge = Decimal("0.00")
    else:
        delivery_charge = Decimal(str(settings.DELIVERY_FEE))
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
        if not offer.is_active or not offer.is_approved or not offer.vendor.is_active:
            return f"{offer.product.name} is no longer available from {offer.vendor.business_name}."
        if not offer.vendor.is_active or not offer.vendor.is_approved:
            return f"{offer.vendor.business_name} is no longer an approved seller."
        if not offer.product.is_active:
            return f"{offer.product.name} is no longer available."
        if offer.product.requires_business_license:
            if not any(
                license_record.is_compatible_with(offer.product.required_license_type)
                for license_record in offer.vendor.licenses.filter(status=BusinessLicense.Status.VERIFIED)
            ):
                return f"{offer.product.name} is temporarily unavailable while the seller licence is being verified."
        if item.quantity > offer.stock_quantity:
            return f"Only {offer.stock_quantity} unit(s) are available for {offer.product.name}."
        safety_message = get_product_safety_blocking_message(offer, item.quantity)
        if safety_message:
            return safety_message
        if offer.product.requires_prescription and not user_has_approved_prescription(
            user,
            offer.product,
            item.quantity,
        ):
            return f"{offer.product.name} requires an approved prescription before checkout."
    return ""


def get_product_safety_blocking_message(offer, quantity, state=""):
    product = offer.product
    if state and not product.is_allowed_in_state(state):
        return f"{product.name} is not available for delivery in {state}."
    if product.recall_status in {
        product.RecallStatus.QUARANTINED,
        product.RecallStatus.RECALLED,
    }:
        return f"{product.name} is temporarily unavailable because it is under a safety hold."
    if product.safety_classification in {
        product.SafetyClassification.SCHEDULE_X,
        product.SafetyClassification.PROHIBITED,
    }:
        return f"{product.name} cannot be sold through this online pharmacy."
    if product.regulatory_schedule in {
        product.RegulatorySchedule.NDPS,
        product.RegulatorySchedule.HABIT_FORMING,
    }:
        return f"{product.name} requires a pharmacist-controlled dispensing workflow and cannot be added to online checkout yet."
    if product.quantity_limit_per_order and quantity > product.quantity_limit_per_order:
        return f"Only {product.quantity_limit_per_order} unit(s) of {product.name} can be ordered at a time."

    batches = offer.inventory_batches.all()
    if batches.exists():
        minimum_shelf_life_days = product.minimum_shelf_life_days
        safe_quantity = sum(
            batch.available_quantity
            for batch in batches
            if batch.is_sellable(minimum_shelf_life_days=minimum_shelf_life_days)
        )
        if safe_quantity < quantity:
            return f"{product.name} is temporarily unavailable while a safe, valid batch is being replenished."
    return ""


def get_cod_ineligibility(items, address, total_amount):
    if total_amount > Decimal(str(settings.COD_MAX_ORDER_VALUE)):
        return f"Cash on Delivery is available only for orders up to ₹{settings.COD_MAX_ORDER_VALUE}."
    if str(address.pincode).strip() in settings.COD_BLOCKED_PINCODES:
        return "Cash on Delivery is not available for this delivery pincode."
    if any(item.vendor_product.product.cold_chain_required for item in items):
        return "Cash on Delivery is unavailable for cold-chain products."
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
    if request.method != "POST":
        return redirect("cart:cart_detail")
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
            return redirect("cart:cart_detail")

        coupon, coupon_error = get_valid_coupon(
            form.cleaned_data.get("coupon_code", ""),
            request.user,
            subtotal,
        )
        subtotal, discount, delivery_charge, total_amount = calculate_cart_totals(items, coupon)

        if payment_method == Order.PaymentMethod.COD:
            cod_error = get_cod_ineligibility(items, form.cleaned_data["address"], total_amount)
            if cod_error:
                messages.error(request, cod_error)
                return redirect("cart:cart_detail")

        if coupon_error:
            messages.error(request, coupon_error)
            return redirect("cart:cart_detail")
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
                    request.session.pop("cart_coupon_code", None)
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

    for field_errors in form.errors.values():
        for error in field_errors:
            messages.error(request, error)
    return redirect("cart:cart_detail")


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
    cart = Cart.objects.select_for_update().get(user=user)
    items = list(
        cart.items.select_for_update()
        .select_related("vendor_product", "vendor_product__product", "vendor_product__vendor")
        .order_by("vendor_product_id", "pk")
    )
    if not items:
        raise CheckoutStockError("Your cart is empty.")
    locked_offers = {}
    locked_lines = []
    for item in items:
        offer = (
            VendorProduct.objects.select_for_update()
            .select_related("vendor", "product")
            .get(pk=item.vendor_product_id)
        )
        if (
            not offer.is_active
            or not offer.is_approved
            or not offer.vendor.is_active
            or not offer.vendor.is_approved
            or not offer.product.is_active
        ):
            raise CheckoutStockError(f"{offer.product.name} is no longer available from this seller.")
        if offer.product.requires_business_license:
            valid_licenses = offer.vendor.licenses.filter(status=BusinessLicense.Status.VERIFIED)
            if not any(
                license_record.is_compatible_with(offer.product.required_license_type)
                for license_record in valid_licenses
            ):
                raise CheckoutStockError(
                    f"{offer.product.name} is unavailable because this seller has no current compatible licence."
                )
        if item.quantity > offer.stock_quantity:
            raise CheckoutStockError(
                f"Only {offer.stock_quantity} unit(s) remain for {offer.product.name}. Your cart was not changed."
            )
        safety_message = get_product_safety_blocking_message(offer, item.quantity, address.state)
        if safety_message:
            raise CheckoutStockError(safety_message)
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
    if subtotal == 0 or settings.FREE_DELIVERY:
        delivery_charge = Decimal("0.00")
    else:
        delivery_charge = Decimal(str(settings.DELIVERY_FEE))
    total_amount = subtotal - discount + delivery_charge
    cod_error = get_cod_ineligibility(items, address, total_amount) if payment_method == Order.PaymentMethod.COD else ""
    if cod_error:
        raise CheckoutStockError(cod_error)

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
        _reserve_inventory_batches(offer, item.quantity, order.order_number, user)
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
    OrderChargeBreakdown.objects.create(
        order=order,
        subtotal=subtotal,
        discount=discount,
        delivery_charge=delivery_charge,
        total_amount=total_amount,
    )
    if coupon:
        CouponUsage.objects.create(coupon=coupon, user=user, order=order)

    return order


def _reserve_inventory_batches(offer, quantity, reference, actor=None):
    batches = list(
        InventoryBatch.objects.select_for_update()
        .filter(vendor_product=offer)
        .order_by("expires_on", "pk")
    )
    if not batches:
        return
    remaining = quantity
    minimum_shelf_life_days = offer.product.minimum_shelf_life_days
    for batch in batches:
        if not batch.is_sellable(minimum_shelf_life_days=minimum_shelf_life_days):
            continue
        reserved = min(remaining, batch.available_quantity)
        if not reserved:
            continue
        batch.reserved_quantity += reserved
        batch.save(update_fields=["reserved_quantity", "updated_at"])
        InventoryMovement.objects.create(
            batch=batch,
            movement_type=InventoryMovement.MovementType.RESERVATION,
            quantity=reserved,
            reference=reference,
            actor=actor,
        )
        remaining -= reserved
        if remaining <= 0:
            return
    if remaining:
        raise CheckoutStockError(
            f"The safe batch quantity for {offer.product.name} changed. Please try checkout again."
        )


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
    processed_reservation_ids = set()
    for item in order.items.all():
        offer = VendorProduct.objects.select_for_update().get(pk=item.vendor_product_id)
        offer.stock_quantity = models.F("stock_quantity") + item.quantity
        offer.save(update_fields=["stock_quantity", "updated_at"])
        reservations = list(
            InventoryMovement.objects.filter(
                batch__vendor_product=offer,
                movement_type=InventoryMovement.MovementType.RESERVATION,
                reference=order.order_number,
            ).select_related("batch")
        )
        for reservation in reservations:
            if reservation.pk in processed_reservation_ids:
                continue
            processed_reservation_ids.add(reservation.pk)
            batch = InventoryBatch.objects.select_for_update().get(pk=reservation.batch_id)
            released_quantity = min(batch.reserved_quantity, reservation.quantity)
            batch.reserved_quantity -= released_quantity
            batch.save(update_fields=["reserved_quantity", "updated_at"])
            InventoryMovement.objects.create(
                batch=batch,
                movement_type=InventoryMovement.MovementType.RELEASE,
                quantity=released_quantity,
                reference=order.order_number,
                actor=actor,
            )
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


def finalize_order_inventory_sale(order_pk, actor=None):
    """Convert a delivered order's batch reservations into sale movements once."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_pk)
        reservations = list(
            InventoryMovement.objects.filter(
                movement_type=InventoryMovement.MovementType.RESERVATION,
                reference=order.order_number,
            )
        )
        if not reservations or InventoryMovement.objects.filter(
            movement_type=InventoryMovement.MovementType.SALE,
            reference=order.order_number,
        ).exists():
            return order
        for reservation in reservations:
            batch = InventoryBatch.objects.select_for_update().get(pk=reservation.batch_id)
            quantity = min(reservation.quantity, batch.reserved_quantity, batch.quantity)
            if quantity < reservation.quantity:
                raise CheckoutStockError("Inventory cannot be finalized because a batch is inconsistent.")
            batch.quantity -= quantity
            batch.reserved_quantity -= quantity
            batch.save(update_fields=["quantity", "reserved_quantity", "updated_at"])
            InventoryMovement.objects.create(
                batch=batch,
                movement_type=InventoryMovement.MovementType.SALE,
                quantity=quantity,
                reference=order.order_number,
                actor=actor,
            )
            order.items.filter(
                vendor_product_id=batch.vendor_product_id,
                dispensed_batch__isnull=True,
            ).update(dispensed_batch=batch)
        return order


def _payment_contact_context(order):
    profile = getattr(order.customer, "profile", None)
    payment = getattr(order, "payment", None)
    return {
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "gateway_order_id": payment.gateway_order_id if payment else "",
        "amount_paise": int(order.total_amount * 100),
        "currency": settings.RAZORPAY_CURRENCY,
        "payment_contact_email": (order.customer.email or "").strip(),
        "payment_contact_phone": (getattr(profile, "phone_number", "") or order.address.phone or "").strip(),
    }


def _save_payment_contact(user, contact):
    if not user.email:
        user.email = contact["email"]
        user.save(update_fields=["email"])
    profile = getattr(user, "profile", None)
    if profile and not profile.phone_number:
        profile.phone_number = contact["phone"]
        profile.save(update_fields=["phone_number"])


@login_required
def order_list(request):
    orders = request.user.orders.all()
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
@require_POST
@transaction.atomic
def quick_reorder(request, pk):
    order = get_object_or_404(
        Order.objects.select_for_update().prefetch_related("items__vendor_product__vendor"),
        pk=pk,
        customer=request.user,
    )
    cart = get_or_create_cart(request.user)
    added = 0
    skipped = []

    for order_item in order.items.all():
        offer = order_item.vendor_product
        if not (
            offer.is_active
            and offer.is_approved
            and offer.vendor.is_active
            and offer.vendor.is_approved
            and offer.stock_quantity > 0
        ):
            skipped.append(order_item.product_name)
            continue
        if offer.product.requires_prescription and not user_has_approved_prescription(
            request.user,
            offer.product,
            order_item.quantity,
        ):
            skipped.append(f"{order_item.product_name} (prescription required)")
            continue

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            vendor_product=offer,
            defaults={"quantity": 0},
        )
        previous_quantity = item.quantity
        item.quantity = min(previous_quantity + order_item.quantity, offer.stock_quantity)
        if item.quantity <= 0:
            skipped.append(order_item.product_name)
            continue
        item.save(update_fields=["quantity", "updated_at"])
        added += item.quantity - previous_quantity

    if added:
        message = f"{added} item{'' if added == 1 else 's'} added to your cart."
        if skipped:
            message += " Some items were unavailable or need a valid prescription."
        status = 200
        ok = True
    else:
        message = "None of the items from this order are currently available to reorder."
        status = 400
        ok = False

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return JsonResponse(
            {
                "ok": ok,
                "message": message,
                "level": "success" if ok else "warning",
                "redirect_url": reverse("cart:cart_detail") if ok else "",
            },
            status=status,
        )
    if ok:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    return redirect("orders:order_list")


@login_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("address", "customer__profile").prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.prefetch_related("return_requests")),
            "status_history",
        ),
        pk=pk,
        customer=request.user,
    )
    for item in order.items.all():
        open_returns = [
            return_request
            for return_request in item.return_requests.all()
            if return_request.status not in RETURN_TERMINAL_STATUSES
        ]
        item.active_return_request = open_returns[-1] if open_returns else None
        item.return_remaining_quantity = return_remaining_quantity(item)
        item.can_request_return = bool(
            order.order_status == Order.OrderStatus.DELIVERED
            and item.return_remaining_quantity
        )
    can_cancel = order.order_status in {Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED}
    status_icons = {
        Order.OrderStatus.PENDING: "bi-hourglass-split",
        Order.OrderStatus.CONFIRMED: "bi-check2-circle",
        Order.OrderStatus.PROCESSING: "bi-box-seam",
        Order.OrderStatus.PACKED: "bi-box2-heart",
        Order.OrderStatus.SHIPPED: "bi-truck",
        Order.OrderStatus.OUT_FOR_DELIVERY: "bi-geo-alt",
        Order.OrderStatus.DELIVERED: "bi-house-check",
        Order.OrderStatus.CANCELLED: "bi-x-circle",
        Order.OrderStatus.RETURNED: "bi-arrow-return-left",
        Order.OrderStatus.REFUNDED: "bi-arrow-counterclockwise",
    }
    histories = list(order.status_history.all())
    current_history = next(
        (history for history in reversed(histories) if history.status == order.order_status),
        histories[-1] if histories else None,
    )
    tracking_timeline = [
        {
            "history": history,
            "icon": status_icons.get(history.status, "bi-circle"),
            "is_current": history is current_history,
        }
        for history in histories
    ]
    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "can_cancel": can_cancel,
            "tracking_timeline": tracking_timeline,
            **_payment_contact_context(order),
        },
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
        Order.objects.select_related("charge_breakdown").prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.select_related("vendor"))
        ),
        pk=pk,
        customer=request.user,
    )
    return render(request, "orders/invoice.html", {"order": order, **invoice_context(order)})


@login_required
def invoice_pdf(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("charge_breakdown").prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.select_related("vendor"))
        ),
        pk=pk,
        customer=request.user,
    )
    buffer = BytesIO()
    build_invoice_pdf(order, buffer)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice-{order.order_number}.pdf"'
    return response


def invoice_context(order):
    """Return seller and checkout-charge data shared by HTML and PDF invoices."""
    try:
        charge_breakdown = order.charge_breakdown
    except OrderChargeBreakdown.DoesNotExist:
        charge_breakdown = None

    seller_profiles = []
    seen_sellers = set()
    for item in order.items.all():
        vendor = getattr(item, "vendor", None)
        seller_key = vendor.pk if vendor else f"snapshot:{item.seller_name}"
        if seller_key in seen_sellers:
            continue
        seen_sellers.add(seller_key)
        seller_profiles.append(
            {
                "business_name": vendor.business_name if vendor else item.seller_name,
                "owner_name": vendor.owner_name if vendor else "",
                "email": vendor.email if vendor else "",
                "phone": vendor.phone if vendor else "",
                "address": vendor.address if vendor else "",
                "gst_number": vendor.gst_number if vendor else "",
                "license_number": vendor.license_number if vendor else "",
            }
        )

    return {
        "seller_profiles": seller_profiles,
        "invoice_totals": {
            "subtotal": charge_breakdown.subtotal if charge_breakdown else order.subtotal,
            "discount": charge_breakdown.discount if charge_breakdown else order.discount,
            "tax_amount": charge_breakdown.tax_amount if charge_breakdown else Decimal("0.00"),
            "handling_charge": charge_breakdown.handling_charge if charge_breakdown else Decimal("0.00"),
            "platform_fee": charge_breakdown.platform_fee if charge_breakdown else Decimal("0.00"),
            "delivery_charge": charge_breakdown.delivery_charge if charge_breakdown else order.delivery_charge,
            "cold_chain_charge": charge_breakdown.cold_chain_charge if charge_breakdown else Decimal("0.00"),
            "total_amount": charge_breakdown.total_amount if charge_breakdown else order.total_amount,
        },
    }


@login_required
@require_POST
@rate_limit("razorpay-create-order", 10, 60, json_response=True)
def payment_create_order(request, pk):
    order = get_object_or_404(
        Order.objects,
        pk=pk,
        customer=request.user,
    )
    if order.payment_method != Order.PaymentMethod.RAZORPAY:
        return JsonResponse({"ok": False, "error": "This order is not configured for Razorpay."}, status=400)
    profile = getattr(request.user, "profile", None)
    contact_form = PaymentContactForm(
        {
            "email": request.POST.get("contact_email") or request.user.email,
            "phone": request.POST.get("contact_phone") or getattr(profile, "phone_number", "") or order.address.phone,
        }
    )
    if not contact_form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "code": "contact_required",
                "error": "Enter a valid email address and phone number for payment updates.",
                "fields": {
                    name: errors[0] for name, errors in contact_form.errors.items() if errors
                },
            },
            status=400,
        )
    _save_payment_contact(request.user, contact_form.cleaned_data)
    if not razorpay_is_configured():
        return JsonResponse({"ok": False, "error": "Razorpay is not configured on the server."}, status=503)
    if order.payment_status == Order.PaymentStatus.PAID:
        return JsonResponse({"ok": False, "error": "This order has already been paid."}, status=409)
    if order.inventory_released_at or (
        order.stock_reserved_until and order.stock_reserved_until <= timezone.now()
    ):
        with transaction.atomic():
            release_order_inventory(order.pk, reason="Online payment reservation expired.")
        return JsonResponse({"ok": False, "error": "This payment reservation expired. Please place the order again."}, status=409)

    payment = getattr(order, "payment", None)
    if not payment:
        return JsonResponse({"ok": False, "error": "Payment record is missing for this order."}, status=500)
    amount_paise = int(order.total_amount * 100)
    if amount_paise < 100:
        return JsonResponse(
            {"ok": False, "error": "Razorpay payments must be at least 100 paise."},
            status=400,
        )
    idempotency_key = (request.headers.get("X-Idempotency-Key") or request.POST.get("idempotency_key") or "").strip()[:80]
    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.gateway_order_id:
                gateway_order = {"id": payment.gateway_order_id}
            else:
                gateway_order = create_razorpay_order(order)
                metadata = dict(payment.gateway_metadata or {})
                if idempotency_key:
                    metadata["idempotency_key"] = idempotency_key
                payment.gateway_order_id = gateway_order["id"]
                payment.transaction_id = gateway_order["id"]
                payment.gateway_metadata = metadata
                payment.save(update_fields=["gateway_order_id", "transaction_id", "gateway_metadata", "updated_at"])
                record_payment_event(
                    payment,
                    "gateway_order_created",
                    {"gateway_order_id": gateway_order["id"], "amount": gateway_order.get("amount"), "idempotency_key": idempotency_key},
                )
    except Exception as exc:
        error_text = str(exc).lower()
        status = 401 if "authentication" in error_text or "api key" in error_text else 500
        return JsonResponse({"ok": False, "error": "Razorpay could not create the payment order."}, status=status)

    return JsonResponse({
        "ok": True,
        "order_id": gateway_order["id"],
        "amount": amount_paise,
        "currency": settings.RAZORPAY_CURRENCY,
    })


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
    return render(
        request,
        "orders/payment_start.html",
        {
            "order": order,
            **_payment_contact_context(order),
        },
    )


@login_required
@require_POST
@rate_limit("razorpay-verify-payment", 20, 60, json_response=True)
def payment_verify(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    payload = {
        "razorpay_order_id": request.POST.get("razorpay_order_id"),
        "razorpay_payment_id": request.POST.get("razorpay_payment_id"),
        "razorpay_signature": request.POST.get("razorpay_signature"),
    }
    payment = getattr(order, "payment", None)
    wants_json = _payment_json_requested(request)
    if not payment or not all(payload.values()):
        return _payment_error(request, order, "Payment verification data is incomplete.", 400, wants_json)
    if payload["razorpay_order_id"] != payment.gateway_order_id:
        record_payment_event(payment, "verification_rejected", {"reason": "gateway_order_mismatch"})
        return _payment_error(request, order, "Payment verification failed.", 400, wants_json)
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{payload['razorpay_order_id']}|{payload['razorpay_payment_id']}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, payload["razorpay_signature"]):
        record_payment_event(payment, "verification_rejected", {"reason": "signature_mismatch"})
        return _payment_error(request, order, "Payment verification failed.", 400, wants_json)
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
        return _payment_error(request, order, "Payment verification failed.", 400, wants_json)
    try:
        with transaction.atomic():
            settle_payment(
                order.pk,
                gateway_payment_id=payload["razorpay_payment_id"],
                gateway_signature=payload["razorpay_signature"],
                event_type="browser_payment_verified",
                event_payload={"gateway_order_id": payload["razorpay_order_id"]},
                gateway_data=gateway_payment,
                actor=request.user,
            )
    except ValueError:
        return _payment_error(
            request,
            order,
            "This payment could not be applied to the order. Please contact support.",
            409,
            wants_json,
        )
    if wants_json:
        return JsonResponse({"ok": True, "redirect_url": reverse("orders:order_detail", args=[order.pk])})
    messages.success(request, "Payment completed successfully.")
    return redirect("orders:order_detail", pk=order.pk)


@login_required
@require_POST
@rate_limit("razorpay-payment-failure", 20, 60, json_response=True)
def payment_failure(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    try:
        payload = json.loads(request.body or "{}") if request.content_type == "application/json" else request.POST
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid payment failure payload."}, status=400)

    payment = getattr(order, "payment", None)
    if not payment or payload.get("razorpay_order_id") != payment.gateway_order_id:
        return JsonResponse({"ok": False, "error": "Payment order could not be matched."}, status=400)
    if order.payment_status == Order.PaymentStatus.PAID:
        return JsonResponse({"ok": False, "error": "This order is already paid."}, status=409)

    error = payload.get("error") or {}
    if not isinstance(error, dict):
        error = {}
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status in {
            Order.PaymentStatus.PENDING,
            Order.PaymentStatus.AUTHORIZED,
            Order.PaymentStatus.FAILED,
        }:
            payment.status = Order.PaymentStatus.FAILED
            payment.gateway_status = "failed"
            payment.failure_code = str(error.get("code", ""))[:100]
            payment.failure_description = str(error.get("description", "Payment was not completed."))[:500]
            payment.last_gateway_check_at = timezone.now()
            payment.save(
                update_fields=[
                    "status",
                    "gateway_status",
                    "failure_code",
                    "failure_description",
                    "last_gateway_check_at",
                    "updated_at",
                ]
            )
            order.payment_status = Order.PaymentStatus.FAILED
            order.save(update_fields=["payment_status", "updated_at"])
            record_payment_event(
                payment,
                "browser_payment_failed",
                {
                    "gateway_order_id": payment.gateway_order_id,
                    "gateway_payment_id": str(payload.get("razorpay_payment_id", ""))[:80],
                    "failure_code": payment.failure_code,
                },
            )
    return JsonResponse({"ok": True})


def _payment_json_requested(request):
    return "application/json" in request.headers.get("Accept", "").lower() or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _payment_error(request, order, message, status, wants_json):
    if wants_json:
        return JsonResponse({"ok": False, "error": message}, status=status)
    messages.error(request, message)
    return redirect("orders:payment_start", pk=order.pk)


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
    gateway_data=None,
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
    payment.gateway_status = str((gateway_data or {}).get("status", "captured"))[:30]
    payment.captured_amount = Decimal(str((gateway_data or {}).get("amount", 0))) / Decimal("100")
    payment.last_gateway_check_at = timezone.now()
    payment.gateway_metadata = _safe_gateway_metadata(gateway_data or {})
    payment.failure_description = ""
    payment.save(
        update_fields=[
            "status",
            "transaction_id",
            "gateway_payment_id",
            "gateway_signature",
            "verified_at",
            "gateway_status",
            "captured_amount",
            "last_gateway_check_at",
            "gateway_metadata",
            "failure_description",
            "updated_at",
        ]
    )
    PaymentReconciliation.objects.update_or_create(
        payment=payment,
        provider_reference=gateway_payment_id,
        defaults={
            "provider_status": payment.gateway_status,
            "gateway_amount": payment.captured_amount,
            "expected_amount": payment.amount,
            "status": PaymentReconciliation.Status.MATCHED,
            "exception_reason": "",
            "reconciled_at": timezone.now(),
        },
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
            if event_type == "refund.processed" and not was_completed:
                complete_refund(refund_record)
            elif event_type == "refund.failed":
                refund_record.status = Refund.Status.FAILED
                refund_record.save(update_fields=["status", "updated_at"])
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
                    gateway_data=entity,
                )
        except (ValueError, IntegrityError):
            return JsonResponse({"ok": False}, status=409)
    elif event_type == "payment.failed":
        error = entity.get("error_description") or entity.get("error_reason") or "Payment failed."
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status in {
                Order.PaymentStatus.PENDING,
                Order.PaymentStatus.AUTHORIZED,
                Order.PaymentStatus.FAILED,
            }:
                payment.status = Order.PaymentStatus.FAILED
                payment.gateway_status = "failed"
                payment.failure_code = str(entity.get("error_code", ""))[:100]
                payment.failure_description = str(error)[:500]
                payment.last_gateway_check_at = timezone.now()
                payment.save(
                    update_fields=[
                        "status",
                        "gateway_status",
                        "failure_code",
                        "failure_description",
                        "last_gateway_check_at",
                        "updated_at",
                    ]
                )
                payment.order.payment_status = Order.PaymentStatus.FAILED
                payment.order.save(update_fields=["payment_status", "updated_at"])
            record_payment_event(
                payment,
                event_type,
                {
                    "gateway_order_id": gateway_order_id,
                    "payment_id": entity.get("id", ""),
                    "failure_code": payment.failure_code,
                },
                provider_event_id=provider_event_id,
            )
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
    event, _ = PaymentEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "payment": payment,
            "event_type": event_type,
            "payload_hash": payload_hash,
            "gateway_order_id": payment.gateway_order_id or "",
            "gateway_payment_id": payment.gateway_payment_id or "",
            "processed": True,
            "processed_at": timezone.now(),
            "payload": payload,
        },
    )
    return event


def _safe_gateway_metadata(gateway_data):
    return {
        key: gateway_data.get(key)
        for key in ("id", "order_id", "status", "currency", "amount", "method")
        if gateway_data.get(key) not in (None, "")
    }


def razorpay_is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def get_razorpay_client():
    import razorpay

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    client.set_app_details({"title": "MediMart", "version": "1.0"})
    return client


def create_razorpay_order(order):
    amount = int(order.total_amount * 100)
    if amount < 100:
        raise ValueError("Razorpay orders must be at least 100 paise.")
    client = get_razorpay_client()
    return client.order.create(
        {
            "amount": amount,
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

    invoice_data = invoice_context(order)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(x, y, "Seller details")
    y -= 5 * mm
    pdf.setFont("Helvetica", 8.5)
    for seller in invoice_data["seller_profiles"]:
        seller_line = seller["business_name"]
        if seller["gst_number"]:
            seller_line += f" | GSTIN: {seller['gst_number']}"
        if seller["license_number"]:
            seller_line += f" | Licence: {seller['license_number']}"
        pdf.drawString(x, y, seller_line[:112])
        y -= 4.2 * mm
        contact = " · ".join(value for value in [seller["email"], seller["phone"]] if value)
        if contact:
            pdf.drawString(x, y, f"Contact: {contact}"[:112])
            y -= 4.2 * mm
        for address_line in (seller["address"] or "").splitlines()[:2]:
            pdf.drawString(x, y, f"Address: {address_line}"[:112])
            y -= 4.2 * mm
    if not invoice_data["seller_profiles"]:
        pdf.drawString(x, y, "Seller details unavailable for this historical order.")
        y -= 4.2 * mm
    y -= 3 * mm

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
        ("Subtotal", invoice_data["invoice_totals"]["subtotal"]),
        ("Discount", invoice_data["invoice_totals"]["discount"]),
        ("Tax / GST", invoice_data["invoice_totals"]["tax_amount"]),
        ("Handling", invoice_data["invoice_totals"]["handling_charge"]),
        ("Platform fee", invoice_data["invoice_totals"]["platform_fee"]),
        ("Delivery", invoice_data["invoice_totals"]["delivery_charge"]),
        ("Cold-chain", invoice_data["invoice_totals"]["cold_chain_charge"]),
        ("Total", invoice_data["invoice_totals"]["total_amount"]),
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
