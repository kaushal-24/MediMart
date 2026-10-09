from django.urls import path

from . import views


app_name = "products"

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("compare/", views.product_compare, name="product_compare"),
    path("compare/add/<int:pk>/", views.compare_add, name="compare_add"),
    path("compare/remove/<int:pk>/", views.compare_remove, name="compare_remove"),
    path("compare/clear/", views.compare_clear, name="compare_clear"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path(
        "price-comparison/<slug:slug>/",
        views.price_comparison,
        name="price_comparison",
    ),
    path(
        "price-comparison/id/<int:pk>/",
        views.price_comparison_by_id,
        name="price_comparison_by_id",
    ),
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),
    path(
        "medical-equipment/",
        views.product_type_detail,
        {"product_type": "medical_equipment"},
        name="medical_equipment",
    ),
    path(
        "surgical-equipment/",
        views.product_type_detail,
        {"product_type": "surgical_equipment"},
        name="surgical_equipment",
    ),
    path(
        "diagnostic-equipment/",
        views.product_type_detail,
        {"product_type": "diagnostic_equipment"},
        name="diagnostic_equipment",
    ),
    path("search/suggestions/", views.search_suggestions, name="search_suggestions"),
    path("search/", views.product_list, name="search"),
]
