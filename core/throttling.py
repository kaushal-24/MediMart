import hashlib
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


def rate_limit(key, limit, period, *, methods=None, json_response=False, body_fields=None):
    """Small cache-backed limiter suitable for login and provider-facing endpoints."""
    methods = {method.upper() for method in (methods or [])}
    body_fields = tuple(body_fields or ())

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if methods and request.method.upper() not in methods:
                return view_func(request, *args, **kwargs)
            client = request.META.get("REMOTE_ADDR", "unknown")
            trusted_proxy_count = max(0, int(getattr(settings, "TRUSTED_PROXY_COUNT", 0)))
            forwarded_values = [
                value.strip()
                for value in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
                if value.strip()
            ]
            if trusted_proxy_count and len(forwarded_values) >= trusted_proxy_count:
                client = forwarded_values[-trusted_proxy_count]
            identity_parts = [
                f"u{request.user.pk}" if request.user.is_authenticated else f"ip:{client}",
                f"client:{client}",
            ]
            for field_name in body_fields:
                value = request.POST.get(field_name, "")
                if value:
                    identity_parts.append(f"{field_name}:{value.strip().casefold()}")
            identity = "|".join(identity_parts)
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            cache_key = f"throttle:{key}:{digest}"
            try:
                if cache.add(cache_key, 1, timeout=period):
                    attempts = 1
                else:
                    attempts = cache.incr(cache_key)
            except Exception:
                if getattr(settings, "RATE_LIMIT_FAIL_CLOSED", True):
                    response = JsonResponse(
                        {"ok": False, "error": "This action is temporarily unavailable. Please try again shortly."},
                        status=503,
                    ) if json_response else HttpResponse(
                        "This action is temporarily unavailable. Please try again shortly.",
                        status=503,
                    )
                    response["Retry-After"] = str(period)
                    return response
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
