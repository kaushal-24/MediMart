import json
from math import asin, cos, radians, sin, sqrt
from urllib.parse import quote_plus
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from extras.models import BlogPost, DoctorProfile
from healthcare.models import LabTest
from prescriptions.models import Prescription
from products.models import Category, Product
from vendors.models import Vendor
from products.services import with_offer_summary

from .services import (
    GeocodingError,
    PlacesAutocompleteError,
    PlacesSearchError,
    autocomplete_google_places,
    geocode_google_place,
    reverse_geocode,
    search_nearby_google_pharmacies,
)
from .throttling import rate_limit


CITY_COORDINATES = {
    "ahmedabad": (23.0225, 72.5714),
    "vadodara": (22.3072, 73.1812),
    "surat": (21.1702, 72.8311),
    "rajkot": (22.3039, 70.8022),
    "gandhinagar": (23.2156, 72.6369),
    "bhavnagar": (21.7645, 72.1519),
}

CATEGORY_IMAGE_FALLBACKS = {
    "baby-care": "categories/healthcare-products.webp",
    "diagnostic-equipment": "categories/diagnostic-equipment.webp",
    "medical-equipment": "categories/medical-equipment.webp",
    "medicines": "categories/medicines.webp",
    "orthopedic-products": "categories/medical-equipment.webp",
    "personal-care": "categories/healthcare-products.webp",
    "supplements": "categories/medicines.webp",
    "surgical-equipment": "categories/surgical-equipment.webp",
}


def _fallback_city_coordinates(value):
    text = str(value or "").casefold()
    return next((coordinates for city, coordinates in CITY_COORDINATES.items() if city in text), None)


def _location_coordinates(location):
    try:
        return float(location.get("latitude")), float(location.get("longitude"))
    except (AttributeError, TypeError, ValueError):
        return _fallback_city_coordinates(location.get("city") if isinstance(location, dict) else "") or (None, None)


def _distance_km(origin, destination):
    if not origin or not destination:
        return None
    lat1, lon1 = map(radians, origin)
    lat2, lon2 = map(radians, destination)
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * (2 * asin(sqrt(a)))


def _selected_location(request):
    location = request.session.get("site_location")
    if location or not request.user.is_authenticated:
        return location or {}

    profile = getattr(request.user, "profile", None)
    if profile and profile.preferred_location_label:
        return {
            "label": profile.preferred_location_label,
            "city": profile.preferred_city,
            "state": profile.preferred_state,
            "pincode": profile.preferred_pincode,
            "latitude": str(profile.preferred_latitude or ""),
            "longitude": str(profile.preferred_longitude or ""),
        }
    return {}


def _category_image_url(category):
    if category.image:
        return category.image.url
    image_path = CATEGORY_IMAGE_FALLBACKS.get(
        category.slug,
        "categories/healthcare-products.webp",
    )
    return f"{settings.MEDIA_URL.rstrip('/')}/{image_path}"


def home(request):
    """Show the MediMart marketplace homepage."""
    location = _selected_location(request)
    featured_categories = Category.objects.filter(is_active=True, parent__isnull=True)[:8]
    for category in featured_categories:
        category.display_image_url = _category_image_url(category)
    featured_products = with_offer_summary(
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .order_by("-is_featured", "-created_at"),
        location=location,
    )[:8]
    equipment_products = with_offer_summary(
        Product.objects.filter(
            is_active=True,
            product_type__in=[
                Product.ProductType.MEDICAL_EQUIPMENT,
                Product.ProductType.SURGICAL_EQUIPMENT,
                Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                Product.ProductType.LAB_EQUIPMENT,
            ],
        )
        .select_related("category", "brand")
        .order_by("-is_featured", "-created_at"),
        location=location,
    )[:4]
    latest_posts = BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED)[:3]
    verified_doctors = DoctorProfile.objects.filter(is_verified=True)[:3]
    featured_lab_tests = (
        LabTest.objects.filter(is_active=True)
        .select_related("partner")
        .order_by("name")[:6]
    )

    marketplace_stats = {
        "products": Product.objects.filter(is_active=True).count(),
        "sellers": Vendor.objects.filter(is_active=True, is_approved=True).count(),
        "doctors": DoctorProfile.objects.filter(is_verified=True).count(),
    }
    prescription_snapshot = None
    if request.user.is_authenticated:
        latest_prescription = request.user.prescriptions.only(
            "id", "status", "valid_until", "created_at"
        ).first()
        prescription_snapshot = {
            "latest": latest_prescription,
            "active_count": request.user.prescriptions.filter(
                status=Prescription.Status.APPROVED,
                valid_until__gte=timezone.localdate(),
            ).count(),
            "action_count": request.user.prescriptions.filter(
                status=Prescription.Status.NEEDS_INFORMATION,
            ).count(),
        }

    return render(
        request,
        "core/home.html",
        {
            "featured_categories": featured_categories,
            "featured_products": featured_products,
            "equipment_products": equipment_products,
            "latest_posts": latest_posts,
            "verified_doctors": verified_doctors,
            "featured_lab_tests": featured_lab_tests,
            "marketplace_stats": marketplace_stats,
            "prescription_snapshot": prescription_snapshot,
            "location_selected": bool(location.get("pincode") or location.get("city") or location.get("latitude")),
        },
    )


