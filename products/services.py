from django.db.models import IntegerField, Min, Q, Sum, Value
from django.db.models.functions import Coalesce


ACTIVE_OFFER_FILTER = Q(
    vendor_products__is_active=True,
    vendor_products__is_approved=True,
    vendor_products__vendor__is_active=True,
    vendor_products__vendor__is_approved=True,
)


def with_offer_summary(queryset):
    return queryset.annotate(
        lowest_offer_price=Min("vendor_products__price", filter=ACTIVE_OFFER_FILTER),
        available_offer_stock=Coalesce(
            Sum("vendor_products__stock_quantity", filter=ACTIVE_OFFER_FILTER),
            Value(0),
            output_field=IntegerField(),
        ),
    )
