from django.urls import path

from . import views


app_name = "reviews"

urlpatterns = [
    path("reviews/", views.review_list, name="review_list"),
    path("products/<slug:slug>/review/", views.review_create, name="review_create"),
    path("reviews/<int:pk>/helpful/", views.helpful_vote, name="helpful_vote"),
    path("reviews/<int:pk>/report/", views.abuse_report, name="abuse_report"),
    path("reviews/<int:pk>/seller-reply/", views.seller_reply, name="seller_reply"),
]
