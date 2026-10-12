from decimal import Decimal, InvalidOperation

import difflib
import hashlib

from django.conf import settings
from django.core.paginator import Paginator
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from reviews.views import can_user_review_product
from core.throttling import rate_limit

from .forms import ProductFilterForm
from .models import Brand, Category, PriceAlert, Product, ProductQuestion, SearchQuery, StockAlert
from .services import with_offer_summary


MAX_COMPARE_PRODUCTS = 3
COMPARE_SESSION_KEY = "compare_product_ids"
RECENTLY_VIEWED_SESSION_KEY = "recently_viewed_product_ids"
MAX_RECENTLY_VIEWED_PRODUCTS = 12
RECENT_SEARCHES_SESSION_KEY = "recent_search_queries"
MAX_RECENT_SEARCHES = 6


def _record_search_query(request, query, *, source, result_count=0, lab_result_count=0):
    query = " ".join(str(query or "").split())[:180]
    if not query:
        return
    session_key = request.session.session_key or "anonymous"
    session_hash = hashlib.sha256(f"{settings.SECRET_KEY}:{session_key}".encode("utf-8")).hexdigest()
    SearchQuery.objects.create(
        query=query,
        source=source,
        result_count=max(0, int(result_count or 0)),
        lab_result_count=max(0, int(lab_result_count or 0)),
        zero_result=not result_count and not lab_result_count,
        user=request.user if request.user.is_authenticated else None,
        session_hash=session_hash,
    )


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


def remember_product_view(request, product_id):
    product_ids = []
    for value in request.session.get(RECENTLY_VIEWED_SESSION_KEY, []):
        try:
            parsed_id = int(value)
        except (TypeError, ValueError):
            continue
        if parsed_id not in product_ids:
            product_ids.append(parsed_id)
    product_ids = [parsed_id for parsed_id in product_ids if parsed_id != product_id]
    product_ids.insert(0, product_id)
    request.session[RECENTLY_VIEWED_SESSION_KEY] = product_ids[:MAX_RECENTLY_VIEWED_PRODUCTS]
    request.session.modified = True


def get_recently_viewed_products(request, exclude_id=None):
    product_ids = []
    for value in request.session.get(RECENTLY_VIEWED_SESSION_KEY, []):
        try:
            product_id = int(value)
        except (TypeError, ValueError):
            continue
        if product_id != exclude_id and product_id not in product_ids:
            product_ids.append(product_id)
    if not product_ids:
        return []

    products = with_offer_summary(
        Product.objects.filter(pk__in=product_ids, is_active=True)
        .select_related("category", "brand")
    )
    product_map = {product.pk: product for product in products}
    return [product_map[product_id] for product_id in product_ids if product_id in product_map]


def remember_search_query(request, query):
    query = " ".join(query.split())[:120]
    if not query:
        return
    previous = [
        item for item in request.session.get(RECENT_SEARCHES_SESSION_KEY, [])
        if item.casefold() != query.casefold()
    ]
    request.session[RECENT_SEARCHES_SESSION_KEY] = [query, *previous][:MAX_RECENT_SEARCHES]
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
                | Q(composition__icontains=q)
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


def get_active_filter_chips(data, form, clear_path):
    if not form.is_valid():
        return []

    values = form.cleaned_data
    labels = []
    if values.get("q"):
        labels.append(("q", f'Search: {values["q"]}'))
    if values.get("category"):
        labels.append(("category", f'Category: {values["category"].name}'))
    if values.get("brand"):
        labels.append(("brand", f'Brand: {values["brand"].name}'))
    if values.get("product_type"):
        product_type_label = dict(Product.ProductType.choices).get(values["product_type"], values["product_type"])
        labels.append(("product_type", f"Product type: {product_type_label}"))
    if values.get("min_price") is not None:
        labels.append(("min_price", f'Min ₹{values["min_price"]}'))
    if values.get("max_price") is not None:
        labels.append(("max_price", f'Max ₹{values["max_price"]}'))
    if values.get("prescription"):
        prescription_label = dict(form.fields["prescription"].choices).get(values["prescription"], values["prescription"])
        labels.append(("prescription", prescription_label))
    if values.get("sort") and values["sort"] != "newest":
        sort_label = dict(form.fields["sort"].choices).get(values["sort"], values["sort"])
        labels.append(("sort", f"Sort: {sort_label}"))

    params = data.copy()
    params.pop("page", None)
    chips = []
    for key, label in labels:
        removal_params = params.copy()
        removal_params.pop(key, None)
        query_string = removal_params.urlencode()
        remove_url = f"{clear_path}?{query_string}" if query_string else clear_path
        chips.append({"label": label, "remove_url": remove_url})
    return chips


def product_list(request):
    form, products = get_filtered_products(request.GET)
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_query = request.GET.copy()
    filter_query.pop("page", None)

    context = {
        "form": form,
        "filter_query": filter_query.urlencode(),
        "page_title": "Products",
        "page_description": "Search and filter medicines, healthcare essentials, and medical equipment.",
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "active_filter_chips": get_active_filter_chips(request.GET, form, request.path),
    }
    if request.GET.get("q"):
        _record_search_query(request, request.GET.get("q"), source="catalog", result_count=page_obj.paginator.count)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "html": render_to_string("products/_catalog_results.html", context, request=request),
            "url": request.get_full_path(),
        })
    return render(request, "products/product_list.html", context)