def nearby_pharmacies(request):
    """List approved pharmacies near the user's saved location."""
    location = _selected_location(request)
    user_lat, user_lon = _location_coordinates(location)

    pharmacies = list(
        Vendor.objects.filter(
            business_type=Vendor.BusinessType.PHARMACY,
            is_active=True,
            is_approved=True,
        ).prefetch_related("vendor_products")
    )
    results = []
    for pharmacy in pharmacies:
        distance = None
        pharmacy_coordinates = (
            (float(pharmacy.latitude), float(pharmacy.longitude))
            if pharmacy.latitude is not None and pharmacy.longitude is not None
            else _fallback_city_coordinates(f"{pharmacy.city} {pharmacy.address}")
        )
        same_pincode = bool(
            location.get("pincode")
            and pharmacy.pincode
            and str(location.get("pincode")) == str(pharmacy.pincode)
        )
        if user_lat is not None and user_lon is not None:
            distance = _distance_km((user_lat, user_lon), pharmacy_coordinates)
            if distance is not None and distance > (settings.GOOGLE_MAPS_RADIUS_METERS / 1000) and not same_pincode:
                continue
        offers = [offer for offer in pharmacy.vendor_products.all() if offer.is_active and offer.is_approved]
        delivery_times = sorted({offer.delivery_time for offer in offers if offer.delivery_time})
        map_query = f"{pharmacy_coordinates[0]},{pharmacy_coordinates[1]}" if pharmacy_coordinates else f"{pharmacy.business_name}, {pharmacy.address}"
        results.append({
            "vendor": pharmacy,
            "distance": distance,
            "delivery_time": delivery_times[0] if delivery_times else "Delivery time confirmed at checkout",
            "serviceability": "Pincode serviceable" if same_pincode else ("Available near your selected location" if distance is not None else "Confirm availability at checkout"),
            "coordinates": pharmacy_coordinates,
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(map_query)}",
        })
    results.sort(key=lambda item: (item["distance"] is None, item["distance"] or 0, item["vendor"].business_name.lower()))

    general_pharmacies = []
    general_pharmacy_message = ""
    if user_lat is not None and user_lon is not None:
        try:
            places, general_pharmacy_message = search_nearby_google_pharmacies(user_lat, user_lon)
            for place in places:
                place_location = place.get("location") or {}
                place_coordinates = (
                    float(place_location["latitude"]),
                    float(place_location["longitude"]),
                ) if "latitude" in place_location and "longitude" in place_location else None
                display_name = (place.get("displayName") or {}).get("text") or "Pharmacy"
                fallback_query = f"{display_name}, {place.get('formattedAddress', '')}".strip(", ")
                general_pharmacies.append(
                    {
                        "name": display_name,
                        "address": place.get("formattedAddress", "Address unavailable"),
                        "distance": _distance_km((user_lat, user_lon), place_coordinates),
                        "rating": place.get("rating"),
                        "rating_count": place.get("userRatingCount"),
                        "phone": place.get("nationalPhoneNumber"),
                        "website": place.get("websiteUri"),
                        "open_now": (place.get("regularOpeningHours") or {}).get("openNow"),
                        "hours": (place.get("regularOpeningHours") or {}).get("weekdayDescriptions", []),
                        "coordinates": place_coordinates,
                        "maps_url": place.get("googleMapsUri") or f"https://www.google.com/maps/search/?api=1&query={quote_plus(fallback_query)}",
                    }
                )
        except PlacesSearchError as exc:
            general_pharmacy_message = str(exc)
    else:
        general_pharmacy_message = "Choose your current location to find general pharmacies nearby."

    map_points = [
        {
            "name": item["vendor"].business_name,
            "latitude": item["coordinates"][0],
            "longitude": item["coordinates"][1],
            "kind": "MediMart partner",
            "url": item["maps_url"],
        }
        for item in results
        if item["coordinates"]
    ]
    map_points += [
        {
            "name": item["name"],
            "latitude": item["coordinates"][0],
            "longitude": item["coordinates"][1],
            "kind": "General Google listing",
            "url": item["maps_url"],
        }
        for item in general_pharmacies
        if item["coordinates"]
    ]

    return render(
        request,
        "core/nearby_pharmacies.html",
        {
            "pharmacies": results,
            "general_pharmacies": general_pharmacies,
            "general_pharmacy_message": general_pharmacy_message,
            "location": location,
            "map_points": map_points,
        },
    )


