import json

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


class GeocodingError(Exception):
    pass


class PlacesSearchError(Exception):
    pass


class PlacesAutocompleteError(Exception):
    pass


def _google_status_message(status, *, service="Google Maps"):
    if status == "REQUEST_DENIED":
        api_hint = "Geocoding API" if service == "Google Maps" else "Places API (New)"
        return (
            f"{service} rejected the server key. Enable {api_hint} and billing, "
            "then allow server-side requests from the MediMart host."
        )
    messages = {
        "OVER_QUERY_LIMIT": (
            f"{service} quota or billing is unavailable. Check the project quota and billing account."
        ),
        "RESOURCE_EXHAUSTED": (
            f"{service} quota has been exhausted. Check the project quota and billing account."
        ),
        "INVALID_REQUEST": f"{service} received an invalid request.",
    }
    return messages.get(status, f"{service} returned an unexpected location-service response.")


def search_nearby_google_pharmacies(latitude, longitude):
    """Return short-lived Google Places pharmacy results without storing place content."""
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return [], "Google Maps is not configured yet. Add GOOGLE_MAPS_API_KEY to enable general listings."

    cache_key = f"google-nearby-pharmacies:{float(latitude):.3f}:{float(longitude):.3f}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached, ""
    cached_error = cache.get(f"{cache_key}:error")
    if cached_error:
        return [], cached_error

    payload = {
        "includedTypes": ["pharmacy"],
        "maxResultCount": settings.GOOGLE_MAPS_MAX_RESULTS,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": float(latitude), "longitude": float(longitude)},
                "radius": float(settings.GOOGLE_MAPS_RADIUS_METERS),
            }
        },
    }
    request = Request(
        "https://places.googleapis.com/v1/places:searchNearby",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": ",".join(
                (
                    "places.id",
                    "places.displayName",
                    "places.formattedAddress",
                    "places.location",
                    "places.googleMapsUri",
                    "places.rating",
                    "places.userRatingCount",
                    "places.nationalPhoneNumber",
                    "places.websiteUri",
                    "places.regularOpeningHours.openNow",
                    "places.regularOpeningHours.weekdayDescriptions",
                )
            ),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        error_payload = {}
        if isinstance(exc, HTTPError):
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        status = (error_payload.get("error") or {}).get("status")
        if status in {"REQUEST_DENIED", "OVER_QUERY_LIMIT", "RESOURCE_EXHAUSTED"}:
            message = _google_status_message(status, service="Google Places")
            cache.set(f"{cache_key}:error", message, settings.GOOGLE_MAPS_ERROR_CACHE_SECONDS)
            raise PlacesSearchError(message) from exc
        raise PlacesSearchError("Google Places is temporarily unavailable.") from exc

    if response_payload.get("error"):
        status = response_payload["error"].get("status")
        message = _google_status_message(status, service="Google Places")
        cache.set(f"{cache_key}:error", message, settings.GOOGLE_MAPS_ERROR_CACHE_SECONDS)
        raise PlacesSearchError(message)

    places = response_payload.get("places", [])
    # Keep this cache short and in-memory. Google place content must not become MediMart's database.
    cache.set(cache_key, places, 60)
    return places, ""


def autocomplete_google_places(query, latitude=None, longitude=None):
    """Return short-lived Google address suggestions for the location picker."""
    query = str(query or "").strip()[:120]
    if len(query) < 3:
        return []
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise PlacesAutocompleteError("Google Maps is not configured yet. Add GOOGLE_MAPS_API_KEY.")

    cache_key = f"google-place-autocomplete:{query.casefold()}:{latitude or ''}:{longitude or ''}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    cached_error = cache.get(f"{cache_key}:error")
    if cached_error:
        raise PlacesAutocompleteError(cached_error)

    payload = {
        "input": query,
        "includedRegionCodes": ["in"],
        "languageCode": "en",
    }
    try:
        if latitude is not None and longitude is not None:
            payload["locationBias"] = {
                "circle": {
                    "center": {"latitude": float(latitude), "longitude": float(longitude)},
                    "radius": min(float(settings.GOOGLE_MAPS_RADIUS_METERS), 50000),
                }
            }
    except (TypeError, ValueError):
        pass

    request = Request(
        "https://places.googleapis.com/v1/places:autocomplete",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": (
                "suggestions.placePrediction.placeId,"
                "suggestions.placePrediction.text,"
                "suggestions.placePrediction.structuredFormat"
            ),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        error_payload = {}
        if isinstance(exc, HTTPError):
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        status = (error_payload.get("error") or {}).get("status")
        if status in {"REQUEST_DENIED", "OVER_QUERY_LIMIT", "RESOURCE_EXHAUSTED", "INVALID_REQUEST"}:
            message = _google_status_message(status, service="Google Places")
            cache.set(f"{cache_key}:error", message, settings.GOOGLE_MAPS_ERROR_CACHE_SECONDS)
            raise PlacesAutocompleteError(message) from exc
        raise PlacesAutocompleteError("Google Places suggestions are temporarily unavailable.") from exc

    if response_payload.get("error"):
        status = response_payload["error"].get("status")
        message = _google_status_message(status, service="Google Places")
        cache.set(f"{cache_key}:error", message, settings.GOOGLE_MAPS_ERROR_CACHE_SECONDS)
        raise PlacesAutocompleteError(message)

    suggestions = []
    for suggestion in response_payload.get("suggestions", []):
        prediction = suggestion.get("placePrediction") or {}
        text = prediction.get("text") or {}
        label = text.get("text", "").strip()
        if label and prediction.get("placeId"):
            suggestions.append({
                "place_id": prediction["placeId"],
                "label": label,
                "primary": (prediction.get("structuredFormat") or {}).get("mainText", {}).get("text", label),
                "secondary": (prediction.get("structuredFormat") or {}).get("secondaryText", {}).get("text", ""),
            })
    cache.set(cache_key, suggestions, settings.GOOGLE_MAPS_AUTOCOMPLETE_CACHE_SECONDS)
    return suggestions


