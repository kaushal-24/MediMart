from .models import UserProfile
from .permissions import capabilities_for_user, has_capability


def dashboard_access(request):
    user = request.user
    can_view_admin_dashboard = has_capability(user, "dashboard.operations")
    can_view_delivery_dashboard = has_capability(user, "dashboard.delivery")
    can_view_doctor_dashboard = False
    profile = None

    if user.is_authenticated:
        profile = getattr(user, "profile", None)
    if user.is_authenticated:
        can_view_doctor_dashboard = bool(profile and profile.role == UserProfile.Role.DOCTOR)

    return {
        "can_view_admin_dashboard": can_view_admin_dashboard,
        "can_view_delivery_dashboard": can_view_delivery_dashboard,
        "can_view_doctor_dashboard": can_view_doctor_dashboard,
        "can_view_vendor_dashboard": bool(
            user.is_authenticated
            and (
                hasattr(user, "vendor_profile")
                or (
                    profile
                    and profile.role
                    in {
                        UserProfile.Role.VENDOR,
                        UserProfile.Role.MANUFACTURER,
                        UserProfile.Role.PHARMACY,
                    }
                )
            )
        ),
        "user_capabilities": capabilities_for_user(user),
    }
