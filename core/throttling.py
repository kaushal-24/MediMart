import hashlib
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


def rate_limit(key, limit, period, *, methods=None, json_response=False):
    """Small cache-backed limiter suitable for login and provider-facing endpoints."""
    methods = {method.upper() for method in (methods or [])}

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if methods and request.method.upper() not in methods:
                return view_func(request, *args, **kwargs)
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            client = forwarded or request.META.get("REMOTE_ADDR", "unknown")
            identity = f"u{request.user.pk}" if request.user.is_authenticated else f"ip:{client}"
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            cache_key = f"throttle:{key}:{digest}"
            try:
                if cache.add(cache_key, 1, timeout=period):
                    attempts = 1
                else:
                    attempts = cache.incr(cache_key)
            except Exception:
                return view_func(request, *args, **kwargs)
            if attempts <= limit:
                return view_func(request, *args, **kwargs)
            if json_response:
                response = JsonResponse(
                    {"ok": False, "error": "Too many requests. Please try again shortly."},
                    status=429,
                )
            else:
                response = HttpResponse("Too many requests. Please try again shortly.", status=429)
            response["Retry-After"] = str(period)
            return response

        return wrapped

    return decorator
