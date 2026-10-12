from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import UserCapabilityOverride, UserProfile


def role_allowed(user, roles, allow_staff=False):
    if not user.is_authenticated or not user.is_active:
        return False
    allowed_roles = set(roles)
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    if not profile:
        return False
    if profile.role in allowed_roles:
        return True
    return bool(
        allow_staff
        and user.is_staff
        and profile.role == UserProfile.Role.ADMIN
        and UserProfile.Role.ADMIN in allowed_roles
    )


def role_required(*roles, allow_staff=False):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not role_allowed(request.user, roles, allow_staff=allow_staff):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


OPERATIONS_ROLES = {
    UserProfile.Role.ADMIN,
    UserProfile.Role.OPERATIONS_MANAGER,
    UserProfile.Role.COMPLIANCE_OFFICER,
    UserProfile.Role.CATALOG_MANAGER,
    UserProfile.Role.WAREHOUSE_MANAGER,
    UserProfile.Role.SUPPORT_STAFF,
    UserProfile.Role.PHLEBOTOMIST,
    UserProfile.Role.PHARMACIST,
}


# Keep business capabilities separate from URL decorators. This gives every
# dashboard and management section one auditable permission vocabulary.
CAPABILITY_ROLES = {
    "dashboard.operations": OPERATIONS_ROLES,
    "dashboard.delivery": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.WAREHOUSE_MANAGER,
        UserProfile.Role.DELIVERY_STAFF,
    },
    "users.manage": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
    },
    "catalog.manage": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.CATALOG_MANAGER,
    },
    "seller.manage": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.COMPLIANCE_OFFICER,
    },
    "compliance.review": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.COMPLIANCE_OFFICER,
    },
    "fulfillment.manage": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.WAREHOUSE_MANAGER,
    },
    "clinical.manage": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.PHARMACIST,
        UserProfile.Role.PHLEBOTOMIST,
    },
    "clinical.prescription_review": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.PHARMACIST,
    },
    "clinical.lab_operations": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.PHLEBOTOMIST,
    },
    "clinical.doctor_operations": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
    },
    "support.manage": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
        UserProfile.Role.SUPPORT_STAFF,
    },
    "finance.manage": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
    },
    "audit.view": {
        UserProfile.Role.ADMIN,
        UserProfile.Role.OPERATIONS_MANAGER,
    },
}


def has_capability(user, capability):
    """Return whether an account can perform a named business capability."""
    if user.is_authenticated and user.is_active and not user.is_superuser:
        override = UserCapabilityOverride.objects.filter(user=user, capability=capability).first()
        if override is not None:
            return override.is_granted
    return role_allowed(
        user,
        CAPABILITY_ROLES.get(capability, set()),
        allow_staff=True,
    )


def capabilities_for_user(user):
    """Expose a stable, template-friendly capability map for the signed-in user."""
    return {capability: has_capability(user, capability) for capability in CAPABILITY_ROLES}
