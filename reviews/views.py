from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from orders.models import Order, OrderItem
from products.models import Product

from .forms import ReviewForm
from .models import Review


def get_reviewable_order_item(user, product):
    return (
        OrderItem.objects.filter(
            order__customer=user,
            order__order_status=Order.OrderStatus.DELIVERED,
            product=product,
        )
        .select_related("order")
        .order_by("-order__created_at")
        .first()
    )


def can_user_review_product(user, product):
    if not user.is_authenticated:
        return False
    if Review.objects.filter(user=user, product=product).exists():
        return False
    return get_reviewable_order_item(user, product) is not None


@login_required
def review_list(request):
    reviews = request.user.reviews.select_related("product").all()
    return render(request, "reviews/review_list.html", {"reviews": reviews})


@login_required
def review_create(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    order_item = get_reviewable_order_item(request.user, product)

    if not order_item:
        messages.error(request, "You can review this product after it has been delivered.")
        return redirect(product.get_absolute_url())
    if Review.objects.filter(user=request.user, product=product).exists():
        messages.info(request, "You have already reviewed this product.")
        return redirect("reviews:review_list")

    if request.method == "POST":
        form = ReviewForm(request.POST, request.FILES)
        if form.is_valid():
            review = form.save(commit=False)
            review.user = request.user
            review.product = product
            review.order_item = order_item
            review.save()
            messages.success(request, "Review submitted and is pending approval.")
            return redirect("reviews:review_list")
    else:
        form = ReviewForm()

    return render(
        request,
        "reviews/review_form.html",
        {
            "form": form,
            "product": product,
        },
    )
