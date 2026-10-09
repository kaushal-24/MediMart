from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
    cart = get_or_create_cart(request.user)
    items = cart.items.select_related(
        "vendor_product",
        "vendor_product__product",
        "vendor_product__vendor",
    )
    subtotal = sum(item.total_price for item in items)
    discount = Decimal("0.00")
    delivery_fee = Decimal("0.00") if subtotal == 0 else Decimal("49.00")
    final_total = subtotal - discount + delivery_fee

    return render(
        request,
        "cart/cart_detail.html",
        {
            "cart": cart,
            "items": items,
            "subtotal": subtotal,
            "discount": discount,
            "delivery_fee": delivery_fee,
            "final_total": final_total,
        },
    )


@login_required
@require_POST
def add_to_cart(request, offer_id):
    offer = get_approved_offer_or_404(offer_id)
    quantity = get_post_quantity(request)

    if offer.stock_quantity == 0:
        messages.error(request, "This seller offer is currently out of stock.")
    elif prescription_is_required_without_approval(request.user, offer, quantity):
        messages.error(
            request,
            "This product requires an approved prescription before it can be added to cart.",
        )
        return redirect("prescriptions:prescription_upload")
    else:
        item = add_offer_to_user_cart(request.user, offer, quantity)
        if item.quantity == offer.stock_quantity:
            messages.warning(request, "Cart quantity was limited to available stock.")
        else:
            messages.success(request, "Product added to your cart.")

    return redirect(request.POST.get("next") or "cart:cart_detail")


@login_required
@require_POST
def update_cart_item(request, item_id):
    cart = get_or_create_cart(request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    quantity = get_post_quantity(request)

    if quantity > item.vendor_product.stock_quantity:
        quantity = item.vendor_product.stock_quantity
        messages.warning(request, "Quantity was limited to available stock.")

    if quantity <= 0:
        item.delete()
        messages.success(request, "Item removed from cart.")
    else:
        item.quantity = quantity
        item.save()
        messages.success(request, "Cart updated.")

    return redirect("cart:cart_detail")


@login_required
@require_POST
def remove_cart_item(request, item_id):
    cart = get_or_create_cart(request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.success(request, "Item removed from cart.")
    return redirect("cart:cart_detail")


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
        messages.success(request, "Product saved for later.")
    else:
        messages.info(request, "Product is already saved for later.")

    return redirect(request.POST.get("next") or "cart:wishlist_detail")


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
