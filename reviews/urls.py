from django.urls import path

from . import views


app_name = "reviews"

urlpatterns = [
    path("reviews/", views.review_list, name="review_list"),
    path("products/<slug:slug>/review/", views.review_create, name="review_create"),
]
