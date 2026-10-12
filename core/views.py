import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from extras.models import BlogPost, DoctorProfile
from healthcare.models import LabTest
from prescriptions.models import Prescription
from products.models import Category, Product
from vendors.models import Vendor
from products.services import with_offer_summary

from .services import GeocodingError, reverse_geocode
from .throttling import rate_limit


def home(request):
    """Show the MediMart marketplace homepage."""
    featured_categories = Category.objects.filter(is_active=True, parent__isnull=True)[:8]
    featured_products = with_offer_summary(
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .order_by("-is_featured", "-created_at")
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
        .order_by("-is_featured", "-created_at")
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
            "id",
            "status",
            "valid_until",
            "created_at",
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
        },
    )


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
    except GeocodingError:
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
            "osm_type": "",
            "osm_id": "",
            "boundingbox": [],
            "address_components": {},
            "raw_payload": {},
            "attribution": "",
        }
        warning = "Coordinates saved, but the address service is temporarily unavailable."

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
        "osm_type": "",
        "osm_id": "",
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
