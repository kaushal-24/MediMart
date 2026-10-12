from django.urls import path

from . import views


app_name = "healthcare"

urlpatterns = [
    path("healthcare/", views.health_dashboard, name="dashboard"),
    path("healthcare/dependents/", views.dependent_list, name="dependents"),
    path("labs/", views.lab_list, name="labs"),
    path("labs/book/", views.lab_booking_create, name="lab_booking_create"),
    path("labs/book/<int:pk>/", views.lab_booking_create, name="lab_booking_for_test"),
    path("labs/bookings/", views.lab_booking_list, name="lab_bookings"),
    path("labs/bookings/<int:pk>/cancel/", views.lab_booking_cancel, name="lab_booking_cancel"),
    path("labs/bookings/<int:pk>/reschedule/", views.lab_booking_reschedule, name="lab_booking_reschedule"),
    path("health-records/", views.health_record_list, name="records"),
    path("health-records/add/", views.health_record_create, name="record_create"),
    path("medication-reminders/", views.reminder_list, name="reminders"),
    path("medication-reminders/<int:pk>/toggle/", views.reminder_toggle, name="reminder_toggle"),
    path("consultations/", views.consultation_list, name="consultations"),
    path("consultations/book/", views.consultation_create, name="consultation_create"),
    path("consultations/<int:pk>/", views.consultation_detail, name="consultation_detail"),
]
