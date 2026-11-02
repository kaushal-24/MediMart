import re

from django.db.models import Case, Count, IntegerField, Min, Q, Sum, Value, When
from django.db.models.functions import Coalesce


ACTIVE_OFFER_FILTER = Q(
    vendor_products__is_active=True,
    vendor_products__is_approved=True,
    vendor_products__vendor__is_active=True,
    vendor_products__vendor__is_approved=True,
)

PRODUCT_SEARCH_FIELDS = (
    "name",
    "slug",
    "sku",
    "short_description",
    "description",
    "composition",
    "manufacturer",
    "barcode",
    "regulatory_classification",
    "regulatory_notes",
    "pack_size",
    "unit",
    "weight",
    "dimensions",
    "seo_title",
    "seo_description",
    "product_type",
    "safety_classification",
    "regulatory_schedule",
    "category__name",
    "category__description",
    "brand__name",
    "brand__description",
    "specifications__name",
    "specifications__value",
    "clinical_profile__active_ingredient",
    "clinical_profile__strength",
    "clinical_profile__dosage_form",
    "clinical_profile__route",
    "clinical_profile__therapeutic_class",
    "clinical_profile__chemical_class",
    "clinical_profile__action_class",
    "clinical_profile__uses",
    "clinical_profile__benefits",
    "clinical_profile__quick_tips",
    "clinical_profile__side_effects",
    "clinical_profile__usage",
    "clinical_profile__how_it_works",
    "clinical_profile__safety_advice",
    "clinical_profile__contraindications",
    "clinical_profile__allergy_warnings",
    "clinical_profile__storage_instructions",
    "clinical_profile__marketer",
    "clinical_profile__country_of_origin",
    "clinical_profile__nppa_status",
    "clinical_profile__content_sources",
)

_PRODUCT_SEARCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "for",
    "from",
    "get",
    "help",
    "i",
    "in",
    "is",
    "me",
    "need",
    "of",
    "on",
    "please",
    "show",
    "the",
    "to",
    "want",
    "with",
}

_PRODUCT_SEARCH_SYNONYMS = {
    "chemist": ("pharmacy", "medical shop"),
    "pharmacy": ("chemist", "medical shop"),
    "bp": ("blood pressure", "hypertension"),
    "sugar": ("diabetes", "glucose", "blood sugar"),
    "diabetic": ("diabetes", "glucose", "blood sugar"),
    "painkiller": ("pain relief", "analgesic"),
    "fever": ("thermometer", "temperature"),
    "cough": ("cold", "respiratory"),
    "glucometer": ("blood glucose", "blood sugar", "diabetes"),
    "thermometer": ("temperature", "fever"),
    "tablet": ("tablets", "medicine"),
    "capsule": ("capsules", "medicine"),
}


def product_search_terms(values, *, limit=48):
    """Normalize phrases and useful words for broad catalogue matching."""
    terms = []
    for value in values or []:
        phrase = " ".join(str(value or "").split()).casefold()
        if len(phrase) >= 2 and phrase not in terms:
            terms.append(phrase)
        for token in re.findall(r"[a-z0-9]+", phrase):
            if len(token) < 2 or token in _PRODUCT_SEARCH_STOPWORDS or token in terms:
                continue
            terms.append(token)
            for synonym in _PRODUCT_SEARCH_SYNONYMS.get(token, ()):
                if synonym not in terms:
                    terms.append(synonym)
            if len(terms) >= limit:
                return terms
    return terms


def product_keyword_query(values):
    """Build an OR query over every public product discovery field.

    The original query and AI-expanded terms can be passed together. This keeps
    AI helpful without allowing a planner response to hide an exact catalogue
    keyword that exists in a product record.
    """
    query = Q()
    for term in product_search_terms(values):
        for field in PRODUCT_SEARCH_FIELDS:
            query |= Q(**{f"{field}__icontains": term})
    return query


def rank_product_queryset(queryset, values):
    """Rank direct name/brand/category matches above broad metadata matches."""
    phrases = [" ".join(str(value or "").split()).casefold() for value in values or []]
    exact_phrase = next((phrase for phrase in phrases if len(phrase) >= 2), "")
    terms = product_search_terms(values, limit=12)
    score = Case(
        When(name__iexact=exact_phrase, then=Value(100)),
        default=Value(0),
        output_field=IntegerField(),
    )
    for term in terms:
        score = score + Case(
            When(name__icontains=term, then=Value(30)),
            When(brand__name__icontains=term, then=Value(20)),
            When(category__name__icontains=term, then=Value(18)),
            When(short_description__icontains=term, then=Value(10)),
            When(description__icontains=term, then=Value(5)),
            default=Value(1),
            output_field=IntegerField(),
        )
    return queryset.annotate(search_relevance=score).order_by("-search_relevance", "name", "pk")


def _vendor_location_area(location, prefix=""):
    location = location or {}
    pincode = str(location.get("pincode") or "").strip()
    city = str(location.get("city") or "").strip()
    state = str(location.get("state") or "").strip()
    area = Q()
    if pincode:
        area |= Q(**{f"{prefix}pincode": pincode})
    if city:
        area |= Q(**{f"{prefix}city__iexact": city})
        area |= Q(**{f"{prefix}address__icontains": city})
    if state:
        area |= Q(**{f"{prefix}state__iexact": state})
    return area if area.children else None


def location_offer_filter(location):
    """Build a seller-location filter from the user's selected delivery area."""
    area = _vendor_location_area(location, "vendor_products__vendor__")
    return ACTIVE_OFFER_FILTER & area if area else None


def vendor_location_filter(location):
    """Build a location filter for an individual VendorProduct queryset."""
    return _vendor_location_area(location, "vendor__")


def with_offer_summary(queryset, location=None):
    summary = {
        "lowest_offer_price": Min("vendor_products__price", filter=ACTIVE_OFFER_FILTER),
        "available_offer_stock": Coalesce(
            Sum("vendor_products__stock_quantity", filter=ACTIVE_OFFER_FILTER),
            Value(0),
            output_field=IntegerField(),
        ),
    }
    local_filter = location_offer_filter(location)
    if local_filter:
        summary.update(
            {
                "location_lowest_offer_price": Min("vendor_products__price", filter=local_filter),
                "location_available_offer_stock": Coalesce(
                    Sum("vendor_products__stock_quantity", filter=local_filter),
                    Value(0),
                    output_field=IntegerField(),
                ),
                "location_offer_count": Count("vendor_products", filter=local_filter),
            }
        )
    return queryset.annotate(**summary)
