"""
URL configuration for MediMart.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("products.urls")),
    path("", include("vendors.urls")),
    path("", include("cart.urls")),
    path("", include("prescriptions.urls")),
    path("", include("orders.urls")),
    path("", include("reviews.urls")),
    path("", include("dashboards.urls")),
    path("", include("extras.urls")),
    path("", include("core.urls")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
