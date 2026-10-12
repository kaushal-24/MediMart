from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from orders.forms import CheckoutForm
from orders.models import Coupon, CouponUsage
from products.models import Product
from prescriptions.views import user_has_approved_prescription
from vendors.models import VendorProduct

from .models import Cart, CartItem, Wishlist, WishlistItem


def get_or_create_cart(user):
    cart, created = Cart.objects.get_or_create(user=user)
    return cart


def get_or_create_wishlist(user):
    wishlist, created = Wishlist.objects.get_or_create(user=user)
    return wishlist


def _is_async_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "").lower()


def _flash(request, level, message):
    if not _is_async_request(request):
        getattr(messages, level)(request, message)


def _valid_cart_coupon(code, user, subtotal):
    if not code:
        return None, ""
    try:
        coupon = Coupon.objects.get(code=code.strip().upper(), is_active=True)
    except Coupon.DoesNotExist:
        return None, "Coupon code is not valid."
    today = timezone.localdate()
    if coupon.start_date > today or coupon.end_date < today:
        return None, "Coupon is not active today."
    if coupon.usages.count() >= coupon.usage_limit:
        return None, "Coupon usage limit has been reached."
    if subtotal < coupon.minimum_order:
        return None, f"Minimum order for this coupon is ₹{coupon.minimum_order}."
    if CouponUsage.objects.filter(coupon=coupon, user=user).exists():
        return None, "You have already used this coupon."
    return coupon, ""


def _cart_context(user, coupon_code=""):
    cart = get_or_create_cart(user)
    items = list(
        cart.items.select_related(
            "vendor_product",
            "vendor_product__product",
            "vendor_product__vendor",
        )
    )
    subtotal = sum(item.total_price for item in items)
    coupon, coupon_error = _valid_cart_coupon(coupon_code, user, subtotal)
    discount = coupon.calculate_discount(subtotal) if coupon else Decimal("0.00")
    delivery_fee = (
        Decimal("0.00")
        if subtotal == 0 or settings.FREE_DELIVERY
        else Decimal(str(settings.DELIVERY_FEE))
    )
    return {
        "cart": cart,
        "items": items,
        "subtotal": subtotal,
        "discount": discount,
        "delivery_fee": delivery_fee,
        "final_total": subtotal - discount + delivery_fee,
        "cart_item_count": sum(item.quantity for item in items),
        "coupon_code": coupon.code if coupon else coupon_code.strip().upper(),
        "coupon_error": coupon_error,
        "applied_coupon": coupon,
        "checkout_form": CheckoutForm(
            user=user,
            initial={"coupon_code": coupon.code if coupon else ""},
        ),
    }


def _navigation_counts(user):
    cart = Cart.objects.filter(user=user).first()
    wishlist = Wishlist.objects.filter(user=user).first()
    return {
        "cart_item_count": sum(item.quantity for item in cart.items.all()) if cart else 0,
        "saved_item_count": wishlist.items.count() if wishlist else 0,
    }


def _async_action_response(
    request,
    message,
    *,
    level="success",
    status=200,
    redirect_name="cart:cart_detail",
    redirect_url=None,
    include_cart=False,
):
    if not _is_async_request(request):
        return redirect(redirect_url or redirect_name)

    payload = {
        "ok": status < 400,
        "message": message,
        "level": level,
        **_navigation_counts(request.user),
    }
    if redirect_url:
        payload["redirect_url"] = redirect_url
    if include_cart:
        context = _cart_context(request.user, request.session.get("cart_coupon_code", ""))
        payload["html"] = render_to_string("cart/_cart_content.html", context, request=request)
        payload["cart_total"] = str(context["final_total"])
    return JsonResponse(payload, status=status)


def get_approved_offer_or_404(offer_id):
    return get_object_or_404(
        VendorProduct,
        pk=offer_id,
        is_active=True,
        is_approved=True,
        vendor__is_active=True,
        vendor__is_approved=True,
    )


def add_offer_to_user_cart(user, offer, quantity=1):
    cart = get_or_create_cart(user)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        vendor_product=offer,
        defaults={"quantity": 0},
    )
    item.quantity += quantity
    if item.quantity > offer.stock_quantity:
        item.quantity = offer.stock_quantity
    item.save()
    return item


def prescription_is_required_without_approval(user, offer, quantity=1):
    return offer.product.requires_prescription and not user_has_approved_prescription(
        user,
        offer.product,
        quantity,
    )


def get_post_quantity(request, default=1):
    try:
        quantity = int(request.POST.get("quantity", default))
    except (TypeError, ValueError):
        quantity = default
    return max(quantity, 1)


