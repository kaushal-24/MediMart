from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import UserProfile


def role_allowed(user, roles, allow_staff=False):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    if not profile:
        return False
    if profile.role in set(roles):
        return True
    return bool(
        allow_staff
        and user.is_staff
        and profile.role == UserProfile.Role.ADMIN
        and UserProfile.Role.ADMIN in set(roles)
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
}
