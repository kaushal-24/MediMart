from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse

from accounts.permissions import STAFF_MFA_ROLES


class ActiveAccountMiddleware:
    """Invalidate sessions immediately when an account is deactivated."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.is_active:
            logout(request)
            request.session.flush()
            if request.path.startswith("/assistant/") or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"ok": False, "error": "Your account is inactive."}, status=401)
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        profile = getattr(user, "profile", None) if user is not None and user.is_authenticated else None
        if (
            profile
            and settings.STAFF_MFA_REQUIRED
            and profile.role in STAFF_MFA_ROLES
            and not (profile.mfa_enabled and profile.mfa_secret)
        ):
            allowed_paths = (
                "/accounts/profile/security/two-factor/",
                "/accounts/logout/",
            )
            if not request.path.startswith(allowed_paths):
                return redirect_to_login(request.get_full_path(), "/accounts/profile/security/two-factor/")
        return self.get_response(request)