@require_GET
@rate_limit("location-autocomplete", 60, 60 * 60, methods={"GET"}, json_response=True)
def location_autocomplete(request):
    query = request.GET.get("q", "").strip()
    location = _selected_location(request)
    try:
        suggestions = autocomplete_google_places(query, location.get("latitude"), location.get("longitude"))
    except PlacesAutocompleteError as exc:
        return JsonResponse({"ok": False, "error": str(exc), "suggestions": []}, status=503)
    return JsonResponse({"ok": True, "suggestions": suggestions})


@require_POST
@rate_limit("location-place", 30, 60 * 60, methods={"POST"}, json_response=True)
def select_location_place(request):
    try:
        payload = json.loads(request.body or "{}")
        place_id = payload.get("place_id", "")
        location = geocode_google_place(place_id)
    except (json.JSONDecodeError, TypeError, GeocodingError) as exc:
        return JsonResponse({"ok": False, "error": str(exc) or "Location could not be selected."}, status=400)
    location.update({"accuracy": 0, "source": "google_place"})
    _save_location(request, location)
    return JsonResponse({"ok": True, "location": location})
@require_POST
@rate_limit("detect-location", 20, 60 * 60, methods={"POST"}, json_response=True)
def detect_location(request):
    try:
        payload = json.loads(request.body or "{}")
        latitude = Decimal(str(payload.get("latitude")))
        longitude = Decimal(str(payload.get("longitude")))
        accuracy = max(0, min(int(float(payload.get("accuracy", 0) or 0)), 100000))
    except (TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid location coordinates."}, status=400)

    if not Decimal("-90") <= latitude <= Decimal("90"):
        return JsonResponse({"ok": False, "error": "Latitude is outside the valid range."}, status=400)
    if not Decimal("-180") <= longitude <= Decimal("180"):
        return JsonResponse({"ok": False, "error": "Longitude is outside the valid range."}, status=400)

    try:
        location = reverse_geocode(latitude, longitude)
        warning = ""
    except GeocodingError as exc:
        location = {
            "label": "Current location",
            "display_name": "",
            "address_line_1": "",
            "city": "",
            "state": "",
            "pincode": "",
            "country": "",
            "country_code": "",
            "house_number": "",
            "road": "",
            "neighbourhood": "",
            "suburb": "",
            "locality": "",
            "subdistrict": "",
            "district": "",
            "place_id": "",
            "boundingbox": [],
            "address_components": {},
            "raw_payload": {},
            "attribution": "",
        }
        warning = f"Coordinates saved, but Google Maps could not resolve the address. {exc}"

    location.update(
        {
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "accuracy": accuracy,
            "source": "geolocation",
        }
    )
    _save_location(request, location)
    return JsonResponse({"ok": True, "location": location, "warning": warning})


@require_POST
@rate_limit("manual-location", 30, 60 * 60, methods={"POST"}, json_response=True)
def set_manual_location(request):
    city = request.POST.get("city", "").strip()[:100]
    state = request.POST.get("state", "").strip()[:100]
    pincode = request.POST.get("pincode", "").strip()
    if not (pincode.isdigit() and len(pincode) == 6):
        return JsonResponse(
            {"ok": False, "error": "Enter a valid 6-digit Indian pincode."},
            status=400,
        )
    if not city:
        return JsonResponse({"ok": False, "error": "Enter your city or town."}, status=400)

    label = f"{city}{', ' + state if state else ''} {pincode}".strip()
    location = {
        "label": label,
        "display_name": label,
        "address_line_1": "",
        "city": city,
        "state": state,
        "pincode": pincode,
        "country": "India",
        "country_code": "in",
        "house_number": "",
        "road": "",
        "neighbourhood": "",
        "suburb": "",
        "locality": "",
        "subdistrict": "",
        "district": "",
        "place_id": "",
        "boundingbox": [],
        "address_components": {},
        "raw_payload": {},
        "latitude": "",
        "longitude": "",
        "accuracy": 0,
        "source": "manual",
        "attribution": "",
    }
    _save_location(request, location)
    return JsonResponse({"ok": True, "location": location})


def _save_location(request, location):
    request.session["site_location"] = location
    request.session.modified = True
    if not request.user.is_authenticated:
        return

    profile = getattr(request.user, "profile", None)
    if not profile:
        return
    profile.preferred_location_label = location["label"]
    profile.preferred_city = location.get("city", "")
    profile.preferred_state = location.get("state", "")
    profile.preferred_pincode = location.get("pincode", "")
    profile.preferred_latitude = location.get("latitude") or None
    profile.preferred_longitude = location.get("longitude") or None
    profile.location_updated_at = timezone.now()
    profile.save(
        update_fields=[
            "preferred_location_label",
            "preferred_city",
            "preferred_state",
            "preferred_pincode",
            "preferred_latitude",
            "preferred_longitude",
            "location_updated_at",
        ]
    )
