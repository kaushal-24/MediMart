from django.urls import path

from . import views


app_name = "extras"

urlpatterns = [
    path("notifications/", views.notification_list, name="notification_list"),
    path(
        "notifications/<int:pk>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
    path("support/", views.support_ticket_list, name="support_ticket_list"),
    path("support/create/", views.support_ticket_create, name="support_ticket_create"),
    path("support/<int:pk>/", views.support_ticket_detail, name="support_ticket_detail"),
    path("blog/", views.blog_list, name="blog_list"),
    path("blog/category/<slug:slug>/", views.blog_category, name="blog_category"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("content-issues/<str:kind>/<int:identifier>/", views.content_issue_create, name="content_issue_create"),
    path("doctors/", views.doctor_list, name="doctor_list"),
    path("doctors/<int:pk>/", views.doctor_detail, name="doctor_detail"),
    path("doctor-dashboard/", views.doctor_dashboard, name="doctor_dashboard"),
]
