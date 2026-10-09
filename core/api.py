from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Min, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from products.models import Product


ACTIVE_OFFER_FILTER = Q(
    vendor_products__is_active=True,
    vendor_products__is_approved=True,
    vendor_products__vendor__is_active=True,
    vendor_products__vendor__is_approved=True,
)


def catalog_queryset():
    return (
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .annotate(
            lowest_offer_price=Min("vendor_products__price", filter=ACTIVE_OFFER_FILTER),
            available_offer_stock=Coalesce(
                Sum("vendor_products__stock_quantity", filter=ACTIVE_OFFER_FILTER),
                0,
            ),
        )
    )


def serialize_product(product, request, *, detailed=False):
    image_url = request.build_absolute_uri(product.image.url) if product.image else ""
    result = {
        "id": product.pk,
        "name": product.name,
        "slug": product.slug,
        "sku": product.sku,
        "type": product.product_type,
        "category": {"name": product.category.name, "slug": product.category.slug},
        "brand": product.brand.name if product.brand else None,
        "price": str(product.lowest_offer_price or product.selling_price),
        "mrp": str(product.mrp),
        "available_stock": product.available_offer_stock,
        "requires_prescription": product.requires_prescription,
        "image": image_url,
        "url": request.build_absolute_uri(product.get_absolute_url()),
    }
    if detailed:
        result.update(
            {
                "description": product.description,
                "short_description": product.short_description,
                "manufacturer": product.manufacturer,
                "composition": product.composition,
                "pack_size": product.pack_size,
                "regulatory_classification": product.regulatory_classification,
            }
        )
    return result


@require_GET
def product_collection(request):
    products = catalog_queryset()
    query = request.GET.get("q", "").strip()[:120]
    product_type = request.GET.get("type", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(category__name__icontains=query)
        )
    if product_type in Product.ProductType.values:
        products = products.filter(product_type=product_type)
    try:
        page_size = min(100, max(1, int(request.GET.get("page_size", 24))))
    except (TypeError, ValueError):
        page_size = 24
    page = Paginator(products.order_by("name", "pk"), page_size).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "count": page.paginator.count,
            "page": page.number,
            "pages": page.paginator.num_pages,
            "results": [serialize_product(product, request) for product in page.object_list],
        }
    )


@require_GET
def product_resource(request, slug):
    product = catalog_queryset().filter(slug=slug).first()
    if not product:
        return JsonResponse({"detail": "Not found."}, status=404)
    return JsonResponse(serialize_product(product, request, detailed=True))


@require_GET
def openapi_schema(request):
    base = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "openapi": "3.1.0",
            "info": {"title": "MediMart Catalog API", "version": "1.0.0"},
            "servers": [{"url": base}],
            "paths": {
                reverse("core:api_products"): {
                    "get": {
                        "summary": "List active products",
                        "parameters": [
                            {"name": "q", "in": "query", "schema": {"type": "string"}},
                            {"name": "type", "in": "query", "schema": {"type": "string"}},
                            {"name": "page", "in": "query", "schema": {"type": "integer"}},
                        ],
                        "responses": {"200": {"description": "Paginated product collection"}},
                    }
                },
                "/api/v1/products/{slug}/": {
                    "get": {
                        "summary": "Get a product",
                        "parameters": [
                            {"name": "slug", "in": "path", "required": True, "schema": {"type": "string"}}
                        ],
                        "responses": {
                            "200": {"description": "Product resource"},
                            "404": {"description": "Product not found"},
                        },
                    }
                },
            },
        }
    )


@require_GET
def health_live(request):
    return JsonResponse({"status": "ok", "service": "MediMart"})


@require_GET
def health_ready(request):
    checks = {"database": False, "cache": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:
        pass
    try:
        cache.set("health:ready", "ok", 10)
        checks["cache"] = cache.get("health:ready") == "ok"
    except Exception:
        pass
    ready = all(checks.values())
    return JsonResponse({"status": "ok" if ready else "unavailable", "checks": checks}, status=200 if ready else 503)