@rate_limit("search-suggestions", 120, 60, json_response=True)
def search_suggestions(request):
    query = request.GET.get("q", "").strip()
    recent_queries = request.session.get(RECENT_SEARCHES_SESSION_KEY, [])
    if len(query) < 2:
        return JsonResponse({"results": [], "categories": [], "brands": [], "lab_tests": [], "suggestions": [], "recent_queries": recent_queries})

    cache_key = f"search-suggestions:{query.casefold()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    products = (
        Product.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(category__name__icontains=query)
            | Q(manufacturer__icontains=query)
            | Q(composition__icontains=query)
        )
        .select_related("brand", "category")
        .order_by("name")[:8]
    )
    results = [
        {
            "name": product.name,
            "url": product.get_absolute_url(),
            "meta": product.brand.name if product.brand else product.get_product_type_display(),
            "type": "product",
        }
        for product in products
    ]
    categories = [
        {"name": category.name, "url": category.get_absolute_url(), "meta": "Category", "type": "category"}
        for category in Category.objects.filter(is_active=True, name__icontains=query).order_by("name")[:4]
    ]
    brands = [
        {"name": brand.name, "url": f"{reverse('products:product_list')}?brand={brand.pk}", "meta": "Brand", "type": "brand"}
        for brand in Brand.objects.filter(is_active=True, name__icontains=query).order_by("name")[:4]
    ]
    from healthcare.models import LabTest

    lab_tests = [
        {"name": test.name, "url": reverse("healthcare:lab_booking_for_test", args=[test.pk]), "meta": "Lab test", "type": "lab_test"}
        for test in LabTest.objects.filter(is_active=True, name__icontains=query).order_by("name")[:4]
    ]
    suggestions = _fuzzy_search_suggestions(query)
    payload = {"results": results, "categories": categories, "brands": brands, "lab_tests": lab_tests, "suggestions": suggestions, "recent_queries": recent_queries}
    cache.set(cache_key, payload, 60)
    return JsonResponse(payload)


@rate_limit("ai-search", 30, 60, json_response=True)
def ai_search(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 3:
        return JsonResponse({"ok": True, "results": [], "understanding": "Ask for a product, use, or healthcare need."})

    remember_search_query(request, query)
    from assistant.services import ai_search_plan
    from healthcare.models import LabTest

    plan = ai_search_plan(query)
    terms = plan["terms"] or [query]
    search_query = Q()
    for term in terms:
        search_query |= (
            Q(name__icontains=term)
            | Q(description__icontains=term)
            | Q(short_description__icontains=term)
            | Q(composition__icontains=term)
            | Q(category__name__icontains=term)
            | Q(brand__name__icontains=term)
            | Q(manufacturer__icontains=term)
            | Q(sku__icontains=term)
        )
    products = with_offer_summary(
        Product.objects.filter(is_active=True)
        .filter(search_query)
        .select_related("brand", "category")
        .order_by("name")
    )[:8]
    results = [
        {
            "name": product.name,
            "url": product.get_absolute_url(),
            "meta": product.brand.name if product.brand else product.get_product_type_display(),
            "price": str(product.lowest_offer_price or product.selling_price),
        }
        for product in products
    ]
    lab_query = Q()
    for term in plan.get("lab_terms", terms):
        lab_query |= Q(name__icontains=term) | Q(description__icontains=term) | Q(preparation__icontains=term) | Q(partner__name__icontains=term)
    lab_tests = LabTest.objects.filter(is_active=True).filter(lab_query).select_related("partner").order_by("name")[:6]
    lab_results = [
        {
            "name": lab_test.name,
            "url": reverse("healthcare:lab_booking_for_test", args=[lab_test.pk]),
            "meta": f"{lab_test.partner.name} · {lab_test.get_category_display()}",
            "price": str(lab_test.price),
            "home_collection": lab_test.is_home_collection,
        }
        for lab_test in lab_tests
    ]
    from extras.models import BlogPost, DoctorProfile

    doctors = [
        {
            "name": doctor.full_name,
            "url": reverse("healthcare:consultation_create"),
            "meta": f"{doctor.specialization} · Verified doctor",
            "type": "doctor",
        }
        for doctor in DoctorProfile.objects.filter(is_verified=True).filter(
            Q(full_name__icontains=query) | Q(specialization__icontains=query)
        ).order_by("full_name")[:4]
    ]
    articles = [
        {
            "name": post.title,
            "url": post.get_absolute_url(),
            "meta": "Reviewed health guide",
            "type": "article",
        }
        for post in BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query) | Q(content__icontains=query)
        ).order_by("-published_at")[:4]
    ]
    _record_search_query(request, query, source="ai", result_count=len(results) + len(doctors) + len(articles), lab_result_count=len(lab_results))
    return JsonResponse({
        "ok": True,
        "results": results,
        "lab_tests": lab_results,
        "doctors": doctors,
        "articles": articles,
        "suggestions": _fuzzy_search_suggestions(query),
        "understanding": plan["summary"],
        "intent": plan.get("intent", "catalog"),
        "source": plan["source"],
        "safety_note": "These are catalog matches, not a diagnosis or prescription. Consult a qualified clinician for medical advice.",
    })


