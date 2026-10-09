import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone


class LicenseLookupError(Exception):
    pass


OFFICIAL_LICENSE_REGISTRIES = {
    "drug": "https://statedrugs.gov.in/SFDA/Homepage",
    "medical_device": "https://www.cdscomdonline.gov.in/NewMedDev/Homepage",
}


def lookup_business_license(license_number, license_type):
    """Query a documented, authorized registry adapter configured by the operator."""
    endpoint = settings.LICENSE_VERIFICATION_API_URL
    if not endpoint:
        return {
            "available": False,
            "matched": False,
            "message": "Automatic registry lookup is not configured. Verify on the official portal.",
            "official_url": official_registry_url(license_type),
        }

    query = urlencode({"license_number": license_number, "license_type": license_type})
    headers = {
        "Accept": "application/json",
        "User-Agent": settings.LICENSE_VERIFICATION_USER_AGENT,
    }
    if settings.LICENSE_VERIFICATION_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LICENSE_VERIFICATION_API_KEY}"
    request = Request(f"{endpoint}?{query}", headers=headers)
    try:
        with urlopen(request, timeout=settings.LICENSE_VERIFICATION_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LicenseLookupError("The authorized licence registry is temporarily unavailable.") from exc

    record = payload.get("record", payload)
    matched = bool(payload.get("matched", record.get("license_number")))
    return {
        "available": True,
        "matched": matched,
        "message": "Registry record found. A compliance officer must still approve it." if matched else "No matching registry record was found.",
        "official_url": official_registry_url(license_type),
        "record": {
            "license_number": record.get("license_number", license_number),
            "form_number": record.get("form_number", ""),
            "legal_name": record.get("firm_name", record.get("legal_name", "")),
            "premises_address": record.get("firm_address", record.get("premises_address", "")),
            "state": record.get("state", ""),
            "licensing_authority": record.get("licensing_authority", ""),
            "issued_on": record.get("issue_date", record.get("issued_on", "")),
            "valid_until": record.get("valid_until", record.get("expiry_date", "")),
            "registry_status": record.get("status", ""),
        },
        "raw": payload,
        "checked_at": timezone.now().isoformat(),
    }


def official_registry_url(license_type):
    if license_type.startswith("device_"):
        return OFFICIAL_LICENSE_REGISTRIES["medical_device"]
    return OFFICIAL_LICENSE_REGISTRIES["drug"]
