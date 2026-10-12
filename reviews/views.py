from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from orders.models import Order, OrderItem
from products.models import Product

from .forms import ReviewAbuseReportForm, ReviewForm, SellerReplyForm
from .models import Review, ReviewAbuseReport, ReviewHelpfulVote, ReviewSellerReply


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


@login_required
@require_POST
def helpful_vote(request, pk):
    review = get_object_or_404(Review, pk=pk, is_approved=True)
    is_helpful = str(request.POST.get("is_helpful", "true")).lower() not in {"0", "false", "no"}
    ReviewHelpfulVote.objects.update_or_create(review=review, user=request.user, defaults={"is_helpful": is_helpful})
    return JsonResponse({"ok": True, "message": "Thanks for your feedback."})


@login_required
@require_POST
def abuse_report(request, pk):
    review = get_object_or_404(Review, pk=pk, is_approved=True)
    form = ReviewAbuseReportForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "message": "Please provide a valid report reason."}, status=400)
    _, created = ReviewAbuseReport.objects.get_or_create(
        review=review,
        user=request.user,
        defaults={"reason": form.cleaned_data["reason"]},
    )
    message = "Report submitted for moderation." if created else "You have already reported this review."
    return JsonResponse({"ok": True, "message": message})


@login_required
@require_POST
def seller_reply(request, pk):
    review = get_object_or_404(Review, pk=pk, is_approved=True)
    vendor = getattr(request.user, "vendor_profile", None)
    if (
        not vendor
        or not vendor.is_approved
        or not vendor.is_active
        or not vendor.vendor_products.filter(product=review.product, is_active=True, is_approved=True).exists()
    ):
        return JsonResponse({"ok": False, "message": "Only the product seller can reply to this review."}, status=403)
    form = SellerReplyForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "message": "Reply must be between 5 and 2,000 characters."}, status=400)
    ReviewSellerReply.objects.update_or_create(
        review=review,
        defaults={"seller": request.user, "reply": form.cleaned_data["reply"], "is_published": False},
    )
    return JsonResponse({"ok": True, "message": "Reply submitted for moderation."})