def _fuzzy_search_suggestions(query):
    """Return safe catalogue suggestions without making another AI request."""
    from extras.models import BlogPost
    from healthcare.models import LabTest

    labels = list(Product.objects.filter(is_active=True).values_list("name", flat=True)[:500])
    labels += list(LabTest.objects.filter(is_active=True).values_list("name", flat=True)[:250])
    labels += list(BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).values_list("title", flat=True)[:250])
    matches = difflib.get_close_matches(query, labels, n=5, cutoff=0.48)
    return [{"name": match, "type": "suggestion"} for match in matches]


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
        with_offer_summary(
            Product.objects.select_related("category", "brand").prefetch_related(
                "images",
                "specifications",
            )
        ),
        slug=slug,
        is_active=True,
    )
    recently_viewed_products = get_recently_viewed_products(request, exclude_id=product.pk)
    remember_product_view(request, product.pk)
    related_products = with_offer_summary(
        Product.objects.filter(category=product.category, is_active=True)
        .exclude(pk=product.pk)
        .select_related("category", "brand")
    )[:4]
    seller_offers = get_approved_seller_offers(product)
    lowest_offer, highest_offer, maximum_saving = get_price_summary(seller_offers)
    approved_reviews = (
        product.reviews.filter(is_approved=True)
        .select_related("user")
        .prefetch_related("helpful_votes", "seller_reply")
        .annotate(helpful_count=Count("helpful_votes", filter=Q(helpful_votes__is_helpful=True)))
    )
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
    stock_alert = None
    price_alert = None
    if request.user.is_authenticated:
        existing_review = product.reviews.filter(user=request.user).first()
        stock_alert = StockAlert.objects.filter(
            user=request.user,
            product=product,
            is_active=True,
        ).first()
        price_alert = PriceAlert.objects.filter(user=request.user, product=product, is_active=True).first()

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
            "recently_viewed_products": recently_viewed_products,
            "stock_alert": stock_alert,
            "price_alert": price_alert,
            "approved_questions": product.questions.filter(status=ProductQuestion.Status.ANSWERED).select_related("user", "answered_by"),
            "active_variants": product.variants.filter(is_active=True, is_approved=True),
            "approved_substitutes": product.substitute_links.filter(status="approved", substitute__is_active=True).select_related("substitute"),
        },
    )


@login_required
@require_POST
def product_question_create(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    question = " ".join(str(request.POST.get("question", "")).split())
    if len(question) < 5 or len(question) > 2000:
        message = "Please enter a question between 5 and 2,000 characters."
        return JsonResponse({"ok": False, "message": message}, status=400)
    ProductQuestion.objects.create(product=product, user=request.user, question=question)
    message = "Your question was submitted for moderation."
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "message": message})
    messages.success(request, message)
    return redirect(product.get_absolute_url())


@login_required
@require_POST
def stock_alert_create(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    if get_approved_seller_offers(product).filter(stock_quantity__gt=0).exists():
        message = "This product is currently in stock. You can add it to your cart now."
        level = "info"
        alert_active = False
    else:
        alert, created = StockAlert.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={"is_active": True},
        )
        if not created and not alert.is_active:
            alert.is_active = True
            alert.notified_at = None
            alert.save(update_fields=["is_active", "notified_at"])
        message = (
            "We’ll notify you when this product is back in stock."
            if created
            else "You’re already on the back-in-stock alert list."
        )
        level = "success" if created else "info"
        alert_active = True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "message": message, "level": level, "alert_active": alert_active})
    messages.info(request, message)
    return redirect("products:product_detail", slug=product.slug)


@login_required
@require_POST
def price_alert_create(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    try:
        target_price = Decimal(str(request.POST.get("target_price") or product.selling_price))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "Enter a valid target price."}, status=400)
    if target_price < 0 or target_price >= product.selling_price:
        return JsonResponse({"ok": False, "message": "Your target price must be below the current price."}, status=400)
    alert, created = PriceAlert.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={"target_price": target_price, "is_active": True},
    )
    if not created:
        alert.target_price = target_price
        alert.is_active = True
        alert.notified_at = None
        alert.save(update_fields=["target_price", "is_active", "notified_at", "updated_at"])
    message = f"We’ll notify you when {product.name} reaches ₹{target_price}."
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "message": message, "alert_active": True})
    messages.success(request, message)
    return redirect("products:product_detail", slug=product.slug)


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
            "active_filter_chips": get_active_filter_chips(data, form, reverse("products:product_list")),
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
            "active_filter_chips": get_active_filter_chips(data, form, reverse("products:product_list")),
        },
    )
