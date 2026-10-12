from .models import Cart, Wishlist


def navigation_counts(request):
    if not request.user.is_authenticated:
        return {"cart_item_count": 0, "saved_item_count": 0}

    cart = Cart.objects.filter(user=request.user).first()
    wishlist = Wishlist.objects.filter(user=request.user).first()
    return {
        "cart_item_count": sum(item.quantity for item in cart.items.all()) if cart else 0,
        "saved_item_count": wishlist.items.count() if wishlist else 0,
    }
