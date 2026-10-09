from django.urls import path

from . import views


app_name = "cart"

urlpatterns = [
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:offer_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/items/<int:item_id>/update/", views.update_cart_item, name="update_cart_item"),
    path("cart/items/<int:item_id>/remove/", views.remove_cart_item, name="remove_cart_item"),
    path("wishlist/", views.wishlist_detail, name="wishlist_detail"),
    path("wishlist/add/<int:product_id>/", views.add_to_wishlist, name="add_to_wishlist"),
    path(
        "wishlist/items/<int:item_id>/remove/",
        views.remove_wishlist_item,
        name="remove_wishlist_item",
    ),
    path(
        "wishlist/items/<int:item_id>/move-to-cart/",
        views.move_wishlist_item_to_cart,
        name="move_wishlist_item_to_cart",
    ),
]
