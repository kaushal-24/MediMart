from django.urls import path

from . import views


app_name = "dashboards"

urlpatterns = [
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-dashboard/checkout-settings/", views.checkout_settings, name="checkout_settings"),
    path("admin-dashboard/google-maps-health/", views.google_maps_health, name="google_maps_health"),
    path("admin-dashboard/finance-report/", views.finance_report, name="finance_report"),
    path("admin-dashboard/approvals/", views.approval_center, name="approval_center"),
    path("admin-dashboard/approvals/<int:pk>/decision/", views.approval_decision, name="approval_decision"),
    path("admin-dashboard/data/", views.custom_data_home, name="custom_data_home"),
    path("admin-dashboard/data/<str:app_label>/<str:model_name>/", views.custom_data_records, name="custom_data_records"),
    path("admin-dashboard/data/<str:app_label>/<str:model_name>/add/", views.custom_data_form, name="custom_data_create"),
    path("admin-dashboard/data/<str:app_label>/<str:model_name>/<int:pk>/edit/", views.custom_data_form, name="custom_data_edit"),
    path("admin-dashboard/data/<str:app_label>/<str:model_name>/<int:pk>/delete/", views.custom_data_delete, name="custom_data_delete"),
    path("admin-dashboard/manage/<str:section>/", views.management_records, name="management_records"),
    path("admin-dashboard/manage/<str:section>/add/", views.management_form, name="management_create"),
    path("admin-dashboard/manage/<str:section>/<int:pk>/edit/", views.management_form, name="management_edit"),
    path("admin-dashboard/manage/<str:section>/<int:pk>/action/", views.management_record_action, name="management_record_action"),
    path("delivery-dashboard/", views.delivery_dashboard, name="delivery_dashboard"),
    path(
        "delivery-dashboard/orders/<int:pk>/status/",
        views.update_delivery_order_status,
        name="update_delivery_order_status",
    ),
    path(
        "admin-dashboard/orders/<int:pk>/assign-delivery/",
        views.assign_delivery_staff,
        name="assign_delivery_staff",
    ),
    path(
        "admin-dashboard/vendors/<int:pk>/review/",
        views.review_vendor,
        name="review_vendor",
    ),
    path(
        "admin-dashboard/offers/<int:pk>/review/",
        views.review_offer,
        name="review_offer",
    ),
    path(
        "admin-dashboard/licenses/<int:pk>/review/",
        views.review_business_license,
        name="review_business_license",
    ),
]
