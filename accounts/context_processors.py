from .models import UserProfile
from .permissions import OPERATIONS_ROLES


def dashboard_access(request):
    user = request.user
    can_view_admin_dashboard = bool(user.is_authenticated and user.is_staff)
    can_view_delivery_dashboard = can_view_admin_dashboard
    can_view_doctor_dashboard = False
    profile = None

    if user.is_authenticated:
        profile = getattr(user, "profile", None)
        can_view_admin_dashboard = can_view_admin_dashboard or bool(
            profile and profile.role in OPERATIONS_ROLES
        )

    if user.is_authenticated and not can_view_delivery_dashboard:
        can_view_delivery_dashboard = bool(
            profile
            and profile.role in {UserProfile.Role.DELIVERY_STAFF, UserProfile.Role.ADMIN}
        )

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
    }
