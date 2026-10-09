from django.core.paginator import Paginator
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from reviews.views import can_user_review_product
from core.throttling import rate_limit

from .forms import ProductFilterForm
from .models import Category, Product
from .services import with_offer_summary


MAX_COMPARE_PRODUCTS = 3
COMPARE_SESSION_KEY = "compare_product_ids"


def parse_compare_ids(values):
    product_ids = []
    for value in values:
        for part in str(value).split(","):
            try:
                product_id = int(part)
            except (TypeError, ValueError):
                continue
            if product_id not in product_ids:
                product_ids.append(product_id)
    return product_ids[:MAX_COMPARE_PRODUCTS]


def get_compare_ids(request):
    return parse_compare_ids(request.session.get(COMPARE_SESSION_KEY, []))


def save_compare_ids(request, product_ids):
    request.session[COMPARE_SESSION_KEY] = product_ids[:MAX_COMPARE_PRODUCTS]
    request.session.modified = True


def get_approved_seller_offers(product):
    return product.vendor_products.filter(
        is_active=True,
        is_approved=True,
        vendor__is_active=True,
        vendor__is_approved=True,
    ).select_related("vendor")


def get_price_summary(offers):
    lowest_offer = offers.first()
    highest_offer = offers.last()
    maximum_saving = None
    if lowest_offer and highest_offer:
        maximum_saving = highest_offer.price - lowest_offer.price
    return lowest_offer, highest_offer, maximum_saving


def get_filtered_products(data):
    products = with_offer_summary(
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .prefetch_related("specifications")
    )
    form = ProductFilterForm(data)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        category = form.cleaned_data.get("category")
        brand = form.cleaned_data.get("brand")
        product_type = form.cleaned_data.get("product_type")
        min_price = form.cleaned_data.get("min_price")
        max_price = form.cleaned_data.get("max_price")
        prescription = form.cleaned_data.get("prescription")
        sort = form.cleaned_data.get("sort")

        if q:
            products = products.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(category__name__icontains=q)
                | Q(brand__name__icontains=q)
                | Q(manufacturer__icontains=q)
            )
        if category:
            products = products.filter(Q(category=category) | Q(category__parent=category))
        if brand:
            products = products.filter(brand=brand)
        if product_type:
            products = products.filter(product_type=product_type)
        if min_price is not None:
            products = products.filter(selling_price__gte=min_price)
        if max_price is not None:
            products = products.filter(selling_price__lte=max_price)
        if prescription == "required":
            products = products.filter(requires_prescription=True)
        elif prescription == "not_required":
            products = products.filter(requires_prescription=False)

        if sort == "price_low":
            products = products.order_by("selling_price")
        elif sort == "price_high":
            products = products.order_by("-selling_price")
        elif sort == "discount":
            products = products.order_by("-mrp", "selling_price")
        else:
            products = products.order_by("-created_at")

    return form, products


def product_list(request):
    form, products = get_filtered_products(request.GET)
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_query = request.GET.copy()
    filter_query.pop("page", None)

    return render(
        request,
        "products/product_list.html",
        {
            "form": form,
            "filter_query": filter_query.urlencode(),
            "page_title": "Products",
            "page_description": "Search and filter medicines, healthcare essentials, and medical equipment.",
            "page_obj": page_obj,
            "products": page_obj.object_list,
        },
    )


@rate_limit("search-suggestions", 120, 60, json_response=True)
def search_suggestions(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    cache_key = f"search-suggestions:{query.casefold()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"results": cached})

    products = (
        Product.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(category__name__icontains=query)
            | Q(manufacturer__icontains=query)
        )
        .select_related("brand", "category")
        .order_by("name")[:8]
    )
    results = [
                {
                    "name": product.name,
                    "url": product.get_absolute_url(),
                    "meta": product.brand.name if product.brand else product.get_product_type_display(),
                }
                for product in products
            ]
    cache.set(cache_key, results, 60)
    return JsonResponse({"results": results})


def product_compare(request):
    requested_ids = request.GET.getlist("products")
    if requested_ids:
        product_ids = parse_compare_ids(requested_ids)
        save_compare_ids(request, product_ids)
    else:
        product_ids = get_compare_ids(request)

    products_qs = Product.objects.filter(pk__in=product_ids, is_active=True).select_related(
        "category",
        "brand",
    ).prefetch_related("specifications")
    product_map = {product.pk: product for product in products_qs}
    products = [product_map[product_id] for product_id in product_ids if product_id in product_map]

    spec_names = sorted(
        {spec.name for product in products for spec in product.specifications.all()}
    )
    spec_rows = [
        {
            "name": spec_name,
            "values": [
                next(
                    (
                        spec.value
                        for spec in product.specifications.all()
                        if spec.name == spec_name
                    ),
                    "-",
                )
                for product in products
            ],
        }
        for spec_name in spec_names
    ]

    return render(
        request,
        "products/product_compare.html",
        {
            "products": products,
            "spec_rows": spec_rows,
            "max_compare_products": MAX_COMPARE_PRODUCTS,
        },
    )


