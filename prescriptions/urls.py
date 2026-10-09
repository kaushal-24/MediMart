from django.urls import path

from . import views


app_name = "prescriptions"

urlpatterns = [
    path("prescriptions/", views.prescription_list, name="prescription_list"),
    path("prescriptions/upload/", views.prescription_upload, name="prescription_upload"),
    path("prescriptions/<int:pk>/", views.prescription_detail, name="prescription_detail"),
]
