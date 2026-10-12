from django.urls import path

from . import views


app_name = "prescriptions"

urlpatterns = [
    path("prescriptions/", views.prescription_list, name="prescription_list"),
    path("prescriptions/upload/", views.prescription_upload, name="prescription_upload"),
    path("prescriptions/<int:pk>/", views.prescription_detail, name="prescription_detail"),
    path("prescriptions/<int:pk>/resubmit/", views.prescription_resubmit, name="prescription_resubmit"),
    path("prescriptions/<int:pk>/cancel/", views.prescription_cancel, name="prescription_cancel"),
    path("prescriptions/<int:pk>/review/", views.prescription_review, name="prescription_review"),
]