@require_POST
def compare_add(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    product_ids = get_compare_ids(request)
    if product.pk in product_ids:
        messages.info(request, "Product is already in your comparison list.")
    elif len(product_ids) >= MAX_COMPARE_PRODUCTS:
        messages.warning(request, "You can compare up to 3 products at a time.")
        return redirect("products:product_compare")
    else:
        product_ids.append(product.pk)
        save_compare_ids(request, product_ids)
        messages.success(request, "Product added to comparison.")

    return redirect(request.POST.get("next") or "products:product_compare")


@require_POST
def compare_remove(request, pk):
    product_ids = [product_id for product_id in get_compare_ids(request) if product_id != pk]
    save_compare_ids(request, product_ids)
    messages.success(request, "Product removed from comparison.")
    return redirect("products:product_compare")


@require_POST
def compare_clear(request):
    save_compare_ids(request, [])
    messages.success(request, "Comparison list cleared.")
    return redirect("products:product_compare")


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category", "brand").prefetch_related(
            "images",
            "specifications",
        ),
        slug=slug,
        is_active=True,
    )
    related_products = with_offer_summary(
        Product.objects.filter(category=product.category, is_active=True)
        .exclude(pk=product.pk)
        .select_related("category", "brand")
    )[:4]
    seller_offers = get_approved_seller_offers(product)
    lowest_offer, highest_offer, maximum_saving = get_price_summary(seller_offers)
    approved_reviews = product.reviews.filter(is_approved=True).select_related("user")
    review_summary = approved_reviews.aggregate(
        average_rating=Avg("rating"),
        total_reviews=Count("id"),
    )
    rating_distribution = [
        {
            "rating": rating,
            "count": approved_reviews.filter(rating=rating).count(),
        }
        for rating in range(5, 0, -1)
    ]
    existing_review = None
    if request.user.is_authenticated:
        existing_review = product.reviews.filter(user=request.user).first()

    return render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "related_products": related_products,
            "seller_offers": seller_offers,
            "lowest_offer": lowest_offer,
            "highest_offer": highest_offer,
            "maximum_saving": maximum_saving,
            "approved_reviews": approved_reviews,
            "review_summary": review_summary,
            "rating_distribution": rating_distribution,
            "can_review": can_user_review_product(request.user, product),
            "existing_review": existing_review,
        },
    )


def price_comparison(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category", "brand").prefetch_related("specifications"),
        slug=slug,
        is_active=True,
    )
    seller_offers = get_approved_seller_offers(product)
    lowest_offer, highest_offer, maximum_saving = get_price_summary(seller_offers)

    return render(
        request,
        "products/price_comparison.html",
        {
            "product": product,
            "seller_offers": seller_offers,
            "lowest_offer": lowest_offer,
            "highest_offer": highest_offer,
            "maximum_saving": maximum_saving,
        },
    )


def price_comparison_by_id(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    return price_comparison(request, product.slug)


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    data = request.GET.copy()
    data["category"] = category.pk
    form, products = get_filtered_products(data)
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_query = request.GET.copy()
    filter_query.pop("page", None)

    return render(
        request,
        "products/product_list.html",
        {
            "category": category,
            "form": form,
            "filter_query": filter_query.urlencode(),
            "page_title": category.name,
            "page_description": category.description
            or "Browse products in this MediMart category.",
            "page_obj": page_obj,
            "products": page_obj.object_list,
        },
    )


def product_type_detail(request, product_type):
    product_type_values = dict(Product.ProductType.choices)
    if product_type not in product_type_values:
        product_type = Product.ProductType.MEDICAL_EQUIPMENT

    data = request.GET.copy()
    data["product_type"] = product_type
    form, products = get_filtered_products(data)
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_query = data.copy()
    filter_query.pop("page", None)

    return render(
        request,
        "products/product_list.html",
        {
            "form": form,
            "filter_query": filter_query.urlencode(),
            "page_title": product_type_values[product_type],
            "page_description": "Compare equipment, specifications, availability, and prices in MediMart.",
            "page_obj": page_obj,
            "products": page_obj.object_list,
            "selected_product_type": product_type,
        },
    )
