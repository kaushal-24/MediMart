def site_location(request):
    location = request.session.get("site_location")
    if not location and request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile and profile.preferred_location_label:
            location = {
                "label": profile.preferred_location_label,
                "city": profile.preferred_city,
                "state": profile.preferred_state,
                "pincode": profile.preferred_pincode,
            }

    return {
        "site_location": location or {},
        "site_location_label": (location or {}).get("label", "Select delivery location"),
    }
