from django.urls import path

from . import views


app_name = "vendors"

urlpatterns = [
    path("vendors/register/", views.vendor_register, name="vendor_register"),
    path("vendor-licenses/", views.business_license_list, name="business_license_list"),
    path("vendor-licenses/add/", views.business_license_create, name="business_license_create"),
    path(
        "vendor-licenses/<int:pk>/lookup/",
        views.business_license_lookup,
        name="business_license_lookup",
    ),
    path("vendors/", views.vendor_list, name="vendor_list"),
    path("vendor/<int:pk>/", views.vendor_detail, name="vendor_detail"),
    path("vendor-dashboard/", views.vendor_dashboard, name="vendor_dashboard"),
    path("vendor-products/", views.vendor_product_list, name="vendor_product_list"),
    path("vendor-products/add/", views.vendor_product_create, name="vendor_product_create"),
    path(
        "vendor-products/catalog/add/",
        views.vendor_catalog_product_create,
        name="vendor_catalog_product_create",
    ),
    path(
        "vendor-products/<int:pk>/edit/",
        views.vendor_product_update,
        name="vendor_product_update",
    ),
    path(
        "vendor-products/<int:pk>/delete/",
        views.vendor_product_delete,
        name="vendor_product_delete",
    ),
]