def reverse_geocode(latitude, longitude):
    """Reverse-geocode coordinates through Google Maps Platform Geocoding."""
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise GeocodingError("Google Maps is not configured yet. Add GOOGLE_MAPS_API_KEY.")

    cache_key = f"google-reverse-geocode:{float(latitude):.4f}:{float(longitude):.4f}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    query = urlencode(
        {
            "latlng": f"{float(latitude):.6f},{float(longitude):.6f}",
            "language": "en",
            "region": "in",
            "key": api_key,
        }
    )
    request = Request(
        f"https://maps.googleapis.com/maps/api/geocode/json?{query}",
        headers={
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeocodingError("Google Maps is temporarily unavailable.") from exc

    provider_status = payload.get("status", "UNKNOWN")
    if provider_status in {"REQUEST_DENIED", "OVER_QUERY_LIMIT", "RESOURCE_EXHAUSTED", "INVALID_REQUEST"}:
        raise GeocodingError(_google_status_message(provider_status))
    if provider_status == "ZERO_RESULTS" or not payload.get("results"):
        raise GeocodingError("Google Maps could not identify an address for these coordinates.")
    if provider_status != "OK":
        raise GeocodingError(_google_status_message(provider_status))

    result = _location_from_geocode_result(payload, payload["results"][0])
    cache.set(cache_key, result, 60 * 60 * 24)
    return result


def geocode_google_place(place_id):
    """Resolve a selected Places suggestion into the same location payload as GPS detection."""
    place_id = str(place_id or "").strip()[:200]
    if not place_id:
        raise GeocodingError("Choose a location suggestion before continuing.")
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise GeocodingError("Google Maps is not configured yet. Add GOOGLE_MAPS_API_KEY.")
    cache_key = f"google-place-geocode:{place_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    query = urlencode({"place_id": place_id, "language": "en", "region": "in", "key": api_key})
    request = Request(f"https://maps.googleapis.com/maps/api/geocode/json?{query}", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeocodingError("Google Maps is temporarily unavailable.") from exc
    provider_status = payload.get("status", "UNKNOWN")
    if provider_status != "OK" or not payload.get("results"):
        raise GeocodingError(_google_status_message(provider_status))
    result = _location_from_geocode_result(payload, payload["results"][0])
    cache.set(cache_key, result, 60 * 60 * 24)
    return result


def _location_from_geocode_result(payload, geocode_result):
    components = geocode_result.get("address_components", [])

    def component(*types):
        for address_component in components:
            if any(item in address_component.get("types", []) for item in types):
                return address_component.get("long_name", "")
        return ""

    city = component("locality", "postal_town", "administrative_area_level_2")
    state = component("administrative_area_level_1")
    pincode = component("postal_code")
    house_number = component("street_number")
    road = component("route")
    neighbourhood = component("neighborhood", "sublocality", "sublocality_level_1")
    country = component("country")
    country_code = next(
        (
            address_component.get("short_name", "").lower()
            for address_component in components
            if "country" in address_component.get("types", [])
        ),
        "",
    )
    formatted_address = geocode_result.get("formatted_address", "")
    address_line_1 = ", ".join(item for item in (house_number, road, neighbourhood) if item)
    if not address_line_1:
        address_line_1 = formatted_address
    result = {
        "label": _build_location_label(city, state, pincode, formatted_address),
        "display_name": formatted_address,
        "address_line_1": address_line_1,
        "city": city,
        "state": state,
        "pincode": pincode,
        "country": country,
        "country_code": country_code,
        "house_number": house_number,
        "road": road,
        "neighbourhood": neighbourhood,
        "suburb": component("sublocality_level_2"),
        "locality": component("sublocality", "sublocality_level_1"),
        "subdistrict": component("administrative_area_level_3"),
        "district": component("administrative_area_level_2"),
        "place_id": str(geocode_result.get("place_id", "")),
        "boundingbox": [],
        "address_components": components,
        "raw_payload": payload,
        "attribution": "Powered by Google Maps",
    }
    return result


def google_maps_healthcheck():
    """Run a safe live server-side check without exposing the configured API key."""
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {
            "ok": False,
            "configured": False,
            "message": "GOOGLE_MAPS_API_KEY is not configured.",
        }
    try:
        reverse_geocode(20.5937, 78.9629)
    except GeocodingError as exc:
        return {"ok": False, "configured": True, "message": str(exc)}
    return {
        "ok": True,
        "configured": True,
        "message": "Google Geocoding is responding successfully.",
    }


def _build_location_label(city, state, pincode, fallback):
    primary = ", ".join(item for item in (city, state) if item)
    if pincode:
        return f"{primary} {pincode}".strip()
    if primary:
        return primary
    return fallback[:120] or "Current location"
