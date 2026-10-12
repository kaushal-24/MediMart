from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse


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
        return self.get_response(request)
