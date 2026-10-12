from django.urls import path

from . import api, private_media, views


app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("location/detect/", views.detect_location, name="detect_location"),
    path("location/manual/", views.set_manual_location, name="set_manual_location"),
    path("secure/prescriptions/<int:pk>/", private_media.prescription_file, name="prescription_file"),
    path("secure/vendors/<int:pk>/document/", private_media.vendor_document, name="vendor_document"),
    path("secure/licenses/<int:pk>/document/", private_media.license_document, name="license_document"),
    path("secure/support/tickets/<int:pk>/attachment/", private_media.support_ticket_attachment, name="support_ticket_attachment"),
    path("secure/support/messages/<int:pk>/attachment/", private_media.support_message_attachment, name="support_message_attachment"),
    path("secure/doctors/<int:pk>/credential/", private_media.doctor_credential, name="doctor_credential"),
    path("secure/health-records/<int:pk>/", private_media.health_record_file, name="health_record_file"),
    path("secure/lab-bookings/<int:pk>/report/", private_media.lab_report_file, name="lab_report_file"),
    path("secure/consultation-messages/<int:pk>/attachment/", private_media.consultation_attachment, name="consultation_attachment"),
    path("api/v1/products/", api.product_collection, name="api_products"),
    path("api/v1/products/<slug:slug>/", api.product_resource, name="api_product_detail"),
    path("api/v1/openapi.json", api.openapi_schema, name="openapi_schema"),
    path("health/live/", api.health_live, name="health_live"),
    path("health/ready/", api.health_ready, name="health_ready"),
]