@login_required
def cart_detail(request):
    requested_coupon = request.GET.get("coupon_code")
    coupon_code = (
        requested_coupon
        if requested_coupon is not None
        else request.session.get("cart_coupon_code", "")
    )
    context = _cart_context(request.user, coupon_code)
    if requested_coupon is not None:
        if context["applied_coupon"]:
            request.session["cart_coupon_code"] = context["applied_coupon"].code
        else:
            request.session.pop("cart_coupon_code", None)
    if _is_async_request(request):
        return JsonResponse(
            {
                "ok": not bool(context["coupon_error"]),
                "message": context["coupon_error"] or (
                    f"Coupon {context['applied_coupon'].code} applied."
                    if context["applied_coupon"]
                    else "Coupon removed."
                ),
                "level": "danger" if context["coupon_error"] else "success",
                "html": render_to_string("cart/_cart_content.html", context, request=request),
                "cart_total": str(context["final_total"]),
                **_navigation_counts(request.user),
            },
            status=400 if context["coupon_error"] else 200,
        )
    return render(request, "cart/cart_detail.html", context)


@login_required
@require_POST
def add_to_cart(request, offer_id):
    offer = get_approved_offer_or_404(offer_id)
    quantity = get_post_quantity(request)

    if offer.stock_quantity == 0:
        _flash(request, "error", "This seller offer is currently out of stock.")
        return _async_action_response(
            request,
            "This seller offer is currently out of stock.",
            level="danger",
            status=400,
            redirect_url=request.POST.get("next") or reverse("cart:cart_detail"),
        )
    elif prescription_is_required_without_approval(request.user, offer, quantity):
        return _async_action_response(
            request,
            "This product requires an approved prescription before it can be added to cart.",
            level="warning",
            status=400,
            redirect_url=reverse("prescriptions:prescription_upload"),
        )
    else:
        item = add_offer_to_user_cart(request.user, offer, quantity)
        if item.quantity == offer.stock_quantity:
            message = "Cart quantity was limited to available stock."
            level = "warning"
        else:
            message = "Product added to your cart."
            level = "success"
        _flash(request, level, message)

    return _async_action_response(
        request,
        message,
        level=level,
        redirect_url=request.POST.get("next") or reverse("cart:cart_detail"),
    )


@login_required
@require_POST
def update_cart_item(request, item_id):
    cart = get_or_create_cart(request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    requested_quantity = get_post_quantity(request)
    quantity = requested_quantity

    if quantity > item.vendor_product.stock_quantity:
        quantity = item.vendor_product.stock_quantity

    if quantity <= 0:
        item.delete()
        message = "Item removed from cart."
        level = "success"
    else:
        item.quantity = quantity
        item.save()
        message = "Quantity was limited to available stock." if quantity != requested_quantity else "Cart updated."
        level = "warning" if quantity != requested_quantity else "success"
    _flash(request, level, message)

    return _async_action_response(request, message, level=level, include_cart=True)


@login_required
@require_POST
def remove_cart_item(request, item_id):
    cart = get_or_create_cart(request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    _flash(request, "success", "Item removed from cart.")
    return _async_action_response(request, "Item removed from cart.", include_cart=True)


@login_required
def wishlist_detail(request):
    wishlist = get_or_create_wishlist(request.user)
    items = wishlist.items.select_related("product", "product__brand", "product__category")
    return render(
        request,
        "cart/wishlist_detail.html",
        {
            "wishlist": wishlist,
            "items": items,
        },
    )


@login_required
@require_POST
def add_to_wishlist(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    wishlist = get_or_create_wishlist(request.user)
    item, created = WishlistItem.objects.get_or_create(wishlist=wishlist, product=product)

    if created:
        message = "Product saved for later."
        level = "success"
    else:
        message = "Product is already saved for later."
        level = "info"
    _flash(request, level, message)

    return _async_action_response(
        request,
        message,
        level=level,
        redirect_url=request.POST.get("next") or reverse("cart:wishlist_detail"),
    )


@login_required
@require_POST
def remove_wishlist_item(request, item_id):
    wishlist = get_or_create_wishlist(request.user)
    item = get_object_or_404(WishlistItem, pk=item_id, wishlist=wishlist)
    item.delete()
    messages.success(request, "Product removed from saved items.")
    return redirect("cart:wishlist_detail")


@login_required
@require_POST
def move_wishlist_item_to_cart(request, item_id):
    wishlist = get_or_create_wishlist(request.user)
    item = get_object_or_404(WishlistItem, pk=item_id, wishlist=wishlist)
    offer = item.product.vendor_products.filter(
        is_active=True,
        is_approved=True,
        vendor__is_active=True,
        vendor__is_approved=True,
        stock_quantity__gt=0,
    ).select_related("vendor").first()

    if not offer:
        messages.error(request, "No approved in-stock seller is available for this product.")
        return redirect("cart:wishlist_detail")
    if prescription_is_required_without_approval(request.user, offer, 1):
        messages.error(
            request,
            "This product requires an approved prescription before it can be moved to cart.",
        )
        return redirect("prescriptions:prescription_upload")

    add_offer_to_user_cart(request.user, offer, 1)
    item.delete()
    messages.success(request, "Product moved from saved items to cart.")
    return redirect("cart:cart_detail")
