from django.conf import settings


class SecurityHeadersMiddleware:
    """Add a conservative policy while allowing the payment and UI CDNs in use."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        directives = [
                    "default-src 'self'",
                    "base-uri 'self'",
                    "object-src 'none'",
                    "frame-ancestors 'none'",
                    "form-action 'self' https://api.razorpay.com",
                    "img-src 'self' data: https:",
                    "font-src 'self' https://cdn.jsdelivr.net data:",
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://checkout.razorpay.com",
                    "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com",
                    "frame-src https://api.razorpay.com https://*.razorpay.com",
                ]
        if not settings.DEBUG:
            directives.append("upgrade-insecure-requests")
        response.setdefault("Content-Security-Policy", "; ".join(directives))
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(self), payment=(self \"https://checkout.razorpay.com\")",
        )
        return response
