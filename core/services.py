import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


class GeocodingError(Exception):
    pass


def reverse_geocode(latitude, longitude):
    cache_key = f"reverse-geocode:{float(latitude):.4f}:{float(longitude):.4f}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    query = urlencode(
        {
            "lat": f"{float(latitude):.6f}",
            "lon": f"{float(longitude):.6f}",
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 18,
        }
    )
    request = Request(
        f"{settings.GEOCODING_REVERSE_URL}?{query}",
        headers={
            "User-Agent": settings.GEOCODING_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-IN,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=settings.GEOCODING_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeocodingError("The location service is temporarily unavailable.") from exc

    address = payload.get("address", {})
    city = next(
        (
            address.get(key)
            for key in ("city", "town", "village", "municipality", "city_district", "county")
            if address.get(key)
        ),
        "",
    )
    state = address.get("state", "")
    pincode = address.get("postcode", "")
    result = {
        "label": _build_location_label(city, state, pincode, payload.get("display_name", "")),
        "display_name": payload.get("display_name", ""),
        "address_line_1": ", ".join(
            item
            for item in (
                address.get("house_number", ""),
                address.get("road", ""),
                address.get("suburb", "") or address.get("neighbourhood", ""),
            )
            if item
        ),
        "city": city,
        "state": state,
        "pincode": pincode,
        "country": address.get("country", ""),
        "country_code": address.get("country_code", ""),
        "house_number": address.get("house_number", ""),
        "road": address.get("road", ""),
        "neighbourhood": address.get("neighbourhood", ""),
        "suburb": address.get("suburb", ""),
        "locality": address.get("locality", "") or address.get("hamlet", ""),
        "subdistrict": address.get("subdistrict", "") or address.get("county", ""),
        "district": address.get("state_district", "") or address.get("city_district", ""),
        "place_id": str(payload.get("place_id", "")),
        "osm_type": payload.get("osm_type", ""),
        "osm_id": str(payload.get("osm_id", "")),
        "boundingbox": payload.get("boundingbox", []),
        "address_components": address,
        "raw_payload": payload,
        "attribution": "Location data © OpenStreetMap contributors",
    }
    cache.set(cache_key, result, 60 * 60 * 24)
    return result


def _build_location_label(city, state, pincode, fallback):
    primary = ", ".join(item for item in (city, state) if item)
    if pincode:
        return f"{primary} {pincode}".strip()
    if primary:
        return primary
    return fallback[:120] or "Current location"
